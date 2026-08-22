"""LiteLLM custom provider handler for the API-key passthrough path only
(TECH.md sections 2, 4, 6 — amendment 1: web chat never goes through litellm).

Mounted read-only into the official litellm proxy image at
/app/ecocode_upstream_handler.py and registered via litellm_config.yaml's
`custom_provider_map`. This file is intentionally the ONLY thing that needs
to change if the upstream service's connection mechanism changes (TECH.md
R3) — it is a dumb HTTP relay:

  1. asks backend's internal `/internal/upstream-config` for the effective
     mode + resolved plaintext credential (backend owns all DB/crypto/host
     credential-file access; this container has none of that);
  2. forwards the request, in genuine Anthropic Messages API shape, to
     `$UPSTREAM_BASE_URL/v1/messages` (or the mock upstream in mode mock);
  3. reports the *real* usage (including cache_read/cache_write tokens,
     which litellm's own streaming-chunk usage schema does not carry) back
     to backend's `/internal/usage-report`, keyed by the `x-ecocode-request-id`
     header backend attaches via `extra_headers` — so usage_ledger stays
     authoritative regardless of what litellm's own usage accounting shows.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator

import httpx
import litellm
from litellm import CustomLLM
from litellm.types.utils import Usage

BACKEND_INTERNAL_URL = os.environ.get("BACKEND_INTERNAL_URL", "http://backend:8000")
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")

_CONFIG_TTL_SECONDS = 15.0
_config_cache: dict[str, Any] = {"value": None, "ts": 0.0}


async def _get_upstream_config() -> dict[str, Any]:
    now = time.time()
    cached = _config_cache["value"]
    if cached and (now - _config_cache["ts"]) < _CONFIG_TTL_SECONDS:
        return cached
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{BACKEND_INTERNAL_URL}/internal/upstream-config",
                headers={"Authorization": f"Bearer {LITELLM_MASTER_KEY}"},
            )
            resp.raise_for_status()
            cfg = resp.json()
    except Exception:
        # Resilience fallback if backend is briefly unreachable: mock target, no creds.
        cfg = {
            "mode": "mock",
            "base_url": os.environ.get("MOCK_UPSTREAM_BASE", "http://mock-upstream:8080"),
            "api_key": None,
            "auth_header": None,
            "oauth_beta": False,
        }
    _config_cache["value"] = cfg
    _config_cache["ts"] = now
    return cfg


async def _report_usage(request_id: str | None, usage: dict[str, Any], upstream_request_id: str | None) -> None:
    if not request_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{BACKEND_INTERNAL_URL}/internal/usage-report",
                headers={"Authorization": f"Bearer {LITELLM_MASTER_KEY}"},
                json={
                    "request_id": request_id,
                    "input_tokens": int(usage.get("input_tokens", 0) or 0),
                    "output_tokens": int(usage.get("output_tokens", 0) or 0),
                    "cache_read_tokens": int(usage.get("cache_read_input_tokens", 0) or 0),
                    "cache_write_tokens": int(usage.get("cache_creation_input_tokens", 0) or 0),
                    "upstream_request_id": upstream_request_id,
                },
            )
    except Exception:
        pass


def _raise_upstream_http_error(status_code: int, detail: str, model: str) -> None:
    """Re-raise an upstream non-2xx as a litellm exception that carries the real
    status_code — a bare httpx raise_for_status gets wrapped by litellm into
    APIConnectionError and the proxy answers 500, which hides 429/401/… from
    backend's client-facing error mapping."""
    message = f"ecocode upstream returned {status_code}: {detail[:500]}"
    provider = "ecocode-upstream"
    # Synthetic response: some litellm exception classes require `response` positionally.
    response = httpx.Response(
        status_code=status_code, request=httpx.Request("POST", "http://upstream/v1/messages")
    )
    if status_code == 401:
        raise litellm.AuthenticationError(
            message=message, llm_provider=provider, model=model, response=response
        )
    if status_code == 403:
        raise litellm.PermissionDeniedError(
            message=message, llm_provider=provider, model=model, response=response
        )
    if status_code == 404:
        raise litellm.NotFoundError(
            message=message, llm_provider=provider, model=model, response=response
        )
    if status_code == 429:
        raise litellm.RateLimitError(
            message=message, llm_provider=provider, model=model, response=response
        )
    # Anything else (including Anthropic's 529 overloaded) keeps its code verbatim.
    raise litellm.APIError(
        status_code=status_code,
        message=message,
        llm_provider=provider,
        model=model,
        request=httpx.Request("POST", "http://upstream/v1/messages"),
    )


def _anthropic_headers(cfg: dict[str, Any]) -> dict[str, str]:
    headers = {"anthropic-version": "2023-06-01", "content-type": "application/json"}
    if cfg.get("auth_header") == "bearer":
        headers["Authorization"] = f"Bearer {cfg.get('api_key') or ''}"
        if cfg.get("oauth_beta"):
            headers["anthropic-beta"] = "oauth-2025-04-20"
    elif cfg.get("auth_header") == "x-api-key":
        headers["x-api-key"] = cfg.get("api_key") or ""
    return headers


def _model_name(model: str, cfg: dict[str, Any] | None = None) -> str:
    key = model.split("/", 1)[1] if "/" in model else model
    # Map internal model key → upstream model id (e.g. claude-sonnet → claude-sonnet-5);
    # without this the internal key leaks upstream and real services 404.
    if cfg:
        return (cfg.get("model_map") or {}).get(key, key)
    return key


def _to_anthropic_body(model_name: str, messages: list[dict], optional_params: dict) -> dict:
    system_text = None
    anthropic_messages = []
    for m in messages:
        if m.get("role") == "system":
            content = m.get("content")
            system_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            continue
        anthropic_messages.append({"role": m.get("role"), "content": m.get("content")})
    body: dict[str, Any] = {
        "model": model_name,
        "messages": anthropic_messages,
        "max_tokens": optional_params.get("max_tokens") or 1024,
    }
    if system_text:
        body["system"] = system_text
    if optional_params.get("temperature") is not None:
        body["temperature"] = optional_params["temperature"]
    return body


class EcoCodeUpstreamAdapter(CustomLLM):
    async def acompletion(
        self,
        model,
        messages,
        api_base,
        custom_prompt_dict,
        model_response,
        print_verbose,
        encoding,
        api_key,
        logging_obj,
        optional_params,
        acompletion=None,
        litellm_params=None,
        logger_fn=None,
        headers=None,
        timeout=None,
        client=None,
    ):
        headers = headers or {}
        cfg = await _get_upstream_config()
        model_name = _model_name(model, cfg)
        body = _to_anthropic_body(model_name, messages, optional_params)
        body["stream"] = False

        async with httpx.AsyncClient(timeout=120) as http_client:
            resp = await http_client.post(
                f"{cfg['base_url']}/v1/messages", json=body, headers=_anthropic_headers(cfg)
            )
            if resp.status_code >= 400:
                _raise_upstream_http_error(resp.status_code, resp.text, model)
            data = resp.json()

        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage") or {}
        request_id = headers.get("x-ecocode-request-id")
        await _report_usage(request_id, usage, data.get("id"))

        result = litellm.completion(model="gpt-3.5-turbo", mock_response=text)
        result.model = model
        result.usage = Usage(
            prompt_tokens=int(usage.get("input_tokens", 0) or 0),
            completion_tokens=int(usage.get("output_tokens", 0) or 0),
            total_tokens=int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0),
            cache_read_input_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
            cache_creation_input_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
        )
        return result

    async def astreaming(
        self,
        model,
        messages,
        api_base,
        custom_prompt_dict,
        model_response,
        print_verbose,
        encoding,
        api_key,
        logging_obj,
        optional_params,
        acompletion=None,
        litellm_params=None,
        logger_fn=None,
        headers=None,
        timeout=None,
        client=None,
    ) -> AsyncIterator[dict]:
        headers = headers or {}
        cfg = await _get_upstream_config()
        model_name = _model_name(model, cfg)
        body = _to_anthropic_body(model_name, messages, optional_params)
        body["stream"] = True
        request_id = headers.get("x-ecocode-request-id")

        usage_accum = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }
        upstream_msg_id: str | None = None

        async with httpx.AsyncClient(timeout=None) as http_client:
            async with http_client.stream(
                "POST", f"{cfg['base_url']}/v1/messages", json=body, headers=_anthropic_headers(cfg)
            ) as resp:
                if resp.status_code >= 400:
                    detail = (await resp.aread()).decode("utf-8", "replace")
                    _raise_upstream_http_error(resp.status_code, detail, model)
                buffer = b""
                async for raw in resp.aiter_bytes():
                    buffer += raw
                    while b"\n\n" in buffer:
                        event_bytes, buffer = buffer.split(b"\n\n", 1)
                        data_line = None
                        for line in event_bytes.split(b"\n"):
                            if line.startswith(b"data:"):
                                data_line = line[len(b"data:") :].strip()
                        if not data_line:
                            continue
                        try:
                            obj = json.loads(data_line)
                        except json.JSONDecodeError:
                            continue
                        obj_type = obj.get("type")
                        if obj_type == "message_start":
                            msg = obj.get("message") or {}
                            upstream_msg_id = msg.get("id")
                            mu = msg.get("usage") or {}
                            usage_accum["input_tokens"] = mu.get("input_tokens", 0)
                        elif obj_type == "content_block_delta":
                            text = (obj.get("delta") or {}).get("text", "")
                            if text:
                                yield {
                                    "text": text,
                                    "is_finished": False,
                                    "finish_reason": "",
                                    "usage": None,
                                    "index": 0,
                                }
                        elif obj_type == "message_delta":
                            mu = obj.get("usage") or {}
                            for k in ("output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                                if k in mu:
                                    usage_accum[k] = mu[k]

        await _report_usage(request_id, usage_accum, upstream_msg_id)

        yield {
            "text": "",
            "is_finished": True,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": usage_accum["input_tokens"],
                "completion_tokens": usage_accum["output_tokens"],
                "total_tokens": usage_accum["input_tokens"] + usage_accum["output_tokens"],
            },
            "index": 0,
        }


adapter = EcoCodeUpstreamAdapter()
