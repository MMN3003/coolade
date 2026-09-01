"""Opt-in token-compression proxy (اصلاحیهٔ ۵ / amendment 5).

A transparent streaming reverse proxy that sits between the Claude Code CLI and the
real upstream. By default it forwards requests UNCHANGED (COMPRESS=0) — a safe, no-op
pass-through — so enabling the `compression` compose profile never silently changes
model behavior.

To actually cut tokens, plug a real compressor into `_maybe_compress` (e.g. an
LLMLingua sidecar, or tamp-style rules) and set COMPRESS=1. IMPORTANT: any edit to the
request body changes the byte prefix Anthropic uses for prompt caching, so a naive
compressor can *increase* cost by busting the cache — measure against real traffic
before enabling in production. That is why this ships as a scaffold, off by default.
"""
from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

TARGET = os.environ.get("UPSTREAM_TARGET", "https://api.anthropic.com").rstrip("/")
COMPRESS = os.environ.get("COMPRESS", "0") == "1"

# Hop-by-hop headers that must not be forwarded verbatim.
_HOP = {"host", "content-length", "connection", "keep-alive", "transfer-encoding", "accept-encoding"}

app = FastAPI()


def _fwd_headers(headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _HOP}


def _maybe_compress(body: bytes) -> bytes:
    """No-op unless COMPRESS=1. Real compression (LLMLingua/tamp) goes here."""
    if not COMPRESS:
        return body
    return body


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "target": TARGET, "compress": COMPRESS}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    body = _maybe_compress(await request.body())
    client = httpx.AsyncClient(timeout=None)
    upstream_req = client.build_request(
        request.method,
        f"{TARGET}/{path}",
        headers=_fwd_headers(request.headers),
        content=body,
        params=request.query_params,
    )
    resp = await client.send(upstream_req, stream=True)

    async def gen():
        try:
            async for chunk in resp.aiter_raw():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(gen(), status_code=resp.status_code, headers=_fwd_headers(resp.headers))
