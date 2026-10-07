"""Checksum helper checks using only synthetic files and the standard library."""

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/release_checksums.py"
spec = importlib.util.spec_from_file_location("release_checksums", SCRIPT)
checksums = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checksums)
ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class ReleaseChecksumTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.manifest = self.root / "SHA256SUMS"

    def write(self, name, data=b"abc"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-S", str(SCRIPT), *map(str, args)],
            cwd=self.root, capture_output=True, text=True,
        )

    def test_known_hashes_stable_order_and_exact_bytes(self):
        a = self.write("a.tar.gz", b"")
        z = self.write("z.whl")
        self.write("unselected.zip", b"not part of the release")
        checksums.create_manifest([z, a], self.manifest)
        expected = f"{EMPTY}  a.tar.gz\n{ABC}  z.whl\n".encode("ascii")
        self.assertEqual(self.manifest.read_bytes(), expected)
        second = self.root / "OTHER-SUMS"
        checksums.create_manifest([a, z], second)
        self.assertEqual(second.read_bytes(), expected)

    def test_large_binary_file_streaming_digest(self):
        data = bytes(range(256)) * 10000
        path = self.write("binary.zip", data)
        self.assertEqual(checksums.digest_file(path), hashlib.sha256(data).hexdigest())

    def test_cli_check_works_outside_artifact_directory(self):
        artifact = self.write("downloads/one.whl")
        manifest = artifact.parent / "SHA256SUMS"
        created = self.run_cli("create", "--output", manifest, artifact)
        self.assertEqual((created.returncode, created.stderr), (0, ""))
        checked = self.run_cli("check", manifest)
        self.assertEqual((checked.returncode, checked.stdout, checked.stderr),
                         (0, "one.whl: OK\n", ""))

    def test_changed_file_fails_while_unchanged_file_is_checked(self):
        a, b = self.write("a.zip"), self.write("b.zip")
        checksums.create_manifest([a, b], self.manifest)
        a.write_bytes(b"altered")
        result = self.run_cli("check", self.manifest)
        self.assertEqual(result.returncode, 1)
        self.assertIn("a.zip: FAILED (SHA-256 mismatch)", result.stderr)
        self.assertEqual(result.stdout, "b.zip: OK\n")

    def test_missing_file_fails_check(self):
        self.manifest.write_text(f"{ABC}  missing.whl\n", encoding="ascii")
        result = self.run_cli("check", self.manifest)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing.whl: FAILED", result.stderr)

    def test_missing_or_directory_input_leaves_no_output(self):
        existing = self.write("exists.whl")
        for invalid in (self.root / "missing.zip", self.root / "folder.zip"):
            if invalid.name == "folder.zip":
                invalid.mkdir()
            with self.subTest(input=invalid):
                result = self.run_cli("create", "--output", self.manifest,
                                      existing, invalid)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.manifest.exists())

    def test_existing_manifest_is_preserved(self):
        artifact = self.write("one.whl")
        self.manifest.write_bytes(b"previous manifest")
        result = self.run_cli("create", "--output", self.manifest, artifact)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.manifest.read_bytes(), b"previous manifest")
        self.assertIn("output already exists", result.stderr)

    def test_manifest_cannot_be_selected_as_input(self):
        for name in ("SHA256SUMS", "nested/SHA256SUMS", "nested/sha256sums"):
            path = self.write(name)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "manifest"):
                checksums.create_manifest([path], self.manifest)

    def test_duplicate_basenames_and_case_collisions_are_rejected(self):
        for names in (("a.zip", "a.zip"), ("one/a.zip", "two/a.zip"),
                      ("one/a.zip", "two/A.zip")):
            paths = [self.write(name) for name in names]
            with self.subTest(names=names), self.assertRaisesRegex(ValueError, "duplicate"):
                checksums.create_manifest(paths, self.manifest)
            self.assertFalse(self.manifest.exists())

    def test_nonportable_names_are_rejected(self):
        for name in ("../a", "/a", "a/b", "a\\b", "with space.zip", "café.zip",
                     "line\nbreak", "a\x00b", "-a.zip", ".hidden", "trailing.",
                     "CON", "nul.zip", "COM1.whl", "lpt9.tar.gz", "a:stream"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                checksums.validate_name(name)

    def test_typical_release_names_are_accepted(self):
        for name in ("junit2context-0.1.0.tar.gz", "junit2context-0.1.0-py3-none-any.whl",
                     "Source_1.zip", "com10.zip"):
            with self.subTest(name=name):
                checksums.validate_name(name)

    def test_malformed_manifest_rejected_before_any_file_check(self):
        for line in ("", "not a hash", f"{ABC} *a.zip", f"{ABC.upper()}  a.zip",
                     f"{ABC}  ../a.zip", f"{ABC}  /a.zip", f"{ABC}  a\\b.zip",
                     f"{ABC}  SHA256SUMS", f"{ABC}  nul.zip", f"{ABC}  a.zip\n\n",
                     f"{ABC}  a.zip\n{ABC}  A.zip", "café"):
            self.manifest.write_text(line, encoding="utf-8")
            with self.subTest(line=line):
                result = self.run_cli("check", self.manifest)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("OK", result.stdout)
                self.assertNotIn("FAILED", result.stderr)

    def test_crlf_manifest_is_supported(self):
        self.write("a.zip")
        self.manifest.write_bytes(f"{ABC}  a.zip\r\n".encode("ascii"))
        self.assertEqual(self.run_cli("check", self.manifest).returncode, 0)

    def test_symlink_artifact_and_output_are_rejected(self):
        artifact = self.write("real.zip")
        alias = self.root / "alias.zip"
        try:
            alias.symlink_to(artifact)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this platform")
        with self.assertRaises(ValueError):
            checksums.create_manifest([alias], self.manifest)
        self.assertFalse(self.manifest.exists())
        self.manifest.symlink_to(self.root / "missing")
        result = self.run_cli("create", "--output", self.manifest, artifact)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root / "missing").exists())

    def test_cli_requires_explicit_inputs(self):
        result = self.run_cli("create")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.manifest.exists())


if __name__ == "__main__":
    unittest.main()
