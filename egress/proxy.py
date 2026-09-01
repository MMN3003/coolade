"""اصلاحیهٔ ۶ / amendment 6 — egress allowlist proxy (Stage 2, security-critical).

The sandbox container has NO direct internet: its only route out is this proxy
(via HTTPS_PROXY). It permits HTTPS only to an explicit host allowlist (ALLOW_HOSTS)
via CONNECT, and refuses everything else. This is what protects the injected upstream
token from exfiltration by malicious code running in the sandbox — without it, Stage 2
must NOT be enabled.

Pure stdlib (no deps). Allowlist is exact-host match (case-insensitive); a leading dot
entry (".ecobin.ir") also matches subdomains.
"""
from __future__ import annotations

import os
import select
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))
_RAW = [h.strip().lower() for h in os.environ.get("ALLOW_HOSTS", "").split(",") if h.strip()]
EXACT = {h for h in _RAW if not h.startswith(".")}
SUFFIX = tuple(h for h in _RAW if h.startswith("."))


def _allowed(host: str) -> bool:
    host = host.lower()
    if host in EXACT:
        return True
    return any(host.endswith(sfx) or host == sfx[1:] for sfx in SUFFIX)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_CONNECT(self) -> None:  # noqa: N802
        host, _, port_s = self.path.partition(":")
        try:
            port = int(port_s or "443")
        except ValueError:
            self.send_error(400, "bad target")
            return
        if not _allowed(host):
            self.send_error(403, "egress host not allowed")
            return
        try:
            upstream = socket.create_connection((host, port), timeout=10)
        except OSError:
            self.send_error(502, "upstream connect failed")
            return
        self.send_response(200, "Connection Established")
        self.end_headers()
        self._tunnel(self.connection, upstream)

    def _tunnel(self, client: socket.socket, upstream: socket.socket) -> None:
        socks = [client, upstream]
        try:
            while True:
                readable, _, _ = select.select(socks, [], [], 120)
                if not readable:
                    break
                for s in readable:
                    other = upstream if s is client else client
                    data = s.recv(65536)
                    if not data:
                        return
                    other.sendall(data)
        except OSError:
            return
        finally:
            for s in socks:
                try:
                    s.close()
                except OSError:
                    pass

    def _deny(self) -> None:
        self.send_error(405, "only CONNECT (HTTPS) is permitted")

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = do_OPTIONS = do_PATCH = _deny  # type: ignore[assignment]

    def log_message(self, *_args) -> None:  # silence default logging
        return


if __name__ == "__main__":
    print(f"egress allowlist proxy on :{PORT}; allow={sorted(EXACT)} suffix={list(SUFFIX)}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
