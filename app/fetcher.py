from __future__ import annotations

import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .config import host_allowed
from .models import FeedConfig, FetchResult


USER_AGENT = "Mozilla/5.0 (compatible; HenanRecruitMonitor/0.1; official-public-information-monitor)"
VERIFY_MARKERS = ("验证码", "访问验证", "安全验证", "请输入验证码")


class FetchError(RuntimeError):
    pass


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_domains: tuple[str, ...]):
        super().__init__()
        self.allowed_domains = allowed_domains

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        host = urlsplit(newurl).hostname or ""
        if not host_allowed(host, self.allowed_domains):
            raise FetchError(f"重定向目标不在白名单内: {host}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(feed: FeedConfig, timeout: int = 15, retries: int = 2) -> FetchResult:
    opener = urllib.request.build_opener(SafeRedirectHandler(feed.allowed_domains))
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        started = time.monotonic()
        request = urllib.request.Request(
            feed.list_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                body = response.read(5 * 1024 * 1024 + 1)
                if len(body) > 5 * 1024 * 1024:
                    raise FetchError("列表页超过5MiB安全上限")
                content_type = response.headers.get("Content-Type", "")
                if "html" not in content_type.lower() and "text" not in content_type.lower():
                    raise FetchError(f"非预期Content-Type: {content_type}")
                sample = body[:20000].decode("utf-8", errors="ignore")
                if any(marker in sample for marker in VERIFY_MARKERS):
                    raise FetchError("返回访问验证页")
                return FetchResult(
                    final_url=response.geturl(),
                    status=int(getattr(response, "status", 200)),
                    content_type=content_type,
                    body=body,
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                )
        except (urllib.error.URLError, TimeoutError, OSError, FetchError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
    raise FetchError(str(last_error) if last_error else "未知抓取错误")
