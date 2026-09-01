"""SPK-SV1 (docs/SERVICES-V2.md ب-۱۰) — minimal streamable-HTTP MCP server.

Question under test: does the real `claude` client inside a workspace container
(ecows_*) speak MCP over plain HTTP to a backend-side gateway, with the
workspace gateway key as Authorization, and complete a full agentic
tools/list -> tools/call round-trip in a headless turn?

This is a stand-in for the future `/mcp/svc/<slug>` gateway in the FastAPI
backend. Faithful parts: transport (streamable HTTP, JSON responses), auth
header check (401/403 like the production contract), read-only tool set
shaped like the Eco ops-DB pilot. Fake parts: canned data, no DB.

Stdlib only, mirrors spike/relay_spike.py conventions. Logs one JSON line per
request to stdout so the spike result is auditable.
"""
from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8899"))
EXPECTED_TOKEN = os.environ.get("EXPECTED_TOKEN", "")  # empty = accept any (not used)
SLUG = "eco-biz"

# Canned "Eco ops DB" — canary values the model must relay for the spike to pass.
TABLES = {
    "pickups": "جمع‌آوری‌ها: pickup_id, route_id, customer_id, kg, picked_at",
    "customers": "مشتری‌ها: customer_id, segment(b2c|b2b|b2g), zone, joined_at",
    "routes": "مسیرها: route_id, zone, vehicle_id, driver_id",
}
CANARY_TOTAL_KG = 48213

TOOLS = [
    {
        "name": "list_tables",
        "description": "فهرست جدول‌های دیتابیس عملیات اکو را برمی‌گرداند.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "run_query",
        "description": (
            "یک کوئری SELECT روی دیتابیس عملیات اکو اجرا می‌کند و ردیف‌ها را برمی‌گرداند. "
            "فقط SELECT مجاز است."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "کوئری SELECT"}},
            "required": ["sql"],
        },
    },
]


def _log(**kv) -> None:
    kv["ts"] = round(time.time(), 3)
    print(json.dumps(kv, ensure_ascii=False), flush=True)


def _tool_result(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _handle_rpc(msg: dict) -> dict | None:
    """Returns the JSON-RPC response object, or None for notifications."""
    method = msg.get("method")
    msg_id = msg.get("id")
    if msg_id is None:  # notification (e.g. notifications/initialized)
        return None
    if method == "initialize":
        proto = (msg.get("params") or {}).get("protocolVersion", "2025-03-26")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": proto,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": f"ecocode-svc-{SLUG}-spike", "version": "0.1"},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "list_tables":
            result = _tool_result(json.dumps(TABLES, ensure_ascii=False))
        elif name == "run_query":
            sql = str(args.get("sql", ""))
            if not sql.lstrip().lower().startswith(("select", "with")):
                result = {
                    "content": [{"type": "text", "text": "فقط SELECT مجاز است (سطح دسترسی: read)."}],
                    "isError": True,
                }
            else:
                # Deterministic canned answer regardless of the exact SELECT.
                result = _tool_result(
                    json.dumps(
                        {"rows": [{"total_kg": CANARY_TOTAL_KG}], "row_count": 1, "sql_executed": sql},
                        ensure_ascii=False,
                    )
                )
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": f"unknown tool: {name}"},
            }
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}
    # ping and anything else we don't implement
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"method not supported: {method}"},
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, obj: dict | None) -> None:
        body = b"" if obj is None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _authed(self) -> bool:
        got = self.headers.get("Authorization", "")
        return bool(EXPECTED_TOKEN) and got == f"Bearer {EXPECTED_TOKEN}"

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != f"/mcp/svc/{SLUG}":
            self._send_json(404, {"error": "unknown service"})
            return
        if not self._authed():
            _log(evt="denied", path=self.path, has_auth=bool(self.headers.get("Authorization")))
            self._send_json(401, {"error": "invalid or missing workspace key"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "bad json"})
            return
        # Batch or single
        msgs = msg if isinstance(msg, list) else [msg]
        responses = [r for m in msgs if isinstance(m, dict) for r in [_handle_rpc(m)] if r]
        for m in msgs:
            _log(
                evt="rpc",
                method=m.get("method"),
                tool=(m.get("params") or {}).get("name"),
                id=m.get("id"),
            )
        if not responses:
            self._send_json(202, None)  # notification(s) only
        elif isinstance(msg, list):
            self.send_response(200)
            body = json.dumps(responses, ensure_ascii=False).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send_json(200, responses[0])

    def do_GET(self) -> None:  # noqa: N802
        # We do not offer a server-initiated SSE stream; spec-compliant refusal.
        self._send_json(405, {"error": "no SSE stream; POST only"})

    def do_DELETE(self) -> None:  # noqa: N802
        self._send_json(200, None)  # stateless: session termination is a no-op

    def log_message(self, *_args) -> None:
        return


if __name__ == "__main__":
    if not EXPECTED_TOKEN:
        print("EXPECTED_TOKEN is required", file=sys.stderr)
        sys.exit(2)
    _log(evt="start", port=PORT, slug=SLUG)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
