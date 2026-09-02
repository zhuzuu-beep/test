PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER NOT NULL
);

INSERT INTO schema_meta(version)
SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_meta);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feeds (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    list_url TEXT NOT NULL,
    parser_type TEXT NOT NULL,
    interval_min INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    initialized_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_success_at TEXT,
    last_error_type TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id TEXT NOT NULL REFERENCES feeds(id),
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    http_status INTEGER,
    item_count INTEGER NOT NULL DEFAULT 0,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_source_runs_feed_started
ON source_runs(feed_id, started_at DESC);

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT NOT NULL UNIQUE,
    canonical_title TEXT NOT NULL,
    category TEXT NOT NULL,
    region TEXT NOT NULL,
    event_type TEXT NOT NULL,
    fresh_grad_scope TEXT NOT NULL,
    contains_education_posts TEXT NOT NULL,
    push_policy TEXT NOT NULL,
    change_link_status TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_announcements_event_seen
ON announcements(event_type, first_seen_at DESC);

CREATE TABLE IF NOT EXISTS announcement_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    announcement_id INTEGER NOT NULL REFERENCES announcements(id),
    source_id TEXT NOT NULL REFERENCES sources(id),
    feed_id TEXT NOT NULL REFERENCES feeds(id),
    source_name TEXT NOT NULL,
    raw_title TEXT NOT NULL,
    url TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    publish_date TEXT,
    discovered_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(source_id, feed_id, url_hash)
);

CREATE INDEX IF NOT EXISTS idx_announcement_sources_announcement
ON announcement_sources(announcement_id);

CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    announcement_id INTEGER NOT NULL REFERENCES announcements(id),
    destination TEXT NOT NULL,
    delivery_type TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    sent_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(announcement_id, destination, delivery_type)
);

CREATE INDEX IF NOT EXISTS idx_deliveries_pending
ON deliveries(status, available_at);

CREATE TABLE IF NOT EXISTS alert_states (
    alert_key TEXT PRIMARY KEY,
    failure_count INTEGER NOT NULL DEFAULT 0,
    first_failed_at TEXT,
    last_alerted_at TEXT,
    recovered_at TEXT,
    updated_at TEXT NOT NULL
);
