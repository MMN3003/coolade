#!/usr/bin/env python3
"""Spike R5 (TECH v2 / P0): raw HTTP relay for Claude Code clients.

Question to answer with ground truth:
  If the CLIENT is Claude Code itself (sending its own identity: system prompt,
  anthropic-beta headers, user-agent) and the gateway ONLY injects the upstream
  OAuth token and relays bytes unchanged, do opus/sonnet work (no 429), do
  client-side tools round-trip, and can usage be read from the SSE stream?

This is a spike, not production code: stdlib only, localhost only, verbose log.

What it does per request:
  * replaces Authorization with the real OAuth access token from the local
    Claude Code credentials file (never logged);
  * guarantees `anthropic-beta: oauth-2025-04-20` is present (a Claude Code
    client sends it only when its OWN token looks like OAuth — with a gateway
    key like `eco-...` it may omit it, so the gateway must add it);
  * streams the response back unchanged (chunked), capturing:
      - status, anthropic-ratelimit-* headers (for V6 account-limit design),
      - usage objects from SSE events (message_start / message_delta),
      - request metadata: model, stream flag, tool count, system[0] prefix.
  * appends one JSON line per request to spike/relay.log
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import time
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

CREDS_PATH = Path(os.environ.get("RELAY_CREDS", Path.home() / ".claude" / ".credentials.json"))
BIND_HOST = os.environ.get("RELAY_HOST", "127.0.0.1")
UPSTREAM = "https://api.anthropic.com"
LISTEN_PORT = 8899
LOG_PATH = Path(os.environ.get("RELAY_LOG", Path(__file__).with_name("relay.log")))

OAUTH_BETA = "oauth-2025-04-20"
# hop-by-hop / recomputed headers we must not blindly copy in either direction
SKIP_REQ = {"host", "authorization", "x-api-key", "content-length", "connection",
            "accept-encoding"}
SKIP_RESP = {"transfer-encoding", "connection", "content-length", "content-encoding"}


def load_token() -> str:
    d = json.loads(CREDS_PATH.read_text())
    c = d.get("claudeAiOauth", d)
    return c["accessToken"]


TOKEN = load_token()
UP = urlsplit(UPSTREAM)


def log_line(obj: dict) -> None:
    obj["ts"] = round(time.time(), 3)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def summarize_request(path: str, body: bytes, headers) -> dict:
    meta: dict = {"path": path, "req_bytes": len(body)}
    # identity-relevant headers, values are not secrets
    for h in ("user-agent", "anthropic-beta", "anthropic-version", "x-app"):
        if headers.get(h):
            meta[f"h_{h.replace('-', '_')}"] = headers.get(h)
    try:
        j = json.loads(body)
        meta["model"] = j.get("model")
        meta["stream"] = j.get("stream")
        tools = j.get("tools") or []
        meta["n_tools"] = len(tools)
        if tools:
            meta["tool_names_first5"] = [t.get("name") for t in tools[:5]]
        sysv = j.get("system")
        if isinstance(sysv, str):
            meta["system0"] = sysv[:80]
        elif isinstance(sysv, list) and sysv:
            meta["system0"] = (sysv[0].get("text") or "")[:80]
        msgs = j.get("messages") or []
        meta["n_messages"] = len(msgs)
        # does the conversation carry tool_result blocks (proof of agentic loop)?
        meta["has_tool_result"] = any(
            isinstance(m.get("content"), list)
            and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])
            for m in msgs
        )
    except Exception:
        meta["body_parse"] = "not-json"
    return meta


def _balanced(s: str, start: int) -> str:
    """Return the JSON object substring starting at the '{' at index `start`."""
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return ""


def extract_usage(sse_text: str) -> dict:
    """Merge every `usage` object in the stream (message_start has input +
    cache tokens; message_delta has final output tokens). Proper brace-match,
    not a flat regex, because usage nests cache_creation objects."""
    out: dict = {}
    for m in re.finditer(r'"usage"\s*:\s*\{', sse_text):
        block = _balanced(sse_text, m.end() - 1)
        try:
            for k, v in json.loads(block).items():
                if isinstance(v, int) and v:
                    out[k] = max(out.get(k, 0), v)  # keep the largest seen per field
        except Exception:
            pass
    stop = re.search(r'"stop_reason"\s*:\s*"([a-z_]+)"', sse_text)
    if stop:
        out["stop_reason"] = stop.group(1)
    return out


class Relay(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _relay(self) -> None:
        t0 = time.time()
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else b""
        meta = summarize_request(self.path, body, self.headers)

        # --- build upstream request: copy everything except auth, inject token ---
        up_headers = {}
        for k, v in self.headers.items():
            if k.lower() not in SKIP_REQ:
                up_headers[k] = v
        up_headers["Authorization"] = f"Bearer {TOKEN}"
        up_headers["Host"] = UP.netloc
        beta = up_headers.get("anthropic-beta", "")
        if OAUTH_BETA not in beta:
            up_headers["anthropic-beta"] = f"{beta},{OAUTH_BETA}" if beta else OAUTH_BETA
            meta["beta_injected"] = True

        conn = http.client.HTTPSConnection(UP.netloc, context=ssl.create_default_context(), timeout=600)
        try:
            conn.request(self.command, self.path, body=body or None, headers=up_headers)
            resp = conn.getresponse()

            meta["status"] = resp.status
            ratelimits = {k: v for k, v in resp.getheaders() if "ratelimit" in k.lower()}
            if ratelimits:
                meta["ratelimit_headers"] = ratelimits
            ctype = resp.getheader("content-type", "")
            meta["resp_content_type"] = ctype

            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in SKIP_RESP:
                    self.send_header(k, v)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            captured = []
            while True:
                chunk = resp.read(16384)
                if not chunk:
                    break
                captured.append(chunk)
                self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")

            full = b"".join(captured)
            meta["resp_bytes"] = len(full)
            if "text/event-stream" in ctype:
                meta["usage"] = extract_usage(full.decode("utf-8", "replace"))
            elif resp.status != 200:
                meta["error_body"] = full[:400].decode("utf-8", "replace")
        except Exception as e:  # log and give the client a 502
            meta["relay_error"] = repr(e)
            try:
                self.send_error(502, "relay error")
            except Exception:
                pass
        finally:
            conn.close()
            meta["ms"] = int((time.time() - t0) * 1000)
            log_line(meta)

    do_POST = _relay
    do_GET = _relay

    def log_message(self, *a):  # silence default stderr noise; we log JSON lines
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else LISTEN_PORT
    if len(sys.argv) > 2:  # optional alternate credentials file (e.g. backend volume copy)
        CREDS_PATH = Path(sys.argv[2])
        TOKEN = load_token()
    LOG_PATH.write_text("")
    print(f"relay: {BIND_HOST}:{port} -> {UPSTREAM}  (log: {LOG_PATH})")
    ThreadingHTTPServer((BIND_HOST, port), Relay).serve_forever()
