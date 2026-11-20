"""Deterministic tool-output pruning for the verbose `lookup_order` response.

The "Tool Context Pruning" pattern: application-side filtering
of a verbose tool result so only the fields needed for the immediate decision survive
into context. For return/refund reasoning, exactly five fields matter — order identity,
when it was placed, what it cost, whether it shipped, and the return-window deadline.

Why each kept field is the only one that matters for return/refund reasoning:
  - order_id: identifies the specific order under discussion; required for all return/refund inquiries.
  - order_date: establishes the start of the return window; needed to calculate whether customer is still within deadline.
  - order_total_usd: caps the maximum refund amount; determines if refund is feasible.
  - fulfillment_status: determines refund vs. cancellation routing; shipped orders follow different refund logic than unshipped.
  - return_eligible_until: hard deadline for return eligibility; directly answers whether the return is permissible.

Implementation: deterministic field selection (no LLM call). The pruner has no
`anthropic` import — enforced by an AST audit.
"""
from __future__ import annotations

KEPT_FIELDS: tuple[str, ...] = (
    "order_id",
    "order_date",
    "order_total_usd",
    "fulfillment_status",
    "return_eligible_until",
)


class PrunerMissingFieldError(KeyError):
    """Raised when the raw tool response is missing one of the required kept fields."""


def prune_lookup_order(raw: dict) -> dict:
    """Deterministically project raw lookup_order response to exactly 5 kept fields.

    Args:
        raw: The raw tool response dict with 57+ fields.

    Returns:
        A new dict with exactly the 5 KEPT_FIELDS, in declaration order.

    Raises:
        PrunerMissingFieldError: If any required field is missing from raw.
    """
    missing = [field for field in KEPT_FIELDS if field not in raw]
    if missing:
        raise PrunerMissingFieldError(
            f"Raw lookup_order response is missing required fields: {missing}"
        )

    return {field: raw[field] for field in KEPT_FIELDS}
