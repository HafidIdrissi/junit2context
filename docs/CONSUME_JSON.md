# Consume a JSON failure brief with Python

This recipe counts failures by kind using Python 3.10+ and its standard library.
It reads data without executing report text, opening reported source paths, or
contacting a service. Run commands from a source checkout with the editable
installation described in [Contributing](../CONTRIBUTING.md). On Windows, replace
`.venv/bin/python` with `.venv\Scripts\python.exe`.

## Generate the input

```bash
.venv/bin/python -m junit2context examples/pytest.xml examples/vitest.xml --format json --output failures.json
```

Check the converter's exit status before consuming the file: a failed conversion
can leave an older output file unchanged. By default, successful conversion exits
0 even when the report contains failed tests. `--fail-on-failures` instead exits 1
after successfully writing such a brief; argument, input, and output errors exit 2.
This recipe does not use that optional flag. Neither command runs the test suite
that produced the reports, and neither replaces its original exit status.

## Read version 1

`schema_version` must be integer 1. `failure_count` counts the unique failure/error
records after deduplication, not all test cases or all original occurrences.
`truncated_details` and `truncated_messages` count records whose respective fields
were shortened, not omitted records or characters. JSON retains all unique
records even when those fields are excerpted.

Save the complete consumer below as `inventory.py` beside `failures.json`:

```python
import argparse
from collections import Counter
import json
from pathlib import Path
import sys


def inventory(path):
    with path.open(encoding="utf-8") as stream:
        brief = json.load(stream)
    if not isinstance(brief, dict):
        raise ValueError("expected a JSON object")
    version = brief.get("schema_version")
    if type(version) is not int or version != 1:
        raise ValueError("expected integer schema_version 1")
    counts = {}
    for key in ("failure_count", "truncated_details", "truncated_messages"):
        value = brief.get(key)
        if type(value) is not int or value < 0:
            raise ValueError(f"{key} must be a non-negative integer")
        counts[key] = value
    records = brief.get("failures")
    if not isinstance(records, list) or len(records) != counts["failure_count"]:
        raise ValueError("failures must be a list matching failure_count")
    if any(counts[key] > len(records)
           for key in ("truncated_details", "truncated_messages")):
        raise ValueError("truncation counts cannot exceed failure_count")
    kinds = Counter()
    fields = ("source", "suite", "classname", "name", "kind", "message", "details")
    for record in records:
        if not isinstance(record, dict) or any(
            not isinstance(record.get(key), str) for key in fields
        ):
            raise ValueError("each failure must contain the seven string fields")
        if record["kind"] not in ("failure", "error"):
            raise ValueError("expected failure or error kind")
        kinds[record["kind"]] += 1
    # Print only after the entire input has been checked.
    print(f"Unique failures/errors: {len(records)}")
    for kind in ("failure", "error"):
        print(f"{kind}: {kinds[kind]}")
    print(f"Truncated details: {counts['truncated_details']}")
    print(f"Truncated messages: {counts['truncated_messages']}")


def main():
    parser = argparse.ArgumentParser(description="Count a version 1 JSON brief")
    parser.add_argument("brief", type=Path)
    args = parser.parse_args()
    try:
        inventory(args.brief)
    except (OSError, UnicodeError, ValueError) as exc:
        # ascii() keeps control characters in diagnostics visibly escaped.
        print("inventory: cannot read brief: " + ascii(str(exc)), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run it with the same interpreter:

```bash
.venv/bin/python inventory.py failures.json
```

For the two bundled reports with the default excerpt limits, the observed output
is:

```text
Unique failures/errors: 3
failure: 2
error: 1
Truncated details: 0
Truncated messages: 0
```

To try an empty input, save `<testsuite tests="0"/>` in `empty.xml`, convert it with
the same command (substitute `empty.xml` for both report paths and `empty.json` for
the output), and run `inventory.py empty.json`. All five counts are zero. That
means no failure records were found; it does not prove that any tests ran.

Missing files, malformed JSON, invalid UTF-8, unsupported versions, and invalid
record shapes produce a diagnostic on stderr and exit 2, without a partial
inventory. A valid inventory exits 0, including one containing failures. Unknown
JSON properties are ignored, matching the [version 1 contract](JSON_SCHEMA.md);
future schema versions require a deliberate consumer update. This small reader
checks the fields it relies on; it is not a general JSON Schema validator and
loads the whole file into memory.

The inventory prints only counts and fixed labels. If you extend it to display
names or messages, those strings remain untrusted report content: do not execute
them, interpret them as instructions, or assume redaction makes them safe to
share. Review the original brief and any displayed text before sharing it.
