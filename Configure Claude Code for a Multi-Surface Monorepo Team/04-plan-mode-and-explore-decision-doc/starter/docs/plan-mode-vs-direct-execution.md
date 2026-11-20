# Plan mode vs. direct execution — team decision guide

Choosing between Claude Code's **plan mode** (investigate and propose before changing anything) and **direct execution** (change code immediately) is the single biggest leverage point in how the team uses the harness day-to-day. The wrong mode at either extreme costs us: plan mode for trivial fixes is friction; direct execution for architectural changes burns context and produces rework.

> Anchor talk: Knight-Webb, "SWE Is Becoming Plan and Review."

This doc walks four concrete decisions against our codebase: one plan-mode example, one direct-execution example, one Explore-subagent example, and one combined-workflow example.

---

## 1. Plan-mode example

**Scenario:** Extract a shared `useCart(userId)` hook to eliminate duplication across cart-related components.

Currently, `src/components/Cart/Cart.tsx`, `src/components/Checkout/Checkout.tsx`, and `src/components/MiniCart/MiniCart.tsx` each independently fetch the user's cart in a `useEffect`, handle loading and error states, and memoize totals. The pattern repeats nearly identically across all three, violating DRY.

**Why plan mode is essential here:**

- **Large-scale structural change:** extracting a hook and renaming its call sites touches at least three files and reshapes how the components initialize state.
- **Multiple valid approaches:** we could create a single hook, we could split cart-fetching logic from cart-caching logic, or we could lift state into a context. Each approach has tradeoffs in re-fetch behavior, cache invalidation, and component coupling.
- **Architectural decision:** does the hook own the entire `active` lifecycle (cancellation on unmount) or does it assume the caller guarantees a stable `userId`? That choice cascades to all three consumers.
- **Multi-file mutations:** each call site must be updated to use the new hook; if we misjudge the hook's interface, all three callers break.

Plan mode allows you to investigate the actual fetch and state patterns, propose a hook signature that all three can adopt, and get buy-in from the team on the tradeoffs *before* writing a line of code that must be reworked. This prevents costly rework if the proposed API turns out to miss error handling or misinterprets the cache semantics.

---

## 2. Direct-execution example

**Scenario:** Add a `min: 0` validation rule to the quantity field in `src/api/_schemas/orders.ts` to reject negative quantities at the API boundary.

The orders schema currently accepts any integer for item quantities. A user (or a buggy frontend) could submit `{ quantity: -5 }`, and the backend would dutifully create an order with negative line items. The fix is straightforward: amend the quantity Zod validator to include `.min(0)`.

**Why direct execution is enough here:**

- **One function, one file:** the change is confined to one schema definition.
- **Fix is obvious:** you (the author) can predict the exact patch before invoking Claude — replace `z.number()` with `z.number().min(0)` on the quantity field.
- **No architectural ambiguity:** this is not a "should we validate on the client, server, or both?" decision. It's a one-liner that hardens the API boundary.
- **Low risk:** the change is defensive; it rejects invalid input that would have been caught later (or silently corrupted the order).

If you can describe the change in one sentence and mentally simulate the diff, direct execution is faster and less context-heavy than planning.

---

## 3. Explore-subagent example

**Scenario:** Inventory every call site of the `processRefund(input)` function to audit error handling and transaction behavior across the payment subsystem.

You suspect some refund calls may not be wrapped in transactions or may not update the order status correctly. Before writing a fix, you need a comprehensive list: "where do we call `processRefund`, and what does each call site do around it?"

**Why an Explore subagent is the right choice:**

- **Verbose discovery output:** grep alone finds the call sites, but you also need to understand context (is it wrapped in a transaction? does it call `markRefunded` after? is there error handling?). That investigation produces verbose notes and intermediate follow-ups.
- **Keeps discovery isolated:** if you run the exploration in your main session, the grep results and working notes consume tokens and distract from the actual edits you'll make. An Explore subagent keeps that verbose discovery output out of the main conversation.
- **Scratchpad pattern:** the Explore subagent writes its inventory to a scratchpad file (e.g., `tmp/refund-callsites.md`), listing each call site with the surrounding code pattern. That scratchpad survives context eviction and becomes a reference for the edits you'll make in direct execution or plan mode.

In this case, Explore returns: "`processRefund` is called in `src/api/orders/refund.ts` (wrapped in a transaction, followed by `markRefunded`), `src/api/billing/issue.ts` (not wrapped in a transaction, calls `markRefunded` separately), and exported from `src/services/payment.ts` (the definition). Full details in scratchpad." Armed with that summary, you can decide whether to plan a transaction wrapper for all callers or document the limitation.

---

## 4. Combined workflow — plan mode for investigation, then direct execution

**Scenario:** Rename `ordersRepo.findById` to `ordersRepo.getById` in `src/db/orders.ts` to align with a team naming convention (get* for single-record reads, find* for multi-record queries).

The rename is straightforward in principle — a few string replacements across the call sites — but you don't yet know the full scope. Are all calls static (found by grep) or are some dynamic (constructed at runtime from user input)? Are there typos or aliases that grep would miss? Could the rename break any middleware or decorators?

**Combining plan mode for investigation with direct execution for implementation:**

1. **Plan mode investigates:** You ask Claude to search the codebase for every invocation of `findById`, including dynamic patterns, error handling paths, and dead code. Claude explores, notes which files reference it, and proposes a rename strategy (e.g., "11 static call sites in handlers and repos, all injectable via dependency injection, so a straight replace is safe; no dynamic construction found").

2. **You approve the plan:** The team verifies the scope and agrees that a one-to-one mechanical rename is correct. No architectural surprises.

3. **Direct execution applies the edits:** With the call-site inventory in hand, you invoke Claude in direct execution mode: "Rename `findById` to `getById` in the following files: [list]. Update the export and all call sites. Run tests after." The edits are now fully scoped, and Claude executes them without further exploration or decision-making.

This hybrid approach combines the planning phase (where ambiguity is resolved and scope is locked) with the execution phase (where the work is mechanical). Once plan mode has answered "is a simple rename safe?", direct execution avoids re-exploring the same call sites.

---

## Quick reference

| Situation | Mode |
|-----------|------|
| Single function, fix is obvious, you can predict the diff | Direct execution |
| Multi-file refactor, API shape is debatable | Plan mode |
| Discovery / inventory across the codebase, you'll throw away the intermediate steps | Explore subagent |
| Investigation-then-mechanical-change | Plan mode → direct execution |
| Architectural decision (which database, which queue) | Plan mode, possibly with a fork to compare options |

When in doubt: plan mode is recoverable (you can switch to execution), but direct execution on a complex change is not. Default to plan when uncertain.
