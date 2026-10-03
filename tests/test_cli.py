import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from junit2context.cli import _excerpt, main


class ExcerptTests(unittest.TestCase):
    def test_marker_boundaries_drop_only_whole_markers(self):
        cases = [
            ("AA[REDACTED]0123456789", "AA", "56789", 15),
            ("0123456789[REDACTED]ZZ", "01234", "ZZ", 15),
            ("AA[REDACTED]----[REDACTED]ZZ", "AA", "ZZ", 24),
        ]
        for value, head, tail, omitted in cases:
            for label in ("message", "detail"):
                with self.subTest(value=value, label=label):
                    self.assertEqual(
                        _excerpt(value, 10, label),
                        f"{head}\n[... {omitted} {label} characters omitted ...]\n{tail}",
                    )

    def test_marker_larger_than_budget_is_omitted_whole(self):
        for limit in range(1, 10):
            with self.subTest(limit=limit):
                self.assertEqual(
                    _excerpt("[REDACTED]", limit, "detail"),
                    "\n[... 10 detail characters omitted ...]\n",
                )
        self.assertEqual(_excerpt("[REDACTED]", 10, "detail"), "[REDACTED]")

    def test_exact_marker_boundaries_keep_complete_markers(self):
        self.assertEqual(
            _excerpt("[REDACTED]0123456789abcdef", 20, "detail"),
            "[REDACTED]\n[... 6 detail characters omitted ...]\n6789abcdef",
        )
        self.assertEqual(
            _excerpt("0123456789abcdef[REDACTED]", 20, "detail"),
            "0123456789\n[... 6 detail characters omitted ...]\n[REDACTED]",
        )
        self.assertEqual(
            _excerpt("[REDACTED][REDACTED]", 19, "detail"),
            "[REDACTED]\n[... 10 detail characters omitted ...]\n",
        )

    def test_ordinary_excerpts_and_unshortened_values_are_unchanged(self):
        self.assertEqual(
            _excerpt("abcdefghij", 5, "message"),
            "abc\n[... 5 message characters omitted ...]\nij",
        )
        self.assertEqual(
            _excerpt("abcdefghij", 1, "message"),
            "a\n[... 9 message characters omitted ...]\n",
        )
        self.assertEqual(_excerpt("[REDACTED]", 11, "message"), "[REDACTED]")
        self.assertEqual(_excerpt("", 1, "detail"), "")
        self.assertEqual(
            _excerpt("é😊abcΩ", 3, "message"),
            "é😊\n[... 3 message characters omitted ...]\nΩ",
        )


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / "report.xml"
        self.report.write_text('<testsuite name="demo"><testcase name="failed">'
                               '<failure message="bad">TOKEN=demo-private-value\ntrace</failure>'
                               '</testcase></testsuite>', encoding="utf-8")

    def run_cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = main([str(arg) for arg in args])
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()

    def test_default_is_success_with_redacted_markdown(self):
        code, out, err = self.run_cli(self.report)
        self.assertEqual(code, 0)
        self.assertIn("failed", out)
        self.assertIn("[REDACTED]", out)
        self.assertNotIn("demo-private-value", out)
        self.assertEqual(err, "")

    def test_ci_failure_exit_still_emits_brief(self):
        code, out, _ = self.run_cli(self.report, "--fail-on-failures")
        self.assertEqual(code, 1)
        self.assertIn("failed", out)

    def test_passing_report_exit(self):
        self.report.write_text('<testsuite><testcase name="ok"/></testsuite>', encoding="utf-8")
        code, out, _ = self.run_cli(self.report, "--fail-on-failures")
        self.assertEqual(code, 0)
        self.assertIn("No failures", out)

    def test_json_schema_and_redaction(self):
        code, out, err = self.run_cli(self.report, "--format", "json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["failure_count"], 1)
        self.assertEqual(data["truncated_details"], 0)
        self.assertIn("[REDACTED]", data["failures"][0]["details"])
        self.assertEqual(err, "")

    def test_detail_truncation_is_after_redaction_and_explicit(self):
        code, out, _ = self.run_cli(self.report, "--format", "json", "--max-detail-chars", "8")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["truncated_details"], 1)
        self.assertIn("detail characters omitted", data["failures"][0]["details"])
        self.assertNotIn("demo-private-value", out)

    def test_redacted_message_and_detail_boundaries_use_actual_omission_count(self):
        text = "AA TOKEN=head-demo-secret middle TOKEN=tail-demo-secret ZZ"
        self.report.write_text(
            '<testsuite><testcase name="failed"><failure message="'
            + text + '">' + text + '</failure></testcase></testsuite>',
            encoding="utf-8",
        )
        code, out, err = self.run_cli(
            self.report, "--format", "json",
            "--max-message-chars", "22", "--max-detail-chars", "22",
        )
        self.assertEqual((code, err), (0, ""))
        data = json.loads(out)
        self.assertEqual(data["truncated_messages"], 1)
        self.assertEqual(data["truncated_details"], 1)
        for field, label in (("message", "message"), ("details", "detail")):
            self.assertEqual(
                data["failures"][0][field],
                f"AA TOKEN=\n[... 34 {label} characters omitted ...]\n ZZ",
            )
        self.assertNotIn("head-demo-secret", out)
        self.assertNotIn("tail-demo-secret", out)

        code, out, err = self.run_cli(
            self.report, "--max-message-chars", "22", "--max-detail-chars", "22",
        )
        self.assertEqual((code, err), (0, ""))
        self.assertIn("AA TOKEN=\n[... 34 detail characters omitted ...]\n ZZ", out)
        self.assertIn(r"\[\.\.\. 34 message characters omitted \.\.\.\]", out)
        self.assertNotIn("REDACTED", out)
        self.assertNotIn("head-demo-secret", out)
        self.assertNotIn("tail-demo-secret", out)

    def test_markdown_keeps_retained_redaction_markers_complete(self):
        text = "TOKEN=head-demo-secret middle TOKEN=tail-demo-secret"
        self.report.write_text(
            '<testsuite><testcase name="failed"><failure message="'
            + text + '">' + text + '</failure></testcase></testsuite>',
            encoding="utf-8",
        )
        code, out, err = self.run_cli(
            self.report, "--max-message-chars", "32", "--max-detail-chars", "32",
        )
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.count("[REDACTED]"), 2)
        self.assertEqual(out.count(r"\[REDACTED\]"), 2)
        self.assertIn("message characters omitted", out)
        self.assertIn("detail characters omitted", out)
        self.assertNotIn("head-demo-secret", out)
        self.assertNotIn("tail-demo-secret", out)

    def test_markdown_budget(self):
        code, out, _ = self.run_cli(self.report, "--max-chars", "128")
        self.assertEqual(code, 0)
        self.assertLessEqual(len(out), 128)
        self.assertIn("omitted", out)

    def test_excerpt_keeps_terminal_exception_and_limits_large_message(self):
        self.report.write_text('<testsuite><testcase name="failed"><failure message="'
                               + 'm' * 15000 + '">START' + 'x' * 5000
                               + 'FINAL EXCEPTION</failure></testcase></testsuite>', encoding="utf-8")
        code, out, _ = self.run_cli(self.report)
        self.assertEqual(code, 0)
        self.assertIn("FINAL EXCEPTION", out)
        self.assertIn("START", out)
        self.assertIn("message characters omitted", out)
        self.assertLessEqual(len(out), 12000)

    def test_invalid_flags_and_missing_arguments(self):
        for extra in [("--max-chars", "127"), ("--max-file-bytes", "0"),
                      ("--max-detail-chars", "no"), ("--format", "json", "--max-chars", "1000")]:
            with self.subTest(extra=extra):
                code, out, err = self.run_cli(self.report, *extra)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertTrue(err)
        self.assertEqual(self.run_cli()[0], 2)

    def test_invalid_report_has_no_partial_output(self):
        bad = self.root / "bad.xml"
        bad.write_text("not xml", encoding="utf-8")
        code, out, err = self.run_cli(self.report, bad)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("invalid XML", err)

    def test_write_output_and_replace_existing(self):
        output = self.root / "brief.md"
        output.write_text("old", encoding="utf-8")
        code, out, err = self.run_cli(self.report, "-o", output)
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertIn("failed", output.read_text(encoding="utf-8"))
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_cannot_overwrite_input(self):
        before = self.report.read_bytes()
        code, out, err = self.run_cli(self.report, "-o", self.report)
        self.assertEqual(code, 2)
        self.assertEqual(self.report.read_bytes(), before)
        self.assertEqual(out, "")
        self.assertIn("overwrite", err)

    def test_input_error_leaves_existing_output_intact(self):
        output = self.root / "brief.md"
        output.write_text("old", encoding="utf-8")
        code, _, _ = self.run_cli(self.report, self.root / "missing.xml", "-o", output)
        self.assertEqual(code, 2)
        self.assertEqual(output.read_text(encoding="utf-8"), "old")

    def test_output_error_is_clean(self):
        code, out, err = self.run_cli(self.report, "-o", self.root / "missing" / "brief.md")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertTrue(err)

    def test_multiple_reports_deduplicate(self):
        code, out, _ = self.run_cli(self.report, self.report, "--format", "json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["failure_count"], 1)


if __name__ == "__main__":
    unittest.main()
