"""Compatibility regression for a recorded pytest 9.1.1 xunit2 export."""

import contextlib
import io
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from junit2context.cli import main
from junit2context.core import parse_reports, render_markdown


REPORT = Path(__file__).parent / "fixtures" / "pytest-9.1.1" / "report.xml"


class PytestFixtureTests(unittest.TestCase):
    def test_assertion_and_setup_error_preserve_identity_and_diagnostics(self):
        failures = parse_reports([REPORT])
        self.assertEqual(
            [(failure.name, failure.kind) for failure in failures],
            [("test_failed_assertion", "failure"), ("test_setup_error", "error")],
        )
        self.assertEqual([failure.suite for failure in failures], ["pytest", "pytest"])
        self.assertEqual([failure.classname for failure in failures],
                         ["sample_tests", "sample_tests"])
        assertion, setup_error = failures
        self.assertIn("synthetic assertion diagnostic", assertion.message)
        self.assertIn("assert (2 + 2) == 5", assertion.details)
        self.assertIn("sample_tests.py:16: in test_failed_assertion", assertion.details)
        self.assertIn("RuntimeError: synthetic setup unavailable", setup_error.message)
        self.assertIn('raise RuntimeError("synthetic setup unavailable")', setup_error.details)
        self.assertIn("sample_tests.py:8: in unavailable_service", setup_error.details)

    def test_markdown_and_json_keep_both_diagnostics_and_exclude_passing_case(self):
        failures = parse_reports([REPORT])
        markdown = render_markdown(failures)
        self.assertIn("2 unique failure(s).", markdown)
        self.assertIn("synthetic assertion diagnostic", markdown)
        self.assertIn("RuntimeError: synthetic setup unavailable", markdown)
        self.assertIn("sample_tests.py:16", markdown)
        self.assertIn("sample_tests.py:8", markdown)
        self.assertNotIn("test_passing", markdown)

        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main([str(REPORT), "--format", "json"])
        self.assertEqual((result, stderr.getvalue()), (0, ""))
        data = json.loads(stdout.getvalue())
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["failure_count"], 2)
        self.assertEqual(data["truncated_messages"], 0)
        self.assertEqual(data["truncated_details"], 0)
        self.assertEqual([record["name"] for record in data["failures"]],
                         ["test_failed_assertion", "test_setup_error"])
        self.assertEqual([record["details"] for record in data["failures"]],
                         [failure.details for failure in failures])

    def test_exporter_summary_retains_passing_case_without_machine_metadata(self):
        root = ET.parse(REPORT).getroot()
        suite = root.find("testsuite")
        self.assertIsNotNone(suite)
        self.assertEqual({key: suite.get(key) for key in ("tests", "failures", "errors", "skipped")},
                         {"tests": "3", "failures": "1", "errors": "1", "skipped": "0"})
        cases = suite.findall("testcase")
        passing = [case for case in cases if case.get("name") == "test_passing"]
        self.assertEqual(len(passing), 1)
        self.assertEqual(list(passing[0]), [])
        for element in root.iter():
            self.assertFalse({"hostname", "timestamp", "time"} & element.attrib.keys())


if __name__ == "__main__":
    unittest.main()
