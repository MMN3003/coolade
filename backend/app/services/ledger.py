"""Usage ledger: credit calculation and insertion — the quota source of truth."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Model, UsageLedger


def credit_breakdown(
    model: Model,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
) -> dict[str, Decimal]:
    """Per-component credits with the model's CURRENT weights (admin display only;
    the stored `credits` column stays the billing truth)."""
    q = Decimal("0.0001")
    return {
        "input": (Decimal(input_tokens) / Decimal(1000) * model.input_weight).quantize(q, rounding=ROUND_HALF_UP),
        "output": (Decimal(output_tokens) / Decimal(1000) * model.output_weight).quantize(q, rounding=ROUND_HALF_UP),
        "cache_read": (Decimal(cache_read_tokens) / Decimal(1000) * model.cache_read_weight).quantize(
            q, rounding=ROUND_HALF_UP
        ),
    }


def compute_credits(
    model: Model,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
) -> Decimal:
    credits = (
        Decimal(input_tokens) / Decimal(1000) * model.input_weight
        + Decimal(output_tokens) / Decimal(1000) * model.output_weight
        + Decimal(cache_read_tokens) / Decimal(1000) * model.cache_read_weight
    )
    return credits.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


async def record_usage(
    db: AsyncSession,
    *,
    user_id: int,
    model: Model,
    surface: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    api_key_id: int | None = None,
    request_id: str | None = None,
    conversation_id: int | None = None,
    message_id: int | None = None,
    thinking_level: str | None = None,
) -> UsageLedger:
    credits = compute_credits(model, input_tokens, output_tokens, cache_read_tokens)
    entry = UsageLedger(
        message_id=message_id,
        thinking_level=thinking_level,
        user_id=user_id,
        api_key_id=api_key_id,
        conversation_id=conversation_id,
        model_id=model.id,
        surface=surface,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        credits=credits,
        request_id=request_id,
    )
    db.add(entry)
    await db.flush()
    return entry
