"""A minimal webhook receiver using only the standard library.

    export STELLARDS_WEBHOOK_SECRET=whsec_...   # shown once when you create the webhook (or rotate its secret)
    python examples/webhook_receiver.py          # listens on http://0.0.0.0:8000/stellards-webhook

Register the public URL of this endpoint as a webhook, e.g. with
``sds.webhooks.create("https://your-host/stellards-webhook", events=["record.created"])``.
"""

from __future__ import annotations

import collections
import http.server
import json
import os
import threading
from typing import Any

from stellards import WebhookSignatureError
from stellards.webhooks import EVENT_ID_HEADER, SIGNATURE_HEADER, construct_event

SECRET = os.environ.get("STELLARDS_WEBHOOK_SECRET", "")
PATH = "/stellards-webhook"
MAX_BODY = 1_000_000

# Deliveries can repeat: remember recent event ids (use a database or cache in production).
_seen: collections.OrderedDict[str, None] = collections.OrderedDict()
_seen_lock = threading.Lock()


def first_time(event_id: str) -> bool:
    with _seen_lock:
        if event_id in _seen:
            return False
        _seen[event_id] = None
        while len(_seen) > 10_000:
            _seen.popitem(last=False)
        return True


def handle(event: Any) -> None:
    table = (event.get("table") or {}).get("name")
    record = (event.get("data") or {}).get("record")
    print(f"{event.get('type')} on {table}: {json.dumps(record)}")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != PATH:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self.send_error(413)
            return
        body = self.rfile.read(length)  # the raw bytes: verify them before parsing
        try:
            event = construct_event(body, self.headers.get(SIGNATURE_HEADER), SECRET)
        except WebhookSignatureError as error:
            self.send_error(400, str(error))
            return
        event_id = self.headers.get(EVENT_ID_HEADER) or str(event.get("id", ""))
        if first_time(event_id) and event.get("type") != "ping":
            handle(event)
        # Answer quickly with a 2xx; do slow work elsewhere, or StellarDS retries the delivery.
        self.send_response(204)
        self.end_headers()


def main() -> None:
    if not SECRET:
        raise SystemExit("Set STELLARDS_WEBHOOK_SECRET to the webhook's secret (whsec_...).")
    port = int(os.environ.get("PORT", "8000"))
    with http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler) as server:
        print(f"Listening on http://0.0.0.0:{port}{PATH}")
        server.serve_forever()


if __name__ == "__main__":
    main()
