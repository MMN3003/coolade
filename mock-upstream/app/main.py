"""mode `mock`: a canned stand-in for the Claude-compatible upstream (TECH.md section 4.3).

Used only by the API-key passthrough path (via the litellm custom handler). No
credentials are required or checked — this exists purely so the whole stack
can bring up and be exercised end-to-end without any real upstream account.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="mock-upstream")

CANNED_CHUNKS = ["سلام! ", "این یک پاسخ ", "قوطی‌شده از ", "mock-upstream است."]
FAKE_USAGE = {
    "input_tokens": 25,
    "output_tokens": 40,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 10,
}

# Magic prompt trigger: a message containing e.g. `mock_error_429` makes this
# endpoint answer with that HTTP status and an Anthropic-shaped error body, so
# the whole error-propagation chain (handler → litellm → backend) can be
# exercised end-to-end in mode mock.
_ERROR_TRIGGER = re.compile(r"mock_error_(\d{3})")
_ERROR_TYPES = {
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    429: "rate_limit_error",
    500: "api_error",
    529: "overloaded_error",
}


def _find_error_trigger(body: dict) -> int | None:
    for m in body.get("messages", []):
        content = m.get("content")
        if isinstance(content, list):
            text = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
        else:
            text = str(content or "")
        match = _ERROR_TRIGGER.search(text)
        if match:
            return int(match.group(1))
    return None


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


@app.post("/v1/messages")
async def messages(request: Request) -> Any:
    body = await request.json()
    model = body.get("model", "mock-model")
    stream = bool(body.get("stream", False))
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    error_status = _find_error_trigger(body)
    if error_status is not None:
        return JSONResponse(
            status_code=error_status,
            content={
                "type": "error",
                "error": {
                    "type": _ERROR_TYPES.get(error_status, "api_error"),
                    "message": f"mock-upstream simulated {error_status}",
                },
            },
        )

    if not stream:
        return JSONResponse(
            {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": "".join(CANNED_CHUNKS)}],
                "stop_reason": "end_turn",
                "usage": FAKE_USAGE,
            }
        )

    async def gen():
        yield _sse(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": model,
                    "usage": {"input_tokens": FAKE_USAGE["input_tokens"], "output_tokens": 0},
                },
            },
        )
        yield _sse(
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        )
        for chunk in CANNED_CHUNKS:
            yield _sse(
                "content_block_delta",
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": chunk}},
            )
            time.sleep(0.03)
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
        yield _sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": FAKE_USAGE,
            },
        )
        yield _sse("message_stop", {"type": "message_stop"})

    return StreamingResponse(gen(), media_type="text/event-stream")
