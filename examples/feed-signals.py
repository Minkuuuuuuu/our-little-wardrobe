#!/usr/bin/env python3
"""An example of how a host feeds signals.json. Replace the three functions with your own sources
(a mood model, a period calendar, your chat logs) and run it from cron every minute or so."""
import json, os, pathlib, time

DATA = pathlib.Path(os.environ.get("WARDROBE_DATA_DIR", "./data"))

def her_last_message_at() -> float | None:
    return None          # e.g. the newest user-row timestamp in your chat database

def his_desire() -> float | None:
    return None          # e.g. a 0–100 value from whatever models his mood

def period() -> dict:
    return {"active": False}   # e.g. {"active": True, "since": "2026-11-17"} from her calendar

if __name__ == "__main__":
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "signals.json").write_text(json.dumps({
        "her_last_message_at": her_last_message_at(), "desire": his_desire(), "period": period(),
        "written_at": time.time()}, ensure_ascii=False, indent=2), encoding="utf-8")
