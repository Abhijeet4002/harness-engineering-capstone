# E-Commerce Platform — Shared Claude Code Conventions

This file is the **project-level** entry point for the e-commerce monorepo. Every teammate's Claude session loads it automatically.

## Scope: what belongs here vs. elsewhere

| Scope | Location | Shared? | Example |
|-------|----------|---------|---------|
| **Project-level** | `./CLAUDE.md`, `.claude/standards/`, `.claude/rules/` | ✓ Via Git | Shared coding standards, React conventions, API patterns |
| **User-level** | `~/.claude/` | ✗ NOT shared — local to your machine only | Personal commit message style, preferred tools, local aliases |
| **Directory-level** | `subdir/CLAUDE.md` | ✓ Via Git | Context-specific overrides for a package or service |

Project-level settings in this repo ensure every teammate follows the same conventions when editing the monorepo, while user-level settings preserve personal preferences without cluttering shared version control.

## Shared standards (modular via @-imports)

The actual conventions live in focused files so this entry point stays scannable:

@.claude/standards/frontend.md
@.claude/standards/api.md
@.claude/standards/database.md
@.claude/standards/testing.md

Path-scoped rules in [.claude/rules/](.claude/rules/) layer on top of these standards and activate only when Claude is editing matching files (React components, API handlers, test files).

## Repository layout

```
src/components/   React components (functional + hooks)
src/pages/        Top-level routes
src/api/          Node.js API handlers
src/db/           PostgreSQL repository-pattern modules
```

Tests are co-located: `Foo.tsx` lives next to `Foo.test.tsx`.

## Troubleshooting

If a convention listed here isn't being followed, run `/memory` to verify which configuration files actually loaded for your session.

## Team workflows

- `/review <pr-ref>` — codified PR review checklist. (You will author this in Exercise 2.)
- `/deploy-check` — read-only pre-deployment validation. (You will author this in Exercise 3.)

For decisions about when to use plan mode vs. direct execution on this codebase, you will produce a team decision doc in Exercise 4.
