"""
Merges each dataset's human-reviewed natural-core and supplemental gold files into one
`gold_all_human_reviewed.json` -- the single pool the judge-config search scores against.

Records are not modified (the canonical schema from window_template.py stays untouched).
Which stratum a record came from is not copied into the record; it stays recoverable from
`dataset_short/<dataset>/used_ids.json` (purpose `gold_natural` / `gold_supplemental`), which
`src/review/validate_judge/gold.py` reads when it needs natural-core-only numbers.

Run from the repo root:
    uv run python -m src.sampling.merge_gold
"""

import argparse
import json
from datetime import datetime, timezone

from src.help_functions.manifest_log import append_manifest_entry
from src.help_functions.review_criteria import CRITERIA_KEYS

DATASETS = ["bgl", "hdfs", "thunderbird"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _record_id(record: dict) -> str:
    return record["metadata"]["identity"]["id"]


def merge_dataset(dataset: str, root: str, manifest_path: str) -> str:
    natural_path = f"{root}/{dataset}/gold_natural_human_reviewed.json"
    supplemental_path = f"{root}/{dataset}/gold_supplemental_human_reviewed.json"
    output_path = f"{root}/{dataset}/gold_all_human_reviewed.json"

    natural = _load(natural_path)
    supplemental = _load(supplemental_path)
    merged = natural + supplemental

    ids = [_record_id(r) for r in merged]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{dataset}: natural and supplemental files share record ids")

    for record in merged:
        scores = record["metadata"]["hallucination-check"].get("criteria_scores") or {}
        if set(scores) != set(CRITERIA_KEYS):
            raise ValueError(f"{dataset}: record {_record_id(record)} lacks a full human criteria_scores vector")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=4)

    append_manifest_entry(manifest_path, {
        "step": 2,
        "action": "gold_merge",
        "timestamp": _now_iso(),
        "dataset": dataset,
        "params": {"natural": len(natural), "supplemental": len(supplemental)},
        "inputs": [natural_path, supplemental_path],
        "outputs": [output_path],
        "metrics": {"agreement": None, "kappa": None, "false_negative_rate": None},
        "notes": (
            "Natural core and supplemental pool merged into one scoring pool. The headline numbers can "
            "still be reported on the natural core alone by filtering ids through used_ids.json."
        ),
    })
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Merge natural + supplemental human-reviewed gold files.")
    parser.add_argument("--root", default="dataset_short")
    parser.add_argument("--manifest", default="docs/llm_judge_validation_log.json")
    parser.add_argument("--datasets", nargs="+", default=DATASETS)
    args = parser.parse_args()

    for dataset in args.datasets:
        path = merge_dataset(dataset, args.root, args.manifest)
        print(f"{dataset}: wrote {path}")


if __name__ == "__main__":
    main()
