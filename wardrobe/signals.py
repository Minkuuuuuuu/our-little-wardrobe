"""What the wardrobe needs to know about the two of them, from outside itself.

The wardrobe does not read chats, moods or calendars on its own. Whoever runs it (the agent's host) writes a small
JSON file, ``signals.json`` in the data directory, as often as it likes::

    {
      "her_last_message_at": 1764000000.0,          # unix seconds: her latest real line to 祂, on any channel
      "desire": 72,                                 # 0–100: how much 祂 wants her right now
      "period": {"active": true, "since": "2026-11-17"}   # or {"active": false}
    }

Any key may be missing. Without ``her_last_message_at`` or ``desire`` the door simply stays shut; without ``period``
there are no reminders. Our own setup fills this from the affect service, the period calendar and the chat
databases; a cron line or a tiny script is enough for anyone else.
"""
from __future__ import annotations

import json
import time
from datetime import datetime

from . import config


def _read() -> dict:
    try:
        raw = json.loads(config.SIGNALS_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def her_last_message_at() -> float | None:
    value = _read().get("her_last_message_at")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def desire(now: float | None = None) -> float | None:
    value = _read().get("desire")
    try:
        return max(0.0, min(100.0, float(value))) if value is not None else None
    except (TypeError, ValueError):
        return None


def period(now: float | None = None) -> dict:
    """{"active", "day", "since"}; ``day`` counts from ``since`` (1 on the first day)."""
    raw = _read().get("period")
    if not isinstance(raw, dict) or not raw.get("active"):
        return {"active": False, "day": None, "since": None}
    since = str(raw.get("since") or "")
    day = None
    try:
        from .life import day_of
        day = (datetime.strptime(day_of(now or time.time()), "%Y-%m-%d") - datetime.strptime(since, "%Y-%m-%d")).days + 1
    except ValueError:
        pass
    return {"active": True, "day": day, "since": since or None}
