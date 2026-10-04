"""Optionally verify the JSON v1 documentation with an installed jsonschema validator."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> int:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print("This optional contributor check requires a Python environment with "
              "jsonschema supporting Draft202012Validator (e.g. jsonschema 4.26). "
              "The junit2context CLI does not require it.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "docs/schema-v1.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    examples = root / "docs/schema-examples"
    for name in ("empty.json", "nonempty.json"):
        validator.validate(json.loads((examples / name).read_text(encoding="utf-8")))
    invalid = json.loads((examples / "invalid-kind.json").read_text(encoding="utf-8"))
    if validator.is_valid(invalid):
        raise ValueError("invalid-kind.json must be rejected")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    with tempfile.TemporaryDirectory() as directory:
        report = Path(directory) / "example.xml"
        for xml in (
            '<testsuite><testcase name="ok"/></testsuite>',
            '<testsuite name="démo"><testcase name="test_café_😊">'
            '<failure message="café TOKEN=synthetic-only-value ' + "x" * 80 + ' Ω">'
            'TOKEN=synthetic-only-value ' + "x" * 80 + ' Ω</failure></testcase>'
            '<testcase name="test_error"><error/></testcase></testsuite>',
        ):
            report.write_text(xml, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-S", "-m", "junit2context", str(report),
                 "--format", "json", "--max-detail-chars", "60", "--max-message-chars", "60"],
                env=env, capture_output=True, text=True, encoding="utf-8", check=True,
            )
            data = json.loads(result.stdout)
            validator.validate(data)
        # The second CLI result includes both supported kinds and shortened text.
        if ({record["kind"] for record in data["failures"]} != {"failure", "error"}
                or data["failure_count"] != 2
                or data["truncated_details"] != 1 or data["truncated_messages"] != 1):
            raise ValueError("Synthetic CLI output must include both kinds and both excerpt counts")
        for text in (data["failures"][0]["message"], data["failures"][0]["details"]):
            if "[REDACTED]" not in text or "characters omitted" not in text:
                raise ValueError("Synthetic CLI output must exercise redaction and excerpts")
        if "synthetic-only-value" in result.stdout or "café" not in result.stdout or "😊" not in result.stdout:
            raise ValueError("Synthetic CLI output must redact the sample value and retain Unicode")

    extended = deepcopy(data)
    extended["future_envelope_field"] = {"example": True}
    extended["failures"][0]["future_record_field"] = None
    validator.validate(extended)
    print("JSON v1 schema: valid examples and real CLI output accepted; "
          "invalid kind rejected; unknown fields accepted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
