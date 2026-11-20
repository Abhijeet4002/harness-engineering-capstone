---
name: deploy-check
description: Pre-deployment validation checklist for the current branch
context: fork
argument-hint: "[target-branch] (defaults to main)"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(gh pr view:*)
---

# /deploy-check

Runs the team's pre-deployment validation checklist against the current working tree and the branch you're about to ship. Read-only by design — this skill never modifies files, never pushes, never deploys. It returns a single structured summary so the calling session can decide whether to proceed.

## Why this is a skill (not a CLAUDE.md addition)

Deploy checks are on-demand, forked, and task-specific: you only invoke them right before shipping, and the verbose intermediate output (file enumeration, diff analysis, check traces) adds no value once you know the verdict. CLAUDE.md conventions, by contrast, must be always-loaded and universal — conventions like "tests are co-located" or "throw ApiError for validation" belong in CLAUDE.md because they guide every session. By moving deploy checks to a skill, the main session stays lean and focused. Rule of thumb: on-demand / forked / task-specific → skill; always-loaded / universal → CLAUDE.md.

## Why `context: fork`

The goal is to keep verbose intermediate output out of the main session and conversation. A deploy check walks the working tree, inspects diffs across the branch, and runs several enumeration passes — none of that inspection detail has any value to the calling session once we know the verdict. `context: fork` is a Claude Code product feature that isolates the skill in a forked sub-agent: the skill runs independently, produces its working output only within the fork, and returns a single structured summary to the main conversation. This embodies the *Branching Reality* pattern: establish a shared starting point, then branch into isolated explorations whose working artifacts never flow back to the parent. The same pattern applies at the session level via `fork_session`, keeping conversation history lean and decision-focused.

## Checks

Run all three. Each check produces a pass-or-fail verdict; if any fails, the overall summary is **fail**.

### Check 1: No uncommitted changes

**Detect:** `git status --porcelain` returns empty.

**Pass:** Working tree is clean; all changes are committed.

**Fail:** `git status --porcelain` lists unstaged or untracked files. Surface the file paths in the verdict summary so the author can stash or commit before deploying.

### Check 2: Migrations up-to-date with code

**Detect:** For every new repository import in the diff since `target-branch`, a corresponding migration file exists in the same commit range. Parse `git diff target-branch..HEAD src/db/*.ts` for new `import` statements from `src/db/` and verify each is backed by a migration file matching the naming convention `NNNN__*.sql` in `src/db/migrations/`.

**Pass:** Every repository layer touched in the branch has a forward migration in the same branch.

**Fail:** One or more new repository imports lack a corresponding migration. Surface the missing import and the expected migration filename pattern so the author can generate it.

### Check 3: CI checks green on the open PR

**Detect:** `gh pr view --json statusCheckRollup` for the open PR associated with the current branch. Parse the rollup status.

**Pass:** All required status checks report `SUCCESS`.

**Fail:** One or more required checks are not `SUCCESS` (e.g., `PENDING`, `FAILURE`, `NEUTRAL`). Surface the failing check name(s) and their status so the author knows whether to wait for CI or address a test failure.

## Output format

Return exactly this shape to the main session:

```
verdict: pass | fail
checks:
  - name: <check-name>
    status: pass | fail
    detail: <one line or empty>
```

Do not include the raw `git status`, raw diff hunks, or full check logs in the returned summary — those stay in the fork. If the author wants to investigate a failed check, they can re-invoke the skill targeting that single check or run the underlying command themselves.

## Personalization

This skill is project-scoped (`.claude/skills/deploy-check/`) so the whole team runs the same pre-deployment checks. If a teammate wants a stricter personal variant — for example, one that additionally fails when the diff exceeds 500 lines without a sufficiently detailed PR description — they can create a parallel skill at `~/.claude/skills/deploy-check-strict/` with a different name (e.g., `name: deploy-check-strict`). Their personal variant will not be committed to the repo and will not affect teammates.

## What this skill deliberately does not do

- It never pushes, deploys, or runs migrations. The `allowed-tools` allowlist is read-only by construction; even if a future maintainer adds `Write` here, the team's `/review` command should catch the change.
- It does not run the test suite. Tests have their own pre-merge gate in CI; duplicating that here would slow every deploy check without adding signal.
- It does not check for secrets in code. That's the job of the `gitleaks` pre-commit hook, which fails the commit, not the deploy.
