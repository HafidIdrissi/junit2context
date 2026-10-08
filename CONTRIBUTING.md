# Contributing

Thanks for helping make test failures easier to understand. Small fixes, report fixtures, documentation, and questions about unexpected behavior are welcome.

## Set up

Use Python 3.10 or newer:

```bash
git clone https://github.com/HafidIdrissi/junit2context.git
cd junit2context
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

On Windows, use `python` and `.venv\Scripts\python.exe`; after the editable install, run `.venv\Scripts\python.exe -m unittest discover -s tests -v`.

The runtime uses only the Python standard library. You can also run the CLI directly without installing it:

```bash
PYTHONPATH=src python3 -m junit2context examples/pytest.xml
```

## Focused checks while developing

Run these commands from the repository root, with the editable environment from
the setup steps above. Use `.venv/bin/python` so installation and testing use the
same interpreter; on Windows, substitute `.venv\Scripts\python.exe`.

To run one test file, use discovery's filename pattern (`-p`):

```bash
.venv/bin/python -m unittest discover -s tests -p "test_core.py" -v
```

To select the report-related CLI tests, combine that pattern with the test-name
filter (`-k`):

```bash
.venv/bin/python -m unittest discover -s tests -p "test_cli.py" -k report -v
```

`-k report` matches names containing `report`, including
`CliTests.test_passing_report_exit`. Check the reported test names and
`Ran N tests` count: `Ran 0 tests` means the selection matched nothing, even if
unittest prints `OK`, and is not evidence that the intended behavior passed.

For a source checkout without an editable install, expose `src` to the same
Python 3.10+ interpreter. For example, on a POSIX shell:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p "test_core.py" -v
PYTHONPATH=src python3 -m unittest discover -s tests -p "test_cli.py" -k report -v
```

Focused checks help during iteration. Before a code pull request, run the full
suite with the editable environment:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Documentation-only edits do not require unrelated tests; verify any commands you
add or change.

## Installed wheel smoke test

From the repository root, use the development environment above to install the
build frontend and check the actual wheel:

```bash
.venv/bin/python -m pip install build
.venv/bin/python scripts/smoke_wheel.py
```

On Windows, substitute `.venv\Scripts\python.exe`. `build` and the backend in
`pyproject.toml` are build-only tooling; the runtime dependency list stays empty.
Building may download backend requirements. The subsequent wheel installation
uses `--no-deps --no-index` and the exact artifact path, without an editable install.

The script builds only a wheel into an empty temporary output directory, requires
exactly one wheel, and installs it into a fresh virtual environment. From an
unrelated temporary working directory, with `PYTHONPATH` and `PYTHONHOME` removed,
it checks installed package/CLI origins and distribution version, both entry
points' `--version`, and synthetic Markdown/JSON conversions through both entry
points. The report includes a failure, an error, a passing case, and a synthetic
token to verify useful output and redaction. Temporary environments and reports
are removed on exit. A failed check exits 1 and reports the command, working
directory, and captured output for subprocess failures.

CI runs this once in the **Installed wheel smoke** job. The standard-library test
suite also installs minimal synthetic wheels to ensure missing console or module
entry points fail the check; these fixtures do not replace the real build check.

## Generated demo artifacts

`scripts/build_demo.py` generates the offline demo (`docs/demo.html`) and sample
brief (`examples/brief.md`) from the bundled reports and current CLI. When changing
the parser, renderer, reports, or demo generator, regenerate and review both text
files before committing. From the repository root with Python 3.10 or newer:

```bash
python3 scripts/build_demo.py
git diff --exit-code -- docs/demo.html examples/brief.md
```

On Windows, use `python` in place of `python3`. The generator uses the source
checkout and standard library, so no package installation is needed. The diff
command prints any changes and exits nonzero until the regenerated files match
the index; review and include expected updates in your change.

CI runs the same check in one separate Ubuntu/Python 3.12 job, rather than
repeating generation in every test-matrix entry. It does not commit or push
updates. The separately maintained PNG screenshot is outside this text-artifact
check.

## Local documentation links

Check repository-local file targets offline, with Python 3.10 or newer:

```bash
python3 scripts/check_local_links.py
```

On Windows, use `python` in place of `python3`. CI runs this command once in the
documentation job. It uses only the standard library and never opens URLs.
The check covers root-level Markdown files, Markdown files recursively under
`docs/`, and `docs/demo.html`. Generated report content in `examples/` and runner
fixture documentation in `tests/` are outside this maintained-document check.

The supported Markdown subset is single-line inline links and images with a
bare destination (no whitespace, parentheses, or backslash escapes), or an
angle-bracket destination for filenames with spaces. For example:

```markdown
[guide](docs/ROADMAP.md)
![preview](docs/demo-preview.png)
[space in filename](<notes with spaces.md>)
[escaped filename](notes%20with%20spaces.md#section)
```

Paths resolve relative to the containing document. Percent escapes are decoded
after separating the query and fragment; queries and fragments are ignored, so
**anchor validation is deferred**. Fragment-only links and all URL schemes or
protocol-relative URLs are skipped, including `https:`, `mailto:` and `file:`.
Local destinations must name files inside the repository; absolute local paths
are unsupported. Errors identify the referring file, line, and destination.

Fenced and indented code lines and same-line backtick code spans are skipped.
This is a deliberately limited check, not a Markdown renderer: reference-style
links, autolinks, raw HTML in Markdown, and multiline links are outside the
supported subset. It scans `](...)` destinations without fully parsing link
labels; put literal syntax examples in code spans or fences. Use the inline form
above for maintained local links. Inline
destinations with titles or backslash escapes produce an **unsupported syntax**
diagnostic rather than a missing-file diagnostic; encode special filename
characters with percent escapes. For the HTML demo, `href` and `src` attributes
are checked using the standard-library HTML parser, including HTML entities;
links in JavaScript strings are not checked.

## Choose a contribution

For local release preparation and download verification, see the
[SHA-256 manifest guide](docs/RELEASE_CHECKSUMS.md). The standard-library helper
hashes only explicitly selected artifacts; it does not create or upload releases.

Check the [roadmap](docs/ROADMAP.md) for starting points. Before undertaking a large feature or adding a dependency, open an issue explaining the problem and an example of the desired output.

For a bug report, include the command, Python version, expected behavior, actual behavior, and a small synthetic XML example. Do not upload private CI reports or credentials. For security issues, follow [SECURITY.md](SECURITY.md).

## Add a runner fixture

JUnit XML differs across tools and versions. A useful compatibility contribution contains:

1. A small report generated by a named runner and version, or a clearly labeled synthetic reproduction.
2. The command or configuration needed to produce that report.
3. Sanitized test names, paths, failure messages, and output. Remove secrets, private source code, and identifying data.
4. A test asserting the user-visible behavior: preserved failures, useful context, deduplication, or safe output.

Keep fixture provenance clear. A passing synthetic fixture does not establish compatibility with every real report from that runner. Do not add a runtime-specific adapter unless a fixture demonstrates why the common JUnit parser cannot handle the case.

## Send a pull request

- Keep the change focused and explain the behavior it improves.
- Add a regression test for a bug or meaningful new behavior. Documentation-only edits do not need tests.
- Run the test suite and include the result in the pull request.
- Use synthetic secrets when testing redaction. Include harmless counterexamples when practical.
- Update documentation when a CLI option or output contract changes.

Preserve the project's defaults: local operation, no network calls, no model requirement, and no automatic test execution. Avoid suggesting that redaction can guarantee safe disclosure.

By submitting a contribution, you agree that it can be distributed under the project's [MIT license](LICENSE). Be respectful, discuss the work rather than the person, and make room for contributors with different experience levels.
