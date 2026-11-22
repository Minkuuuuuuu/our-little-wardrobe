"""One SQLite file: her pieces, the two slots, what happened to each piece, 祂's washes and uses, her 吐槽 under
his records, the counted things, showers, his picks, small events, and the tokens that make a wake count."""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- Her wardrobe: 祂 reads it, washes for her and may use pieces; only she changes what she is wearing.
CREATE TABLE IF NOT EXISTS wardrobe (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, code TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '', style TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'closet', place TEXT NOT NULL DEFAULT '', sneaked INTEGER NOT NULL DEFAULT 0,
    wash_id INTEGER, state_at REAL NOT NULL,
    tag_text TEXT NOT NULL DEFAULT '', tag_at REAL,
    created_at REAL NOT NULL, updated_at REAL NOT NULL, deleted_at REAL
);
CREATE TABLE IF NOT EXISTS wardrobe_slots (
    slot TEXT PRIMARY KEY, item_id INTEGER, special TEXT, set_at REAL
);
CREATE TABLE IF NOT EXISTS wardrobe_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL, from_state TEXT, to_state TEXT NOT NULL,
    by TEXT NOT NULL, reason TEXT NOT NULL, place TEXT NOT NULL DEFAULT '', at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS wardrobe_washes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, started_at REAL NOT NULL, due_at REAL NOT NULL, done_at REAL,
    outlet TEXT NOT NULL, item_ids TEXT NOT NULL, names TEXT NOT NULL,
    start_line TEXT NOT NULL, done_line TEXT NOT NULL, start_default INTEGER NOT NULL DEFAULT 0,
    done_default INTEGER NOT NULL DEFAULT 0, use_id INTEGER, told_at REAL, reserved_until REAL
);
CREATE TABLE IF NOT EXISTS wardrobe_uses (
    id INTEGER PRIMARY KEY AUTOINCREMENT, used_at REAL NOT NULL, day TEXT NOT NULL, outlet TEXT NOT NULL,
    journal TEXT NOT NULL, chat_line TEXT NOT NULL, chat_line_default INTEGER NOT NULL DEFAULT 0,
    after TEXT NOT NULL, place TEXT NOT NULL DEFAULT '', after_line TEXT, after_line_default INTEGER NOT NULL DEFAULT 0,
    wash_id INTEGER, deleted_at REAL
);
CREATE TABLE IF NOT EXISTS wardrobe_use_items (
    use_id INTEGER NOT NULL, item_id INTEGER NOT NULL, name TEXT NOT NULL, PRIMARY KEY(use_id, item_id)
);
-- Her 吐槽 under one of 祂's records (target='use') and his replies (author='him', reply_to).
CREATE TABLE IF NOT EXISTS life_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, target TEXT NOT NULL, target_id INTEGER NOT NULL, text TEXT NOT NULL,
    created_at REAL NOT NULL, updated_at REAL NOT NULL, deleted_at REAL, told_at REAL, reserved_until REAL,
    author TEXT, reply_to INTEGER, outlet TEXT
);
CREATE TABLE IF NOT EXISTS life_tokens (
    token TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL, sent_at REAL
);
-- Her period things are counted, not hung (pad / night_pants); every change she marks resets 祂's reminder.
CREATE TABLE IF NOT EXISTS wardrobe_stock (
    kind TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0, updated_at REAL
);
CREATE TABLE IF NOT EXISTS wardrobe_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, by TEXT NOT NULL, at REAL NOT NULL
);
-- She said she is going to shower: half an hour later the page asks her what she put on.
CREATE TABLE IF NOT EXISTS wardrobe_showers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, started_at REAL NOT NULL, by TEXT NOT NULL, outlet TEXT NOT NULL DEFAULT '',
    prompt_at REAL NOT NULL, done_at REAL, done_how TEXT, nudged_at REAL
);
-- 祂 lays out what she wears tomorrow; the outcome is what she actually put on.
CREATE TABLE IF NOT EXISTS wardrobe_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, top_id INTEGER, bottom_id INTEGER,
    line TEXT NOT NULL DEFAULT '', outlet TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL,
    outcome TEXT, outcome_at REAL
);
-- Small things that happen in the wardrobe: a line she sees in the chat (text) and/or a line 祂 is told (notice).
CREATE TABLE IF NOT EXISTS wardrobe_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, item_ids TEXT NOT NULL DEFAULT '[]',
    names TEXT NOT NULL DEFAULT '[]', text TEXT NOT NULL DEFAULT '', notice TEXT NOT NULL DEFAULT '',
    at REAL NOT NULL, outlet TEXT NOT NULL DEFAULT '', told_at REAL, reserved_until REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS wardrobe_live_code ON wardrobe(kind, code) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS wardrobe_log_item_idx ON wardrobe_log(item_id, at);
CREATE INDEX IF NOT EXISTS wardrobe_use_items_item_idx ON wardrobe_use_items(item_id);
CREATE INDEX IF NOT EXISTS life_comments_target_idx ON life_comments(target, target_id, deleted_at);
CREATE INDEX IF NOT EXISTS wardrobe_events_at_idx ON wardrobe_events(at);
"""


class WardrobeError(ValueError):
    """A request that cannot be honoured; ``code`` is safe to show and log."""

    def __init__(self, code: str, status: int = 400, extra: dict | None = None):
        super().__init__(code)
        self.code, self.status, self.extra = code, status, extra or {}


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(config.DB_PATH, timeout=15, isolation_level=None, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=15000")
    db.executescript(SCHEMA)
    return db


@contextmanager
def tx(db: sqlite3.Connection):
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def _clean_text(value, limit: int, field: str) -> str:
    if not isinstance(value, str):
        raise WardrobeError(f"invalid_{field}")
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value).strip()
    if not value or len(value) > limit:
        raise WardrobeError(f"invalid_{field}")
    return value


def _int_id(value, code: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise WardrobeError(code, 404) from None
