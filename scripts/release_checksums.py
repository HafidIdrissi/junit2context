"""Create and check SHA-256 manifests for explicitly selected release files."""

import argparse
import hashlib
from pathlib import Path
import re
import sys


NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
ENTRY = re.compile(r"([0-9a-f]{64})  (.+)\Z")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def validate_name(name):
    """Keep entries unescaped, basename-only, and usable on Windows and Unix."""
    if (not NAME.fullmatch(name) or name.endswith(".")
            or name.split(".", 1)[0].upper() in RESERVED):
        raise ValueError(f"unsupported artifact filename: {name!r}")


def digest_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"expected a regular, non-symlink file: {str(path)!r}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_manifest(artifacts, output):
    """Hash all inputs before exclusively creating the output (never replace it)."""
    names = set()
    for path in artifacts:
        validate_name(path.name)
        name = path.name.lower()
        if name in names:
            raise ValueError(f"duplicate artifact filename: {path.name!r}")
        if name == output.name.lower() or path.resolve() == output.resolve():
            raise ValueError("the manifest must not be an input artifact")
        names.add(name)
    if output.exists() or output.is_symlink():
        raise ValueError(f"output already exists: {str(output)!r}")
    entries = [(digest_file(path), path.name)
               for path in sorted(artifacts, key=lambda path: path.name)]
    with output.open("x", encoding="ascii", newline="\n") as stream:
        stream.writelines(f"{digest}  {name}\n" for digest, name in entries)


def read_manifest(manifest):
    """Validate every entry before opening any artifact named by the manifest."""
    lines = manifest.read_text(encoding="ascii").splitlines()
    if not lines:
        raise ValueError("empty checksum manifest")
    entries = []
    names = set()
    for number, line in enumerate(lines, 1):
        match = ENTRY.fullmatch(line)
        if not match:
            raise ValueError(f"invalid checksum entry on line {number}")
        digest, name = match.groups()
        validate_name(name)
        if name.lower() == manifest.name.lower():
            raise ValueError("the manifest must not reference itself")
        if name.lower() in names:
            raise ValueError(f"duplicate artifact filename on line {number}")
        names.add(name.lower())
        entries.append((digest, name))
    return entries


def check_manifest(manifest):
    """Check files beside the manifest; return false for missing/changed inputs."""
    entries = read_manifest(manifest)
    passed = True
    for expected, name in entries:
        try:
            actual = digest_file(manifest.parent / name)
        except (OSError, ValueError) as error:
            print(f"{name}: FAILED ({error})", file=sys.stderr)
            passed = False
            continue
        if actual != expected:
            print(f"{name}: FAILED (SHA-256 mismatch)", file=sys.stderr)
            passed = False
        else:
            print(f"{name}: OK")
    return passed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="hash explicit local artifact files")
    create.add_argument("--output", type=Path, default=Path("SHA256SUMS"))
    create.add_argument("artifacts", nargs="+", type=Path)
    check = commands.add_parser("check", help="verify files beside a manifest")
    check.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            create_manifest(args.artifacts, args.output)
            return 0
        return 0 if check_manifest(args.manifest) else 1
    except (OSError, ValueError) as error:
        parser.exit(2, f"release_checksums: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
