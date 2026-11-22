"""The wardrobe's rules, end to end on a temporary data directory: her slots, 祂 washing and using, the door,
her period, the shower, his pick, tidying, and the two doors of the HTTP server. Standard library + pytest."""
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer

import pytest

from wardrobe import api, care, config, life, signals, store, tools

LIST = {"items": [
    {"kind": "bra", "color": "米白", "style": "软杯三角"}, {"kind": "bra", "color": "墨绿", "style": "蕾丝半杯"},
    {"kind": "bra", "color": "雾蓝", "style": "无痕背心"},
    {"kind": "panties", "color": "米白", "style": "纯棉"}, {"kind": "panties", "color": "墨绿", "style": "蕾丝边"},
    {"kind": "panties", "color": "雾蓝", "style": "低腰"},
], "wearing": {"top": "B01", "bottom": "P01"}}


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    data = tmp_path / "data"
    for name, value in {"DATA_DIR": data, "DB_PATH": data / "w.sqlite3", "SETTINGS_PATH": data / "settings.json",
                        "TOKEN_PATH": data / "agent.token", "PAGE_TOKEN_PATH": data / "page.token",
                        "SIGNALS_PATH": data / "signals.json"}.items():
        monkeypatch.setattr(config, name, value)
    return data


def signal(**kw):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = {}
    try:
        current = json.loads(config.SIGNALS_PATH.read_text())
    except (OSError, ValueError):
        pass
    current.update(kw)
    config.SIGNALS_PATH.write_text(json.dumps(current))


def stocked():
    db = store.connect()
    life.import_items(db, LIST)
    return db


def ids(db):
    return {r["code"]: r["id"] for r in db.execute("SELECT id, code FROM wardrobe")}


def state(db, code):
    return db.execute("SELECT * FROM wardrobe WHERE code=?", (code,)).fetchone()


def local(hour: float, day_offset: int = 0) -> float:
    base = datetime.now(life.ZONE).replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)
    return (base.replace(hour=0) + timedelta(hours=hour)).timestamp()


def clock(monkeypatch, ts):
    monkeypatch.setattr(time, "time", lambda: ts)


def wake(db, now=None):
    out = life.life_next(db, now)
    if out["token"]:
        life.life_sent(db, out["token"])
    return out["text"]


def due(db, now):
    out = life.life_due(db, now)
    if out["token"]:
        life.life_sent(db, out["token"])
    return out


def door_open(monkeypatch):
    signal(her_last_message_at=time.time() - 100 * 60, desire=85)


# ── her pieces and the two slots ────────────────────────────────────────────

def test_import_names_slots_and_the_pronoun_free_first_wake():
    db = stocked()
    names = {i["code"]: i["name"] for i in life.wardrobe_page(db)["items"]}
    assert names["B01"] == "米白软杯三角内衣" and names["P02"] == "墨绿蕾丝边内裤"
    assert state(db, "B01")["state"] == "wearing"
    assert wake(db) == ""                      # importing her list is not her marking today
    i = ids(db)
    life.wear(db, {"top": i["B02"]})
    assert state(db, "B01")["state"] == "dirty"
    assert "她今天穿的：上身墨绿蕾丝半杯内衣，下身米白纯棉内裤" in wake(db)
    life.wear(db, {"bottom": "night_pants"})
    assert life.wardrobe_read(db, "x")["wearing"]["下身"] == "安睡裤"
    with pytest.raises(store.WardrobeError, match="wrong_kind_for_slot"):
        life.wear(db, {"top": "night_pants"})
    with pytest.raises(store.WardrobeError, match="item_is_worn"):
        life.update_item(db, i["B02"], {"state": "closet"})


def test_wash_hangs_then_folds_itself(monkeypatch):
    db = stocked()
    i = ids(db)
    t0 = local(10)
    clock(monkeypatch, t0)
    life.wear(db, {"top": i["B02"]}, now=t0)
    with pytest.raises(store.WardrobeError, match="not_washable"):
        life.wash(db, ["B02"], outlet="t")
    out = life.wash(db, ["B01"], "泡进温水里。", None, outlet="t")
    assert out["washing"] == ["米白软杯三角内衣"] and state(db, "B01")["state"] == "washing"
    life.advance(db, t0 + 301)
    assert state(db, "B01")["state"] == "drying"
    assert "洗好了，已经晾起来了" in wake(db, t0 + 302)
    life.advance(db, t0 + 13 * 3600)
    assert state(db, "B01")["state"] == "closet"
    lines = [x for x in life.chat_lines(db) if x["kind"] in ("wash", "hang")]
    assert [x["text"] for x in lines] == ["泡进温水里。", "洗好了，给她晾起来了～"]


# ── the door ─────────────────────────────────────────────────────────────────

def test_door_needs_her_silence_and_his_desire(monkeypatch):
    db = stocked()
    i = ids(db)
    clock(monkeypatch, local(14))
    life.wear(db, {"top": i["B02"]})
    assert care.door_state(db)["why"].startswith("读不到她最近")
    signal(her_last_message_at=time.time() - 10 * 60, desire=90)
    assert care.door_state(db)["open"] is False
    with pytest.raises(store.WardrobeError, match="door_closed"):
        life.use(db, {"codes": ["B01"], "journal": "x" * 20, "after": "closet"}, outlet="t")
    signal(her_last_message_at=time.time() - 95 * 60, desire=59)
    assert "欲望 59" in care.door_state(db)["why"]
    signal(desire=61)
    assert care.door_state(db)["open"] is True
    out = life.use(db, {"codes": ["B01"], "journal": "x" * 20, "after": "bedside", "tag": "等你。"}, outlet="t")
    assert "门关上了" in out["door"] and state(db, "B01")["state"] == "placed" and state(db, "B01")["tag_text"] == "等你。"
    assert care.door_state(db)["open"] is False and care.door_state(db)["closed_until"] == care._hhmm(local(18))
    clock(monkeypatch, local(18.1))
    assert care.door_state(db)["open"] is True


def test_pieces_she_hands_him_skip_the_door_and_he_is_told(monkeypatch):
    db = stocked()
    i = ids(db)
    clock(monkeypatch, local(15))
    signal(her_last_message_at=time.time() - 60, desire=5)
    life.update_item(db, i["P02"], {"state": "given"})
    assert "她把墨绿蕾丝边内裤交到你手里了" in wake(db)
    assert any(line["kind"] == "given" for line in life.chat_lines(db))
    out = life.use(db, {"codes": ["P02"], "journal": "x" * 20, "after": "closet"}, outlet="t")
    assert "door" not in out and state(db, "P02")["sneaked"] == 1
    life.wear(db, {"top": i["B02"], "old_to": "given"})
    assert state(db, "B01")["state"] == "given"


def test_open_door_wakes_him_once_in_six_hours(monkeypatch):
    db = stocked()
    life.wear(db, {"top": ids(db)["B02"]}, now=local(13.5))
    clock(monkeypatch, local(14))
    door_open(monkeypatch)
    first = due(db, local(14))
    assert first["kind"] == "door" and "柜子对你开着" in first["text"] and "还带着体温" in first["text"]
    assert care.due(db, local(15)) is None
    assert care.due(db, local(20.5))["kind"] == "door"


# ── her period ───────────────────────────────────────────────────────────────

def test_period_stock_and_reminder_ladder(monkeypatch):
    db = stocked()
    since = (datetime.strptime(life.day_of(time.time()), "%Y-%m-%d") - timedelta(days=2)).strftime("%Y-%m-%d")  # her 04:00 day, not midnight
    signal(period={"active": True, "since": since})
    assert care.period()["day"] == 3
    care.stock_set(db, "pad", 2)
    care.stock_set(db, "night_pants", 1)
    life.wear(db, {"bottom": "night_pants"}, now=local(7.5))
    assert care.stock_dict(db)["night_pants"]["count"] == 0
    assert "安睡裤用完了" in wake(db)
    assert care.due(db, local(8)) is None                          # before the day window
    care.stock_change(db, "pad", by="她", now=local(9))
    assert care.due(db, local(13.9)) is None
    first = due(db, local(14))
    assert first["kind"] == "pad" and "上次换是 09:00" in first["text"] and "卫生巾只剩 1 片" in first["text"]
    assert care.due(db, local(14.5)) is None
    assert due(db, local(15.6))["kind"] == "pad"                   # 1.5 h after the first
    assert care.due(db, local(17)) is None
    assert due(db, local(17.7))["kind"] == "pad"                   # then every 2 h
    care.stock_change(db, "pad", by="她", now=local(17.75))
    assert care.due(db, local(18)) is None
    assert care.due(db, local(22.8))["kind"] == "pad"
    assert care.due(db, local(23.5)) is None                       # the window closes at 23:00
    assert "换卫生巾" in life.recall_notices(db, local(12, 1))      # her message carries it and it counts as said
    assert care.due(db, local(12.2, 1)) is None
    signal(period={"active": False})
    assert care.due(db, local(15, 1)) is None


# ── the shower, his pick, tidying ────────────────────────────────────────────

def test_shower_asks_then_wakes_him(monkeypatch):
    db = stocked()
    t0 = local(21)
    clock(monkeypatch, t0)
    started = tools.dispatch("wardrobe_shower", {}, "t")
    assert started["minutes_left"] == 30 and tools.dispatch("wardrobe_shower", {}, "t")["id"] == started["id"]
    assert care.shower_prompt(db, t0 + 600)["prompt"] is None
    prompt = care.shower_prompt(db, t0 + 31 * 60)
    assert prompt["prompt"]["showing"] and [c["code"] for c in prompt["choices"]["top"]][-1] == "B01"  # worn last
    i = ids(db)
    life.wear(db, {"top": i["B02"], "shower_id": started["id"]}, now=t0 + 32 * 60)
    assert care.shower_prompt(db, t0 + 33 * 60)["prompt"] is None
    second = care.shower_start(db, by="她", outlet="page", now=t0 + 3600)
    assert care.due(db, t0 + 3600 + 45 * 60) is None
    nudge = due(db, t0 + 3600 + 51 * 60)
    assert nudge["kind"] == "shower" and "她还没点" in nudge["text"]
    assert care.due(db, t0 + 3600 + 52 * 60) is None
    care.shower_finish(db, second["id"], "skip")
    third = care.shower_start(db, by="她", outlet="page", now=t0 + 2 * 3600)
    life.advance(db, t0 + 9 * 3600)
    assert db.execute("SELECT done_how FROM wardrobe_showers WHERE id=?", (third["id"],)).fetchone()[0] == "expired"


def test_pick_for_tomorrow_and_tidy(monkeypatch):
    db = stocked()
    i = ids(db)
    t0 = local(22)
    clock(monkeypatch, t0)
    with pytest.raises(store.WardrobeError, match="not_pickable"):
        tools.dispatch("wardrobe_pick", {"top_code": "B01"}, "t")      # worn
    out = tools.dispatch("wardrobe_pick", {"top_code": "B03", "bottom_code": "P02", "line": "明天穿这套。"}, "t")
    assert out["picked"] == ["雾蓝无痕背心", "墨绿蕾丝边内裤"]   # 背心 already says what it is
    assert life.wardrobe_page(db)["pick"]["for"] == "明天"
    t1 = t0 + 11 * 3600
    life.wear(db, {"top": i["B03"]}, now=t1)
    assert "你挑的" not in wake(db, t1)                       # one slot still untouched today
    life.wear(db, {"bottom": i["P02"]}, now=t1 + 60)
    assert "她穿上了你挑的雾蓝无痕背心、墨绿蕾丝边内裤" in wake(db, t1 + 120)
    life.update_item(db, i["P03"], {"state": "drying"})
    with pytest.raises(store.WardrobeError, match="not_tidyable"):
        tools.dispatch("wardrobe_tidy", {"codes": ["B02"]}, "t")
    tidied = tools.dispatch("wardrobe_tidy", {"codes": ["P03"], "line": "收好了。"}, "t")
    assert tidied["tidied"] == ["雾蓝低腰内裤"] and state(db, "P03")["state"] == "closet"
    assert [x["text"] for x in life.chat_lines(db) if x["kind"] == "tidy"] == ["收好了。"]


def test_her_comment_reaches_him_once_and_he_can_answer(monkeypatch):
    db = stocked()
    clock(monkeypatch, local(12))
    door_open(monkeypatch)
    life.use(db, {"codes": ["P02"], "journal": "x" * 20, "after": "closet"}, outlet="t")
    life.add_comment(db, "use", 1, "你又来！")
    text = wake(db)
    assert "那次记录下面吐槽了：「你又来！」（吐槽 #1）" in text
    assert "吐槽" not in wake(db)
    reply = tools.dispatch("comment_reply", {"comment_id": 1, "text": "嗯。"}, "t")["reply"]
    uses = tools.dispatch("wardrobe_uses_read", {}, "t")["uses"]
    assert [c["author"] for c in uses[0]["comments"]] == ["her", "him"] and reply["reply_to"] == 1


# ── the HTTP server's two doors ──────────────────────────────────────────────

def test_http_page_and_agent_doors(monkeypatch):
    stocked()
    server = ThreadingHTTPServer(("127.0.0.1", 0), api.make_handler("a" * 40))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with opener.open(req, timeout=5) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")
    try:
        status, body = call("GET", "/api/v1/wardrobe")            # loopback: the page is let in
        assert status == 200 and len(body["items"]) == 6 and body["period"]["active"] is False
        assert call("GET", "/internal/v1/life/due")[0] == 401
        agent = {"Authorization": "Bearer " + "a" * 40}
        status, body = call("POST", "/internal/v1/tool/wardrobe_read", {"args": {}, "outlet": "t"}, agent)
        assert status == 200 and body["door"]["open"] is False
        status, body = call("POST", "/internal/v1/tool/wardrobe_use", {"args": {"codes": ["P02"], "journal": "x" * 20, "after": "closet"}}, agent)
        assert status == 409 and body["error"] == "door_closed"
        status, body = call("GET", "/internal/v1/tools", headers=agent)
        assert status == 200 and [t["name"] for t in body["tools"]] == list(tools.TOOL_NAMES)
        status, body = call("POST", "/api/v1/wardrobe/shower", {})
        assert status == 201 and body["shower"]["minutes_left"] == 30
        with opener.open(urllib.request.Request(base + "/app/records.html"), timeout=5) as r:
            assert r.status == 200 and b"<!doctype html>" in r.read().lower()
        assert call("GET", "/app/../README.md")[0] == 404
    finally:
        server.shutdown()


def test_signals_file_tolerates_everything(tmp_path):
    assert signals.her_last_message_at() is None and signals.desire() is None and signals.period()["active"] is False
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.SIGNALS_PATH.write_text("not json")
    assert signals.desire() is None
    signal(desire="150", her_last_message_at="abc", period={"active": True, "since": "yesterday?"})
    assert signals.desire() == 100.0 and signals.her_last_message_at() is None
    assert signals.period() == {"active": True, "day": None, "since": "yesterday?"}
