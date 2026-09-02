from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "spm"}
CHANGE_WORDS = (
    "补充",
    "更正",
    "延期",
    "延长报名",
    "重新报名",
    "重新选报",
    "岗位调整",
    "核减",
    "核销",
    "取消",
    "恢复招聘",
    "考试时间调整",
)


def collapse_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u3000", " ")).strip()


def normalize_title(title: str) -> str:
    text = collapse_space(title)
    text = re.sub(r"^[·•\-—_\s]+", "", text)
    text = re.sub(r"[\s，,。；;：:！!？?（）()【】\[\]《》<>]+", "", text)
    return text.lower()


def core_title(title: str) -> str:
    text = normalize_title(title)
    for word in CHANGE_WORDS:
        text = text.replace(normalize_title(word), "")
    text = text.replace("公告", "").replace("通知", "")
    return text


def normalize_url(url: str, keep_params: tuple[str, ...] = ()) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    keep = set(keep_params)
    params = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in TRACKING_PARAMS and key not in keep:
            continue
        params.append((key, value))
    query = urlencode(sorted(params))
    return urlunsplit((scheme, netloc, path, query, ""))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def url_hash(url: str) -> str:
    return sha256_text(normalize_url(url))


def dedupe_key(title: str, event_type: str, publish_date: str | None, source_name: str) -> str:
    canonical = normalize_title(title)
    year = (publish_date or "")[:4]
    discriminator = source_name if len(canonical) < 16 else ""
    return sha256_text("|".join((event_type, canonical, year, discriminator)))
