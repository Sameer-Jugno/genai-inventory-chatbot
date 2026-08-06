"""Small, dependency-free HTML to visible text parser for scraped catalogs."""

from __future__ import annotations

import re
from html.parser import HTMLParser


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._hidden_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth and data.strip():
            self._parts.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._parts)


def html_to_text(content: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(content)
    return re.sub(r"\n{3,}", "\n\n", parser.text()).strip()


def chunk_text(text: str, *, max_chars: int = 10_000) -> list[str]:
    """Split visible page text without silently dropping the tail."""
    if max_chars < 1_000:
        raise ValueError("max_chars must be at least 1000")
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    size = 0

    for paragraph in paragraphs:
        pieces = [
            paragraph[index : index + max_chars]
            for index in range(0, len(paragraph), max_chars)
        ]
        for piece in pieces:
            if current and size + len(piece) + 2 > max_chars:
                chunks.append("\n\n".join(current))
                current = []
                size = 0
            current.append(piece)
            size += len(piece) + 2

    if current:
        chunks.append("\n\n".join(current))
    return chunks
