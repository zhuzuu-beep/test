from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_config
from .fetcher import fetch
from .parser import decode_html, parse_candidates


def run_phase0(
    config_dir: str | Path,
    db_path: str | Path,
    log_dir: str | Path,
    network: bool = False,
) -> dict[str, object]:
    config = load_config(config_dir)
    database_parent = Path(db_path).parent
    log_path = Path(log_dir)
    database_parent.mkdir(parents=True, exist_ok=True)
    log_path.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, object]] = []

    checks.append({"name": "python_version", "ok": sys.version_info >= (3, 10), "value": platform.python_version()})
    try:
        shanghai = ZoneInfo("Asia/Shanghai")
        timezone_value = datetime.now(shanghai).isoformat(timespec="seconds")
        checks.append({"name": "timezone", "ok": True, "value": timezone_value})
    except Exception as exc:
        checks.append({"name": "timezone", "ok": False, "value": str(exc)})
    checks.append({"name": "db_directory_writable", "ok": os.access(database_parent, os.W_OK), "value": str(database_parent)})
    checks.append({"name": "log_directory_writable", "ok": os.access(log_path, os.W_OK), "value": str(log_path)})
    checks.append({"name": "systemctl_available", "ok": shutil.which("systemctl") is not None, "value": shutil.which("systemctl") or "not_found"})
    checks.append({"name": "feishu_webhook_configured", "ok": bool(os.getenv("FEISHU_WEBHOOK_URL")), "value": "configured" if os.getenv("FEISHU_WEBHOOK_URL") else "missing"})

    feeds: list[dict[str, object]] = []
    for feed in config.feeds:
        item: dict[str, object] = {
            "feed_id": feed.id,
            "source": feed.source_name,
            "enabled": feed.enabled,
            "verification_status": feed.verification_status,
            "list_url": feed.list_url,
            "network_test": "not_requested",
        }
        if network and feed.enabled:
            try:
                result = fetch(feed)
                candidates = parse_candidates(decode_html(result.body, result.content_type, feed.encoding), feed)
                item.update({"network_test": "success", "http_status": result.status, "parsed_items": len(candidates)})
            except Exception as exc:
                item.update({"network_test": "failed", "error_type": type(exc).__name__, "error": str(exc)[:300]})
        feeds.append(item)

    return {
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "environment": "local_check_only",
        "checks": checks,
        "feeds": feeds,
        "ready_for_phase1_offline": all(bool(x["ok"]) for x in checks[:4]),
        "production_blockers": [
            "尚未取得生产主机及既有monitor-xicheng.py部署信息",
            "飞书Webhook须在生产环境以环境变量配置",
            "pending状态栏目须在生产网络完成列表页和解析器踩点后方可启用",
        ],
    }


def write_report(report: dict[str, object], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
