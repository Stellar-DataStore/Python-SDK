"""StellarDS quick start: create a table with a few fields, add records, query them and clean up.

Usage::

    pip install stellards
    export STELLARDS_TOKEN=...          # an access token of your project (Access & roles in the app)
    export STELLARDS_PROJECT=...        # your project's id
    python examples/quickstart.py
"""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import sys
from decimal import Decimal

from stellards import FieldType, NotFoundError, StellarDS, StellarDSError, where


def main() -> int:
    token = os.environ.get("STELLARDS_TOKEN")
    project = os.environ.get("STELLARDS_PROJECT")
    if not token or not project:
        print("Set STELLARDS_TOKEN and STELLARDS_PROJECT first.", file=sys.stderr)
        return 2

    with StellarDS(token, project=project, base_url=os.environ.get("STELLARDS_URL", "https://api.stellards.io")) as sds:
        print("API:", sds.ping())

        table = sds.tables.create("QuickstartProducts", description="Created by the Python SDK quick start")
        try:
            sds.fields.create(table.id, "name", FieldType.nvarchar(100))
            sds.fields.create(table.id, "price", FieldType.decimal(12, 2))
            sds.fields.create(table.id, "available", FieldType.date())
            sds.fields.create(table.id, "status", FieldType.enum(["draft", "published"]))

            sds.records.create(
                table.id,
                [
                    {
                        "name": "Telescope",
                        "price": Decimal("1299.99"),
                        "available": dt.date(2025, 1, 15),
                        "status": "published",
                    },
                    {
                        "name": "Star map",
                        "price": Decimal("19.50"),
                        "available": dt.date(2025, 3, 1),
                        "status": "draft",
                    },
                    {
                        "name": "Red torch",
                        "price": Decimal("7.25"),
                        "available": dt.date(2025, 2, 1),
                        "status": "published",
                    },
                ],
            )

            published = sds.records.query(table.id, where=where("status", "=", "published"), sort="-price")
            print(f"{published.count} published products:")
            for record in published:
                print(f"  #{record['id']} {record['name']}: {record['price']}")

            # Walk through every record, 2 per request.
            names = [record["name"] for record in sds.records.iter(table.id, page_size=2, sort="name")]
            print("All products:", ", ".join(names))
        except StellarDSError as error:
            print(f"StellarDS said no: {error} (status {error.status})", file=sys.stderr)
            return 1
        finally:
            with contextlib.suppress(NotFoundError):
                sds.tables.delete(table.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
