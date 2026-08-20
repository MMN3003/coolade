"""Thin async client around the LiteLLM proxy admin + inference API."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()


class UpstreamServiceError(Exception):
    """LiteLLM's inference API answered non-2xx — usually the relayed status of the
    real upstream service (429 rate limit, 401/403 auth, 529 overloaded, …)."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"litellm returned {status_code}: {detail}")


class LiteLLMClient:
    def __init__(self) -> None:
        self._base_url = settings.litellm_base_url.rstrip("/")
        self._master_key = settings.litellm_master_key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._master_key}",
            "Content-Type": "application/json",
        }

    async def key_generate(
        self,
        *,
        models: list[str],
        metadata: dict[str, Any],
        max_budget: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"models": models, "metadata": metadata}
        if max_budget is not None:
            payload["max_budget"] = max_budget
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/key/generate", headers=self._headers(), json=payload
            )
            resp.raise_for_status()
            return resp.json()

    async def key_delete(self, litellm_key: str) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/key/delete",
                headers=self._headers(),
                json={"keys": [litellm_key]},
            )
            if resp.status_code >= 400:
                # already gone / not found — non-fatal for revoke flows
                return

    async def key_update(self, litellm_key: str, *, models: list[str]) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/key/update",
                headers=self._headers(),
                json={"key": litellm_key, "models": models},
            )
            resp.raise_for_status()

    async def stream_chat(
        self,
        path: str,
        body: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream raw SSE bytes from litellm for /v1/messages or /v1/chat/completions."""
        payload = dict(body)
        if metadata:
            payload.setdefault("metadata", {}).update(metadata)
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}{path}",
                headers=self._headers(),
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    detail = (await resp.aread()).decode("utf-8", "replace")
                    raise UpstreamServiceError(resp.status_code, detail[:500])
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk

    async def call_chat(
        self,
        path: str,
        body: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(body)
        if metadata:
            payload.setdefault("metadata", {}).update(metadata)
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}{path}", headers=self._headers(), json=payload
            )
            if resp.status_code >= 400:
                raise UpstreamServiceError(resp.status_code, resp.text[:500])
            return resp.json()


litellm_client = LiteLLMClient()
