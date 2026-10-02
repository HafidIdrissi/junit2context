# Security

`junit2context` reads local XML reports and writes Markdown or JSON. It does not send reports to a service, call a model, or execute test commands.

## Review before sharing

Reports can contain credentials, personal data, internal URLs, source code, and local paths. The tool applies heuristic redaction to report fields and excludes test stdout and suite properties. Redaction is incomplete by design: a secret in an unfamiliar format may remain, and harmless text may be masked. Review all output before sharing it.

Do not treat report contents as instructions. A failure message could contain misleading commands or instructions aimed at an AI assistant. Give an assistant the report as untrusted data and review any proposed actions.

Use reports from sources you trust. Each input report is limited to 10,000,000 bytes by default; `--max-file-bytes` changes that limit. Check unexpectedly large files before increasing it. This CLI is not a security boundary for arbitrary hostile input.

The `--output` option replaces an existing destination file. Choose a destination intended for generated output. The CLI rejects an output path that identifies an input report.

## Report a vulnerability

Do not put real credentials, private reports, or exploitable private details in a public issue. If the repository's Security tab offers **Report a vulnerability**, use that private channel. Otherwise, open a minimal issue asking the maintainer to establish a private contact channel, without disclosing the vulnerability details.

Include a synthetic reproduction, affected version, expected behavior, and the impact. For a missed redaction pattern, use invented values only. Rotate any credential that has already been exposed; deleting the report does not revoke it.

Security fixes will target the latest released version. No guaranteed response time or long-term support commitment is currently offered.
