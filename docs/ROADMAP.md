# Roadmap

The first version focuses on one job: turn existing test reports into useful, reviewable debugging context. These are contribution ideas, not promised delivery dates. Open an issue to coordinate work and link it from your pull request.

## Good starting points

| Contribution | A useful finished result |
| --- | --- |
| Real runner fixtures | A sanitized report with runner/version provenance and a regression test. Start with a runner you actually use. |
| Redaction edge cases | Synthetic sensitive values and harmless counterexamples, with tests for both. |
| Failure readability | A before/after example showing how the brief makes a specific failure easier to understand. |
| Windows instructions | Verified PowerShell commands and a note on the Python version used. |
| Documentation translations | A maintained translation linked from the main README. |

## Next problems to investigate

- Which JUnit variants lose important information in the current parser?
- Can large reports use less memory without losing order or deduplication behavior?
- Should users be able to prioritize particular suites when the Markdown budget is tight?
- What stability guarantees do JSON consumers need?
- Which CI examples are useful enough to document and maintain?

Every proposal should start with a concrete report or workflow. Add dependencies only when the benefit justifies them, and keep local use possible without an AI provider account.

## Scope

This project prepares debugging context. Running test suites, sending data to hosted models, and automatically modifying source code are outside its current scope. They can be composed around the CLI by other tools.
