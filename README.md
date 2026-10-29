# StellarDS Python SDK

The official Python client for the [StellarDS.io](https://stellards.io) v2 API: a synchronous and an asynchronous
client with the same resources, typed results, automatic OAuth token refresh, exact decimals and webhook signature
verification.

- Python 3.9 or newer; one dependency ([httpx](https://www.python-httpx.org/)).
- Fully typed (`py.typed`), so editors complete every method and result.

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [Authentication](#authentication)
- [Resources](#resources)
- [Field types and values](#field-types-and-values)
- [Webhooks](#webhooks)
- [Errors](#errors)
- [Async](#async)
- [Migrating from 0.0.x](#migrating-from-00x)
- [Development](#development)

## Install

```bash
pip install stellards
```

## Quick start

```python
from decimal import Decimal

from stellards import FieldType, StellarDS, where

with StellarDS("your-access-token", project="your-project-id") as sds:
    table = sds.tables.create("Products")
    sds.fields.create(table.id, "name", FieldType.nvarchar(100))
    sds.fields.create(table.id, "price", FieldType.decimal(12, 2))

    sds.records.create(table.id, {"name": "Telescope", "price": Decimal("1299.99")})

    page = sds.records.query(table.id, where=where("price", ">", 100), sort="-price", take=20)
    print(page.count, "matching records")
    for record in page:
        print(record["id"], record["name"], record["price"])
```

Records are plain dicts keyed by field name. Every other result is a dataclass (`Table`, `Field`, `Webhook`, ...);
the response object it was parsed from is always available as `.raw`, and fields the SDK doesn't know yet never break
parsing.

`project=` on the client is the default for every call; each method also takes `project=...` to use another one.
More complete scripts are in [`examples/`](examples/).

## Authentication

### Static access token

Create an access token for your project in the StellarDS application (Access & roles) and pass it:

```python
sds = StellarDS("your-access-token", project="your-project-id")
```

### OAuth with automatic refresh

Give the client your OAuth client's id and secret plus a refresh token. It refreshes the access token by itself,
shortly before it expires and once when a request gets a 401 (then retries that request once). Concurrent requests
share a single refresh.

The SDK never writes tokens to disk. When it gets new tokens it calls `on_tokens`: store them there (in your
database, the OS keychain, ...) and pass them back in the next time your program starts.

```python
from stellards import OAuthCredentials, StellarDS, Tokens


def save_tokens(tokens: Tokens) -> None:
    # tokens.access_token, tokens.refresh_token, tokens.expires_at (UTC)
    my_secret_store.save("stellards", tokens.refresh_token)


sds = StellarDS(
    oauth=OAuthCredentials(
        client_id="your-client-id",
        client_secret="your-client-secret",
        refresh_token=my_secret_store.load("stellards"),
    ),
    project="your-project-id",
    on_tokens=save_tokens,
)
```

The refresh token changes on every refresh, so always store the newest one.

### Getting the first tokens (authorization-code flow)

```python
from stellards import oauth

state = oauth.generate_state()
url = oauth.authorization_url("your-client-id", "https://your.app/callback", state)
# Send the user to `url`. StellarDS redirects back to https://your.app/callback?code=...
tokens = oauth.exchange_code("your-client-id", "your-client-secret", code, "https://your.app/callback")
```

`redirect_uri` must match one of the client's registered redirect URLs. The sign-in page is
`https://stellards.io/oauth` (pass `authorize_url=` for another environment). `exchange_code_async`,
`refresh_tokens` and `refresh_tokens_async` exist too, and a configured client offers
`sds.oauth.exchange_code(...)`, `sds.oauth.refresh()` and `sds.oauth.revoke()` (sign out).

> The StellarDS server currently doesn't send your `state` back to the redirect URI. To check it, put it in the
> redirect URI itself with `oauth.add_state(redirect_uri, state)` (it still matches the registered URL) and use that
> same URI for `exchange_code`.

For scripts and desktop tools, `authorize_in_browser` does all of it with a short-lived local web server (register
the loopback URL, with its port, as a redirect URL of your client):

```python
tokens = oauth.authorize_in_browser("your-client-id", "your-client-secret", "http://127.0.0.1:8765/callback")
```

## Resources

| Attribute | What it covers |
|---|---|
| `sds.projects` | list, get, create, update, delete, users, user_count, invited_users, app_access, log, get/update_oauth_design |
| `sds.tables` | list, get, create, update, delete |
| `sds.fields` | list, get, create, update, delete |
| `sds.records` | query, iter, get, create, update, delete, delete_many, clear, download_blob, upload_blob |
| `sds.query` | execute (custom read-only SQL) |
| `sds.procedures` | list, get, create, update, delete, execute |
| `sds.relations` | list, check, create, update, delete, get_layout, save_layout |
| `sds.roles` | list, get, simple, top_level, table_permissions, table_roles, template, create, update, delete, duplicate, update_table, matrix, update_matrix |
| `sds.permissions` | info |
| `sds.audit` | schema, management, rollback |
| `sds.webhooks` | list, get, create, update, delete, test, rotate_secret, deliveries, redeliver |
| `sds.users` | me, delete_me, permissions, invite, update_invitation, revoke_invitation, update_access, remove_access |
| `sds.applications` | access tokens and OAuth clients: list, create, update, delete, regenerate |
| `sds.project_tiers` | get, current |
| `sds.oauth` | exchange_code, refresh, revoke |
| `sds.ping()` | checks the API is reachable |

Some groups (relations, roles, audit, applications, project management) are meant for the StellarDS management
application; the server refuses them for other tokens with a `PermissionDeniedError`.

Updates take only what you want to change: settings you leave out keep their current value (the SDK reads them
first where the server needs the whole object).

### Projects

```python
for project in sds.projects.list():
    print(project.id, project.name)

project = sds.projects.get()  # the client's default project
sds.projects.update(description="Telescope shop")
```

### Tables and fields

```python
table = sds.tables.create("Orders", description="Web shop orders", is_multitenant=False)
sds.tables.update(table.id, name="ShopOrders")

sds.fields.create(table.id, "status", FieldType.enum(["new", "paid", "shipped"]))
for field in sds.fields.list(table.id):
    print(field.id, field.name, field.type)

# Rename an Enum value; records that use "new" get "open"
sds.fields.update(table.id, field_id, options=["open", "paid", "shipped"], replace_options={"new": "open"})
sds.fields.delete(table.id, field_id)
sds.tables.delete(table.id)
```

### Records

```python
from stellards import join, where

page = sds.records.query(
    table_id,
    where=where("status", "in", ["paid", "shipped"]) & where("total", ">=", Decimal("50")),
    sort=["-createdAt", "id"],  # "-" for descending
    select=["id", "status", "total"],
    offset=0,
    take=50,
)
print(page.count)  # all matching records, not just this page

for record in sds.records.iter(table_id, where=where("status", "=", "paid"), page_size=200):
    ...  # every matching record, 200 per request

created = sds.records.create(table_id, {"status": "new", "total": Decimal("74.90")})  # one dict -> one record
many = sds.records.create(table_id, [{"status": "new"}, {"status": "paid"}])  # a list -> a list
sds.records.update(table_id, {"status": "shipped"}, ids=[created["id"]])
sds.records.update(table_id, {"archived": True}, force=True)  # every record: needs force
sds.records.delete(table_id, created["id"])
sds.records.delete_many(table_id, [1, 2, 3])
sds.records.clear(table_id)  # deletes every record

sds.records.upload_blob(table_id, record_id, "photo", open("photo.jpg", "rb"), content_type="image/jpeg")
data: bytes = sds.records.download_blob(table_id, record_id, "photo")
```

`where` operators: `=`, `!=`, `>`, `<`, `>=`, `<=`, `like` (SQL wildcards `%` and `_`), `notlike`, `in`, `notin`
(pass a list) and `null` (`where("deletedAt", "null")` / `where("deletedAt", "null", False)` for "is not null").
Combine with `&` (and) and `|` (or); StellarDS evaluates them left to right without parentheses. The SDK encodes the
values, so they may contain any character, except that `in` values can't contain commas. Joins:
`join=join("Orders", "customerId", "Customers", "id")` (or a list of them). You can also pass the raw StellarDS syntax
as a string, e.g. `where="status;equal;paid"`.

### Custom queries and procedures

```python
result = sds.query.execute("select city, count(*) as n from Customers where country = @c group by city", {"c": "BE"})
for row in result.rows:
    print(row["city"], row["n"])

sds.procedures.create(
    "monthly_totals",
    parameters=[ProcedureParameter(name="year", type="Int", required=True)],
    steps=[
        (
            "totals",
            "select month(createdAt) as m, sum(total) as t from Orders where year(createdAt) = @year group by month(createdAt)",
        )
    ],
)
run = sds.procedures.execute("monthly_totals", {"year": 2025})
print(run.results[0].rows)
```

### Relations

```python
check = sds.relations.check(orders_id, customer_field_id, customers_id)
if check.is_valid:
    sds.relations.create(orders_id, to_table=customers_id, from_field=customer_field_id, on_delete="Restrict")
```

### Roles and permissions

```python
from stellards import RolePermissions, TablePermissions

role = sds.roles.create(
    "Support",
    RolePermissions(
        read_members=True, tables=[TablePermissions(table_name="Orders", read_table=True, read_records=True)]
    ),
)
matrix = sds.roles.matrix()  # every role x every table
print(sds.users.permissions())  # what you may do in the project
```

### Audit and undo

```python
log = sds.audit.schema(take=20)
for entry in log.audits:
    print(entry.date_time, entry.operation, entry.table_name)
sds.audit.rollback(log.audits[0].id)  # undo the last schema change
```

### Webhooks

```python
hook = sds.webhooks.create("https://your.app/stellards-webhook", events=["record.created", "record.updated"])
print("Store this secret:", hook.secret)  # only shown now (and after rotate_secret)
sds.webhooks.test(hook.id)  # sends a "ping" event
for delivery in sds.webhooks.deliveries(hook.id, take=20):
    print(delivery.event_type, delivery.status, delivery.last_status_code)
```

### Users, applications and tiers

```python
me = sds.users.me()
sds.users.invite("colleague@example.com", role_id, allow_app_access=True)

from stellards import DurationUnit

token = sds.applications.create_access_token("CI", role=role_id, duration=30, span=DurationUnit.DAYS)
print("Store this token:", token.access_token)

print(sds.project_tiers.get().max_requests, sds.project_tiers.current())
```

## Field types and values

Use `FieldType` to build a field's type:

| Builder | Type string | Python value you send / get |
|---|---|---|
| `FieldType.nvarchar(200)`, `FieldType.nvarchar("max")` | `NVarChar(200)` | `str` |
| `FieldType.tinyint()`, `smallint()`, `int()`, `bigint()` | `TinyInt`, ... | `int` |
| `FieldType.real()`, `FieldType.float()` | `Real`, `Float` | `float` |
| `FieldType.decimal(10, 2)` | `Decimal(10,2)` | `decimal.Decimal` (sent as an exact JSON number) |
| `FieldType.boolean()` | `Boolean` | `bool` |
| `FieldType.datetime()` | `DateTime` | `datetime.datetime` -> ISO 8601 |
| `FieldType.datetime_offset()` | `DateTimeOffset` | aware `datetime.datetime` -> ISO 8601 with offset |
| `FieldType.date()` | `Date` | `datetime.date` -> `"2025-01-31"` |
| `FieldType.time()` | `Time` | `datetime.time` -> `"13:45:00"` |
| `FieldType.uuid()` | `Uuid` | `uuid.UUID` -> string |
| `FieldType.json()` | `Json` | any JSON value (dict, list, ...) |
| `FieldType.enum(["a", "b"])` | `Enum` + options | one of the options (`str`) |
| `FieldType.blob()` | `Blob` | bytes, via `upload_blob` / `download_blob` |

You can also pass the type string itself (`"Decimal(10,2)"`). When you send records, native values are converted to
these wire formats for you; `Decimal("12345678901234.5678")` goes out as the JSON number `12345678901234.5678`, never
through a float.

Values come back as JSON types: dates and times as strings, decimals as `float`. Create the client with
`parse_decimals=True` to get every number with a fraction as an exact `Decimal` instead (Real and Float fields then
become `Decimal` too).

## Webhooks

Verify every delivery before trusting it, using the raw body exactly as received:

```python
from stellards import WebhookSignatureError
from stellards.webhooks import EVENT_ID_HEADER, SIGNATURE_HEADER, construct_event, verify_signature

# True/False:
ok = verify_signature(raw_body, headers[SIGNATURE_HEADER], "whsec_...")

# Or verify and parse in one go:
try:
    event = construct_event(raw_body, headers[SIGNATURE_HEADER], "whsec_...")
except WebhookSignatureError:
    ...  # answer 400
print(event["type"], event["data"].get("record"))
```

The `StellarDS-Signature` header is `t=<unix seconds>,v1=<hex>[,v1=<hex>...]`, an HMAC-SHA256 of `"<t>.<body>"` keyed
with the webhook's secret. Deliveries more than 5 minutes old are rejected (`tolerance=` changes that). While a secret
is being rotated, deliveries carry a signature for the old and the new secret, so either verifies. Deliveries can
repeat: deduplicate on the `StellarDS-Event-Id` header. Answer with a 2xx quickly, or StellarDS retries.
[`examples/webhook_receiver.py`](examples/webhook_receiver.py) is a complete receiver using only the standard library.

## Errors

Every error is a `StellarDSError` with `status` (HTTP status, or `None` without a response), `messages` (the server's
`[Message(code, message, type)]`) and `body` (the raw response).

| Exception | When |
|---|---|
| `AuthenticationError` | 401: missing/invalid token, or the refresh failed |
| `PermissionDeniedError` | 403 |
| `NotFoundError` | 404 |
| `RateLimitError` | 429; `retry_after` holds the `Retry-After` header in seconds |
| `ApiError` | any other error status, or a response with `isSuccess: false` (base of the four above) |
| `ApiConnectionError` / `ApiTimeoutError` | no response: network problem, or the timeout passed |

```python
from stellards import NotFoundError, RateLimitError, StellarDSError

try:
    sds.tables.get(12345)
except NotFoundError:
    print("no such table")
except RateLimitError as error:
    time.sleep(error.retry_after or 1)
except StellarDSError as error:
    print(error.status, [m.message for m in error.messages])
```

Requests time out after 30 seconds by default: `StellarDS(..., timeout=10)` (or an `httpx.Timeout`). The library
doesn't log or print anything.

## Async

`AsyncStellarDS` has exactly the same resources and methods, as coroutines:

```python
import asyncio

from stellards import AsyncStellarDS


async def main() -> None:
    async with AsyncStellarDS("your-access-token", project="your-project-id") as sds:
        tables, me = await asyncio.gather(sds.tables.list(), sds.users.me())
        async for record in sds.records.iter(tables[0].id):
            print(record)


asyncio.run(main())
```

`on_tokens` may be a regular function or a coroutine function. Use one client for the lifetime of your program (it
keeps a connection pool) and close it at the end, or use it as a (async) context manager. You can pass your own
`httpx.Client` / `httpx.AsyncClient` with `http_client=` (proxies, custom TLS, ...).

## Migrating from 0.0.x

Version 1.0 is a rewrite for the v2 API; nothing of the old `StellarDS.py` API remains.

| 0.0.x | 1.0 |
|---|---|
| `from StellarDS import StellarDS` | `from stellards import StellarDS` |
| `StellarDS(is_oauth=False)` + `.access_token(token)` | `StellarDS(token, project=...)` |
| `StellarDS(is_oauth=True)` + `.oauth(client_id, redirect, secret)` | `oauth.authorize_in_browser(...)` once, then `StellarDS(oauth=OAuthCredentials(...), on_tokens=...)` |
| `is_persistent=True` (encrypted `settings.json`) | removed: store tokens yourself in `on_tokens` |
| `stellar_ds.project.get(project_id)` | `sds.projects.get(project_id)` |
| `stellar_ds.table.add(project, Table(...))` | `sds.tables.create("Name", description=...)` |
| `stellar_ds.field.add(project, table, Field(...))` | `sds.fields.create(table, "name", FieldType.int())` |
| `stellar_ds.data.get(project, table, queries)` | `sds.records.query(table, where=..., sort=..., take=...)` |
| `stellar_ds.data.add(project, table, data)` | `sds.records.create(table, record_or_records)` |
| `stellar_ds.data.update(project, table, record, ids, force)` | `sds.records.update(table, values, ids=..., force=...)` |
| `stellar_ds.data.delete(project, table, ids)` | `sds.records.delete_many(table, ids)` |
| `stellar_ds.data.blob.get/add(...)` | `sds.records.download_blob/upload_blob(...)` |
| `stellar_ds.user.get()` | `sds.users.me()` |
| `response.status_code` / `response.is_success` / `response.data` | the method returns the data; failures raise a `StellarDSError` |

## Development

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

ruff check . && ruff format --check .
mypy
pytest
python -m build
```

The async resources (`src/stellards/_async/resources.py`) are generated from the sync ones: edit
`src/stellards/_sync/resources.py` and run `python scripts/generate_async.py` (a test fails when they drift apart).

## License

MIT, see [LICENSE](LICENSE).
