"""Behavioral tests for parsing untrusted reports and sharing bounded context."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from junit2context.core import (
    Failure,
    ReportError,
    parse_reports,
    redact,
    render_markdown,
    sanitize_failure,
)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def report(self, text, name="report.xml", encoding="utf-8"):
        path = self.root / name
        path.write_bytes(text.encode(encoding))
        return path

    def test_collects_failures_and_errors_without_captured_output(self):
        path = self.report('''<testsuite name="checkout">
          <properties><testcase name="fake"><failure>secret</failure></testcase></properties>
          <testcase name="passes"><system-out>private output</system-out></testcase>
          <testcase name="skipped"><skipped message="later"/></testcase>
          <testcase name="fails"><failure message="expected 2"> actual 1 </failure>
            <system-out>private output</system-out><system-err>private error</system-err>
          </testcase>
          <testcase name="crashes"><error type="TimeoutError">traceback</error></testcase>
          <system-out><testcase name="fake"><failure>secret</failure></testcase></system-out>
        </testsuite>''')
        self.assertEqual(parse_reports([path]), [
            Failure(str(path), "checkout", "fails", "failure", "expected 2", "actual 1"),
            Failure(str(path), "checkout", "crashes", "error", "TimeoutError", "traceback"),
        ])

    def test_namespaced_nested_suites_keep_order_and_inherit_names(self):
        path = self.report('''<j:testsuites xmlns:j="urn:junit">
          <j:testsuite name="outer">
            <j:testcase name="first"><j:failure/></j:testcase>
            <j:testsuite name="inner">
              <j:testcase name="second"><j:error/></j:testcase>
              <j:testsuite><j:testcase name="third"><j:failure/></j:testcase></j:testsuite>
            </j:testsuite>
            <j:testcase name="fourth"><j:failure/></j:testcase>
          </j:testsuite>
        </j:testsuites>''')
        self.assertEqual(
            [(failure.suite, failure.name) for failure in parse_reports([path])],
            [("outer", "first"), ("inner", "second"), ("inner", "third"), ("outer", "fourth")],
        )

    def test_exact_duplicates_keep_first_source_but_distinct_failures_survive(self):
        first = self.report('''<testsuite name="suite"><testcase name="test">
          <failure message="oops">trace</failure><failure message="oops">trace</failure>
        </testcase></testsuite>''', "first.xml")
        second = self.report('''<testsuite name="suite"><testcase name="test">
          <failure message="oops">trace</failure>
          <failure message="other">trace</failure>
          <failure message="oops">other trace</failure>
          <error message="oops">trace</error>
        </testcase></testsuite>''', "second.xml")
        failures = parse_reports([first, second, first])
        self.assertEqual(len(failures), 4)
        self.assertEqual(failures[0].source, str(first))
        self.assertTrue(all(item.source == str(second) for item in failures[1:]))

    def test_fallback_names_and_nested_failure_text(self):
        path = self.report('''<testsuites>
          <testsuite><testcase classname="Calculator"><failure>before <b>middle</b> after</failure></testcase></testsuite>
          <testsuite><testcase><error/></testcase></testsuite>
        </testsuites>''')
        first, second = parse_reports([path])
        self.assertEqual((first.suite, first.name, first.details),
                         ("Calculator", "(unnamed test)", "before middle after"))
        self.assertEqual((second.suite, second.message, second.details),
                         ("(unnamed suite)", "", ""))

    def test_deep_suites_do_not_require_python_recursion(self):
        path = self.report('<testsuite name="deep">' * 1100 +
                           '<testcase name="failure"><failure/></testcase>' +
                           '</testsuite>' * 1100)
        self.assertEqual(parse_reports([path])[0].suite, "deep")

    def test_utf8_bom_and_non_ascii_are_supported(self):
        path = self.report('<?xml version="1.0" encoding="UTF-8"?>'
                           '<testsuite name="équipe"><testcase name="東京"><failure>échec</failure></testcase></testsuite>',
                           encoding="utf-8-sig")
        failure = parse_reports([path])[0]
        self.assertEqual((failure.suite, failure.name, failure.details), ("équipe", "東京", "échec"))

    def test_invalid_xml_and_unsupported_roots_fail(self):
        for report in ("<testsuite>", "", "<notjunit/>", "<testcase><failure/></testcase>"):
            with self.subTest(report=report), self.assertRaises(ReportError):
                parse_reports([self.report(report)])

    def test_dtd_and_entity_declarations_are_rejected(self):
        for declaration in (
            '<!DOCTYPE testsuite [<!ENTITY x "expanded">]>',
            '<!DOCTYPE testsuite SYSTEM "file:///etc/passwd">',
            '<!ENTITY external SYSTEM "https://example.com/private">',
        ):
            with self.subTest(declaration=declaration):
                path = self.report(declaration + '<testsuite/>')
                with self.assertRaisesRegex(ReportError, "DTD and entity"):
                    parse_reports([path])

    def test_non_utf8_and_binary_reports_are_rejected(self):
        for encoding in ("utf-16", "utf-16-le", "utf-16-be", "utf-32"):
            with self.subTest(encoding=encoding), self.assertRaises(ReportError):
                parse_reports([self.report('<testsuite/>', encoding=encoding)])
        path = self.report('<?xml version="1.0" encoding="ISO-8859-1"?><testsuite/>')
        with self.assertRaisesRegex(ReportError, "declare UTF-8"):
            parse_reports([path])
        with self.assertRaises(ReportError):
            parse_reports([self.report('<testsuite>\x00</testsuite>')])

    def test_file_byte_limit_is_inclusive_and_positive(self):
        path = self.report('<testsuite/>')
        size = path.stat().st_size
        self.assertEqual(parse_reports([path], max_file_bytes=size), [])
        with self.assertRaisesRegex(ReportError, "exceeds"):
            parse_reports([path], max_file_bytes=size - 1)
        for limit in (0, -1):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                parse_reports([path], max_file_bytes=limit)

    def test_file_that_grows_after_stat_is_still_bounded(self):
        path = self.report('<testsuite/>')
        import io
        with patch.object(Path, "open", return_value=io.BytesIO(b"x" * 100)):
            with self.assertRaisesRegex(ReportError, "exceeds 20 bytes"):
                parse_reports([path], max_file_bytes=20)

    def test_missing_directory_and_unreadable_reports_are_errors(self):
        for path in (self.root / "missing.xml", self.root):
            with self.subTest(path=path), self.assertRaises(ReportError):
                parse_reports([path])
        path = self.report('<testsuite/>')
        with patch.object(Path, "open", side_effect=PermissionError("access denied")):
            with self.assertRaisesRegex(ReportError, "cannot read report"):
                parse_reports([path])

    def test_invalid_later_report_does_not_return_partial_success(self):
        valid = self.report('<testsuite><testcase><failure/></testcase></testsuite>')
        invalid = self.report('<notjunit/>', "invalid.xml")
        with self.assertRaises(ReportError):
            parse_reports([valid, invalid])


class RedactionTests(unittest.TestCase):
    def test_common_provider_credentials(self):
        # These values are intentionally fake. Construct them at runtime so
        # repository scanners cannot mistake fixtures for real credentials.
        suffix = "a" * 24
        tokens = [prefix + suffix for prefix in
                  ("sk-", "sk-proj-", "sk-ant-api03-", "ghp_", "github_pat_", "xoxb-")]
        tokens.extend(prefix + "A" * 16 for prefix in ("AKIA", "ASIA"))
        for token in tokens:
            with self.subTest(token=token):
                self.assertEqual(redact(f"credential {token} end"), "credential [REDACTED] end")

    def test_assignments_bearer_and_url_credentials(self):
        pairs = (
            ('PASSWORD=hunter2', 'PASSWORD=[REDACTED]'),
            ('api_key="a secret with spaces"', 'api_key="[REDACTED]"'),
            ("'access_token': 'abc123'", "'access_token': '[REDACTED]'"),
            ('{"api-key": "value", "status": "bad"}', '{"api-key": "[REDACTED]", "status": "bad"}'),
            ('Authorization: Bearer abc.def_ghi==', 'Authorization: Bearer [REDACTED]'),
            ('https://alice:p%40ss@example.com/path', 'https://[REDACTED]@example.com/path'),
        )
        for original, expected in pairs:
            with self.subTest(original=original):
                self.assertEqual(redact(original), expected)
                self.assertEqual(redact(expected), expected)

    def test_terminal_sequences_controls_and_newlines(self):
        value = '\x1b[31mred\x1b[0m\r\nnext\rlast\x00\x7f\u202e'
        self.assertEqual(redact(value), "red\nnext\nlast")
        self.assertEqual(redact('\x1b]8;;https://example.com\x07label\x1b]8;;\x07'), "label")
        self.assertEqual(redact('\x1b]0;window title\x1b\\text'), "text")
        self.assertEqual(redact("expected 2, received 1\n\ttrace.py:23"), "expected 2, received 1\n\ttrace.py:23")

    def test_sanitization_covers_every_field_without_mutating_original(self):
        original = Failure(*(["PASSWORD=secret"] * 6))
        sanitized = sanitize_failure(original)
        self.assertEqual(sanitized, Failure(*(["PASSWORD=[REDACTED]"] * 6)))
        self.assertEqual(original.name, "PASSWORD=secret")


class MarkdownTests(unittest.TestCase):
    def failure(self, name="adds", details="expected 2\nreceived 1"):
        return Failure("report.xml", "math", name, "failure", "incorrect result", details)

    def test_empty_report_and_minimum_budget(self):
        self.assertEqual(render_markdown([]), "# Test failure context\n\nNo failures or errors found.\n")
        with self.assertRaises(ValueError):
            render_markdown([], max_chars=127)

    def test_output_is_deterministic_and_redacted(self):
        failure = self.failure(details="TOKEN=secret\nAuthorization: Bearer abc123")
        first = render_markdown([failure])
        self.assertEqual(first, render_markdown([failure]))
        self.assertNotIn("secret", first)
        self.assertNotIn("abc123", first)
        self.assertIn("TOKEN=[REDACTED]", first)
        self.assertIn("1 unique failure(s).", first)
        self.assertIn("### 1. adds", first)

    def test_budget_includes_header_and_notice_without_partial_failure_blocks(self):
        failures = [self.failure(name=f"test{number}") for number in range(5)]
        full = render_markdown(failures)
        for budget in (128, 200, 400, len(full), len(full) + 100):
            with self.subTest(budget=budget):
                output = render_markdown(failures, max_chars=budget)
                self.assertLessEqual(len(output), budget)
                included = output.count("### ")
                self.assertEqual(output.count("```text"), included)
                self.assertEqual(output.count("\n```\n"), included)
                self.assertTrue(all(f"### {index + 1}. test{index}" in output for index in range(included)))
                if included < len(failures):
                    self.assertIn(f"> {5 - included} failure(s) omitted: {budget}-character limit.", output)
                else:
                    self.assertNotIn("omitted", output)
        self.assertEqual(render_markdown(failures, max_chars=len(full)), full)

    def test_oversized_first_failure_omits_ordered_suffix(self):
        failures = [self.failure(details="x" * 1000), self.failure(name="tiny", details="")]
        output = render_markdown(failures, max_chars=256)
        self.assertNotIn("###", output)
        self.assertIn("2 failure(s) omitted", output)

    def test_budget_counts_unicode_characters(self):
        failure = self.failure(details="é" * 100)
        output = render_markdown([failure])
        self.assertGreater(len(output.encode("utf-8")), len(output))
        self.assertEqual(render_markdown([failure], max_chars=len(output)), output)

    def test_embedded_fences_cannot_escape_details_block(self):
        details = "first\n```\n# forged heading\n`````\nlast"
        output = render_markdown([self.failure(details=details)])
        self.assertIn("\n``````text\n" + details + "\n``````\n", output)

    def test_metadata_is_escaped_and_cannot_create_markdown_structure(self):
        failure = self.failure(name="[click](https://example.com)\n# heading <script>")
        output = render_markdown([failure])
        self.assertIn(r"\[click\]\(https://example\.com\) \# heading &lt;script&gt;", output)
        self.assertNotIn("\n# heading", output)
        self.assertNotIn("<script>", output)


if __name__ == "__main__":
    unittest.main()
