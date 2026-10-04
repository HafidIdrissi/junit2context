# JSON version 1 schema

[schema-v1.json](schema-v1.json) describes the existing CLI JSON output using
[JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12/json-schema-validation).
It is a repository document, not a new CLI option or a promise about future schema
versions. The CLI still uses only the Python standard library.

The envelope requires `schema_version` (integer `1`), the three non-negative
integer counts (`failure_count`, `truncated_details`, `truncated_messages`), and
the `failures` array. Every failure requires the seven current string fields:
`source`, `suite`, `classname`, `name`, `kind`, `message`, and `details`. The only
supported kinds are `failure` and `error`; passing and skipped tests are excluded.
Empty strings are allowed, including absent class names, messages, and details.
Paths are sanitized report strings, not URI fields or paths that a reader must
be able to open. Unicode, `[REDACTED]`, and excerpt notices are ordinary string
content, so the schema imposes no character limit or secret-detection constraint.

Unknown properties are explicitly accepted in both the envelope and each record.
This allows readers to tolerate added metadata while still checking all current
required fields and their types. The tradeoff is that extra misspelled or
unexpected fields are not rejected. Missing required fields and other schema
versions still fail. This policy does not promise that future versions will be
compatible with version 1.

The schema checks structure. It does not enforce that `failure_count` equals the
array length, that truncation counts are bounded by it, or that text actually is
redacted. Consumers needing these relationships should check them separately.

## Contributor verification

The examples are synthetic, hand-written contract illustrations:

- [empty.json](schema-examples/empty.json): valid output with no failures.
- [nonempty.json](schema-examples/nonempty.json): valid output with both kinds,
  Unicode, an empty class name, a redaction marker, and a detail excerpt notice.
- [invalid-kind.json](schema-examples/invalid-kind.json): intentionally invalid;
  `failures[0].kind` is `skipped`, which the CLI does not emit.

Use a Draft 2020-12 validator to check the schema and instances. For an optional,
repeatable check, run from the repository root with a Python 3.10+ environment
that already provides [`jsonschema`](https://python-jsonschema.readthedocs.io/en/stable/validate/)
and its `Draft202012Validator` (verified with jsonschema 4.26):

```bash
python3 scripts/check_json_schema.py
```

On Windows, use `python` in place of `python3`. The check validates the schema
itself, both valid examples, rejection of the invalid example, and acceptance of
extra fields. It also invokes the source-checkout CLI on temporary synthetic
passing/failing XML reports and validates the actual JSON containing Unicode,
redaction markers, and message/detail excerpt notices. No reports are uploaded
and no network access or package installation occurs during the check. If the
optional validator is absent, it exits `2` with an explanation.

This check is separate from the standard-library unit suite and is not run by
the existing CI matrix. It adds no runtime or development dependency. To validate
another output with the same optional Python validator, from the repository root:

```bash
python3 -c 'import json, sys; from jsonschema import Draft202012Validator; schema = json.load(open("docs/schema-v1.json", encoding="utf-8")); Draft202012Validator.check_schema(schema); Draft202012Validator(schema).validate(json.load(open(sys.argv[1], encoding="utf-8")))' failures.json
```

The final example uses POSIX shell quoting; on Windows, use the verification
script above for the bundled checks, or call the validator from Python.
