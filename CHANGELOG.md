# Changelog

## 0.1.0

Initial implementation:

- Convert one or more UTF-8 JUnit XML reports into Markdown or JSON.
- Extract failures and errors from nested and namespaced suites.
- Deduplicate exact failure records across input files.
- Preserve class identity when distinct classes contain identically named tests.
- Apply heuristic redaction to report fields.
- Bound input file size and truncate long failure messages and details with explicit notices, preserving both the beginning and end.
- Reject incomplete reports that claim failures or errors without corresponding records.
- Budget Markdown output using complete failure items and explicit omission notices.
- Support atomic file output and an optional failure exit status.
- Include representative pytest and Vitest reports, tests, and contributor documentation.
