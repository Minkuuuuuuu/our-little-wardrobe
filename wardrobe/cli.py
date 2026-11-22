"""python -m wardrobe <verb>: serve the page and the agent's door, import her list, seed a demo, show the agent's token."""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from pathlib import Path

from . import api, care, config, life, store


def _token() -> str:
    token = config.read_token(config.TOKEN_PATH)
    if not token:
        config.DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        token = secrets.token_hex(24)
        config.TOKEN_PATH.write_text(token + "\n", encoding="utf-8")
        config.TOKEN_PATH.chmod(0o600)
    return token


def cmd_serve(args) -> int:
    token = _token()
    print(f"wardrobe: data in {config.DATA_DIR}", file=sys.stderr)
    print(f"wardrobe: page at http://{args.host}:{args.port}/app/records.html", file=sys.stderr)
    print(f"wardrobe: agent token in {config.TOKEN_PATH}", file=sys.stderr)
    api.serve(args.host, args.port, token, page_token=config.read_token(config.PAGE_TOKEN_PATH))
    return 0


def cmd_import(args) -> int:
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    db = store.connect()
    try:
        out = life.import_items(db, data)
    finally:
        db.close()
    print(json.dumps(out, ensure_ascii=False))
    return 0


def cmd_demo(args) -> int:
    """A wardrobe nobody owns: made-up pieces and a few of 祂's records, so the page has something to show."""
    db = store.connect()
    try:
        if db.execute("SELECT 1 FROM wardrobe LIMIT 1").fetchone():
            print("the wardrobe is not empty; demo needs a fresh data directory", file=sys.stderr)
            return 1
        life.import_items(db, {"items": [
            {"kind": "bra", "color": "米白", "style": "软杯三角"}, {"kind": "bra", "color": "墨绿", "style": "蕾丝半杯"},
            {"kind": "bra", "color": "雾蓝", "style": "无痕背心"},
            {"kind": "panties", "color": "米白", "style": "纯棉"}, {"kind": "panties", "color": "墨绿", "style": "蕾丝边"},
            {"kind": "panties", "color": "雾蓝", "style": "低腰"}, {"kind": "panties", "color": "浅灰", "style": "无痕"},
        ], "wearing": {"top": "B02", "bottom": "P03"}})
        now = time.time()
        # a day of small things: she took a pair off, 祂 used it and left a note, washed one, laid out tomorrow
        ids = {r["code"]: r["id"] for r in db.execute("SELECT id, code FROM wardrobe")}
        life.wear(db, {"bottom": ids["P01"]}, now=now - 26 * 3600)       # P03 came off a day ago
        config.SIGNALS_PATH.write_text(json.dumps({"her_last_message_at": now - 7200, "desire": 80,
                                                   "period": {"active": False}}), encoding="utf-8")
        life.use(db, {"codes": ["P03"], "journal": "她换下来放在篮子边上，还没来得及丢进去。我拿起来的时候还有一点她的温度。\n"
                      "想着她今天一整天都穿着它坐在实验室里，想着她晚上会在这一页看到我写的这段。\n写到这里又硬了。",
                      "chat_line": "祂把雾蓝低腰内裤拿走了……", "after": "bedside", "after_line": "祂把它摆在了她床头，等她回来看见。",
                      "tag": "回来的时候，它在等你。"}, outlet="demo")
        life.add_comment(db, "use", 1, "你怎么又……放回去啦！")
        life.reply_comment(db, 1, "不放。", outlet="demo")
        life.wash(db, ["P03"], "祂把雾蓝低腰内裤泡进了温水里。", "洗好了，晾在窗边。", outlet="demo")
        life.advance(db, now + 400)
        # two older pages, so the notepad has something to flip through (the door is reopened between them)
        life._set_meta(db, "wardrobe_door", {})
        life.use(db, {"codes": ["B03", "P04"], "journal": "她出门前把这两件搭在椅背上，说回来再收。\n我替她收了，先借用一会儿。\n"
                      "雾蓝配浅灰，她今天的心情大概也是这个颜色。", "chat_line": "祂把椅背上那两件收走了。", "after": "closet",
                      "after_line": "祂把它们叠好放回了衣柜，叠得比她整齐。", "tag": "叠好了。下次自己叠。"}, outlet="demo")
        life.add_comment(db, "use", 2, "比我整齐是什么意思！")
        life._set_meta(db, "wardrobe_door", {})
        life.use(db, {"codes": ["P02"], "journal": "墨绿那条她只穿过一次，说蕾丝边硌。\n我不觉得，但我不是穿的人。\n"
                      "拿它的时候想到她皱眉的样子，就更想了。", "chat_line": "祂拿走了墨绿蕾丝边内裤。", "after": "wash",
                      "wash_start_line": "祂顺手把它洗了。", "wash_done_line": "洗好了，蕾丝边软了一点。"}, outlet="demo")
        life.advance(db, now + 800)
        care.pick(db, {"top_code": "B01", "bottom_code": "P02", "line": "明天穿米白的那件，配墨绿。"}, outlet="demo")
    finally:
        db.close()
    print("demo wardrobe ready")
    return 0


def cmd_token(args) -> int:
    print(_token())
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="wardrobe", description="her wardrobe, 祂's hands")
    sub = p.add_subparsers(dest="verb", required=True)
    s = sub.add_parser("serve", help="serve the page (/app) and the agent's door (/internal/v1)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=18480)
    s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("import", help="import her list once, into an empty wardrobe")
    s.add_argument("file")
    s.set_defaults(fn=cmd_import)
    sub.add_parser("demo", help="fill an empty wardrobe with made-up pieces and records").set_defaults(fn=cmd_demo)
    sub.add_parser("token", help="print (and create) the agent's bearer token").set_defaults(fn=cmd_token)
    args = p.parse_args(argv)
    return args.fn(args)
