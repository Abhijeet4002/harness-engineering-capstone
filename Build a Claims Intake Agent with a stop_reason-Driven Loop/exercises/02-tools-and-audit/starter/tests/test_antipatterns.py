"""Anti-pattern audit.

Verifies, by static AST analysis, that the agentic loop does NOT:
- use string-membership tests against text content to drive control flow
- use an integer-literal iteration cap as its primary stopping mechanism
- omit reference to `stop_reason` as the loop-breaking signal

And that the package broadly does not branch on `claim_type` equality
outside of the tool-schema definitions and the cost-estimate module.

Each test parses the relevant file with `ast` and walks the tree. There are
no runtime imports of claims_intake here — the audit is static, so it works
even if loop.py / tools.py do not run end-to-end.
"""

from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "claims_intake"
LOOP_PY = PKG / "loop.py"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# ---------------------------------------------------------------------------
# Anti-pattern 1 — no string-membership tests against assistant text in the loop
# ---------------------------------------------------------------------------
def test_no_string_membership_against_text_in_loop() -> None:
    """No `"some_token" in <something>` expressions in loop.py.

    Heuristic: any `ast.Compare` node using `ast.In` whose `left` operand is a
    string `ast.Constant` is flagged. The loop has no legitimate reason to test
    for the presence of a magic string inside the model's output — that would be
    natural-language-driven control flow.
    """
    tree = _parse(LOOP_PY)
    offenders = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            # Check if any operator is ast.In
            if any(isinstance(op, ast.In) for op in node.ops):
                # Check if left operand is a string constant
                if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                    offenders.append(ast.unparse(node))

    assert offenders == [], f"Found string-membership tests against text: {offenders}"


# ---------------------------------------------------------------------------
# Anti-pattern 2 — no integer-literal iteration cap as the primary stop mechanism
# ---------------------------------------------------------------------------
def test_no_integer_literal_iteration_cap_in_loop() -> None:
    """No `for _ in range(<int literal>)` and no `while <var> < <int literal>` in loop.py.

    Token/wall-clock/config-sourced budgets are explicitly allowed because they
    read their cap from a `Budget` instance (an attribute access or a function
    arg), not from a literal. If you need a cap, pass it in.
    """
    tree = _parse(LOOP_PY)
    offenders = []

    for node in ast.walk(tree):
        # Check for ast.For with range(<int literal>, ...)
        if isinstance(node, ast.For):
            if isinstance(node.iter, ast.Call):
                if isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range":
                    # Check if any argument is an integer constant
                    for arg in node.iter.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                            offenders.append(ast.unparse(node.iter))
                            break

        # Check for ast.While with <var> < <int literal>
        elif isinstance(node, ast.While):
            if isinstance(node.test, ast.Compare):
                # Check if the right side has an integer constant
                for comparator in node.test.comparators:
                    if isinstance(comparator, ast.Constant) and isinstance(comparator.value, int):
                        offenders.append(ast.unparse(node.test))
                        break

    assert offenders == [], f"Found integer-literal iteration caps (use a Budget instead): {offenders}"


# ---------------------------------------------------------------------------
# Positive evidence — stop_reason is the value that breaks the while loop
# ---------------------------------------------------------------------------
def test_stop_reason_is_loop_control() -> None:
    """loop.py references `stop_reason` AND a `while` loop exits via return/raise on it."""
    tree = _parse(LOOP_PY)

    # Check if there is at least one reference to stop_reason
    has_stop_reason_ref = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "stop_reason":
            has_stop_reason_ref = True
            break
        if isinstance(node, ast.Name) and node.id == "stop_reason":
            has_stop_reason_ref = True
            break

    assert has_stop_reason_ref, "loop.py must reference 'stop_reason'"

    # Check if at least one while loop exits on stop_reason
    while_loops_with_stop_reason = False
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            body_text = ast.unparse(node.body)
            # Check if the body mentions both stop_reason and (return or raise)
            has_stop_reason_in_body = "stop_reason" in body_text
            has_exit_in_body = "return" in body_text or "raise" in body_text

            if has_stop_reason_in_body and has_exit_in_body:
                while_loops_with_stop_reason = True
                break

    assert while_loops_with_stop_reason, "loop.py must have a while loop that exits via return/raise on stop_reason"


# ---------------------------------------------------------------------------
# Decision-tree-in-Python — no `if claim_type == "..."` branches in the package
# ---------------------------------------------------------------------------
def test_no_claim_type_equality_branching_in_package() -> None:
    """Decision logic about claim type lives in the model, not in Python.

    tools.py is exempt (it defines the enum in input_schema).
    pricing.py is exempt (it may map claim_type to per-queue cost weights).
    """
    offenders = []

    # Walk all .py files in the package
    for py_file in PKG.rglob("*.py"):
        # Skip exempt files
        if py_file.name in ("tools.py", "pricing.py", "__init__.py"):
            continue

        tree = _parse(py_file)

        # Find ast.Compare nodes with equality operators
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                # Check if any operator is Eq
                if any(isinstance(op, ast.Eq) for op in node.ops):
                    # Check if left operand is a Name or Attribute named "claim_type"
                    is_claim_type_left = False
                    if isinstance(node.left, ast.Name) and node.left.id == "claim_type":
                        is_claim_type_left = True
                    elif isinstance(node.left, ast.Attribute) and node.left.attr == "claim_type":
                        is_claim_type_left = True

                    if is_claim_type_left:
                        # Check if any comparator is a string constant
                        for comparator in node.comparators:
                            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                                offenders.append(
                                    f"{py_file.relative_to(PKG.parent)}:{node.lineno}: {ast.unparse(node)}"
                                )
                                break

    assert offenders == [], (
        f"Found claim_type equality branching (move decision logic into the model): {offenders}"
    )
