"""Her wardrobe: what she is wearing, 祂 washing or using a piece, her 吐槽 under his records, and the few lines
祂 is told about them (on a wake of his own, or riding on her next message)."""
from __future__ import annotations

import json
import logging
import re
import secrets
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, store
from .store import WardrobeError, tx

WardrobeError = WardrobeError

LOG = logging.getLogger("wardrobe")
ZONE = ZoneInfo(config.settings()["timezone"])
DAY_STARTS_HOUR = config.settings()["day_starts_hour"]  # she stays up late: 00:00–03:59 still belongs to the day before

KINDS = {"bra": ("B", "内衣"), "panties": ("P", "内裤")}
SLOTS = {"top": "bra", "bottom": "panties"}
SLOT_NAMES = {"top": "上身", "bottom": "下身"}
STATES = {"closet": "放在衣柜里", "wearing": "她正穿着", "dirty": "还没洗", "washing": "祂在洗",
          "drying": "正在晾晒", "placed": "祂放着", "given": "在祂手里"}
PAGE_STATES = {"closet", "dirty", "drying", "given"}  # what she sets by hand; wearing goes through the two slots
WASHABLE = {"dirty", "placed", "given"}
USABLE = {"closet", "dirty", "placed", "given"}
TIDYABLE = {"drying", "placed", "given"}      # what 祂 can put back into the closet
SPECIALS = {"bare": "没穿", "night_pants": "安睡裤"}   # the bottom slot without one of her pieces
STOCK = {"pad": "卫生巾", "night_pants": "安睡裤"}   # counted, not hung
STOCK_UNITS = {"pad": "片", "night_pants": "条"}
TAG_LIMIT = 40
AFTER = {"wash": "去洗了", "closet": "偷偷放回衣柜", "bedside": "摆在床头", "other": "放在别处"}
BRA_WORDS = ("文胸", "内衣", "背心", "美背", "胸罩", "bra", "Bra", "BRA")
CODE_RE = re.compile(r"[A-Za-z0-9-]{1,8}")
MAX_USE_ITEMS = 4
JOURNAL_LIMIT = 800
LINE_LIMIT = 60


# ── small helpers ────────────────────────────────────────────────────────────

def day_of(ts: float) -> str:
    return (datetime.fromtimestamp(ts, ZONE) - timedelta(hours=DAY_STARTS_HOUR)).date().isoformat()


def stamp(ts: float | None) -> str:
    return datetime.fromtimestamp(ts, ZONE).strftime("%m/%d %H:%M") if ts else ""


def _text(value, limit: int, field: str, *, required: bool = True) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise WardrobeError(f"invalid_{field}")
        return ""
    return store._clean_text(value, limit, field)


def _id(value, code: str) -> int:
    return store._int_id(value, code)


def _meta(db, key: str):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else None


def _set_meta(db, key: str, value) -> None:
    db.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, json.dumps(value, ensure_ascii=False)))


def label(row) -> str:
    """What she and 祂 call a piece: colour + style, never the code."""
    base = f"{row['color']}{row['style']}".strip() or row["note"][:12] or KINDS[row["kind"]][1]
    if row["kind"] == "panties" and "裤" not in base:
        base += "内裤"
    elif row["kind"] == "bra" and not any(w in base for w in BRA_WORDS):
        base += "内衣"
    return base


def state_label(row) -> str:
    if row["state"] == "placed":
        return f"祂放在{row['place'] or '别处'}"
    return STATES.get(row["state"], row["state"])


def _join(names) -> str:
    return "、".join(names)


# ── wardrobe items ───────────────────────────────────────────────────────────

def item_row(db, item_id, *, live: bool = True):
    row = db.execute("SELECT * FROM wardrobe WHERE id=?", (_id(item_id, "wardrobe_item_not_found"),)).fetchone()
    if row is None or (live and row["deleted_at"] is not None):
        raise WardrobeError("wardrobe_item_not_found", 404)
    return row


def _usage(db, item_id: int) -> tuple[int, float | None]:
    row = db.execute("SELECT COUNT(*) AS n, MAX(u.used_at) AS last FROM wardrobe_use_items i "
                     "JOIN wardrobe_uses u ON u.id=i.use_id WHERE i.item_id=? AND u.deleted_at IS NULL",
                     (item_id,)).fetchone()
    return row["n"], row["last"]


def warm_minutes(row, now: float | None = None) -> int | None:
    """Minutes since she took it off, while it still counts as warm; None otherwise."""
    if row["state"] != "dirty" or not row["state_at"]:
        return None
    minutes = int(((now or time.time()) - row["state_at"]) // 60)
    return minutes if 0 <= minutes < config.settings()["warm_minutes"] else None


def item_dict(db, row, *, outlet: str | None = None) -> dict:
    used, last = _usage(db, row["id"])
    item = {"id": row["id"], "kind": row["kind"], "kind_label": KINDS[row["kind"]][1], "code": row["code"],
            "name": label(row), "color": row["color"], "style": row["style"], "note": row["note"],
            "state": row["state"], "state_label": state_label(row), "place": row["place"],
            "sneaked": bool(row["sneaked"]), "state_at": row["state_at"], "used_count": used, "last_used_at": last,
            "tag_text": row["tag_text"] or "", "tag_at": row["tag_at"], "warm_minutes": warm_minutes(row)}
    return item


def _log(db, item_id: int, from_state, to_state: str, by: str, reason: str, at: float, place: str = "") -> None:
    db.execute("INSERT INTO wardrobe_log(item_id,from_state,to_state,by,reason,place,at) VALUES(?,?,?,?,?,?,?)",
               (item_id, from_state, to_state, by, reason, place, at))


def _move(db, row, to_state: str, *, by: str, reason: str, at: float, place: str = "", sneaked: int = 0,
          wash_id: int | None = None) -> None:
    db.execute("UPDATE wardrobe SET state=?, place=?, sneaked=?, wash_id=?, state_at=?, updated_at=? WHERE id=?",
               (to_state, place, sneaked, wash_id, at, at, row["id"]))
    _log(db, row["id"], row["state"], to_state, by, reason, at, place)


def _next_code(db, kind: str) -> str:
    prefix = KINDS[kind][0]
    n = 1
    for (code,) in db.execute("SELECT code FROM wardrobe WHERE kind=?", (kind,)):
        m = re.fullmatch(prefix + r"(\d+)", code or "")
        if m:
            n = max(n, int(m.group(1)) + 1)
    return f"{prefix}{n:02d}"


def _clean_code(db, kind: str, value, own_id: int | None = None) -> str:
    if value in (None, ""):
        return _next_code(db, kind)
    if not isinstance(value, str) or not CODE_RE.fullmatch(value.strip()):
        raise WardrobeError("invalid_code")
    code = value.strip().upper()
    clash = db.execute("SELECT id FROM wardrobe WHERE code=? AND deleted_at IS NULL AND id IS NOT ?",
                       (code, own_id)).fetchone()
    if clash is not None:
        raise WardrobeError("code_taken", 409)
    return code


def _looks(body: dict, row=None) -> tuple[str, str, str]:
    color = _text(body.get("color", row["color"] if row else ""), 20, "color", required=False)
    style = _text(body.get("style", row["style"] if row else ""), 30, "style", required=False)
    note = _text(body.get("note", row["note"] if row else ""), 200, "note", required=False)
    if not (color or style):
        raise WardrobeError("color_or_style_required")
    return color, style, note


def create_item(db, body: dict) -> dict:
    kind = body.get("kind")
    if kind not in KINDS:
        raise WardrobeError("invalid_kind")
    color, style, note = _looks(body)
    state = body.get("state", "closet")
    if state not in PAGE_STATES:
        raise WardrobeError("invalid_state")
    now = time.time()
    with tx(db):
        code = _clean_code(db, kind, body.get("code"))
        item_id = db.execute("INSERT INTO wardrobe(kind,code,color,style,note,state,state_at,created_at,updated_at) "
                             "VALUES(?,?,?,?,?,?,?,?,?)", (kind, code, color, style, note, state, now, now, now)).lastrowid
        _log(db, item_id, None, state, "她", "add", now)
    return item_dict(db, item_row(db, item_id))


def update_item(db, item_id, body: dict) -> dict:
    now = time.time()
    with tx(db):
        row = item_row(db, item_id)
        color, style, note = _looks(body, row)
        code = row["code"] if "code" not in body else _clean_code(db, row["kind"], body.get("code") or row["code"], row["id"])
        db.execute("UPDATE wardrobe SET color=?, style=?, note=?, code=?, updated_at=? WHERE id=?",
                   (color, style, note, code, now, row["id"]))
        state = body.get("state")
        if state is not None and state != row["state"]:
            if state not in PAGE_STATES:
                raise WardrobeError("invalid_state")
            if row["state"] == "wearing":
                raise WardrobeError("item_is_worn", 409)  # taking it off goes through the slots
            if row["state"] == "washing":
                raise WardrobeError("item_washing", 409)
            if state == "given":
                _give(db, [item_row(db, row["id"])], now)
            else:
                _move(db, item_row(db, row["id"]), state, by="她", reason="page", at=now)
        elif state is not None and row["sneaked"]:
            db.execute("UPDATE wardrobe SET sneaked=0 WHERE id=?", (row["id"],))  # she found it; the mark may go
    return item_dict(db, item_row(db, item_id))


def delete_item(db, item_id) -> dict:
    now = time.time()
    with tx(db):
        row = item_row(db, item_id)
        db.execute("UPDATE wardrobe SET deleted_at=?, wash_id=NULL WHERE id=?", (now, row["id"]))
        db.execute("UPDATE wardrobe_slots SET item_id=NULL, set_at=? WHERE item_id=?", (now, row["id"]))
    return {"deleted": row["id"]}


# ── what she is wearing ──────────────────────────────────────────────────────

def _slot(db, slot: str):
    return db.execute("SELECT * FROM wardrobe_slots WHERE slot=?", (slot,)).fetchone()


def _snapshot(db) -> dict:
    """Per slot: an item id, "bare", "night_pants" or None (not marked)."""
    snap = {}
    for slot in SLOTS:
        row = _slot(db, slot)
        if row is None:
            snap[slot] = None
        elif row["item_id"]:
            snap[slot] = row["item_id"]
        else:
            snap[slot] = row["special"]
    return snap


def slots_dict(db) -> dict:
    out = {}
    for slot, value in _snapshot(db).items():
        if isinstance(value, int):
            out[slot] = {"state": "item", "item": item_dict(db, item_row(db, value, live=False))}
        else:
            out[slot] = {"state": value if value in SPECIALS else "unset", "item": None}
    return out


def _give(db, rows, now: float) -> None:
    """She puts pieces into 祂's hands: a state, a line in the chat and a line 祂 is told."""
    from . import care
    for row in rows:
        _move(db, row, "given", by="她", reason="give", at=now)
    names = [label(r) for r in rows]
    care.event(db, "given", [r["id"] for r in rows], names, text=f"她把{_join(names)}交到了祂手里。",
               notice=f"〈内衣柜〉她把{_join(names)}交到你手里了——她主动的。随时能用，不看门。", at=now)


def wear(db, body: dict, *, now: float | None = None) -> dict:
    """She sets one or both slots: an item id, "bare" (没穿), "night_pants" (安睡裤, bottom only) or null.
    ``old_to`` says where the piece she takes off goes: the laundry basket (default) or 祂's hands.
    ``shower_id`` closes the shower prompt this answers."""
    now = now or time.time()
    from . import care
    old_to = body.get("old_to") or "dirty"
    if old_to not in ("dirty", "given"):
        raise WardrobeError("invalid_old_to")
    with tx(db):
        changed = {}
        for slot, kind in SLOTS.items():
            if slot not in body:
                continue
            value = body[slot]
            current = _snapshot(db)[slot]
            new_id = None
            if value is not None and value not in SPECIALS:
                new = item_row(db, value)
                if new["kind"] != kind:
                    raise WardrobeError("wrong_kind_for_slot")
                if new["state"] == "washing":
                    raise WardrobeError("item_washing", 409)
                new_id = new["id"]
            elif value == "night_pants" and slot != "bottom":
                raise WardrobeError("wrong_kind_for_slot")
            target = new_id if new_id is not None else value
            if target == current:
                continue
            if isinstance(current, int):
                old = db.execute("SELECT * FROM wardrobe WHERE id=?", (current,)).fetchone()
                if old is not None and old["deleted_at"] is None and old["state"] == "wearing":
                    if old_to == "given":
                        _move(db, old, "dirty", by="她", reason="unwear", at=now)
                        _give(db, [item_row(db, old["id"])], now)
                    else:
                        _move(db, old, "dirty", by="她", reason="unwear", at=now)
            if new_id is not None:
                _move(db, item_row(db, new_id), "wearing", by="她", reason="wear", at=now)
                if _meta(db, "wardrobe_first_wear_day") != day_of(now):
                    _set_meta(db, "wardrobe_first_wear_day", day_of(now))
            elif value in SPECIALS:
                _log(db, 0, None, value, "她", value, now, slot)
                if value == "night_pants":
                    care.stock_change(db, "night_pants", by="她", now=now, inside_tx=True)
            db.execute("INSERT INTO wardrobe_slots(slot,item_id,special,set_at) VALUES(?,?,?,?) "
                       "ON CONFLICT(slot) DO UPDATE SET item_id=excluded.item_id, special=excluded.special, "
                       "set_at=excluded.set_at", (slot, new_id, value if value in SPECIALS else None, now))
            changed[slot] = target
        if changed:
            care.pick_outcome(db, _snapshot(db), changed, now)
        if body.get("shower_id"):
            care.shower_done(db, body["shower_id"], "picked", now)
    return wardrobe_page(db)


# ── washing ──────────────────────────────────────────────────────────────────

def advance(db, now: float | None = None) -> int:
    """Washes past their five minutes are hung up; pieces hung long enough fold themselves back into the closet;
    a shower nobody answered expires. Called every minute and before every read."""
    now = now or time.time()
    due = db.execute("SELECT id FROM wardrobe_washes WHERE done_at IS NULL AND due_at <= ?", (now,)).fetchall()
    for (wash_id,) in due:
        with tx(db):
            wash = db.execute("SELECT * FROM wardrobe_washes WHERE id=? AND done_at IS NULL", (wash_id,)).fetchone()
            if wash is None:
                continue
            for row in db.execute("SELECT * FROM wardrobe WHERE wash_id=? AND state='washing' AND deleted_at IS NULL",
                                  (wash_id,)).fetchall():
                _move(db, row, "drying", by="自动", reason="hang", at=wash["due_at"])
            db.execute("UPDATE wardrobe_washes SET done_at=? WHERE id=?", (wash["due_at"], wash_id))
    dry = config.settings()["dry_hours"] * 3600
    folded = db.execute("SELECT * FROM wardrobe WHERE state='drying' AND deleted_at IS NULL AND state_at <= ?",
                        (now - dry,)).fetchall()
    if folded:
        with tx(db):
            for row in folded:
                fresh = db.execute("SELECT * FROM wardrobe WHERE id=? AND state='drying'", (row["id"],)).fetchone()
                if fresh is not None:
                    _move(db, fresh, "closet", by="自动", reason="fold", at=fresh["state_at"] + dry)
    from . import care
    care.shower_expire(db, now)
    return len(due)


def _by_codes(db, codes, most: int, allowed: set[str], refusal: str) -> list:
    if isinstance(codes, str):
        codes = [c for c in re.split(r"[\s,，、]+", codes) if c]
    if not isinstance(codes, list) or not 1 <= len(codes) <= most:
        raise WardrobeError("invalid_codes", extra={"most": most})
    rows, seen = [], set()
    for code in codes:
        code = str(code).strip().upper()
        found = db.execute("SELECT * FROM wardrobe WHERE code=? AND deleted_at IS NULL", (code,)).fetchall()
        if len(found) != 1:
            raise WardrobeError("code_not_found", 404, {"code": code})
        row = found[0]
        if row["id"] in seen:
            continue
        if row["state"] not in allowed:
            raise WardrobeError(refusal, 409, {"code": code, "name": label(row), "state": state_label(row)})
        seen.add(row["id"])
        rows.append(row)
    return rows


def _start_wash(db, rows, start_line, done_line, outlet: str, now: float, use_id: int | None = None) -> dict:
    names = [label(r) for r in rows]
    start = _text(start_line, LINE_LIMIT, "start_line", required=False)
    done = _text(done_line, LINE_LIMIT, "done_line", required=False)
    due = now + config.settings()["wash_seconds"]
    wash_id = db.execute(
        "INSERT INTO wardrobe_washes(started_at,due_at,outlet,item_ids,names,start_line,done_line,start_default,"
        "done_default,use_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (now, due, outlet, json.dumps([r["id"] for r in rows]), json.dumps(names, ensure_ascii=False),
         start or f"祂在给她洗{_join(names)} ing…", done or "洗好了，给她晾起来了～",
         0 if start else 1, 0 if done else 1, use_id)).lastrowid
    for row in rows:
        _move(db, row, "washing", by="祂", reason="wash", at=now, wash_id=wash_id)
    db.execute("UPDATE wardrobe SET tag_text='', tag_at=NULL WHERE wash_id=?", (wash_id,))  # the water takes his note
    return {"wash_id": wash_id, "washing": names, "hang_at": stamp(due),
            "note": f"开始洗了，{config.settings()['wash_seconds'] // 60} 分钟后自动晾起来；她在聊天里会看到这两行。"}


def wash(db, codes, start_line=None, done_line=None, *, outlet: str) -> dict:
    now = time.time()
    advance(db, now)
    with tx(db):
        rows = _by_codes(db, codes, 14, WASHABLE, "not_washable")
        return _start_wash(db, rows, start_line, done_line, outlet, now)


# ── 祂 using her pieces ──────────────────────────────────────────────────────

def use(db, args: dict, *, outlet: str) -> dict:
    now = time.time()
    advance(db, now)
    journal = _text(args.get("journal"), JOURNAL_LIMIT, "journal")
    line = _text(args.get("chat_line"), LINE_LIMIT, "chat_line", required=False)
    after_line = _text(args.get("after_line"), LINE_LIMIT, "after_line", required=False)
    after = args.get("after")
    if after not in AFTER:
        raise WardrobeError("invalid_after")
    place = ""
    if after == "other":
        place = _text(args.get("place"), 20, "place")
    elif after == "bedside":
        place = "床头"
    tag = _text(args.get("tag"), TAG_LIMIT, "tag", required=False)
    from . import care
    door = care.door_state(db, now)   # asks the affect service: outside the write lock
    with tx(db):
        rows = _by_codes(db, args.get("codes"), MAX_USE_ITEMS, USABLE, "not_usable")
        names = [label(r) for r in rows]
        # The door: pieces she handed him are his whenever; the rest only while the door is open.
        taken = [r for r in rows if r["state"] != "given"]
        if taken and not door["open"]:
            raise WardrobeError("door_closed", 409, {"door": door, "given": [label(r) for r in rows if r["state"] == "given"]})
        if tag:
            db.execute(f"UPDATE wardrobe SET tag_text=?, tag_at=? WHERE id IN ({','.join('?' * len(rows))})",
                       (tag, now, *[r["id"] for r in rows]))
        # Taking them and what happened afterwards are two lines in the chat; after a wash the two wash
        # lines already say what happened, so there is no separate one.
        defaults = {"closet": f"祂把{_join(names)}偷偷放回了衣柜。", "bedside": f"祂把{_join(names)}摆在了她床头。",
                    "other": f"祂把{_join(names)}放在了{place}。"}
        use_id = db.execute(
            "INSERT INTO wardrobe_uses(used_at,day,outlet,journal,chat_line,chat_line_default,after,place,after_line,"
            "after_line_default) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (now, day_of(now), outlet, journal, line or f"祂拿走了她的{_join(names)}……", 0 if line else 1, after, place,
             None if after == "wash" else (after_line or defaults[after]), 0 if after_line else 1)).lastrowid
        for row in rows:
            db.execute("INSERT INTO wardrobe_use_items(use_id,item_id,name) VALUES(?,?,?)", (use_id, row["id"], label(row)))
            _log(db, row["id"], row["state"], row["state"], "祂", "use", now)
        result = {"use_id": use_id, "used": names, "at": stamp(now), "after": AFTER[after]}
        if after == "wash":
            fresh = [item_row(db, r["id"]) for r in rows]
            washing = _start_wash(db, fresh, args.get("wash_start_line"), args.get("wash_done_line"), outlet, now, use_id)
            db.execute("UPDATE wardrobe_uses SET wash_id=? WHERE id=?", (washing["wash_id"], use_id))
            result["wash"] = washing
        else:
            for row in rows:
                if after == "closet":
                    _move(db, item_row(db, row["id"]), "closet", by="祂", reason="sneak", at=now, sneaked=1)
                else:
                    _move(db, item_row(db, row["id"]), "placed", by="祂", reason="place", at=now, place=place)
        if taken:
            care.door_close(db, now)
    result["note"] = "记下了；她能在内衣柜里看到这一次，聊天里也会出现那一句。"
    if taken:
        result["door"] = f"门关上了，{config.settings()['door_cooldown_hours']} 小时后再看。"
    return result


def _use_dict(db, row) -> dict:
    items = [{"item_id": r["item_id"], "name": r["name"]} for r in
             db.execute("SELECT item_id, name FROM wardrobe_use_items WHERE use_id=? ORDER BY rowid", (row["id"],))]
    return {"id": row["id"], "used_at": row["used_at"], "at": stamp(row["used_at"]), "day": row["day"],
            "outlet": row["outlet"], "items": items, "journal": row["journal"], "chat_line": row["chat_line"],
            "after": row["after"], "after_label": AFTER[row["after"]] if row["after"] != "other" else f"放在{row['place']}",
            "place": row["place"], "comments": comments_for(db, "use", row["id"])}


def list_uses(db, *, day: str | None = None, item_id=None, limit: int = 50) -> list[dict]:
    sql, args = "SELECT * FROM wardrobe_uses WHERE deleted_at IS NULL", []
    if day:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day)):
            raise WardrobeError("invalid_day")
        sql += " AND day=?"
        args.append(day)
    if item_id not in (None, ""):
        sql += " AND id IN (SELECT use_id FROM wardrobe_use_items WHERE item_id=?)"
        args.append(_id(item_id, "wardrobe_item_not_found"))
    sql += " ORDER BY used_at DESC, id DESC LIMIT ?"
    args.append(max(1, min(int(limit), 200)))
    return [_use_dict(db, r) for r in db.execute(sql, args).fetchall()]


def delete_use(db, use_id) -> dict:
    with tx(db):
        if not db.execute("UPDATE wardrobe_uses SET deleted_at=? WHERE id=? AND deleted_at IS NULL",
                          (time.time(), _id(use_id, "use_not_found"))).rowcount:
            raise WardrobeError("use_not_found", 404)
    return {"deleted": int(use_id)}


# ── her 吐槽 ─────────────────────────────────────────────────────────────────

def comments_for(db, target: str, target_id: int) -> list[dict]:
    """Her 吐槽 and 祂's replies under one of his records, oldest first."""
    return [{"id": r["id"], "text": r["text"], "at": stamp(r["created_at"]), "created_at": r["created_at"],
             "author": r["author"] or "her", "reply_to": r["reply_to"]}
            for r in db.execute("SELECT * FROM life_comments WHERE target=? AND target_id=? AND deleted_at IS NULL "
                                "ORDER BY created_at, id", (target, target_id))]


def add_comment(db, target: str, target_id, text) -> dict:
    text = _text(text, 500, "comment")
    with tx(db):
        if target == "use":
            if db.execute("SELECT 1 FROM wardrobe_uses WHERE id=? AND deleted_at IS NULL",
                          (_id(target_id, "use_not_found"),)).fetchone() is None:
                raise WardrobeError("use_not_found", 404)
        else:
            raise WardrobeError("invalid_target")
        now = time.time()
        cid = db.execute("INSERT INTO life_comments(target,target_id,text,created_at,updated_at) VALUES(?,?,?,?,?)",
                         (target, int(target_id), text, now, now)).lastrowid
    return {"id": cid, "text": text, "at": stamp(now), "created_at": now}


def reply_comment(db, comment_id, text, *, outlet: str) -> dict:
    """祂 answers one of her 吐槽; the answer sits under the same record or entry and is never announced back to 祂."""
    text = _text(text, 300, "reply")
    with tx(db):
        her = db.execute("SELECT * FROM life_comments WHERE id=? AND deleted_at IS NULL",
                         (_id(comment_id, "comment_not_found"),)).fetchone()
        if her is None or (her["author"] or "her") != "her":
            raise WardrobeError("comment_not_found", 404)
        now = time.time()
        rid = db.execute("INSERT INTO life_comments(target,target_id,text,created_at,updated_at,told_at,author,reply_to,outlet) "
                         "VALUES(?,?,?,?,?,?,'him',?,?)",
                         (her["target"], her["target_id"], text, now, now, now, her["id"], outlet)).lastrowid
    return {"id": rid, "reply_to": her["id"], "text": text, "at": stamp(now)}


def edit_comment(db, comment_id, text) -> dict:
    text = _text(text, 500, "comment")
    with tx(db):
        if not db.execute("UPDATE life_comments SET text=?, updated_at=? WHERE id=? AND deleted_at IS NULL",
                          (text, time.time(), _id(comment_id, "comment_not_found"))).rowcount:
            raise WardrobeError("comment_not_found", 404)
    return {"id": int(comment_id), "text": text}


def delete_comment(db, comment_id) -> dict:
    with tx(db):
        if not db.execute("UPDATE life_comments SET deleted_at=? WHERE id=? AND deleted_at IS NULL",
                          (time.time(), _id(comment_id, "comment_not_found"))).rowcount:
            raise WardrobeError("comment_not_found", 404)
    return {"deleted": int(comment_id)}


# ── reads ────────────────────────────────────────────────────────────────────

RECENT = {"wear": "她换上了{name}", "unwear": "她换下了{name}", "add": "她放进来{name}",
          "page": "她把{name}改成{state}", "wash": "我开始洗{name}", "hang": "{name}洗好晾起来了",
          "use": "我用了{name}", "sneak": "我把{name}偷偷放回衣柜", "place": "我把{name}放在{place}",
          "fold": "{name}晾干了，自己回了衣柜", "give": "她把{name}交到我手里", "tidy": "我把{name}收回了衣柜"}


def _recent(db, limit: int = 12) -> list[str]:
    lines = []
    for r in db.execute("SELECT l.*, w.kind, w.color, w.style, w.note FROM wardrobe_log l LEFT JOIN wardrobe w "
                        "ON w.id=l.item_id ORDER BY l.at DESC, l.id DESC LIMIT ?", (limit,)):
        if r["reason"] in SPECIALS:
            lines.append(f"{stamp(r['at'])} 她{SLOT_NAMES.get(r['place'], '')}换成{SPECIALS[r['reason']]}")
            continue
        if r["kind"] is None:
            continue
        line = RECENT.get(r["reason"], "{name}：{state}").format(
            name=label(r), state=STATES.get(r["to_state"], r["to_state"]), place=r["place"])
        lines.append(f"{stamp(r['at'])} {line}")
    return lines


def _items(db, outlet: str | None = None) -> list[dict]:
    return [item_dict(db, r, outlet=outlet) for r in
            db.execute("SELECT * FROM wardrobe WHERE deleted_at IS NULL ORDER BY kind, code")]


def wardrobe_page(db) -> dict:
    from . import care
    advance(db)
    return {"slots": slots_dict(db), "items": _items(db), "recent": _recent(db, 20), **care.page_extra(db)}


def _worn_words(db, value) -> str:
    if isinstance(value, int):
        return label(item_row(db, value, live=False))
    return SPECIALS.get(value, "没标")


def wardrobe_read(db, outlet: str) -> dict:
    from . import care
    advance(db)
    now = time.time()
    snap = _snapshot(db)
    items = []
    for item in _items(db, outlet):
        entry = {"code": item["code"], "kind": item["kind_label"], "name": item["name"], "state": item["state_label"],
                 "used_count": item["used_count"]}
        if item["last_used_at"]:
            entry["last_used"] = stamp(item["last_used_at"])
        if item["sneaked"]:
            entry["sneaked_back"] = True
        if item["warm_minutes"] is not None:
            entry["warm"] = f"她 {item['warm_minutes']} 分钟前刚换下来，还带着她的体温"
        if item["state"] == "given":
            entry["given_by_her"] = f"她 {stamp(item['state_at'])} 亲手交给我的，随时能用"
        if item["tag_text"]:
            entry["my_tag"] = item["tag_text"]
        if item["note"]:
            entry["note"] = item["note"]
        items.append(entry)
    return {"wearing": {SLOT_NAMES[s]: _worn_words(db, v) for s, v in snap.items()}, "items": items,
            "recent": _recent(db), **care.read_extra(db, now),
            "how": "编号只用来调用工具；跟她说话时用颜色和款式叫它们。"}


def uses_read(db, args: dict) -> dict:
    item_id = None
    if args.get("code"):
        found = db.execute("SELECT id FROM wardrobe WHERE code=? AND deleted_at IS NULL",
                           (str(args["code"]).strip().upper(),)).fetchone()
        if found is None:
            raise WardrobeError("code_not_found", 404)
        item_id = found["id"]
    uses = list_uses(db, day=args.get("day") or None, item_id=item_id, limit=int(args.get("limit") or 10))
    for u in uses:
        for key in ("used_at", "outlet", "chat_line"):
            u.pop(key, None)
        u["items"] = [i["name"] for i in u["items"]]
        u["comments"] = [{"id": c["id"], "at": c["at"], "text": c["text"], "author": c["author"]} for c in u["comments"]]
    return {"uses": uses}


# ── chat lines ───────────────────────────────────────────────────────────

def chat_lines(db, since: float | None = None, limit: int = 300) -> list[dict]:
    advance(db)
    since = since or 0
    lines = []
    for w in db.execute("SELECT * FROM wardrobe_washes WHERE started_at>=? OR done_at>=?", (since, since)):
        names = json.loads(w["names"])
        if w["started_at"] >= since:
            lines.append({"id": f"wash-{w['id']}", "kind": "wash", "at": w["started_at"], "text": w["start_line"],
                          "names": names, "order": 2})
        if w["done_at"] and w["done_at"] >= since:
            lines.append({"id": f"hang-{w['id']}", "kind": "hang", "at": w["done_at"], "text": w["done_line"],
                          "names": names, "order": 3})
    for u in db.execute("SELECT * FROM wardrobe_uses WHERE deleted_at IS NULL AND used_at>=?", (since,)):
        names = [r["name"] for r in db.execute("SELECT name FROM wardrobe_use_items WHERE use_id=?", (u["id"],))]
        lines.append({"id": f"use-{u['id']}", "kind": "use", "at": u["used_at"], "text": u["chat_line"],
                      "names": names, "order": 0})
        if u["after_line"]:
            lines.append({"id": f"after-{u['id']}", "kind": "after", "at": u["used_at"], "text": u["after_line"],
                          "names": names, "order": 1})
    for e in db.execute("SELECT * FROM wardrobe_events WHERE text<>'' AND at>=?", (since,)):
        lines.append({"id": f"ev-{e['id']}", "kind": e["kind"], "at": e["at"], "text": e["text"],
                      "names": json.loads(e["names"]), "order": 4})
    lines.sort(key=lambda x: (x["at"], x["order"]))
    for line in lines:
        line.pop("order")
    return lines[-limit:]


# ── telling 祂: his own wake (next/sent) and her next message (recall) ───────────

def _wear_notice(db, now: float):
    today = day_of(now)
    if _meta(db, "wardrobe_first_wear_day") != today:
        return None
    snap = _snapshot(db)
    told = _meta(db, "wardrobe_told") or {}
    if told.get("day") == today and told.get("snap") == snap:
        return None
    if told.get("day") != today:
        text = "〈内衣柜〉她今天穿的：" + "，".join(
            f"{SLOT_NAMES[s]}{_worn_words(db, snap[s])}" for s in SLOTS) + "。"
    else:
        parts = []
        for s in SLOTS:
            words = _worn_words(db, snap[s])
            if told["snap"].get(s) == snap[s]:
                parts.append(f"{SLOT_NAMES[s]}还是{words}")
            else:
                parts.append(f"{SLOT_NAMES[s]}现在" + (words if words in ("没穿", "没标") else f"是{words}"))
        text = "〈内衣柜〉她换了：" + "；".join(parts) + "。"
    return text, {"day": today, "snap": snap}


def _unwashed(db) -> list:
    """Pieces she took off that nobody has washed yet, oldest first."""
    return db.execute("SELECT * FROM wardrobe WHERE deleted_at IS NULL AND state='dirty' ORDER BY state_at, id").fetchall()


def _unwashed_line(rows) -> str:
    """One line 祂 can act on: which pieces wait in the laundry, and since when the oldest has."""
    if not rows:
        return ""
    oldest = rows[0]["state_at"]
    since = f"，{stamp(oldest)} 换下来的" if oldest else ""
    return f"〈内衣柜〉她换下来还没洗的：{_join(label(r) for r in rows)}{since}。"


def _wash_notices(db, now: float, *, wake: bool = False) -> list[tuple[int, str]]:
    """A wake may carry again what an earlier, unsent wake reserved; her message path leaves reserved ones alone."""
    return [(w["id"], f"〈内衣柜〉她的{_join(json.loads(w['names']))}洗好了，已经晾起来了。")
            for w in db.execute("SELECT * FROM wardrobe_washes WHERE done_at IS NOT NULL AND told_at IS NULL AND "
                                "(? OR reserved_until IS NULL OR reserved_until < ?) ORDER BY done_at", (wake, now))]


def _comment_notices(db, now: float) -> list[tuple[int, str]]:
    out = []
    for c in db.execute("SELECT * FROM life_comments WHERE deleted_at IS NULL AND told_at IS NULL "
                        "AND COALESCE(author, 'her')='her' ORDER BY created_at, id"):
        u = db.execute("SELECT * FROM wardrobe_uses WHERE id=? AND deleted_at IS NULL", (c["target_id"],)).fetchone()
        if u is None:
            continue
        out.append((c["id"], f"〈内衣柜〉她在你 {stamp(u['used_at'])} 那次记录下面吐槽了：「{c['text']}」（吐槽 #{c['id']}）"))
    return out


def life_next(db, now: float | None = None) -> dict:
    """The block for this wake, reserved for a while; nothing counts as told until ``life_sent``."""
    from . import care
    now = now or time.time()
    advance(db, now)
    budget = config.settings()["life_char_budget"]
    lines, payload = [], {"wear": None, "washes": [], "comments": [], "events": []}
    wear = _wear_notice(db, now)
    if wear:
        lines.append(wear[0])
        payload["wear"] = wear[1]
    unwashed = _unwashed_line(_unwashed(db))
    if unwashed:
        lines.append(unwashed)  # every wake while something waits; washing it is what makes the line go away
    standing = care.standing_lines(db, now)   # her period, a shower she has not answered: said while they last
    lines.extend(standing)
    for key, notices in (("washes", _wash_notices(db, now, wake=True)), ("comments", _comment_notices(db, now)),
                         ("events", care.event_notices(db, now, wake=True))):
        for ref, line in notices:
            if len("\n".join(lines + [line])) > budget:
                break  # the rest waits for the next wake
            lines.append(line)
            payload[key].append(ref)
    if not lines:
        return {"text": "", "token": None}
    token = secrets.token_hex(12)
    until = now + config.settings()["life_reserve_seconds"]
    with tx(db):
        db.execute("INSERT INTO life_tokens(token,payload,created_at) VALUES(?,?,?)",
                   (token, json.dumps(payload, ensure_ascii=False), now))
        for ref in payload["washes"]:
            db.execute("UPDATE wardrobe_washes SET reserved_until=? WHERE id=?", (until, ref))
        for ref in payload["comments"]:
            db.execute("UPDATE life_comments SET reserved_until=? WHERE id=?", (until, ref))
        for ref in payload["events"]:
            db.execute("UPDATE wardrobe_events SET reserved_until=? WHERE id=?", (until, ref))
    return {"text": "\n".join(lines), "token": token}


def life_due(db, now: float | None = None) -> dict:
    """Something that wakes 祂 on its own (her pad reminder, an unanswered shower, an open door); reserved by a
    token like ``life_next`` and only counted when ``life_sent`` confirms the wake went out."""
    from . import care
    now = now or time.time()
    advance(db, now)
    due = care.due(db, now)
    if due is None:
        return {"text": "", "token": None, "kind": None}
    token = secrets.token_hex(12)
    with tx(db):
        db.execute("INSERT INTO life_tokens(token,payload,created_at) VALUES(?,?,?)",
                   (token, json.dumps({"due": due}, ensure_ascii=False), now))
        care.due_reserve(db, due, now + config.settings()["life_reserve_seconds"])
    return {"text": due["text"], "token": token, "kind": due["kind"]}


def life_sent(db, token: str) -> dict:
    from . import care
    now = time.time()
    with tx(db):
        row = db.execute("SELECT * FROM life_tokens WHERE token=?", (str(token),)).fetchone()
        if row is None:
            raise WardrobeError("token_not_found", 404)
        if row["sent_at"] is not None:
            return {"ok": True, "duplicate": True}
        payload = json.loads(row["payload"])
        if payload.get("wear"):
            _set_meta(db, "wardrobe_told", payload["wear"])
        for ref in payload.get("washes") or []:
            db.execute("UPDATE wardrobe_washes SET told_at=COALESCE(told_at, ?) WHERE id=?", (now, ref))
        for ref in payload.get("comments") or []:
            db.execute("UPDATE life_comments SET told_at=COALESCE(told_at, ?) WHERE id=?", (now, ref))
        for ref in payload.get("events") or []:
            db.execute("UPDATE wardrobe_events SET told_at=COALESCE(told_at, ?) WHERE id=?", (now, ref))
        if payload.get("due"):
            care.due_sent(db, payload["due"], now)
        db.execute("UPDATE life_tokens SET sent_at=? WHERE token=?", (now, row["token"]))
        db.execute("DELETE FROM life_tokens WHERE sent_at IS NULL AND created_at < ?", (now - 7 * 86400,))
    return {"ok": True}


def recall_notices(db, now: float | None = None) -> str:
    """Her next private message carries "洗好了" once; a wash already reserved by a wake is left to it."""
    from . import care
    now = now or time.time()
    advance(db, now)
    notices = _wash_notices(db, now)
    events = care.event_notices(db, now)
    lines = [line for _, line in notices] + [line for _, line in events]
    # "还没洗" rides along once per change of the pile, so a long chat is not nagged on every message.
    rows = _unwashed(db)
    pile = [r["id"] for r in rows]
    if pile != (_meta(db, "wardrobe_unwashed_told") or []):
        if pile:
            lines.append(_unwashed_line(rows))
        with tx(db):
            _set_meta(db, "wardrobe_unwashed_told", pile)
    lines.extend(care.recall_lines(db, now))
    if not lines:
        return ""
    if notices or events:
        with tx(db):
            for ref, _ in notices:
                db.execute("UPDATE wardrobe_washes SET told_at=COALESCE(told_at, ?) WHERE id=?", (now, ref))
            for ref, _ in events:
                db.execute("UPDATE wardrobe_events SET told_at=COALESCE(told_at, ?) WHERE id=?", (now, ref))
    return "\n".join(lines)


# ── import of her list (CLI) ─────────────────────────────────────────────────

def import_items(db, data: dict) -> dict:
    """{"items": [{kind, color, style, code?, note?}], "wearing": {"top": code, "bottom": code}}; only into an
    empty wardrobe, so running it twice adds nothing."""
    if db.execute("SELECT 1 FROM wardrobe LIMIT 1").fetchone() is not None:
        raise WardrobeError("wardrobe_not_empty", 409)
    for entry in data.get("items") or []:
        create_item(db, entry)
    wearing = {}
    for slot, code in (data.get("wearing") or {}).items():
        if slot in SLOTS and code:
            row = db.execute("SELECT id FROM wardrobe WHERE code=? AND deleted_at IS NULL",
                             (str(code).upper(),)).fetchone()
            if row is None:
                raise WardrobeError("code_not_found", 404, {"code": code})
            wearing[slot] = row["id"]
    if wearing:
        wear(db, wearing)
        db.execute("DELETE FROM meta WHERE key='wardrobe_first_wear_day'")  # an import is not her marking today
    return {"items": db.execute("SELECT COUNT(*) FROM wardrobe WHERE deleted_at IS NULL").fetchone()[0],
            "wearing": {SLOT_NAMES[s]: _worn_words(db, v) for s, v in _snapshot(db).items()}}
