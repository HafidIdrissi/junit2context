"""Synthetic repository fixtures for the offline documentation check."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_local_links.py"
spec = importlib.util.spec_from_file_location("check_local_links", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class LocalLinkTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()

    def write(self, name, text=""):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def check(self, text, name="docs/guide.md"):
        return checker.check_document(self.write(name, text), self.root)

    def test_relative_links_images_and_nested_badge(self):
        self.write("LICENSE")
        self.write("docs/image.png")
        errors, count = self.check(
            "[license](../LICENSE) ![image](image.png)\n"
            "[![badge](https://example.invalid/badge)](../LICENSE)\n"
        )
        self.assertEqual(errors, [])
        self.assertEqual(count, 3)

    def test_decodes_paths_after_removing_query_and_fragment(self):
        self.write("docs/café guide#1?.md")
        self.write("docs/with space.md")
        errors, count = self.check(
            "[guide](caf%C3%A9%20guide%231%3F.md?download=1#not-a-real-anchor)\n"
            "[spaces](<with space.md>) [self](#anchor) [query](?download=1)\n"
        )
        self.assertEqual(errors, [])
        self.assertEqual(count, 2)

    def test_missing_file_reports_referrer_line_and_resolved_target(self):
        errors, count = self.check("# Guide\n\n[broken](../missing.md#section)\n")
        self.assertEqual(count, 1)
        self.assertEqual(errors, [
            "docs/guide.md:3: missing local file: '../missing.md#section' "
            "(resolved to missing.md)"
        ])

    def test_remote_schemes_are_ignored_without_network_access(self):
        errors, count = self.check(
            '[web](https://example.invalid/a(b) "title")\n'
            '[mail](mailto:person@example.invalid) [file](file:///missing.md)\n'
            '[host](//example.invalid/missing.md) [data](data:text/plain,example)\n'
        )
        self.assertEqual((errors, count), ([], 0))

    def test_code_spans_and_fences_are_not_links(self):
        self.write("docs/exists.md")
        errors, count = self.check(
            '`[ignored](missing.md)` ``[ignored](other.md)``\n'
            '````markdown\n[ignored](missing.md)\n```\n[ignored](missing.md)\n````\n'
            '~~~text\n[ignored](missing.md)\n~~~\n'
            '    [ignored](missing.md)\n\t[ignored](missing.md)\n'
            '[real](exists.md)\n'
        )
        self.assertEqual((errors, count), ([], 1))

    def test_unsupported_inline_syntax_is_not_reported_as_missing(self):
        for text in (
            '[title](missing.md "title")', '[space](with space.md)',
            '[parens](file(name).md)', '[escape](file\\ name.md)',
            '[angle escape](<file\\ name.md>)', '[angle paren](<file(.md>)',
            '[unclosed](missing.md', '[unclosed](<missing.md>', '[empty]()',
        ):
            with self.subTest(text=text):
                errors, count = self.check(text)
                self.assertEqual(count, 0)
                self.assertEqual(len(errors), 1)
                self.assertIn("unsupported link syntax", errors[0])
                self.assertNotIn("missing local file", errors[0])

    def test_code_spans_require_exact_backtick_runs(self):
        for text in (
            '`before `` [ignored](missing.md)`',
            '``before ``` [ignored](missing.md)``',
        ):
            with self.subTest(text=text):
                self.assertEqual(self.check(text), ([], 0))
        for text in (
            '`unclosed [real](missing.md)``',
            '``unclosed [real](missing.md)```',
        ):
            with self.subTest(text=text):
                errors, count = self.check(text)
                self.assertEqual(count, 1)
                self.assertIn("missing local file", errors[0])

    def test_removing_code_spans_does_not_create_links(self):
        self.write("docs/exists.md")
        self.assertEqual(self.check('[word]`example`(missing.md)'), ([], 0))
        self.assertEqual(self.check('[`word`](exists.md)'), ([], 1))

    def test_reference_links_and_markdown_html_are_outside_subset(self):
        errors, count = self.check(
            '[reference][name]\n[name]: missing.md\n'
            '<a href="missing.md">HTML in Markdown</a>\n'
        )
        self.assertEqual((errors, count), ([], 0))

    def test_absolute_paths_and_paths_outside_repository_are_diagnostics(self):
        errors, count = self.check('[root](/missing.md) [outside](../../missing.md)')
        self.assertEqual(count, 0)
        self.assertEqual(len(errors), 2)
        self.assertIn("unsupported absolute local path", errors[0])
        self.assertIn("outside repository", errors[1])

    def test_directory_target_is_not_accepted_as_a_file(self):
        errors, count = self.check('[directory](../docs)')
        self.assertEqual(count, 1)
        self.assertIn("missing local file", errors[0])

    def test_html_attributes_entities_and_script_text(self):
        self.write("README.md")
        self.write("docs/image&one.png")
        errors, count = self.check(
            '<a href="../README.md#not-validated">Guide</a>\n'
            '<img src="image&amp;one.png"/>\n'
            '<a href="https://example.invalid/">Remote</a>\n'
            '<script>const example = \'<a href="missing.md">\';</script>\n'
            '<a href="../missing.md">Broken</a>\n',
            "docs/demo.html",
        )
        self.assertEqual(count, 3)
        self.assertEqual(errors, [
            "docs/demo.html:5: missing local file: '../missing.md' (resolved to missing.md)"
        ])

    def test_bad_url_and_undecodable_filename_are_diagnostics(self):
        for link in ('[bad](%FF.md)', '<a href="//[bad">bad</a>'):
            with self.subTest(link=link):
                # Malformed remote URLs are ignored just like valid remote URLs.
                errors, count = self.check(link, "docs/demo.html" if link.startswith("<")
                                           else "docs/guide.md")
                self.assertEqual(count, 0)
                if link.startswith("["):
                    self.assertIn("unsupported URL", errors[0])
                else:
                    self.assertEqual(errors, [])

    def test_unreadable_document_is_reported(self):
        errors, count = checker.check_document(self.root / "missing.md", self.root)
        self.assertEqual(count, 0)
        self.assertIn("missing.md: cannot read document", errors[0])

    def test_invalid_local_filename_is_a_diagnostic(self):
        errors, count = self.check('[invalid](bad%00name.md)')
        self.assertEqual(count, 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("invalid or unreadable local target", errors[0])

    def test_cli_scope_exit_status_and_working_directory(self):
        copied = self.root / "scripts/check_local_links.py"
        copied.parent.mkdir()
        shutil.copyfile(SCRIPT, copied)
        self.write("README.md", '[guide](docs/guide.md)')
        self.write("docs/guide.md", '[readme](../README.md#anchor)')
        self.write("docs/demo.html", '<a href="../README.md">Guide</a>')
        self.write("tests/fixtures/README.md", '[excluded](missing.md)')
        self.write("examples/brief.md", '[untrusted example](missing.md)')
        command = [sys.executable, "-S", str(copied)]
        result = subprocess.run(command, cwd=self.root.parent, capture_output=True,
                                text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("3 file targets checked in 3 documents", result.stdout)
        self.assertIn("anchors not validated", result.stdout)
        self.write("docs/nested/new.md", '[broken](missing.md)')
        result = subprocess.run(command, cwd=self.root.parent, capture_output=True,
                                text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/nested/new.md:1: missing local file", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
