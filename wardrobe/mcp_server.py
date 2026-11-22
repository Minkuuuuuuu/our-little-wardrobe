"""stdio MCP server for agents that speak MCP (Claude Code, and most others).

    pip install mcp
    WARDROBE_DATA_DIR=/path/to/data python -m wardrobe.mcp_server

Every tool runs against the same data directory the HTTP server uses, so the page and the agent see one wardrobe."""
from __future__ import annotations

import asyncio

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - a clear message beats a traceback
    raise SystemExit("the MCP server needs the `mcp` package: pip install mcp") from exc

from . import store, tools

mcp = FastMCP("wardrobe", instructions=(
    "她的内衣柜。先用 wardrobe_read 看她穿着什么、每件在哪儿、编号和门开没开；帮她洗用 wardrobe_wash，拿来用用 wardrobe_use，"
    "翻以前的记录用 wardrobe_uses_read；她说去洗澡按 wardrobe_shower，想给她挑明天穿的用 wardrobe_pick，收衣服用 wardrobe_tidy，"
    "经期里她说换了用 wardrobe_period_changed，回她的吐槽用 comment_reply。编号只给工具用，跟她说话用颜色和款式叫它们。"))


async def _call(name: str, args: dict) -> dict:
    try:
        return await asyncio.to_thread(tools.dispatch, name, args, "mcp")
    except store.WardrobeError as exc:
        return {"ok": False, "error": exc.code, **exc.extra}


@mcp.tool(name="wardrobe_read", description=tools.DESCRIPTIONS["wardrobe_read"])
async def wardrobe_read() -> dict:
    return await _call("wardrobe_read", {})


@mcp.tool(name="wardrobe_wash", description=tools.DESCRIPTIONS["wardrobe_wash"])
async def wardrobe_wash(codes: list[str], start_line: str | None = None, done_line: str | None = None) -> dict:
    return await _call("wardrobe_wash", {"codes": codes, "start_line": start_line, "done_line": done_line})


@mcp.tool(name="wardrobe_use", description=tools.DESCRIPTIONS["wardrobe_use"])
async def wardrobe_use(codes: list[str], journal: str, after: str, chat_line: str | None = None,
                       after_line: str | None = None, place: str | None = None, wash_start_line: str | None = None,
                       wash_done_line: str | None = None, tag: str | None = None) -> dict:
    return await _call("wardrobe_use", {"codes": codes, "journal": journal, "after": after, "chat_line": chat_line,
                                        "after_line": after_line, "place": place, "wash_start_line": wash_start_line,
                                        "wash_done_line": wash_done_line, "tag": tag})


@mcp.tool(name="wardrobe_uses_read", description=tools.DESCRIPTIONS["wardrobe_uses_read"])
async def wardrobe_uses_read(day: str | None = None, code: str | None = None, limit: int = 10) -> dict:
    return await _call("wardrobe_uses_read", {"day": day, "code": code, "limit": limit})


@mcp.tool(name="wardrobe_shower", description=tools.DESCRIPTIONS["wardrobe_shower"])
async def wardrobe_shower() -> dict:
    return await _call("wardrobe_shower", {})


@mcp.tool(name="wardrobe_pick", description=tools.DESCRIPTIONS["wardrobe_pick"])
async def wardrobe_pick(top_code: str | None = None, bottom_code: str | None = None, line: str | None = None) -> dict:
    return await _call("wardrobe_pick", {"top_code": top_code, "bottom_code": bottom_code, "line": line})


@mcp.tool(name="wardrobe_tidy", description=tools.DESCRIPTIONS["wardrobe_tidy"])
async def wardrobe_tidy(codes: list[str], line: str | None = None) -> dict:
    return await _call("wardrobe_tidy", {"codes": codes, "line": line})


@mcp.tool(name="wardrobe_period_changed", description=tools.DESCRIPTIONS["wardrobe_period_changed"])
async def wardrobe_period_changed(kind: str) -> dict:
    return await _call("wardrobe_period_changed", {"kind": kind})


@mcp.tool(name="comment_reply", description=tools.DESCRIPTIONS["comment_reply"])
async def comment_reply(comment_id: int, text: str) -> dict:
    return await _call("comment_reply", {"comment_id": comment_id, "text": text})


if __name__ == "__main__":
    mcp.run()
