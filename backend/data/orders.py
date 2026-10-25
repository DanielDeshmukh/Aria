import json
from pathlib import Path

ORDERS_PATH = Path(__file__).resolve().parent / "orders.json"


def load_orders() -> dict[str, dict]:
    return {o["id"]: o for o in json.loads(ORDERS_PATH.read_text(encoding="utf-8"))}


# Single shared instance: tools.py re-exports it, so tests that monkeypatch
# tools.ORDERS and this repository always read the same dict.
ORDERS: dict[str, dict] = load_orders()


def get_order(order_id: str) -> dict | None:
    """Repository read: one order by id, None when unknown."""
    return ORDERS.get(order_id)
