---
description: Conventions for Node.js API handlers
paths:
  - "src/api/**/*"
---

# API handler rules

Loads when editing any file under `src/api/`.

## Handler return shape

- Every handler must be `async` and return `{ status: number, body: unknown }`. Do not write directly to response objects or use middleware transformers inside the handler — keep handlers testable.
- Status must be a valid HTTP code (200, 400, 401, 404, 500, etc.). Use semantic codes and let the error middleware convert `ApiError` exceptions into appropriate responses.

## Error handling

- Never `throw new Error(...)` from handler code. Always throw `ApiError(status, code, message)` for expected failures.
- Do not catch-and-ignore exceptions. If you catch an exception from repository code, wrap it in a new `ApiError` with context about which operation failed.
- Unexpected exceptions propagate to the global error handler — do not catch-and-rethrow without adding context.

## Input validation

- Validate request bodies at the boundary using shared `zod` schemas from `src/api/_schemas/`. Do not duplicate validation downstream.
- Parsing errors from `zod` should throw `ApiError(400, "VALIDATION_ERROR", ...)` with the validation details in the body.

## Response contracts

- Response bodies must match the schemas defined in `src/api/_schemas/responses/`. Adding a field to a response requires updating the schema in the same commit.
- Never return internal implementation details or database identifiers that shouldn't be exposed to clients.
