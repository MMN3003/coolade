"""Minimal SSE byte-stream -> JSON event parser (used to read litellm's OpenAI-shaped stream)."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator


async def iter_sse_json(byte_iter: AsyncIterator[bytes]) -> AsyncIterator[dict | None]:
    """Yield parsed JSON payloads from `data: ...` SSE lines. Yields None on `[DONE]`."""
    buffer = b""
    async for chunk in byte_iter:
        buffer += chunk
        while b"\n\n" in buffer:
            raw_event, buffer = buffer.split(b"\n\n", 1)
            for line in raw_event.split(b"\n"):
                line = line.strip()
                if not line.startswith(b"data:"):
                    continue
                payload = line[len(b"data:") :].strip()
                if payload == b"[DONE]":
                    yield None
                    return
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue
