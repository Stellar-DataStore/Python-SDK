# Changelog

## 1.0.0

A rewrite from scratch for the StellarDS v2 API. Breaking: nothing of the 0.0.x API remains (see "Migrating from
0.0.x" in the README).

- `StellarDS` (sync) and `AsyncStellarDS` (async) clients with the same resources: projects, tables, fields, records,
  query, procedures, relations, roles, permissions, audit, webhooks, users, applications, project_tiers and oauth.
- Static access tokens, or OAuth credentials with automatic refresh (before expiry and once on a 401, one refresh for
  concurrent requests) and an `on_tokens` callback to persist new tokens. Tokens are never written to disk.
- Authorization-code helpers: `oauth.authorization_url`, `oauth.exchange_code(_async)`, `oauth.refresh_tokens(_async)`
  and `oauth.authorize_in_browser` (local loopback server with a state check, configurable redirect URI and port).
- Typed results (dataclasses parsed tolerantly, raw response on `.raw`); records stay plain dicts.
- `records.iter(...)` pages through all matching records; `where(...)`, `join(...)` and sort helpers build queries.
- `FieldType` builders for every field type; `Decimal` values go on the wire as exact JSON numbers; dates, times,
  datetimes and UUIDs in StellarDS's formats; optional `parse_decimals=True`.
- `stellards.webhooks.verify_signature` / `construct_event` for webhook deliveries (constant-time, rotation-aware,
  5-minute replay window by default).
- Typed exceptions: `StellarDSError`, `ApiError`, `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`,
  `RateLimitError`, `ApiConnectionError`, `ApiTimeoutError`, `WebhookSignatureError`.
- Default 30-second timeout, one reusable connection pool, context-manager support.
- Packaging: `src/` layout, hatchling, `py.typed`, Python 3.9+, `httpx` as the only dependency.
- Examples: `examples/quickstart.py`, `examples/webhook_receiver.py`, `examples/raspberry_pi_bmp180.py`.

Removed: the hardcoded encryption key and `settings.json` token storage, the fixed OAuth redirect port, the
`requests`/`cryptography` dependencies and the old Raspberry Pi test script.
