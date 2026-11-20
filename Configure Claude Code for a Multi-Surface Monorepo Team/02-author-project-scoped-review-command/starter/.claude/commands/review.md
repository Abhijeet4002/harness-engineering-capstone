---
description: Review code changes against project standards and conventions
argument-hint: "git diff output, PR reference (e.g., 'origin/main'), or file diff"
allowed-tools:
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git show:*)
  - Bash(git status:*)
  - Bash(git blame:*)
  - Bash(gh pr view:*)
  - Bash(gh pr diff:*)
  - Bash(gh pr checks:*)
  - Read
  - Grep
  - Glob
---

# /review — team PR review

You are reviewing the diff identified by `$ARGUMENTS` against this repository's conventions. Apply the path-scoped rules in `.claude/rules/` (they auto-load based on the files touched) and the shared standards in `.claude/standards/`.

## Phase 1 — Interview pattern

Before reporting findings on ambiguous changes, ask clarifying questions. Without this step, the reviewer can commit to a confidently-wrong verdict—e.g., flagging "no test coverage" on a refactor when the behavior was already tested upstream, forcing the author to argue against a false positive.

**Interview instead of report when:**

- **Dependency changes** (package.json or pyproject.toml diffs): Ask what motivated the update. Is this a security patch, a feature bump, or a breaking upgrade? The strategy for review changes.
- **Public API response shape or DB column changes**: Ask if this is intentional (new feature) or accidental (breaking change). The diff alone doesn't reveal the author's intent.
- **Refactors with no test file changes**: Ask if tests were already in place. A refactor to a React component or API handler might have passing tests upstream without any .test.ts edits.
- **Cross-surface changes** (API + components + DB at once): Ask what ties them together. Is this a single feature spanning layers, or multiple independent PRs squashed together? The bundling strategy depends on intent.

## Phase 2 — Review criteria

**Must-report findings:**

- **Logic bugs**: Missing `await`, race conditions, off-by-one errors, unreachable code, incorrect conditionals, or state mutations that break invariants.
- **Security vulnerabilities**: Raw SQL with unsanitized user input, missing authorization checks, secrets in code (API keys, passwords), `dangerouslySetInnerHTML`, or unchecked file operations.
- **Convention violations**: Code that violates rules in `.claude/standards/` or `.claude/rules/` (e.g., class components when only functions are allowed, `.catch()` without rethrowing, hardcoded URLs).
- **Breaking changes**: API response field removals, DB column drops, or public function signature changes without migration period.
- **Migration safety**: Forward-only migrations, unprotected concurrent writes, or transactions missing proper isolation levels.

**Skip (do not report):**

- **Minor formatting**: Prettier, ESLint, or other auto-formatters will catch it. Don't bikeshed whitespace or semicolons.
- **Naming preferences**: If the name is clear and consistent with existing code, don't argue for a different name.
- **Personal style**: Subjective preferences not encoded in rules/standards (e.g., "I would use a different variable name" is a skip unless the name is misleading).
- **Existing tracked tickets**: If a TODO cites a ticket (e.g., `// TODO: #42`), assume it's intentional and skip.
- **Third-party behavior**: Don't report patterns we're importing from libraries (e.g., Prisma-generated code, OpenAPI schemas).

## Phase 3 — Bundling: interacting vs. independent findings

**Interacting findings** share a single fix. Bundle them into ONE detailed message so the author sees the full context and doesn't fix half the problem.
Example: a handler with a missing `await` on a database call AND no transaction wrapper AND wrong ordering between payment and DB writes—all three are fixed by the same refactoring step.

**Independent findings** have no shared fix and affect separate parts of the code. Report them SEQUENTIALLY as separate items so each piece of feedback is actionable on its own.
Example: one handler returning `{ status: 404 }` instead of throwing `ApiError` (in src/api/handlers/orders.ts) AND another handler calling raw SQL instead of a repository function (in src/api/handlers/payments.ts)—the fixes don't overlap.

**Heuristic:** If fixing finding A requires changing code that finding B references or depends on, they are interacting and must be bundled. If each finding can be fixed independently without affecting the other, report sequentially.

## Phase 4 — Output format

For each finding, produce:

```
[severity] path/to/file.ts:line
finding: <one-sentence description>
fix: <one-sentence recommendation>
```

Severity is `bug` | `security` | `convention` | `breaking`. End with a one-line verdict: `approve`, `comment`, or `request-changes`.

## Examples

### Example 1: Independent findings

**Input** (diff excerpt in `src/api/handlers/order.ts`):

```diff
export async function refund(req: RequestShape) {
  const { orderId } = req.body;

-  if (!auth.check(req.user)) return { status: 401, body: { error: "unauthorized" } };
+  const refundResult = { status: 200, body: { refunded: true } };
+  if (refundResult.status === 200) {
+    const sql = `UPDATE orders SET refunded = true WHERE id = ${orderId}`;
+    await pool.query(sql);
+  }
+  return refundResult;
}
```

**Output:**

```
[convention] src/api/handlers/order.ts:4
finding: Handler returns literal { status, body } object instead of throwing ApiError
fix: Replace return statement with throw ApiError(401, 'unauthorized', 'User not authorized')

[convention] src/api/handlers/order.ts:8
finding: Raw SQL query with unsanitized user input (orderId interpolated directly)
fix: Use the orders repository function orderRepo.refund(orderId) instead of direct SQL
```

**Verdict:** `request-changes` — these are independent violations (error handling vs. data layer). The author must fix both, but each fix stands alone.

---

### Example 2: Interacting findings

**Input** (diff excerpt in `src/api/handlers/refund.ts`):

```diff
export async function refundOrder(req: RequestShape) {
  const { orderId, paymentMethodId } = req.body;

  // Charge the customer's card for the refund
  paymentService.refund(paymentMethodId, 15.99);

  // Mark order as refunded in the database
  const refundRecord = { orderId, status: "refunded", amount: 15.99 };
  ordersRepo.createRefundRecord(refundRecord);

  return { status: 200, body: { refunded: true } };
}
```

**Output:**

```
[bug] src/api/handlers/refund.ts:5–8
finding: Three related issues prevent atomicity: (1) missing await on paymentService.refund,
(2) no transaction wrapper around payment + DB writes, (3) wrong ordering (payment succeeds
but DB write fails, leaving inconsistent state). These must be fixed together.
fix: Wrap the entire handler in withTransaction(async (tx) => ...), await paymentService.refund()
before all DB operations, and ensure the transaction commits only after both succeed. Example:
```
  export async function refundOrder(req: RequestShape) {
    const { orderId, paymentMethodId } = req.body;
    return withTransaction(async (tx) => {
      await paymentService.refund(paymentMethodId, 15.99);
      const refundRecord = { orderId, status: "refunded", amount: 15.99 };
      await tx.query(ordersRepo.createRefundRecord(refundRecord));
      return { status: 200, body: { refunded: true } };
    });
  }
```
```

**Verdict:** `request-changes` — these findings are interacting (all fixed by the same refactoring). Bundle them into one message because the author must understand the full atomicity issue to fix it correctly.

## Notes

- This command is project-scoped (`.claude/commands/review.md`) so everyone on the team gets the same review. If you want to layer personal preferences (e.g. a stricter accessibility check on your own PRs), put a `~/.claude/commands/review-strict.md` in your home directory — it will not affect teammates.
- If a finding requires running code or modifying files to verify, ask the author to run a specific check rather than attempting it from the review session. This command's `allowed-tools` are read-only by design.
