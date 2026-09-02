from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .config import host_allowed
from .models import Candidate, FeedConfig
from .normalize import collapse_space


DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?(?!\d)")
META_CHARSET_RE = re.compile(br"charset\s*=\s*['\"]?([a-zA-Z0-9._-]+)", re.I)


def _date(value: str) -> str | None:
    match = DATE_RE.search(value)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def decode_html(body: bytes, content_type: str = "", configured: str = "auto") -> str:
    candidates: list[str] = []
    if configured and configured.lower() != "auto":
        candidates.append(configured)
    header_match = re.search(r"charset=([a-zA-Z0-9._-]+)", content_type, re.I)
    if header_match:
        candidates.append(header_match.group(1))
    meta_match = META_CHARSET_RE.search(body[:4096])
    if meta_match:
        candidates.append(meta_match.group(1).decode("ascii", errors="ignore"))
    candidates.extend(["utf-8", "gb18030"])
    for encoding in dict.fromkeys(x.lower() for x in candidates if x):
        try:
            return body.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", errors="replace")


class _AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current: dict[str, object] | None = None
        self.records: list[dict[str, str]] = []
        self.last_record: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a" or self.current is not None:
            return
        mapping = {key.lower(): value or "" for key, value in attrs}
        self.current = {
            "href": mapping.get("href", ""),
            "title_attr": mapping.get("title", ""),
            "date_attr": mapping.get("data-date", "") or mapping.get("data-time", ""),
            "parts": [],
        }

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            parts = self.current["parts"]
            assert isinstance(parts, list)
            parts.append(data)
        elif self.last_record is not None and len(self.last_record["tail"]) < 120:
            self.last_record["tail"] += " " + data

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self.current is None:
            return
        parts = self.current["parts"]
        assert isinstance(parts, list)
        record = {
            "href": str(self.current["href"]),
            "title": collapse_space(" ".join(parts)) or collapse_space(str(self.current["title_attr"])),
            "date_attr": str(self.current["date_attr"]),
            "tail": "",
        }
        self.records.append(record)
        self.last_record = record
        self.current = None


def _matches_patterns(value: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, value, flags=re.I) for pattern in patterns)


def parse_candidates(html: str, feed: FeedConfig) -> list[Candidate]:
    if feed.parser_type != "generic_link_date":
        raise ValueError(f"尚未支持parser_type={feed.parser_type}")
    parser = _AnchorParser()
    parser.feed(html)
    result: list[Candidate] = []
    seen: set[str] = set()

    for record in parser.records:
        href = record["href"].strip()
        title = collapse_space(record["title"])
        if not href or len(title) < 4:
            continue
        url = urljoin(feed.list_url, href)
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            continue
        if not host_allowed(parts.hostname, feed.allowed_domains):
            continue
        if feed.link_include_patterns and not _matches_patterns(url, feed.link_include_patterns):
            continue
        if feed.link_exclude_patterns and _matches_patterns(url, feed.link_exclude_patterns):
            continue
        if url in seen:
            continue
        seen.add(url)
        publish_date = _date(" ".join((record["date_attr"], record["tail"], title)))
        title = DATE_RE.sub("", title).strip(" -_|，,")
        result.append(
            Candidate(
                source_id=feed.source_id,
                source_name=feed.source_name,
                feed_id=feed.id,
                region=feed.region,
                title=title,
                url=url,
                publish_date=publish_date,
                recruitment_context=feed.recruitment_context,
            )
        )
    return result
