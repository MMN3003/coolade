"""In-memory per-conversation turn registry + ring buffer (TECH.md Issue A, section 5.1).

Deliberate design (TECH.md section 5.1, "انتخاب مکانیزم reattach"): a single
in-process registry, not redis/celery. backend runs as a single uvicorn
worker, so this is sufficient and "boring". A turn's background asyncio.Task
runs independently of any client connection; `GET /stream` (conversations.py)
attaches to the TurnState found here to replay-then-follow. If the process
restarts, all registry state and buffers are lost with it — that's the
accepted "کاوئت restart" (TECH.md): main.py's startup marks any row still
`status='streaming'` as `failed/aborted_restart` so the UI never waits
forever, and Issue C's retry endpoint lets the user resume.

Ring buffer cap: TECH.md specifies ~4096 events / ~4MB per turn; beyond that,
old *delta* events get merged (never dropped) so replay stays complete.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

_RING_BUFFER_CAP = 4096


@dataclass
class TurnState:
    conversation_id: int
    assistant_message_id: int
    events: list[dict[str, Any]] = field(default_factory=list)
    done: bool = False
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    created_at: float = field(default_factory=time.monotonic)

    async def append(self, event: dict[str, Any]) -> None:
        """event = {"event": "<sse-event-name>", "data": {...}}"""
        async with self.condition:
            self.events.append(event)
            if len(self.events) > _RING_BUFFER_CAP:
                self._compact()
            self.condition.notify_all()

    def _compact(self) -> None:
        """Merge the oldest consecutive `delta` events pairwise until back under cap.
        Never drops events (replay must stay complete) — only merges adjacent text deltas,
        which are safe to coalesce since the client just concatenates them anyway."""
        while len(self.events) > _RING_BUFFER_CAP:
            merged = False
            for i in range(len(self.events) - 1):
                a, b = self.events[i], self.events[i + 1]
                if a.get("event") == "delta" and b.get("event") == "delta":
                    a["data"]["text"] = a["data"].get("text", "") + b["data"].get("text", "")
                    del self.events[i + 1]
                    merged = True
                    break
            if not merged:
                break

    async def mark_done(self) -> None:
        async with self.condition:
            self.done = True
            self.condition.notify_all()


class TurnRegistry:
    """conversation_id -> TurnState for the turn currently in flight (if any).

    Only ever holds *active* turns. A turn is removed the instant its terminal
    event (done/error) lands — that's also what `generating` reflects. Any SSE
    consumer that already grabbed a reference to the TurnState keeps replaying
    it to completion regardless (plain Python reference lifetime — no extra
    bookkeeping needed, matches TECH.md's "بافر تا بسته‌شدن آخرین مشترک زنده
    می‌ماند").
    """

    def __init__(self) -> None:
        self._turns: dict[int, TurnState] = {}

    def start(self, conversation_id: int, assistant_message_id: int) -> TurnState:
        state = TurnState(conversation_id=conversation_id, assistant_message_id=assistant_message_id)
        self._turns[conversation_id] = state
        return state

    def get(self, conversation_id: int) -> TurnState | None:
        return self._turns.get(conversation_id)

    def is_generating(self, conversation_id: int) -> bool:
        return conversation_id in self._turns

    def finish(self, conversation_id: int, state: TurnState) -> None:
        # Guard against removing a *newer* turn that replaced this one (shouldn't
        # normally happen since try_acquire_conversation serializes turns per
        # conversation, but keep this defensive).
        if self._turns.get(conversation_id) is state:
            del self._turns[conversation_id]


registry = TurnRegistry()
