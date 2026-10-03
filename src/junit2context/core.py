"""Parse JUnit failures and render bounded, local-only debugging context.

The parser deliberately ignores captured output, report properties, and passing
tests. Redaction is a best-effort convenience, not a secret-detection guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import html
from pathlib import Path
import re
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class Failure:
    """One JUnit failure or error; ``source`` identifies its first report."""

    source: str
    suite: str
    name: str
    kind: str
    message: str
    details: str
    classname: str = ""


class ReportError(ValueError):
    """A report could not be read safely as supported JUnit XML."""


_ANSI = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b\[[0-?]*[ -/]*[@-~]"
    r"|\x1b[ -/]*[@-Z\\-_]"
)
_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")
_PROVIDER_TOKEN = re.compile(
    r"\b(?:"
    r"sk-(?:proj-|ant-api\d{2}-)?[A-Za-z0-9_-]{16,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|(?:AKIA|ASIA)[A-Z0-9]{16}"
    r")\b"
)
_BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/-]+=*")
_URL_CREDENTIALS = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@")
_ASSIGNMENT = re.compile(
    r"(?i)(?P<prefix>[\"']?"
    r"[A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY)"
    r"[A-Z0-9_]*[\"']?\s*[:=]\s*)"
    r"(?P<value>\[REDACTED\]|\"(?:\\.|[^\"\\\r\n])*\"|'(?:\\.|[^'\\\r\n])*'|[^\s,;}\]]+)"
)
_XML_ENCODING = re.compile(
    r"\A<\?xml\s[^?]*\bencoding\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE
)
_UNSAFE_XML = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


def redact(text: str) -> str:
    """Remove terminal controls and redact common explicit credential patterns.

    This does not identify every secret. Review output before sharing it.
    """

    text = _ANSI.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROLS.sub("", text)
    text = _PROVIDER_TOKEN.sub("[REDACTED]", text)
    text = _BEARER.sub(r"\1[REDACTED]", text)
    text = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", text)

    def replace_assignment(match: re.Match[str]) -> str:
        value = match.group("value")
        quote = value[0] if value[:1] in ("'", '"') else ""
        return match.group("prefix") + quote + "[REDACTED]" + quote

    return _ASSIGNMENT.sub(replace_assignment, text)


def sanitize_failure(failure: Failure) -> Failure:
    """Return a redacted copy suitable for JSON or other output formats."""

    return replace(
        failure,
        source=redact(failure.source),
        suite=redact(failure.suite),
        name=redact(failure.name),
        kind=redact(failure.kind),
        message=redact(failure.message),
        details=redact(failure.details),
        classname=redact(failure.classname),
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_report(path: Path, max_file_bytes: int) -> ET.Element:
    source = redact(str(path))
    try:
        if not path.is_file():
            raise ReportError(f"{source}: expected a regular report file")
        if path.stat().st_size > max_file_bytes:
            raise ReportError(f"{source}: report exceeds {max_file_bytes} bytes")
        # The bounded read also covers a file that grows after stat().
        with path.open("rb") as stream:
            raw = stream.read(max_file_bytes + 1)
    except OSError as exc:
        raise ReportError(f"{source}: cannot read report ({redact(str(exc))})") from exc
    if len(raw) > max_file_bytes:
        raise ReportError(f"{source}: report exceeds {max_file_bytes} bytes")
    try:
        document = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ReportError(f"{source}: reports must use UTF-8 encoding") from exc
    if "\x00" in document:
        raise ReportError(f"{source}: binary or non-UTF-8 XML is unsupported")
    encoding = _XML_ENCODING.search(document)
    if encoding and encoding.group(1).lower().replace("_", "-") not in {"utf-8", "utf8"}:
        raise ReportError(f"{source}: reports must declare UTF-8 encoding")
    if _UNSAFE_XML.search(document):
        raise ReportError(f"{source}: DTD and entity declarations are not allowed")
    try:
        root = ET.fromstring(document)
    except (ET.ParseError, ValueError) as exc:
        # Parser diagnostics contain positions, not raw report contents.
        raise ReportError(f"{source}: invalid XML ({redact(str(exc))})") from exc
    if _local_name(root.tag) not in {"testsuite", "testsuites"}:
        raise ReportError(f"{source}: expected a JUnit testsuite or testsuites root")
    return root


def parse_reports(paths: list[Path], max_file_bytes: int = 10_000_000) -> list[Failure]:
    """Read UTF-8 JUnit reports, preserving order and deduplicating failures.

    Namespace prefixes are ignored. A nested suite supplies its own name, or
    inherits its parent's name when unnamed. The same failure appearing in
    multiple reports keeps the first source. Class names remain part of test
    identity even when the suite is named. No captured stdout or properties
    are included. Reports declaring failures but containing no extractable
    failure/error outcomes are rejected; aggregate counters are not otherwise
    reconciled. Any invalid input raises ``ReportError`` instead of returning a
    misleading partial result.
    """

    if max_file_bytes < 1:
        raise ValueError("max_file_bytes must be positive")
    failures: list[Failure] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()
    for input_path in paths:
        path = Path(input_path)
        root = _read_report(path, max_file_bytes)
        declared_failures = False
        report_outcomes = 0
        # An explicit stack avoids recursion depth errors on deeply nested XML.
        stack = [(root, "")]
        while stack:
            element, suite = stack.pop()
            tag = _local_name(element.tag)
            if tag in {"testsuite", "testsuites"}:
                declared_failures = declared_failures or any(
                    re.fullmatch(r"\s*\+?0*[1-9][0-9]*\s*", element.get(attribute, ""))
                    for attribute in ("failures", "errors")
                )
            if tag == "testsuite":
                suite = element.get("name") or suite
            if tag == "testcase":
                for child in element:
                    kind = _local_name(child.tag)
                    if kind not in {"failure", "error"}:
                        continue
                    report_outcomes += 1
                    failure = Failure(
                        source=str(path),
                        suite=suite or element.get("classname") or "(unnamed suite)",
                        name=element.get("name") or "(unnamed test)",
                        kind=kind,
                        message=child.get("message") or child.get("type") or "",
                        details="".join(child.itertext()).strip(),
                        classname=element.get("classname") or "",
                    )
                    key = (failure.suite, failure.classname, failure.name,
                           failure.kind, failure.message, failure.details)
                    if key not in seen:
                        seen.add(key)
                        failures.append(failure)
                continue
            # Only JUnit structural elements participate in discovery, so a
            # testcase embedded in captured output or properties is ignored.
            children = [
                child for child in element
                if _local_name(child.tag) in {"testsuites", "testsuite", "testcase"}
            ]
            stack.extend((child, suite) for child in reversed(children))
        if declared_failures and not report_outcomes:
            raise ReportError(
                f"{redact(str(path))}: report declares failures/errors but contains no "
                "extractable testcase failure/error outcomes"
            )
    return failures


def _inline(text: str) -> str:
    text = html.escape(" ".join(text.split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|~-])", r"\\\1", text)


def _failure_block(failure: Failure, index: int) -> str:
    lines = [
        f"### {index}. {_inline(failure.name)}",
        "",
        f"- Suite: {_inline(failure.suite)}",
    ]
    if failure.classname:
        lines.append(f"- Class: {_inline(failure.classname)}")
    lines.extend([f"- Kind: {_inline(failure.kind)}", f"- Source: {_inline(failure.source)}"])
    if failure.message:
        lines.extend(["", f"Message: {_inline(failure.message)}"])
    if failure.details:
        # A detail containing Markdown fences cannot escape its code block.
        longest_run = max((len(run) for run in re.findall(r"`+", failure.details)), default=0)
        fence = "`" * max(3, longest_run + 1)
        lines.extend(["", f"{fence}text", failure.details, fence])
    return "\n".join(lines)


def render_markdown(failures: list[Failure], max_chars: int = 12_000) -> str:
    """Render complete failure blocks within a Unicode character budget.

    Only an ordered prefix of whole failure blocks is included. Omission is
    explicit, and both the header and omission notice count toward the budget.
    The minimum budget is 128 characters. This is not a tokenizer estimate.
    """

    return _render_markdown(failures, max_chars, sanitize=True)


def _render_markdown(failures: list[Failure], max_chars: int = 12_000,
                     *, sanitize: bool = False) -> str:
    """Render already sanitized CLI excerpts, or sanitize public API inputs."""

    if max_chars < 128:
        raise ValueError("max_chars must be at least 128")
    if not failures:
        return "# Test failure context\n\nNo failures or errors found.\n"
    count = len(failures)
    header = f"# Test failure context\n\n{count} unique failure(s)."

    def assemble(blocks: list[str], omitted: int) -> str:
        parts = [header, *blocks]
        if omitted:
            parts.append(f"> {omitted} failure(s) omitted: {max_chars}-character limit.")
        return "\n\n".join(parts) + "\n"

    blocks: list[str] = []
    for index, failure in enumerate(failures, start=1):
        if sanitize:
            failure = sanitize_failure(failure)
        block = _failure_block(failure, index)
        candidate = assemble([*blocks, block], count - index)
        if len(candidate) > max_chars:
            break
        blocks.append(block)
    return assemble(blocks, count - len(blocks))
