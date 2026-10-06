"""Check the documented subset of repository-local documentation links offline."""

from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


def markdown_links(text: str):
    """Yield line numbers and destinations of single-line inline links/images."""
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            if (marker and marker[1][0] == fence[0]
                    and len(marker[1]) >= len(fence) and not marker[2].strip()):
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        if line.startswith(("    ", "\t")):
            continue
        # Remove same-line code spans before looking for link destinations.
        line = re.sub(r"(?<!`)(`+)(?!`)(.*?)(?<!`)\1(?!`)", " ", line)
        for match in re.finditer(r"\]\(([^)\n]*)(\)|$)", line):
            yield number, match[1], bool(match[2])


class HTMLLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in {"href", "src"} and value is not None:
                self.links.append((self.getpos()[0], value, True))


def check_document(document: Path, root: Path) -> tuple[list[str], int]:
    """Return diagnostics and the number of checked local file destinations."""
    label = document.relative_to(root).as_posix()
    try:
        text = document.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [f"{label}: cannot read document: {error}"], 0
    if document.suffix == ".html":
        parser = HTMLLinks()
        parser.feed(text)
        links = parser.links
    else:
        links = markdown_links(text)

    problems = []
    checked = 0
    for line, raw, closed in links:
        destination = raw.strip()
        if re.match(r"^<?(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)", destination):
            continue  # No scheme is opened, including file:, mailto: and data:.
        if document.suffix != ".html":
            if not closed or not destination:
                problems.append(f"{label}:{line}: unsupported link syntax: {raw!r}")
                continue
            if destination.startswith("<") and destination.endswith(">"):
                destination = destination[1:-1]
                if re.search(r"[()\\<>]", destination):
                    problems.append(f"{label}:{line}: unsupported link syntax: {raw!r}")
                    continue
            elif re.search(r"[\s()\\<>]", destination):
                problems.append(f"{label}:{line}: unsupported link syntax: {raw!r}")
                continue
        try:
            url = urlsplit(destination)
            if url.scheme or url.netloc:
                continue
            path = unquote(url.path, errors="strict")
        except (ValueError, UnicodeError) as error:
            problems.append(f"{label}:{line}: unsupported URL {raw!r}: {error}")
            continue
        if not path:
            continue  # Fragment/query-only links do not name another file.
        if "\x00" in path:
            problems.append(f"{label}:{line}: invalid or unreadable local target "
                            f"{raw!r}: NUL is not allowed in filenames")
            continue
        if path.startswith("/"):
            problems.append(f"{label}:{line}: unsupported absolute local path: {raw!r}")
            continue
        try:
            target = (document.parent / path).resolve()
            exists = target.is_file()
        except (OSError, ValueError) as error:
            problems.append(f"{label}:{line}: invalid or unreadable local target "
                            f"{raw!r}: {error}")
            continue
        if not target.is_relative_to(root.resolve()):
            problems.append(f"{label}:{line}: local target outside repository: {raw!r}")
            continue
        checked += 1
        if not exists:
            problems.append(f"{label}:{line}: missing local file: {raw!r} "
                            f"(resolved to {target.relative_to(root.resolve()).as_posix()})")
    return problems, checked


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    documents = sorted(root.glob("*.md")) + sorted((root / "docs").rglob("*.md"))
    documents.append(root / "docs/demo.html")
    problems = []
    checked = 0
    for document in documents:
        errors, count = check_document(document, root)
        problems.extend(errors)
        checked += count
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"Local documentation links: {checked} file targets checked "
          f"in {len(documents)} documents (anchors not validated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
