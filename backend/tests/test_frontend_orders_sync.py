"""The frontend Test-orders panel is a display mirror of the mock database.

backend/data/orders.json is the single source of truth (never edited by the
UI). This test fails whenever the factual fields of the frontend copy in
frontend/src/data/orders.ts drift from the JSON, so a database change cannot
ship with a stale panel. The panel's `note` is display-only prose (it may add
annotations the agent never says) and is intentionally not compared; JSON
nulls are rendered as "—" in the panel.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "backend" / "data" / "orders.json"
FRONTEND_MIRROR_PATH = REPO_ROOT / "frontend" / "src" / "data" / "orders.ts"

SHARED_FIELDS = ("customer", "product", "value", "status", "carrier", "tracking")


def _load_frontend_orders() -> list[dict]:
    text = FRONTEND_MIRROR_PATH.read_text(encoding="utf-8")
    match = re.search(r"export const ORDERS = (\[.*?\]);", text, re.S)
    assert match, f"ORDERS array not found in {FRONTEND_MIRROR_PATH}"
    block = match.group(1)
    # TS object literal -> JSON: quote bare keys, drop trailing commas.
    block = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)", r'\1"\2"\3', block)
    block = re.sub(r",(\s*[}\]])", r"\1", block)
    return json.loads(block)


def _field_matches(frontend_value, db_value) -> bool:
    if db_value is None:  # JSON null renders as the panel's em dash
        return frontend_value in ("—", "", None)
    return frontend_value == db_value


def test_frontend_orders_mirror_matches_database() -> None:
    db_orders = json.loads(DB_PATH.read_text(encoding="utf-8"))
    frontend_orders = _load_frontend_orders()

    db_ids = {o["id"] for o in db_orders}
    frontend_ids = {o["id"] for o in frontend_orders}
    assert frontend_ids == db_ids, (
        f"id mismatch: frontend-only={sorted(frontend_ids - db_ids)} "
        f"db-only={sorted(db_ids - frontend_ids)}"
    )

    db_by_id = {o["id"]: o for o in db_orders}
    for fe_order in frontend_orders:
        db_order = db_by_id[fe_order["id"]]
        for field in SHARED_FIELDS:
            assert _field_matches(fe_order.get(field), db_order.get(field)), (
                f"{db_order['id']}.{field}: frontend={fe_order.get(field)!r} "
                f"database={db_order.get(field)!r} — update frontend/src/data/orders.ts"
            )
        assert fe_order.get("note"), f"{fe_order['id']}: panel note missing"
        assert db_order.get("notes"), f"{db_order['id']}: database notes missing"
