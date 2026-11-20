"""Tool schemas and dispatcher.

Seven tools, registered with Anthropic tool-use shape. The dispatcher returns
serialized JSON strings to be wrapped as `tool_result` content. Errors follow
the "Graceful Tool Failure" shape:

    {"is_error": true,
     "error_category": "transient"|"permanent",
     "is_retryable": bool,
     "message": "..."}

Errors are never raised to the loop.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claims_intake.session import ClaimSession

CLAIM_TYPES = ["property_damage", "theft", "liability", "auto"]
SEVERITIES = ["low", "medium", "high"]

# ----------------------------------------------------------------------------
# Schemas — passed verbatim to the Anthropic Messages API as the `tools` arg.
# ----------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "lookup_policy",
        "description": "Look up and retrieve the full policy record for a given policy ID. Use this early in the conversation to understand coverage, deductible, limits, and status. Call this tool when you need to verify the claimant's policy details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "policy_id": {
                    "type": "string",
                    "description": "The unique policy ID (e.g., POL-1001)",
                }
            },
            "required": ["policy_id"],
        },
    },
    {
        "name": "record_claim_fact",
        "description": "Record a single normalized fact about the claim, such as incident_date, location, items_lost, witness_statement, or any other relevant detail. Call this tool repeatedly to build up the case file as you gather information from the claimant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "description": "The name of the fact being recorded (e.g., 'incident_date', 'location', 'items_lost')",
                },
                "value": {
                    "type": "string",
                    "description": "The normalized value of the fact",
                },
            },
            "required": ["field", "value"],
        },
    },
    {
        "name": "classify_claim",
        "description": "Commit to a final claim type classification once you have gathered sufficient information. Provide a confidence score (0.0 to 1.0) and explain your reasoning. Use this tool when you are confident enough to assign a claim type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim_type": {
                    "type": "string",
                    "enum": CLAIM_TYPES,
                    "description": f"The claim type category. Must be one of: {', '.join(CLAIM_TYPES)}",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score from 0.0 to 1.0",
                },
                "rationale": {
                    "type": "string",
                    "description": "Explanation of why you classified the claim this way",
                },
            },
            "required": ["claim_type", "confidence", "rationale"],
        },
    },
    {
        "name": "assess_severity",
        "description": "Assess and commit to a severity level (low, medium, or high) based on the financial impact, extent of damage, or scope of the claim. Call this tool when you have enough context to determine severity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": SEVERITIES,
                    "description": f"Severity level. Must be one of: {', '.join(SEVERITIES)}",
                },
                "rationale": {
                    "type": "string",
                    "description": "Explanation of why you assigned this severity level",
                },
            },
            "required": ["severity", "rationale"],
        },
    },
    {
        "name": "request_clarification",
        "description": "Ask the claimant a clarifying question when there is ambiguity between claim types or missing critical information. Explain the ambiguity and ask for clarification.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The clarification question to ask",
                },
                "ambiguity_between": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of claim types or interpretations being disambiguated",
                },
            },
            "required": ["question", "ambiguity_between"],
        },
    },
    {
        "name": "route_to_adjuster",
        "description": "Route the claim to the appropriate adjuster queue after classification and severity assessment. This is a terminal action that ends the intake process.",
        "input_schema": {
            "type": "object",
            "properties": {
                "queue": {
                    "type": "string",
                    "enum": CLAIM_TYPES,
                    "description": f"The queue to route to. Must be one of: {', '.join(CLAIM_TYPES)}",
                },
                "claim_summary": {
                    "type": "string",
                    "description": "A brief summary of the claim for the adjuster",
                },
            },
            "required": ["queue", "claim_summary"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Escalate the claim to a human specialist when classification is ambiguous, information is contradictory, or the case requires human judgment. This is a terminal action.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "The reason for escalation",
                },
                "structured_summary": {
                    "type": "object",
                    "properties": {
                        "policy_id": {
                            "type": "string",
                            "description": "The policy ID",
                        },
                        "root_cause": {
                            "type": "string",
                            "description": "The root cause of ambiguity or concern",
                        },
                        "candidate_claim_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Possible claim types being considered",
                        },
                        "case_facts": {
                            "type": "object",
                            "description": "Key facts gathered so far",
                        },
                        "recommended_action": {
                            "type": "string",
                            "description": "Recommended action for the human reviewer",
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence level (0.0 to 1.0)",
                        },
                    },
                    "required": ["policy_id", "root_cause", "candidate_claim_types", "case_facts", "recommended_action", "confidence"],
                },
            },
            "required": ["reason", "structured_summary"],
        },
    },
]

# ----------------------------------------------------------------------------
# Errors — Graceful Tool Failure shape
# ----------------------------------------------------------------------------


def _err(category: str, retryable: bool, message: str) -> str:
    return json.dumps({
        "is_error": True,
        "error_category": category,
        "is_retryable": retryable,
        "message": message,
    })


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


# ----------------------------------------------------------------------------
# Tool implementations
# ----------------------------------------------------------------------------


def _t_lookup_policy(session: ClaimSession, inp: dict[str, Any]) -> str:
    policy_id = inp.get("policy_id")
    if not isinstance(policy_id, str):
        return _err("permanent", False, "policy_id must be a string")

    policy = session.policies.get(policy_id)
    if policy is None:
        return _err("permanent", False, f"policy {policy_id} not found")

    return _ok(policy)


def _t_record_claim_fact(session: ClaimSession, inp: dict[str, Any]) -> str:
    field = inp.get("field")
    value = inp.get("value")

    if not isinstance(field, str):
        return _err("permanent", False, "field must be a string")
    if not isinstance(value, str):
        return _err("permanent", False, "value must be a string")

    session.case_facts[field] = value

    return _ok({
        "recorded": True,
        "field": field,
        "case_facts_count": len(session.case_facts),
    })


def _t_classify_claim(session: ClaimSession, inp: dict[str, Any]) -> str:
    claim_type = inp.get("claim_type")
    confidence = inp.get("confidence")
    rationale = inp.get("rationale")

    if claim_type not in CLAIM_TYPES:
        return _err("permanent", False, f"claim_type must be one of {CLAIM_TYPES}")

    if not isinstance(confidence, (int, float)):
        return _err("permanent", False, "confidence must be a number")
    if not (0.0 <= confidence <= 1.0):
        return _err("permanent", False, "confidence must be between 0.0 and 1.0")

    if not isinstance(rationale, str):
        return _err("permanent", False, "rationale must be a string")

    session.classification = {
        "claim_type": claim_type,
        "confidence": confidence,
        "rationale": rationale,
    }

    return _ok({
        "recorded": True,
        "claim_type": claim_type,
        "confidence": confidence,
        "rationale": rationale,
    })


def _t_assess_severity(session: ClaimSession, inp: dict[str, Any]) -> str:
    severity = inp.get("severity")
    rationale = inp.get("rationale")

    if severity not in SEVERITIES:
        return _err("permanent", False, f"severity must be one of {SEVERITIES}")

    if not isinstance(rationale, str):
        return _err("permanent", False, "rationale must be a string")

    session.severity = {
        "severity": severity,
        "rationale": rationale,
    }

    return _ok({
        "recorded": True,
        "severity": severity,
        "rationale": rationale,
    })


def _t_request_clarification(session: ClaimSession, inp: dict[str, Any]) -> str:
    question = inp.get("question")
    ambiguity_between = inp.get("ambiguity_between")

    if not isinstance(question, str):
        return _err("permanent", False, "question must be a string")

    if not isinstance(ambiguity_between, list) or len(ambiguity_between) < 2:
        return _err("permanent", False, "ambiguity_between must be a list of at least 2 items")

    # Record the clarification asked
    session.clarifications_asked.append({
        "question": question,
        "ambiguity_between": ambiguity_between,
    })

    # Substring-match the question against clarification_responses
    question_lower = question.lower()
    for key, reply in session.clarification_responses.items():
        if key.lower() in question_lower:
            return _ok({"claimant_reply": reply})

    return _ok({"claimant_reply": "NO_RESPONSE"})


def _t_route_to_adjuster(session: ClaimSession, inp: dict[str, Any]) -> str:
    # Guard against double-terminal
    if session.terminal_called:
        return _err("permanent", False, "terminal action already called (cannot route after escalate or vice versa)")

    queue = inp.get("queue")
    claim_summary = inp.get("claim_summary")

    # Validate queue and claim_summary
    if queue not in CLAIM_TYPES:
        return _err("permanent", False, f"queue must be one of {CLAIM_TYPES}")

    if not isinstance(claim_summary, str):
        return _err("permanent", False, "claim_summary must be a string")

    # Require classification and severity
    if session.classification is None:
        return _err("permanent", False, "classify_claim must be called before routing")

    if session.severity is None:
        return _err("permanent", False, "assess_severity must be called before routing")

    # Build routing record
    routing_record = {
        "claim_id": session.claim_id,
        "policy_id": session.policy_id,
        "claim_type": session.classification["claim_type"],
        "severity": session.severity["severity"],
        "confidence": session.classification["confidence"],
        "rationale": session.classification["rationale"],
        "claim_summary": claim_summary,
        "case_facts": session.case_facts,
    }

    session.routing = routing_record

    # Append to queue file
    queue_file = session.run_dir / "queues" / f"{queue}.jsonl"
    _append_jsonl(queue_file, routing_record)

    return _ok({"routed": True, "queue": queue})


def _t_escalate_to_human(session: ClaimSession, inp: dict[str, Any]) -> str:
    # Guard against double-terminal
    if session.terminal_called:
        return _err("permanent", False, "terminal action already called (cannot escalate after route or vice versa)")

    reason = inp.get("reason")
    structured_summary = inp.get("structured_summary")

    # Validate reason
    if not isinstance(reason, str):
        return _err("permanent", False, "reason must be a string")

    # Validate structured_summary
    if not isinstance(structured_summary, dict):
        return _err("permanent", False, "structured_summary must be a dict")

    required_keys = {"policy_id", "root_cause", "candidate_claim_types", "case_facts", "recommended_action", "confidence"}
    missing_keys = required_keys - set(structured_summary.keys())
    if missing_keys:
        return _err("permanent", False, f"structured_summary missing required keys: {', '.join(sorted(missing_keys))}")

    # Build escalation record
    escalation_record = {
        "claim_id": session.claim_id,
        "policy_id": session.policy_id,
        "reason": reason,
        **structured_summary,
        "case_facts_at_escalation": session.case_facts,
    }

    session.escalation = escalation_record

    # Append to escalations file
    escalations_file = session.run_dir / "escalations.jsonl"
    _append_jsonl(escalations_file, escalation_record)

    return _ok({"escalated": True})


# ----------------------------------------------------------------------------
# Dispatcher
# ----------------------------------------------------------------------------


_DISPATCH = {
    "lookup_policy": _t_lookup_policy,
    "record_claim_fact": _t_record_claim_fact,
    "classify_claim": _t_classify_claim,
    "assess_severity": _t_assess_severity,
    "request_clarification": _t_request_clarification,
    "route_to_adjuster": _t_route_to_adjuster,
    "escalate_to_human": _t_escalate_to_human,
}


def make_executor(session: ClaimSession) -> Executor:
    """Return a ToolExecutor callable bound to this session."""

    def execute(name: str, tool_input: dict[str, Any]) -> str:
        handler = _DISPATCH.get(name)
        if handler is None:
            return _err("permanent", False, f"unknown tool: {name}")
        try:
            return handler(session, tool_input)
        except Exception as exc:
            # Defensive: anything raised inside a handler becomes a graceful error,
            # never crashes the loop.
            return _err("transient", True, f"{type(exc).__name__}: {exc}")

    return execute


# Type alias for clarity; the loop only sees a Callable.
Executor = Any


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
