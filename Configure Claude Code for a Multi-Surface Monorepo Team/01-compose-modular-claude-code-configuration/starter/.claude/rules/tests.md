---
description: Conventions for test files
paths:
  - "**/*.test.ts"
  - "**/*.test.tsx"
  - "tests/**/*"
---

# Test file rules

Loads when editing any `*.test.ts(x)` file or integration test under `tests/`.

## Test file location

- Tests are co-located with source code: `Cart.tsx` lives next to `Cart.test.tsx` in the same directory.
- Integration tests that span multiple modules live in `tests/integration/`. Do not create a separate `__tests__/` tree.

## What to test

- Component tests: assert on rendered output and user-visible behavior, not internal hook state or implementation details.
- API handler tests: call the handler function directly with a request shape, never spin up the HTTP layer or mock request/response objects.
- Repository tests: hit a real PostgreSQL test instance using Docker Compose. Mocking the database layer is forbidden — we learned the hard way that mocks hide broken migrations.

## What NOT to test

- Do not test generated code (Prisma client, OpenAPI types). Trust the generation tool.
- Do not test third-party libraries. If you need to verify a library works, wrap it and test the wrapper; never mock the library itself.
- Do not use `setTimeout` in tests — always use deterministic assertions or test utilities like `waitFor`.
- Do not use snapshot testing for UI assertions — write specific assertions instead.

## Test assertions

- Use specific assertions that describe the expected behavior rather than relying on output comparison.
- For async operations in components, use `waitFor` from testing utilities to handle timing correctly.
