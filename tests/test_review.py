"""Regression coverage for distinct test identity and misleading report output."""

from pathlib import Path
import tempfile
import unittest

from junit2context.core import Failure, ReportError, parse_reports, redact, render_markdown, sanitize_failure


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def report(self, content, name="report.xml"):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_distinct_classes_survive_dedup_and_duplicate_reports_keep_first_source(self):
        content = '''<testsuite name="pytest" failures="2">
          <testcase classname="tests.A" name="test_ok">
            <failure message="assert False">AssertionError</failure>
          </testcase>
          <testcase classname="tests.B" name="test_ok">
            <failure message="assert False">AssertionError</failure>
          </testcase>
        </testsuite>'''
        first = self.report(content)
        duplicate = self.report(content, "duplicate.xml")
        failures = parse_reports([first, duplicate])
        self.assertEqual(len(failures), 2)
        self.assertEqual([failure.classname for failure in failures], ["tests.A", "tests.B"])
        self.assertEqual([failure.source for failure in failures], [str(first), str(first)])
        markdown = render_markdown(failures)
        self.assertIn(r"- Class: tests\.A", markdown)
        self.assertIn(r"- Class: tests\.B", markdown)

    def test_classname_is_redacted_and_escaped_without_mutating_original(self):
        failure = Failure("report.xml", "suite", "test", "failure", "bad", "trace",
                          classname="<Class>\nPASSWORD=private-value")
        sanitized = sanitize_failure(failure)
        self.assertEqual(sanitized.classname, "<Class>\nPASSWORD=[REDACTED]")
        self.assertEqual(failure.classname, "<Class>\nPASSWORD=private-value")
        markdown = render_markdown([failure])
        self.assertNotIn("private-value", markdown)
        self.assertNotIn("<Class>", markdown)
        self.assertIn(r"- Class: &lt;Class&gt; PASSWORD=\[REDACTED\]", markdown)

    def test_missing_classname_preserves_existing_constructors_and_output(self):
        failure = Failure("report.xml", "suite", "test", "failure", "bad", "trace")
        self.assertEqual(failure.classname, "")
        self.assertNotIn("- Class:", render_markdown([failure]))

    def test_escaped_quotes_do_not_expose_the_remaining_secret(self):
        cases = (
            (r'password="first\"SECOND_SECRET" status=failed',
             'password="[REDACTED]" status=failed'),
            (r"password='first\'SECOND_SECRET' status=failed",
             "password='[REDACTED]' status=failed"),
            (r'{"token": "first\"SECOND_SECRET", "status": "bad"}',
             '{"token": "[REDACTED]", "status": "bad"}'),
            (r'password="first\\" status=failed',
             'password="[REDACTED]" status=failed'),
        )
        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(redact(original), expected)
                self.assertEqual(redact(expected), expected)

    def test_declared_failures_without_outcomes_are_rejected(self):
        reports = (
            '<testsuite tests="1" failures="1"/>',
            '<testsuites errors="1"><testsuite><testcase name="passing"/></testsuite></testsuites>',
            '<testsuites><testsuite failures="02"/></testsuites>',
            '<j:testsuite xmlns:j="urn:junit" errors="1"/>',
        )
        for content in reports:
            with self.subTest(content=content):
                with self.assertRaisesRegex(ReportError, "declares failures/errors"):
                    parse_reports([self.report(content)])

    def test_valid_earlier_report_cannot_hide_incomplete_later_report(self):
        valid = self.report('<testsuite><testcase><failure/></testcase></testsuite>')
        invalid = self.report('<testsuite failures="1"/>', "incomplete.xml")
        with self.assertRaisesRegex(ReportError, "declares failures/errors"):
            parse_reports([valid, invalid])

    def test_nested_outcomes_satisfy_parent_aggregate_declarations(self):
        report = self.report('''<testsuites failures="1">
          <testsuite name="outer" failures="1">
            <testsuite name="inner" failures="1">
              <testcase name="test"><failure>bad</failure></testcase>
            </testsuite>
          </testsuite>
        </testsuites>''')
        self.assertEqual(len(parse_reports([report, report])), 1)

    def test_truly_empty_reports_and_zero_counters_remain_valid(self):
        for content in ('<testsuites/>', '<testsuite tests="0" failures="0" errors="0"/>'):
            with self.subTest(content=content):
                self.assertEqual(parse_reports([self.report(content)]), [])


if __name__ == "__main__":
    unittest.main()
