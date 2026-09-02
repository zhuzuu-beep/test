from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FeedConfig:
    id: str
    source_id: str
    source_name: str
    region: str
    list_url: str
    parser_type: str
    interval_min: int
    enabled: bool
    encoding: str
    min_items: int
    recruitment_context: bool
    allowed_domains: tuple[str, ...]
    link_include_patterns: tuple[str, ...] = ()
    link_exclude_patterns: tuple[str, ...] = ()
    verification_status: str = "pending"


@dataclass(frozen=True)
class Candidate:
    source_id: str
    source_name: str
    feed_id: str
    region: str
    title: str
    url: str
    publish_date: str | None = None
    recruitment_context: bool = False


@dataclass(frozen=True)
class Classification:
    accepted: bool
    event_type: str
    category: str
    region: str
    fresh_grad_scope: str
    contains_education_posts: str
    push_policy: str
    change_link_status: str | None = None
    reason: str = ""
    matched_terms: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FetchResult:
    final_url: str
    status: int
    content_type: str
    body: bytes
    elapsed_ms: int


@dataclass(frozen=True)
class IngestResult:
    announcement_id: int
    created_announcement: bool
    created_source: bool
    created_delivery: bool


@dataclass
class RunSummary:
    feed_id: str
    status: str
    initialized_before: bool
    initialized_after: bool
    parsed: int = 0
    accepted: int = 0
    discarded: int = 0
    new_announcements: int = 0
    new_sources: int = 0
    deliveries_created: int = 0
    failure_count: int = 0
    error_type: str | None = None
    error_message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()
