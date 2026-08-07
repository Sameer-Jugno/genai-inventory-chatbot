"""
Generic vendor HTML fetcher (SOW secondary path).

Fetches page text only — no site-specific selectors, proxies, or retries.
Output is written under uploads/ so the existing S3 → Lambda pipeline ingests it.
"""

from __future__ import annotations

import argparse
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


class _VisibleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        return "\n".join(self._chunks)


def fetch_html(url: str, *, timeout: int = 30) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {url}")

    request = Request(
        url,
        headers={"User-Agent": "inventory-planner-scraper/1.0 (training-poc)"},
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def html_to_text(html: str) -> str:
    parser = _VisibleTextExtractor()
    parser.feed(html)
    text = parser.text()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def vendor_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = host.removeprefix("www.")
    return host.split(".")[0] or "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generic HTML fetch for inventory ingest")
    parser.add_argument("url", help="Vendor page URL")
    parser.add_argument(
        "--out-dir",
        default="scraper/out",
        help="Directory for HTML/text artifacts (upload these under s3://…/uploads/{vendor}/)",
    )
    args = parser.parse_args()

    html = fetch_html(args.url)
    text = html_to_text(html)
    vendor = vendor_from_url(args.url)

    out_dir = Path(args.out_dir) / vendor
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", urlparse(args.url).path.strip("/") or "index")

    html_path = out_dir / f"{stem}.html"
    text_path = out_dir / f"{stem}.txt"
    html_path.write_text(html, encoding="utf-8")
    text_path.write_text(text, encoding="utf-8")

    logger.info("wrote %s (%s chars html)", html_path, len(html))
    logger.info("wrote %s (%s chars text)", text_path, len(text))
    logger.info(
        "Next: aws s3 cp %s s3://$DATA_BUCKET/uploads/%s/",
        html_path,
        vendor,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
