import json
import os
from datetime import datetime, timezone


def _read_ledger(ledger_path: str) -> list[dict]:
    if not os.path.exists(ledger_path):
        return []
    with open(ledger_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_used_ids(ledger_path: str) -> set[str]:
    """
    Returns every id already recorded in the ledger, regardless of purpose, so a
    sampling run can exclude them from its draw pool before random.sample.
    """
    return {str(entry["id"]) for entry in _read_ledger(ledger_path)}


def append_used_ids(ledger_path: str, ids: list[str], purpose: str) -> None:
    """
    Appends one ledger entry per id ({id, purpose, drawn_at}) and writes the ledger
    back out. Creates the ledger file (as an empty list) first if it doesn't exist.

    :param purpose: "gold_natural" | "gold_supplemental" | "production"
    """
    ledger = _read_ledger(ledger_path)
    drawn_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ledger.extend({"id": str(seq_id), "purpose": purpose, "drawn_at": drawn_at} for seq_id in ids)

    os.makedirs(os.path.dirname(ledger_path) or ".", exist_ok=True)
    with open(ledger_path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2)