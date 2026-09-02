from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .models import FeedConfig


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class AppConfig:
    feeds: tuple[FeedConfig, ...]
    rules: dict[str, Any]
    sources_version: int
    rules_version: int

    def feed(self, feed_id: str) -> FeedConfig:
        for item in self.feeds:
            if item.id == feed_id:
                return item
        raise ConfigError(f"未知feed_id: {feed_id}")

    def enabled_feeds(self) -> tuple[FeedConfig, ...]:
        return tuple(item for item in self.feeds if item.enabled)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"缺少配置文件: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"JSON配置错误 {path}:{exc.lineno}:{exc.colno}: {exc.msg}") from exc


def host_allowed(host: str, allowed_domains: tuple[str, ...] | list[str]) -> bool:
    value = host.lower().rstrip(".")
    return any(value == domain.lower() or value.endswith("." + domain.lower()) for domain in allowed_domains)


def load_config(config_dir: str | Path) -> AppConfig:
    root = Path(config_dir)
    sources_doc = _read_json(root / "sources.json")
    rules_doc = _read_json(root / "rules.json")
    feeds: list[FeedConfig] = []
    seen_sources: set[str] = set()
    seen_feeds: set[str] = set()

    for source in sources_doc.get("sources", []):
        source_id = str(source.get("id", "")).strip()
        if not source_id or source_id in seen_sources:
            raise ConfigError(f"source id为空或重复: {source_id!r}")
        seen_sources.add(source_id)
        domains = tuple(str(x).lower().strip() for x in source.get("allowed_domains", []) if str(x).strip())
        if not domains:
            raise ConfigError(f"{source_id}未配置allowed_domains")

        for feed in source.get("feeds", []):
            feed_id = str(feed.get("id", "")).strip()
            if not feed_id or feed_id in seen_feeds:
                raise ConfigError(f"feed id为空或重复: {feed_id!r}")
            seen_feeds.add(feed_id)
            list_url = str(feed.get("list_url", "")).strip()
            parsed = urlsplit(list_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ConfigError(f"{feed_id}的list_url无效")
            if not host_allowed(parsed.hostname, domains):
                raise ConfigError(f"{feed_id}的list_url不在allowed_domains内")
            interval = int(feed.get("interval_min", 30))
            if interval < 15:
                raise ConfigError(f"{feed_id}轮询间隔不得低于15分钟")
            feeds.append(
                FeedConfig(
                    id=feed_id,
                    source_id=source_id,
                    source_name=str(source["name"]),
                    region=str(source["region"]),
                    list_url=list_url,
                    parser_type=str(feed.get("parser_type", "generic_link_date")),
                    interval_min=interval,
                    enabled=bool(source.get("enabled", True) and feed.get("enabled", True)),
                    encoding=str(feed.get("encoding", "auto")),
                    min_items=max(1, int(feed.get("min_items", 1))),
                    recruitment_context=bool(feed.get("recruitment_context", False)),
                    allowed_domains=domains,
                    link_include_patterns=tuple(feed.get("link_include_patterns", [])),
                    link_exclude_patterns=tuple(feed.get("link_exclude_patterns", [])),
                    verification_status=str(feed.get("verification_status", "pending")),
                )
            )

    if not feeds:
        raise ConfigError("未配置任何栏目")
    required_rule_lists = (
        "whitelist",
        "selection_exclude",
        "teacher_exclude",
        "process_terms",
        "major_change_terms",
    )
    for key in required_rule_lists:
        if not isinstance(rules_doc.get(key), list) or not rules_doc[key]:
            raise ConfigError(f"rules.json缺少非空数组: {key}")

    return AppConfig(
        feeds=tuple(feeds),
        rules=rules_doc,
        sources_version=int(sources_doc.get("version", 1)),
        rules_version=int(rules_doc.get("version", 1)),
    )
