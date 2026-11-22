"""One small HTTP server, standard library only.

    /app/…            the page (web/), static
    /api/v1/…         what the page calls (loopback, or a bearer page token when you expose it)
    /internal/v1/…    the agent's door (bearer agent token): tools, the lines for his wakes, her next message

Run it behind your own reverse proxy / access layer when it leaves the machine; it knows nothing about users."""
from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import mimetypes
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote

from . import care, life, store, tools

LOG = logging.getLogger("wardrobe")
WEB = Path(__file__).resolve().parent.parent / "web"
PUBLIC, INTERNAL, APP = "/api/v1", "/internal/v1", "/app/"
MAX_BODY = 64 * 1024


def make_handler(agent_token: str, page_token: str = ""):
    class Handler(BaseHTTPRequestHandler):
        server_version = "wardrobe/1"

        def log_message(self, fmt, *args):  # quiet; errors go through LOG
            pass

        # ── plumbing ──────────────────────────────────────────────────────
        def _json(self, status: int, payload) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise store.WardrobeError("body_too_large", 413)
            raw = self.rfile.read(length) if length else b""
            if not raw:
                return {}
            try:
                value = json.loads(raw.decode("utf-8"))
            except ValueError:
                raise store.WardrobeError("invalid_json") from None
            return value if isinstance(value, dict) else {}

        def _bearer(self) -> str:
            auth = self.headers.get("Authorization", "")
            return auth[7:].strip() if auth.startswith("Bearer ") else ""

        def _loopback(self) -> bool:
            try:
                return ipaddress.ip_address(self.client_address[0]).is_loopback
            except ValueError:
                return False

        def _page_allowed(self) -> bool:
            if page_token:
                return hmac.compare_digest(self._bearer(), page_token) or hmac.compare_digest(
                    self.headers.get("X-Page-Token", ""), page_token)
            return self._loopback()

        def _agent_allowed(self) -> bool:
            return bool(agent_token) and hmac.compare_digest(self._bearer(), agent_token)

        def _route(self, method: str) -> None:
            path, _, query = self.path.partition("?")
            path = unquote(path)
            q = {k: v[0] for k, v in parse_qs(query).items()}
            try:
                if path.startswith(APP):
                    return self._static(path[len(APP):])
                if path.startswith(PUBLIC + "/"):
                    if not self._page_allowed():
                        return self._json(403, {"error": "forbidden"})
                    return self._page(method, path[len(PUBLIC):], q)
                if path.startswith(INTERNAL + "/"):
                    if not self._agent_allowed():
                        return self._json(401, {"error": "unauthorized"})
                    return self._internal(method, path[len(INTERNAL):], q)
                if path in ("/", ""):
                    self.send_response(302)
                    self.send_header("Location", APP + "wardrobe.html")
                    self.end_headers()
                    return None
                return self._json(404, {"error": "not_found"})
            except store.WardrobeError as exc:
                return self._json(exc.status, {"error": exc.code, **exc.extra})
            except Exception as exc:  # noqa: BLE001
                LOG.warning("wardrobe request failed kind=%s", type(exc).__name__)
                return self._json(500, {"error": "internal"})

        def do_GET(self): self._route("GET")        # noqa: E704
        def do_POST(self): self._route("POST")      # noqa: E704
        def do_PUT(self): self._route("PUT")        # noqa: E704
        def do_PATCH(self): self._route("PATCH")    # noqa: E704
        def do_DELETE(self): self._route("DELETE")  # noqa: E704

        # ── the page's files ──────────────────────────────────────────────
        def _static(self, rel: str) -> None:
            target = (WEB / rel).resolve()
            if not rel or ".." in rel or not str(target).startswith(str(WEB.resolve())) or not target.is_file():
                return self._json(404, {"error": "not_found"})
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        # ── what the page calls ───────────────────────────────────────────
        def _page(self, method: str, path: str, q: dict) -> None:
            db = store.connect()
            try:
                if path == "/wardrobe" and method == "GET":
                    return self._json(200, life.wardrobe_page(db))
                if path == "/wardrobe" and method == "POST":
                    return self._json(201, {"item": life.create_item(db, self._body())})
                if path == "/wardrobe/slots" and method == "PUT":
                    return self._json(200, life.wear(db, self._body()))
                if path == "/wardrobe/chat-lines" and method == "GET":
                    return self._json(200, {"lines": life.chat_lines(db, float(q["since"]) if q.get("since") else None)})
                if path == "/wardrobe/prompt" and method == "GET":
                    return self._json(200, care.shower_prompt(db))
                if path == "/wardrobe/shower" and method == "POST":
                    return self._json(201, {"shower": care.shower_start(db, by="她", outlet="page")})
                m = re.fullmatch(r"/wardrobe/shower/(\d+)/done", path)
                if m and method == "POST":
                    return self._json(200, care.shower_finish(db, int(m.group(1)), str(self._body().get("how") or "later")))
                if path == "/wardrobe/stock" and method == "PUT":
                    body = self._body()
                    return self._json(200, {"stock": care.stock_set(db, body.get("kind"), body.get("count"))})
                if path == "/wardrobe/stock/change" and method == "POST":
                    return self._json(200, {"change": care.stock_change(db, self._body().get("kind"), by="她"),
                                            "stock": care.stock_dict(db)})
                if path == "/wardrobe/uses" and method == "GET":
                    return self._json(200, {"uses": life.list_uses(db, day=q.get("day") or None, item_id=q.get("item"),
                                                                   limit=int(q.get("limit") or 50))})
                m = re.fullmatch(r"/wardrobe/uses/(\d+)", path)
                if m and method == "DELETE":
                    return self._json(200, life.delete_use(db, int(m.group(1))))
                m = re.fullmatch(r"/wardrobe/uses/(\d+)/comments", path)
                if m and method == "POST":
                    return self._json(201, {"comment": life.add_comment(db, "use", int(m.group(1)), self._body().get("text"))})
                m = re.fullmatch(r"/wardrobe/(\d+)", path)
                if m and method == "PATCH":
                    return self._json(200, {"item": life.update_item(db, int(m.group(1)), self._body())})
                if m and method == "DELETE":
                    return self._json(200, life.delete_item(db, int(m.group(1))))
                m = re.fullmatch(r"/comments/(\d+)", path)
                if m and method == "PATCH":
                    return self._json(200, {"comment": life.edit_comment(db, int(m.group(1)), self._body().get("text"))})
                if m and method == "DELETE":
                    return self._json(200, life.delete_comment(db, int(m.group(1))))
                return self._json(404, {"error": "not_found"})
            finally:
                db.close()

        # ── the agent's door ──────────────────────────────────────────────
        def _internal(self, method: str, path: str, q: dict) -> None:
            m = re.fullmatch(r"/tool/([a-z_]+)", path)
            if m and method == "POST":
                body = self._body()
                return self._json(200, tools.dispatch(m.group(1), body.get("args") or {}, str(body.get("outlet") or "agent")))
            db = store.connect()
            try:
                if path == "/recall" and method == "POST":
                    # Her message has just arrived: anything the wardrobe wants to whisper to him rides along, once.
                    return self._json(200, {"context": life.recall_notices(db)})
                if path == "/life/next" and method == "GET":
                    return self._json(200, life.life_next(db))
                if path == "/life/due" and method == "GET":
                    return self._json(200, life.life_due(db))
                m = re.fullmatch(r"/life/([0-9a-f]{24})/sent", path)
                if m and method == "POST":
                    return self._json(200, life.life_sent(db, m.group(1)))
                if path == "/tools" and method == "GET":
                    return self._json(200, {"tools": [{"name": n, "description": tools.DESCRIPTIONS[n],
                                                       "parameters": {"type": "object", "properties": tools.SCHEMAS[n],
                                                                      "required": tools.REQUIRED.get(n, [])}}
                                                      for n in tools.TOOL_NAMES]})
                return self._json(404, {"error": "not_found"})
            finally:
                db.close()

    return Handler


def _tick(stop: threading.Event) -> None:
    """Once a minute: washes hang themselves up, dry pieces fold themselves, old showers expire."""
    while not stop.wait(60):
        try:
            db = store.connect()
            try:
                life.advance(db, time.time())
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("wardrobe tick failed kind=%s", type(exc).__name__)


def serve(host: str, port: int, agent_token: str, *, page_token: str = "") -> None:
    server = ThreadingHTTPServer((host, port), make_handler(agent_token, page_token))
    stop = threading.Event()
    threading.Thread(target=_tick, args=(stop,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
