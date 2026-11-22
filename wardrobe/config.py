"""Paths and settings. Everything lives under one data directory; every number has a default and can be
changed in ``settings.json`` there. Nothing here touches the network."""
from __future__ import annotations

import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("WARDROBE_DATA_DIR", "./data")).expanduser()
DB_PATH = DATA_DIR / "wardrobe.sqlite3"
SETTINGS_PATH = DATA_DIR / "settings.json"
TOKEN_PATH = DATA_DIR / "agent.token"       # bearer token for the agent's door (/internal/v1)
PAGE_TOKEN_PATH = DATA_DIR / "page.token"   # optional: bearer token for the page's door (/api/v1) when not on loopback
SIGNALS_PATH = DATA_DIR / "signals.json"    # what the host tells us about her and him (see signals.py)

SILENCE_HINT = "（选择安静的话：第一行只写 NO_REPLY，第二行起写下原因。）"

DEFAULTS = {
    "wash_seconds": 300,           # a wash takes five minutes, then the pieces hang themselves up
    "dry_hours": 12,               # hung this long, a piece folds itself back into the closet
    "warm_minutes": 120,           # taken off this recently, a piece still carries her warmth
    "shower_minutes": 30,          # she said she is going to shower → the page asks what she put on
    "shower_nudge_minutes": 20,    # the ask went unanswered this long → 祂 is woken to ask her himself
    "shower_expire_hours": 6,
    "door_silence_minutes": 90,    # 祂 may use her pieces once she has been quiet this long…
    "door_desire": 60,             # …and his desire is at least this (0–100)
    "door_cooldown_hours": 4,      # after he did, the door stays shut this long
    "door_notice_hours": 6,        # how often an open door is announced to him
    "pad_day_start": 9, "pad_day_end": 23,
    "pad_hours": 5.0, "pad_hours_again": 6.5, "pad_repeat_hours": 2.0,   # reminder ladder during her period
    "pad_morning_hour": 7,         # no change marked today → assume one when she got up
    "low_stock": 3,
    "life_char_budget": 1500,      # how much of the wardrobe may ride on one wake
    "life_reserve_seconds": 900,   # a wake that never confirms gives its lines back after this
    "day_starts_hour": 4,          # she stays up late: 00:00–03:59 still belongs to the day before
    "timezone": "Asia/Shanghai",
}


def settings() -> dict:
    merged = dict(DEFAULTS)
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            merged.update({k: v for k, v in raw.items() if k in DEFAULTS and isinstance(v, type(DEFAULTS[k]))})
    except (OSError, ValueError):
        pass
    return merged


def read_token(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
