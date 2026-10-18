"""
Re-scores every config that already has a run file on one part of the gold split, using only the cached
judge outputs: no LLM calls, no API key, no run file touched. Use it to rank the grid-search configs on the
2/3 "search" part (or check them on "held_out") without re-running anything.

A config is skipped (and listed) when its run file is missing or its prompt wording changed since it was run.
Results go to a JSON file (every config, best first) and a ranked table is printed. One `grid_rescore` entry
is added to the manifest.

Run from the repo root:
    uv run python -m src.review.validate_judge.rescore                  # the 2/3 search part
    uv run python -m src.review.validate_judge.rescore --split held_out
"""

import argparse
import glob
import json
import os
from datetime import datetime, timezone

from src.help_functions.manifest_log import append_manifest_entry
from src.help_functions.review_criteria import CRITERIA_KEYS
from src.review.validate_judge.evaluator import Evaluator
from src.review.validate_judge.gold import (
    DATASETS, DEFAULT_GOLD_FILE, DEFAULT_SPLIT_FILE, SPLIT_PARTS, load_gold, select_split,
)
from src.review.validate_judge.judge import JudgeConfig


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_files(runs_dir: str) -> list[str]:
    """Per-config run files only (not stale copies, search-state files or half-written temp files)."""
    return sorted(p for p in glob.glob(os.path.join(runs_dir, "*.json"))
                  if ".stale-" not in p and not p.endswith("_state.json"))


def _row(config: JudgeConfig, metrics: dict) -> dict:
    overall = metrics["overall"]
    return {
        "key": config.key,
        **config.as_params(),
        "fitness": overall["fitness"],
        "agreement": overall["agreement"],
        "kappa": overall["kappa"],
        "false_negative_rate": overall["false_negative_rate"],
        "youden_j_per_criterion": {c: metrics["per_criterion"][c]["youden_j"] for c in CRITERIA_KEYS},
        "fitness_by_dataset": {ds: m["fitness"] for ds, m in metrics["by_dataset"].items()},
        "n_scored": metrics["n_scored"],
        "error_rate": metrics["error_rate"],
        "invalid_output_rate": metrics["invalid_output_rate"],
        "discarded": metrics.get("discarded"),
    }


def _fmt(value) -> str:
    return "  -  " if value is None else f"{value:.3f}"


def main():
    parser = argparse.ArgumentParser(description="Rank cached judge runs on one part of the gold split.")
    parser.add_argument("--split", choices=SPLIT_PARTS, default="search")
    parser.add_argument("--split_file", default=DEFAULT_SPLIT_FILE)
    parser.add_argument("--root", default="dataset_short")
    parser.add_argument("--runs_dir", default="dataset_short/judge_runs")
    parser.add_argument("--datasets", nargs="+", default=DATASETS)
    parser.add_argument("--gold_file", default="gold_all_relabeled.json",
                        help=f"Gold file name inside each dataset folder (the search default is {DEFAULT_GOLD_FILE}).")
    parser.add_argument("--output", default=None,
                        help="Default: docs/llm_judge_grid_results_<split>.json")
    parser.add_argument("--manifest", default="docs/llm_judge_validation_log.json")
    args = parser.parse_args()

    output = args.output or f"docs/llm_judge_grid_results_{args.split}.json"
    items = select_split(load_gold(args.datasets, args.root, args.gold_file), args.split, args.split_file)
    evaluator = Evaluator(items, args.runs_dir, args.manifest)  # only used for scoring, never for judging

    rows, skipped = [], []
    for path in _run_files(args.runs_dir):
        with open(path, "r", encoding="utf-8") as f:
            params = json.load(f)["config"]
        config = JudgeConfig(params["model"], params["temperature"], params["prompt_id"], params["effort"])
        metrics = evaluator.score_cached(config)
        if metrics is None:
            skipped.append(config.key)
        else:
            rows.append(_row(config, metrics))
    rows.sort(key=lambda r: r["fitness"], reverse=True)

    print(f"{len(rows)} configs scored on the '{args.split}' part ({len(items)} records); {len(skipped)} skipped\n")
    print(f"{'#':>3}  {'config':<58} {'fitness':>7} {'agree':>6} {'kappa':>6} {'FNR':>6}  "
          + " ".join(f"{d[:4]:>5}" for d in DATASETS))
    for rank, r in enumerate(rows, start=1):
        by_ds = " ".join(f"{_fmt(r['fitness_by_dataset'].get(d)):>5}" for d in DATASETS)
        note = "  (discarded)" if r["discarded"] else ""
        print(f"{rank:>3}  {r['key']:<58} {_fmt(r['fitness']):>7} {_fmt(r['agreement']):>6} {_fmt(r['kappa']):>6} "
              f"{_fmt(r['false_negative_rate']):>6}  {by_ds}{note}")
    for key in skipped:
        print(f"skipped (no run file or prompt changed): {key}")

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump({"created": _now_iso(), "split": args.split, "split_file": args.split_file,
                   "gold_file": args.gold_file, "records": len(items), "skipped": skipped, "ranked": rows},
                  f, indent=2)
    print(f"\nwrote {output}")

    append_manifest_entry(args.manifest, {
        "step": 3,
        "action": "grid_rescore",
        "timestamp": _now_iso(),
        "dataset": "all" if len(args.datasets) > 1 else args.datasets[0],
        "params": {"split": args.split, "records": len(items), "configs_scored": len(rows), "skipped": skipped},
        "inputs": [f"{args.root}/{d}/{args.gold_file}" for d in args.datasets] + [args.split_file, args.runs_dir],
        "outputs": [output],
        "metrics": {"fitness": rows[0]["fitness"] if rows else None,
                    "detail": {"top5": [(r["key"], r["fitness"]) for r in rows[:5]]}},
        "notes": f"Cached judge runs re-scored on the '{args.split}' part of the gold split; no judge calls made.",
    })


if __name__ == "__main__":
    main()
