"""
Splits the gold pool into a 2/3 "search" part (used to compare judge configs) and a 1/3 "held_out" part
(used once, to confirm the winner). Writes the result to `dataset_short/judge_split.json`; the judge search
reads it through `--split` (see src/review/validate_judge/search.py).

How the split is made:
  1. Hard strata: dataset x classification. Every cell is split 2/3 to 1/3, so both parts hold the same
     mix of datasets and of normal/abnormal.
  2. Human fails: inside those quotas, records are swapped between the parts (seeded, only swaps that
     help are kept) until each criterion's human-fail count is as close to 1/3 as possible in the
     held-out part -- overall, per dataset and per class -- and records with at least one fail are
     spread evenly per cell. The judge score of a criterion is only as precise as the number of human
     fails behind it, so the fails must not pile up in one part.

Run from the repo root:
    uv run python -m src.sampling.split_gold
"""

import argparse
import json
import random
from collections import defaultdict
from datetime import datetime, timezone

from src.help_functions.manifest_log import append_manifest_entry
from src.help_functions.review_criteria import CRITERIA_KEYS
from src.review.validate_judge.gold import DATASETS, DEFAULT_GOLD_FILE, load_gold

CLASSES = ["normal", "abnormal"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cell_quotas(cells: dict, held_fraction: float = 1 / 3) -> dict:
    """
    Held-out records per (dataset, classification) cell. Each cell gets floor(size / 3); the leftover
    records needed to reach the total go to cells that do not divide evenly, walking the cells in a
    dataset/class zig-zag so the extras do not pile up in one dataset or one class.
    """
    quotas = {cell: int(len(items) * held_fraction) for cell, items in cells.items()}
    extra = round(sum(len(items) for items in cells.values()) * held_fraction) - sum(quotas.values())

    zigzag = []
    for i in range(len(DATASETS) * len(CLASSES)):
        zigzag.append((DATASETS[i % len(DATASETS)], CLASSES[i % len(CLASSES)]))
    for cell in zigzag:
        if extra == 0:
            break
        if cell in cells and quotas[cell] < len(cells[cell]) and len(cells[cell]) % 3:
            quotas[cell] += 1
            extra -= 1
    if extra:
        raise ValueError(f"Could not place {extra} extra held-out records; cell sizes: "
                         f"{ {c: len(i) for c, i in cells.items()} }")
    return quotas


def _fails(item: dict) -> list[int]:
    return [int(not item["human"][k]) for k in CRITERIA_KEYS]


def make_split(items: list[dict], seed: int, iterations: int) -> tuple[set, dict]:
    """Returns (held_out item keys, quotas)."""
    cells = defaultdict(list)
    for it in sorted(items, key=lambda i: i["key"]):
        cells[(it["dataset"], it["sequence_classification"])].append(it)
    quotas = cell_quotas(cells)

    fails = {it["key"]: _fails(it) for it in items}
    any_fail = {key: int(any(f)) for key, f in fails.items()}

    # Groups the fail counts are balanced over: whole pool, each dataset, each class.
    groups = [("all", 3.0, [it["key"] for it in items])]
    for ds in sorted({it["dataset"] for it in items}):
        groups.append((ds, 1.0, [it["key"] for it in items if it["dataset"] == ds]))
    for cls in sorted({it["sequence_classification"] for it in items}):
        groups.append((cls, 1.0, [it["key"] for it in items if it["sequence_classification"] == cls]))
    totals = [[sum(fails[k][i] for k in keys) for i in range(len(CRITERIA_KEYS))] for _, _, keys in groups]
    cell_any_total = {cell: sum(any_fail[it["key"]] for it in members) for cell, members in cells.items()}

    def loss(held: set) -> float:
        total = 0.0
        for (_, weight, keys), group_totals in zip(groups, totals):
            for i, t in enumerate(group_totals):
                if t:
                    h = sum(fails[k][i] for k in keys if k in held)
                    total += weight * (h - t / 3) ** 2 / max(t / 3, 1)
        for cell, members in cells.items():
            t = cell_any_total[cell]
            h = sum(any_fail[it["key"]] for it in members if it["key"] in held)
            total += (h - t / 3) ** 2 / max(t / 3, 1)
        return total

    rng = random.Random(seed)
    held = set()
    for cell, members in cells.items():
        held |= {it["key"] for it in rng.sample(members, quotas[cell])}

    current = loss(held)
    swappable = [cell for cell in cells if 0 < quotas[cell] < len(cells[cell])]
    for _ in range(iterations):
        cell = rng.choice(swappable)
        out_key = rng.choice([it["key"] for it in cells[cell] if it["key"] in held])
        in_key = rng.choice([it["key"] for it in cells[cell] if it["key"] not in held])
        candidate = (held - {out_key}) | {in_key}
        candidate_loss = loss(candidate)
        if candidate_loss <= current:
            held, current = candidate, candidate_loss
    return held, quotas


def summarize(items: list[dict], held: set) -> dict:
    """Counts per part, for the printout and the manifest."""
    summary = {}
    for part, in_part in (("search", lambda k: k not in held), ("held_out", lambda k: k in held)):
        sub = [it for it in items if in_part(it["key"])]
        summary[part] = {
            "records": len(sub),
            "by_dataset": {ds: sum(it["dataset"] == ds for it in sub) for ds in DATASETS},
            "by_classification": {c: sum(it["sequence_classification"] == c for it in sub) for c in CLASSES},
            "human_fails_per_criterion": {k: sum(not it["human"][k] for it in sub) for k in CRITERIA_KEYS},
            "records_with_a_fail": sum(any(_fails(it)) for it in sub),
        }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Split the gold pool 2/3 search, 1/3 held-out.")
    parser.add_argument("--root", default="dataset_short")
    parser.add_argument("--gold_file", default=DEFAULT_GOLD_FILE,
                        help="Gold file name inside each dataset folder, e.g. gold_all_relabeled.json.")
    parser.add_argument("--datasets", nargs="+", default=DATASETS)
    parser.add_argument("--output", default="dataset_short/judge_split.json")
    parser.add_argument("--manifest", default="docs/llm_judge_validation_log.json")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--iterations", type=int, default=40000, help="Swap attempts when balancing human fails.")
    args = parser.parse_args()

    items = load_gold(args.datasets, args.root, args.gold_file)
    held, quotas = make_split(items, args.seed, args.iterations)
    summary = summarize(items, held)

    split = {
        "created": _now_iso(),
        "seed": args.seed,
        "gold_file": args.gold_file,
        "rule": "dataset x classification quotas (2/3 search, 1/3 held_out); human-fail counts per criterion "
                "balanced inside the quotas",
        "held_out_quota_per_cell": {f"{d}/{c}": n for (d, c), n in sorted(quotas.items())},
        "summary": summary,
        "search": sorted(it["key"] for it in items if it["key"] not in held),
        "held_out": sorted(held),
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(split, f, indent=2)

    for part in ("search", "held_out"):
        s = summary[part]
        print(f"{part}: {s['records']} records  datasets {s['by_dataset']}  classes {s['by_classification']}")
        print(f"  human fails per criterion {list(s['human_fails_per_criterion'].values())}  "
              f"records with a fail {s['records_with_a_fail']}")

    append_manifest_entry(args.manifest, {
        "step": 3,
        "action": "gold_split",
        "timestamp": split["created"],
        "dataset": "all" if len(args.datasets) > 1 else args.datasets[0],
        "params": {"seed": args.seed, "iterations": args.iterations, "held_out_fraction": "1/3"},
        "inputs": [f"{args.root}/{d}/{args.gold_file}" for d in args.datasets],
        "outputs": [args.output],
        "metrics": {"agreement": None, "kappa": None, "false_negative_rate": None, "detail": summary},
        "notes": "2/3 search, 1/3 held-out split of the gold pool; rank configs on 'search', confirm the winner on 'held_out'.",
    })
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
