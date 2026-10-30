"""Standard-library tests for the source-distribution inventory check."""

import importlib.util
import io
import re
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    spec = importlib.util.spec_from_file_location("check_sdist", SCRIPTS / "check_sdist.py")
    sdist = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sdist)
finally:
    sys.path.pop(0)


class SourceDistributionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.destination = self.root / "unpacked"
        self.destination.mkdir()

    def archive(self, entries, *, metadata=True):
        path = self.root / "source.tar.gz"
        if metadata and not any(name == "package-1/PKG-INFO" for name, _, _ in entries):
            entries = [self.regular("package-1/PKG-INFO", "metadata"), *entries]
        with tarfile.open(path, "w:gz") as bundle:
            for name, content, kind in entries:
                member = tarfile.TarInfo(name)
                member.type = kind
                if kind == tarfile.REGTYPE:
                    data = content.encode("utf-8")
                    member.size = len(data)
                    bundle.addfile(member, io.BytesIO(data))
                else:
                    member.linkname = content
                    bundle.addfile(member)
        return path

    def regular(self, name, content="public source"):
        return (name, content, tarfile.REGTYPE)

    def test_explicit_manifest_rejects_patterns_paths_and_duplicates(self):
        manifest = self.root / "MANIFEST.in"
        manifest.write_text("# approved source\nglobal-exclude *\n"
                            "include MANIFEST.in\ninclude src/package.py\n", encoding="utf-8")
        self.assertEqual(sdist.source_files(manifest), {"MANIFEST.in", "src/package.py"})
        for line in ("recursive-include src *.py", "include tests/*.py", "include /absolute.py",
                     "include ../outside.py", "include C:/outside.py", r"include src\outside.py", "include MANIFEST.in",
                     "include src/./file.py", "include src//file.py", "include two files.py"):
            with self.subTest(line=line):
                manifest.write_text("include MANIFEST.in\n" + line + "\n", encoding="utf-8")
                with self.assertRaises(sdist.SmokeError):
                    sdist.source_files(manifest)
        manifest.write_text("include README.md\n", encoding="utf-8")
        with self.assertRaisesRegex(sdist.SmokeError, "include itself"):
            sdist.source_files(manifest)

    def test_extracts_exact_inventory_with_generated_metadata(self):
        archive = self.archive([
            ("package-1", "", tarfile.DIRTYPE),
            self.regular("package-1/README.md", "read me"),
            self.regular("package-1/src/package.py", "code"),
            self.regular("package-1/PKG-INFO", "metadata"),
        ])
        source = sdist.extract_source(archive, self.destination, {"README.md", "src/package.py"})
        self.assertEqual((source / "README.md").read_text(), "read me")
        self.assertEqual((source / "src/package.py").read_text(), "code")
        self.assertFalse((source / ".git").exists())

    def test_missing_test_support_fails_before_extracting_anything(self):
        archive = self.archive([self.regular("package-1/tests/test_example.py")])
        with self.assertRaisesRegex(sdist.SmokeError, "missing.*scripts/helper.py"):
            sdist.extract_source(archive, self.destination,
                                 {"tests/test_example.py", "scripts/helper.py"})
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_missing_distribution_metadata_is_rejected(self):
        archive = self.archive([self.regular("package-1/README.md")], metadata=False)
        with self.assertRaisesRegex(sdist.SmokeError, "missing.*PKG-INFO"):
            sdist.extract_source(archive, self.destination, {"README.md"})
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_unlisted_files_fail_before_extracting_anything(self):
        for name in (".env", "private-report.xml", "tests/private_test.py", ".venv/bin/python",
                     "src/__pycache__/package.pyc", ".git/config", "dist/old.tar.gz"):
            with self.subTest(name=name):
                archive = self.archive([self.regular("package-1/README.md"),
                                        self.regular("package-1/" + name)])
                with self.assertRaisesRegex(sdist.SmokeError, "unexpected.*" + re.escape(name)):
                    sdist.extract_source(archive, self.destination, {"README.md"})
                self.assertEqual(list(self.destination.iterdir()), [])

    def test_unsafe_paths_duplicates_links_and_multiple_roots_are_rejected(self):
        extra_entries = [
            self.regular("/outside"), self.regular("C:/outside"),
            self.regular("package-1/../outside"),
            self.regular(r"package-1\outside"), self.regular("package-1/./README.md"),
            self.regular("package-1//README.md"), self.regular("package-1/README.md"),
            self.regular("other/README.md"),
            ("package-1/link", "README.md", tarfile.SYMTYPE),
            ("package-1/link", "package-1/README.md", tarfile.LNKTYPE),
        ]
        for entry in extra_entries:
            with self.subTest(entry=entry):
                archive = self.archive([self.regular("package-1/README.md"), entry])
                with self.assertRaises(sdist.SmokeError):
                    sdist.extract_source(archive, self.destination, {"README.md"})
                self.assertEqual(list(self.destination.iterdir()), [])

    def test_nonempty_destination_is_preserved(self):
        existing = self.destination / "keep.txt"
        existing.write_text("keep", encoding="utf-8")
        archive = self.archive([self.regular("package-1/README.md")])
        with self.assertRaisesRegex(sdist.SmokeError, "empty directory"):
            sdist.extract_source(archive, self.destination, {"README.md"})
        self.assertEqual(existing.read_text(), "keep")
        self.assertEqual(list(self.destination.iterdir()), [existing])


if __name__ == "__main__":
    unittest.main()
