import json
from pathlib import Path

ORDERS_PATH = Path(__file__).resolve().parent / "orders.json"


def load_orders() -> dict[str, dict]:
    return {o["id"]: o for o in json.loads(ORDERS_PATH.read_text(encoding="utf-8"))}
