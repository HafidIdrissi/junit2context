"""Command-line interface. Reports are data; no commands or network are run."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import sys
import tempfile

from . import __version__
from .core import ReportError, parse_reports, redact, render_markdown, sanitize_failure


def _positive(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a positive integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Turn JUnit XML failures into local, redacted Markdown or JSON context."
    )
    parser.add_argument("reports", nargs="+", type=Path, help="UTF-8 JUnit XML report files")
    parser.add_argument("--version", action="version", version=f"junit2context {__version__}")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--max-chars", type=_positive, default=None,
                        help="Markdown character budget, including notices (default: 12000; minimum: 128)")
    parser.add_argument("--max-detail-chars", type=_positive, default=2000,
                        help="traceback characters to retain per failure, from head and tail (default: 2000)")
    parser.add_argument("--max-message-chars", type=_positive, default=500,
                        help="message characters to retain per failure, from head and tail (default: 500)")
    parser.add_argument("--max-file-bytes", type=_positive, default=10_000_000,
                        help="maximum size of each input report (default: 10000000)")
    parser.add_argument("-o", "--output", type=Path,
                        help="write UTF-8 output atomically to this file (replaces existing output)")
    parser.add_argument("--fail-on-failures", action="store_true",
                        help="exit 1 when test failures exist; invalid inputs always exit 2")
    return parser


def _write_output(path: Path, content: str) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _excerpt(value: str, limit: int, label: str) -> str:
    if len(value) <= limit:
        return value
    head = (limit + 1) // 2
    tail = limit // 2
    notice = f"\n[... {len(value) - limit} {label} characters omitted ...]\n"
    return value[:head] + notice + (value[-tail:] if tail else "")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.format == "json" and args.max_chars is not None:
        parser.error("--max-chars applies to Markdown only; JSON always contains every unique failure")
    if args.max_chars is not None and args.max_chars < 128:
        parser.error("--max-chars must be at least 128")
    try:
        if args.output is not None and any(args.output.resolve() == p.resolve() for p in args.reports):
            raise ReportError("output must not overwrite an input report")
        failures = [sanitize_failure(f) for f in parse_reports(args.reports, args.max_file_bytes)]
        limited = []
        truncated = 0
        truncated_messages = 0
        for failure in failures:
            if len(failure.details) > args.max_detail_chars:
                truncated += 1
            if len(failure.message) > args.max_message_chars:
                truncated_messages += 1
            failure = replace(failure,
                              details=_excerpt(failure.details, args.max_detail_chars, "detail"),
                              message=_excerpt(failure.message, args.max_message_chars, "message"))
            limited.append(failure)
        if args.format == "json":
            content = json.dumps({
                "schema_version": 1,
                "failure_count": len(limited),
                "truncated_details": truncated,
                "truncated_messages": truncated_messages,
                "failures": [asdict(f) for f in limited],
            }, ensure_ascii=False, indent=2) + "\n"
        else:
            content = render_markdown(limited, max_chars=args.max_chars or 12_000)
        if args.output is not None:
            _write_output(args.output, content)
        else:
            sys.stdout.write(content)
    except (ReportError, OSError, ValueError) as exc:
        print(f"junit2context: {redact(str(exc))}", file=sys.stderr)
        return 2
    return 1 if args.fail_on_failures and failures else 0
