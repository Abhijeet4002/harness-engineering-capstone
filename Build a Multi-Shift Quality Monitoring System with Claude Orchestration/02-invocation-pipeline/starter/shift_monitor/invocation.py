"""Three invocation shapes.

thin     — prompt only.
rich     — hot state + new defects.
resumed  — prior partial findings + new defects since the last manifest step.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .state import HotState

InvocationShape = Literal["thin", "rich", "resumed"]


@dataclass(frozen=True)
class Invocation:
    shape: InvocationShape
    prompt: str


def thin(prompt: str) -> Invocation:
    # TODO: Return an Invocation with shape="thin" and the prompt unchanged.
    # The thin shape is for one-shot calls that don't need any project state.
    return Invocation(shape="thin", prompt=prompt)


def rich(
    role: str, hot_state: HotState, new_defects: Sequence[Mapping[str, Any]]
) -> Invocation:
    # TODO: Build a rich prompt that includes:
    #   - A one-line role framing ("You are the on-call {role} for Northridge Plant 3.")
    #   - A "## Current hot state" section listing recent_defect_hashes,
    #     current_shift_summary, active_alerts, threshold_statuses.
    #   - A "## New defects since last shift" section enumerating each new defect
    #     (id / ts / shift / component / severity / description).
    #   - A trailing instruction asking for: Summary, Findings, Recommended
    #     actions, and an Updated hot state proposal as a JSON block.
    # Return an Invocation with shape="rich" and the rendered prompt.
    lines = []

    # Role framing
    lines.append(f"You are the on-call {role} for Northridge Plant 3.")
    lines.append("")

    # Current hot state section
    lines.append("## Current hot state")
    lines.append(f"Recent defect hashes: {', '.join(hot_state.recent_defect_hashes)}")
    lines.append(f"Summary: {hot_state.current_shift_summary}")
    lines.append(f"Active alerts: {', '.join(hot_state.active_alerts) if hot_state.active_alerts else '(none)'}")
    lines.append(f"Threshold statuses: {hot_state.threshold_statuses}")
    lines.append("")

    # New defects section
    lines.append("## New defects since last shift")
    for defect in new_defects:
        lines.append(
            f"- {defect['id']}: {defect['ts']} | {defect['shift']} | "
            f"{defect['component']} | {defect['severity']} | {defect['description']}"
        )
    if not new_defects:
        lines.append("(none)")
    lines.append("")

    # Trailing instruction
    lines.append("Please provide:")
    lines.append("1. Summary")
    lines.append("2. Findings")
    lines.append("3. Recommended actions")
    lines.append("4. Updated hot state proposal as a JSON block.")

    prompt = "\n".join(lines)
    return Invocation(shape="rich", prompt=prompt)


def resumed(
    session_id: str,
    summary: str,
    latest_message: str,
    prior_steps: Sequence[Mapping[str, Any]],
    new_defects: Sequence[Mapping[str, Any]],
) -> Invocation:
    # TODO: Build a resumed prompt with three required sections:
    #   - "## Prior partial findings" — one line per prior step, showing its
    #     `name` and a truncated representation of its `payload`.
    #   - "## Prior summary" — the supplied summary string.
    #   - "## New defects since last partial step" — enumerate new_defects
    #     (id / ts / component / severity / description), or "- (none)" if empty.
    # Close with the latest_message under "## Latest instruction".
    # Return an Invocation with shape="resumed".
    lines = []

    # Prior partial findings section
    lines.append("## Prior partial findings")
    for step in prior_steps:
        name = step.get("name", "unknown")
        payload = step.get("payload", {})
        payload_repr = str(payload)[:100]
        lines.append(f"- {name}: {payload_repr}")
    if not prior_steps:
        lines.append("(none)")
    lines.append("")

    # Prior summary section
    lines.append("## Prior summary")
    lines.append(summary)
    lines.append("")

    # New defects section
    lines.append("## New defects since last partial step")
    for defect in new_defects:
        lines.append(
            f"- {defect['id']}: {defect['ts']} | "
            f"{defect['component']} | {defect['severity']} | {defect['description']}"
        )
    if not new_defects:
        lines.append("- (none)")
    lines.append("")

    # Latest instruction
    lines.append("## Latest instruction")
    lines.append(latest_message)

    prompt = "\n".join(lines)
    return Invocation(shape="resumed", prompt=prompt)
