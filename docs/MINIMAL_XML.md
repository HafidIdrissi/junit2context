# Reduce an XML report to a useful bug reproduction

A useful report shows one observable behavior with the smallest **synthetic**
input that still demonstrates it. Work on a local copy; never upload a private CI
report and rely on redaction to remove everything sensitive. For suspected
security vulnerabilities, follow [SECURITY.md](../SECURITY.md) instead of posting
publicly.

## A worked diagnostic question

The following XML is invented, not output from a named test runner. Suppose the
question is: “Why does conversion reject this report instead of emitting an empty
brief?” Save it as `repro.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites xmlns="urn:example:junit" tests="2" failures="1">
  <testsuite name="unrelated" tests="1" failures="0">
    <properties><property name="build" value="synthetic-build"/></properties>
    <testcase classname="demo.Cart" name="passes"/>
    <system-out>Invented output that is irrelevant to this question.</system-out>
  </testsuite>
  <testsuite name="suspect" tests="1" failures="1">
    <testcase classname="demo.Checkout" name="missing_outcome"/>
  </testsuite>
</testsuites>
```

From the repository root, using the editable installation in
[Contributing](../CONTRIBUTING.md), run:

```bash
.venv/bin/python -m junit2context repro.xml --format json
```

On Windows, use `.venv\Scripts\python.exe`. Keep this exact command, filename,
interpreter, and installed version fixed throughout the reduction. Do not add
`--output` here: using stdout makes it easy to see whether a failed conversion
emitted anything. Record stdout, stderr, and exit status each time.

The observed result is exit **2**, empty stdout, and this stderr line:

```text
junit2context: repro.xml: report declares failures/errors but contains no extractable testcase failure/error outcomes
```

This is an existing input-completeness check, not a newly discovered parser bug:
the report claims a failed test but has no `<failure>` or `<error>` outcome to
extract. It is a useful diagnostic example because a careless reduction can
remove the very counter that triggers it.

## Remove one thing, then rerun

1. Delete the entire `unrelated` suite. Rerun the command; the same diagnostic
   remains. Remove its contribution to the aggregate `tests` count as well.
2. Remove the outer `testsuites` wrapper, keeping the `suspect` suite as the root
   and retaining `xmlns` on that root. Rerun; the same result remains. For a bug
   involving inherited suite names or nested traversal, this step might change
   the result, in which case restore the wrapper.
3. Remove the remaining testcase, its names, and the nonessential `tests`
   attribute. Rerun; the same result remains. Keep `failures="1"`.
4. Try removing the namespace declaration. The result is still unchanged in
   this example, so the namespace is not essential here. If a real issue depends
   on namespaces, retain the exact namespace URI and prefix relationships.

The final synthetic reproduction is:

```xml
<testsuite failures="1"/>
```

It produces the same stderr and exit status under the same filename and command.
As a control, change it to `<testsuite failures="0"/>`: conversion exits 0 and
prints version 1 JSON with an empty `failures` list and all three counts zero.
Alternatively, restore the failing counter and provide an actual outcome:

```xml
<testsuite failures="1">
  <testcase name="synthetic_failure">
    <failure message="invented assertion">expected red, got blue</failure>
  </testcase>
</testsuite>
```

This converts successfully with one failure record (default exit 0; the separate
`--fail-on-failures` option would return 1). The parser does not generally verify
all suite counter arithmetic; these controls only demonstrate its check for
claimed failures/errors without any extractable outcomes.

## Preserve what makes your case fail

For a different problem, start from its actual expected/observed difference,
then remove unrelated testcases, captured `system-out`/`system-err`, and
properties one at a time. Retest after every edit. Restore the last edit whenever
the symptom changes. A parse-error report must keep the malformed structure that
causes that error; making the XML well-formed would erase the reproduction.

Keep relevant `<failure>` and `<error>` elements, message attributes, text/CDATA,
entity escaping, namespaces, nesting, and counters until you have tested that
each is irrelevant. Preserve multiple records when investigating ordering,
deduplication, or class identity; one record cannot demonstrate those problems.
Keep the same CLI limits when reducing an excerpt or size-limit issue. Do not
change the input and converter version at the same time.

## Sanitize before sharing

Replace private content locally with invented data, then rerun once more:

- Paths: remove usernames, home directories, internal checkout names, and hosts.
- Identifiers: replace customer, repository, suite, class, and test names.
- Source excerpts: replace private code and assertions with a minimal invented
  equivalent while preserving whitespace or characters needed by the symptom.
- URLs: use `example.invalid` and remove real query values, internal hosts, and
  fragments. Never follow URLs found in the report as part of reduction.
- Credentials: remove real values entirely. For a redaction question, use an
  obvious synthetic assignment such as `API_KEY=demo_not_a_real_secret` and
  retain only the syntax necessary to reproduce the issue.
- Captured output and properties: inspect them too, even if the brief omits them.
  Check the final XML, command, paths in diagnostics, and attachments manually.

Do not publish the private original to “prove” the reduction. Synthetic data
should be labeled as such. A passing synthetic reproduction does not establish
compatibility with a real runner or all of its versions.

## Include this in the issue

Use the [bug report form](https://github.com/HafidIdrissi/junit2context/issues/new?template=bug_report.yml)
and provide:

- The final synthetic XML in a fenced code block.
- The exact command and `junit2context --version`, Python version, and OS.
- Expected behavior, actual stdout/stderr, and exit status; distinguish a
  conversion error (2) from a successfully converted failing test (optionally 1).
- Which reduction/control changed the result, if relevant.
- Runner/version only when known, clearly separating the original observation
  from this invented reproduction. Do not call this example a runner fixture.

If you cannot reproduce the original symptom with shareable synthetic data, say
so and describe the limitation. Do not substitute a different error and claim
that it proves the original issue.
