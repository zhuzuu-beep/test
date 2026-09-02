from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from .database import Database


class DeliveryError(RuntimeError):
    pass


def feishu_sign(timestamp: int, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _safe_text(value: object, limit: int = 300) -> str:
    text = str(value or "").replace("<", "＜").replace(">", "＞")
    return text[:limit]


def build_card(items: list[dict[str, object]], title: str = "河南招聘公告监控") -> dict[str, Any]:
    elements: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        sources = item.get("sources") or []
        source = sources[0] if isinstance(sources, list) and sources else {}
        assert isinstance(source, dict)
        category = _safe_text(item.get("category"), 20)
        region = _safe_text(item.get("region"), 20)
        raw_title = _safe_text(source.get("raw_title") or item.get("canonical_title"), 240)
        source_names = "、".join(_safe_text(x.get("source_name"), 40) for x in sources if isinstance(x, dict))
        publish_date = _safe_text(source.get("publish_date") or "日期未标注", 20)
        url = str(source.get("url") or "")
        tags = [f"【{category}·{region}】"]
        fresh = str(item.get("fresh_grad_scope") or "")
        if fresh in {"明确面向", "部分包含"}:
            tags.append(f"【应届生：{fresh}】")
        if item.get("change_link_status") == "未关联原事项":
            tags.append("【重大变更·未关联原事项】")
        content = (
            f"**{''.join(tags)}**\n"
            f"{raw_title}\n"
            f"来源：{source_names or '来源未标注'}　发布日期：{publish_date}\n"
            f"[查看原文]({url})"
        )
        elements.append({"tag": "markdown", "content": content})
        if index != len(items) - 1:
            elements.append({"tag": "hr"})
    return {
        "msg_type": "interactive",
        "card": {
            "header": {"template": "blue", "title": {"tag": "plain_text", "content": title}},
            "elements": elements,
        },
    }


def build_health_card(snapshot: dict[str, int]) -> dict[str, Any]:
    failed = snapshot["failed_feeds"]
    status_text = "今日监控运行正常" if failed == 0 else "今日监控存在抓取失败，请检查渠道状态"
    content = (
        f"{status_text}\n"
        f"启用栏目：{snapshot['enabled_feeds']}\n"
        f"成功栏目：{snapshot['successful_feeds']}\n"
        f"失败栏目：{failed}\n"
        f"新增公告：{snapshot['new_announcements']}"
    )
    color = "green" if failed == 0 else "orange"
    return {
        "msg_type": "interactive",
        "card": {
            "header": {"template": color, "title": {"tag": "plain_text", "content": "招聘监控每日运行回执"}},
            "elements": [{"tag": "markdown", "content": content}],
        },
    }


class FeishuWebhookSender:
    def __init__(self, webhook_url: str, secret: str | None = None):
        parsed = urlsplit(webhook_url)
        if parsed.scheme != "https" or parsed.hostname not in {"open.feishu.cn", "open.larksuite.com"}:
            raise DeliveryError("Webhook必须使用飞书官方HTTPS域名")
        self.webhook_url = webhook_url
        self.secret = secret or ""

    def send(self, payload: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
        body = dict(payload)
        if self.secret:
            timestamp = int(time.time())
            body["timestamp"] = timestamp
            body["sign"] = feishu_sign(timestamp, self.secret)
        request = urllib.request.Request(
            self.webhook_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise DeliveryError(str(exc)) from exc
        code = result.get("code", result.get("StatusCode", 0))
        if code not in (0, None):
            raise DeliveryError(_safe_text(result.get("msg") or result.get("StatusMessage") or result, 500))
        return result


def deliver_pending(
    database: Database,
    webhook_url: str | None,
    secret: str | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    while True:
        items = database.pending_deliveries(limit=10)
        if not items:
            break
        payload = build_card(items)
        payloads.append(payload)
        delivery_ids = [int(item["delivery_id"]) for item in items]
        if dry_run:
            break
        if not webhook_url:
            raise DeliveryError("未配置FEISHU_WEBHOOK_URL")
        try:
            FeishuWebhookSender(webhook_url, secret).send(payload)
        except DeliveryError as exc:
            database.mark_deliveries_failed(delivery_ids, str(exc))
            raise
        database.mark_deliveries_sent(delivery_ids)
    return payloads
