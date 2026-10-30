"""Verify the source archive, its shipped tests, and a rebuilt installed wheel."""

from pathlib import Path, PurePosixPath
import sys
import tarfile
import tempfile

from smoke_wheel import (
    ROOT, SmokeError, check_installed, clean_environment, run, venv_commands,
    wheel_artifact, wheel_version,
)


GENERATED_FILES = {
    "PKG-INFO", "setup.cfg",
    *(f"src/junit2context.egg-info/{name}" for name in (
        "PKG-INFO", "SOURCES.txt", "dependency_links.txt", "entry_points.txt",
        "top_level.txt",
    )),
}


def source_files(manifest: Path) -> set[str]:
    """Read the explicit source allowlist, rejecting implicit glob expansion."""
    files = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line == "global-exclude *":
            continue
        directive, _, name = line.partition(" ")
        path = PurePosixPath(name)
        if (directive != "include" or not name or path.is_absolute()
                or any(part in ("", ".", "..") for part in name.split("/"))
                or any(char in name for char in "*?[]\\: \t")):
            raise SmokeError(f"Unsupported source-manifest line: {line!r}")
        if name in files:
            raise SmokeError(f"Duplicate source-manifest file: {name}")
        files.add(name)
    if "MANIFEST.in" not in files:
        raise SmokeError("Source manifest must include itself")
    return files


def extract_source(archive: Path, destination: Path, expected: set[str]) -> Path:
    """Check the entire member inventory before writing into an empty directory."""
    if any(destination.iterdir()):
        raise SmokeError("Source extraction requires an empty directory")
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        roots = set()
        files = {}
        names = set()
        for member in members:
            name = member.name
            path = PurePosixPath(name)
            if (path.is_absolute() or "\\" in name or ":" in name
                    or any(part in ("", ".", "..") for part in name.split("/"))):
                raise SmokeError(f"Unsafe source-archive path: {name!r}")
            roots.add(path.parts[0])
            if name in names:
                raise SmokeError(f"Duplicate source-archive path: {name}")
            names.add(name)
            if member.isdir():
                continue
            if not member.isfile() or len(path.parts) < 2:
                raise SmokeError(f"Not a regular source file: {name}")
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            files[relative] = member
        if len(roots) != 1:
            raise SmokeError("Expected one source-archive root directory")
        missing = (expected | {"PKG-INFO"}) - files.keys()
        extra = files.keys() - expected - GENERATED_FILES
        if missing or extra:
            raise SmokeError(f"Source inventory mismatch; missing: {sorted(missing)}; "
                             f"unexpected: {sorted(extra)}")
        root = destination / roots.pop()
        for relative, member in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source:
                target.write_bytes(source.read())
    return root


def main() -> int:
    env = clean_environment()
    try:
        expected = source_files(ROOT / "MANIFEST.in")
        with tempfile.TemporaryDirectory(prefix="junit2context-sdist-") as directory:
            temporary = Path(directory).resolve()
            if temporary.is_relative_to(ROOT):
                raise SmokeError("Temporary directory is inside the checkout; "
                                 "set TMPDIR/TEMP to an unrelated directory")
            artifacts, extracted, work = (temporary / name for name in ("sdist", "source", "work"))
            for path in (artifacts, extracted, work):
                path.mkdir()
            run([sys.executable, "-m", "build", "--sdist", "--outdir", str(artifacts),
                 str(ROOT)], work, env)
            archives = sorted(artifacts.iterdir())
            if len(archives) != 1 or not archives[0].name.endswith(".tar.gz"):
                raise SmokeError("Expected exactly one .tar.gz source distribution")
            source = extract_source(archives[0], extracted, expected)
            print(f"Source inventory passed: {len(expected)} allowlisted files; "
                  "only known build metadata additionally permitted.", flush=True)
            test_env = dict(env, PYTHONPATH=str(source / "src"))
            run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                source, test_env)
            print("Shipped source tests passed outside the checkout, without .git.", flush=True)
            wheels = temporary / "wheels"
            wheels.mkdir()
            run([sys.executable, "-m", "build", "--wheel", "--outdir", str(wheels),
                 str(source)], work, env)
            wheel = wheel_artifact(wheels)
            environment = temporary / "venv"
            run([sys.executable, "-m", "venv", str(environment)], work, env)
            python, _ = venv_commands(environment)
            run([str(python), "-m", "pip", "--isolated", "install", "--no-deps",
                 "--no-index", str(wheel)], work, env)
            check_installed(environment, work, wheel_version(wheel), env)
            print(f"Source-distribution smoke passed: {archives[0].name} -> {wheel.name}")
            print("Rebuilt installed console and module: --version, Markdown, JSON, "
                  "redaction, and isolated package origins passed.")
    except (SmokeError, OSError, ValueError, tarfile.TarError) as exc:
        print(f"Source-distribution smoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
