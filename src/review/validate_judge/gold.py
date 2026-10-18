"""
Loads the merged, human-reviewed gold pool (see src/sampling/merge_gold.py) into the flat
per-record items the judge search works on: what the judge is shown, plus the human's
5-criterion verdicts it is scored against.
"""

import json

from src.help_functions.human_review_io import format_logs_for_review
from src.help_functions.review_criteria import CRITERIA_KEYS

DATASETS = ["bgl", "hdfs", "thunderbird"]
DEFAULT_GOLD_FILE = "gold_all_human_reviewed.json"
SESSION_BASED = {"bgl": False, "thunderbird": False, "hdfs": True}


def item_key(dataset: str, record_id: str) -> str:
    return f"{dataset}:{record_id}"


def _natural_ids(dataset: str, root: str) -> set[str]:
    with open(f"{root}/{dataset}/used_ids.json", "r", encoding="utf-8") as f:
        return {e["id"] for e in json.load(f) if e["purpose"] == "gold_natural"}


def load_gold(datasets: list[str] = None, root: str = "dataset_short", gold_file: str = DEFAULT_GOLD_FILE) -> list[dict]:
    """
    One item per gold record:
      key, dataset, id, stratum ("natural" | "supplemental"), session_based,
      sequence_classification ("normal" | "abnormal"), log_lines (as the reviewer saw them),
      explanation, human (criterion key -> True for PASS / False for FAIL).
    """
    items = []
    for dataset in datasets or DATASETS:
        with open(f"{root}/{dataset}/{gold_file}", "r", encoding="utf-8") as f:
            records = json.load(f)
        natural = _natural_ids(dataset, root)
        session_based = SESSION_BASED[dataset]

        for record in records:
            record_id = record["metadata"]["identity"]["id"]
            classification = "abnormal" if record["classification"] == "anomaly" else record["classification"]
            raw_logs = record["metadata"]["raw_content"].get("raw_log_sequence")
            human = record["metadata"]["hallucination-check"]["criteria_scores"]

            items.append({
                "key": item_key(dataset, record_id),
                "dataset": dataset,
                "id": record_id,
                "stratum": "natural" if record_id in natural else "supplemental",
                "session_based": session_based,
                "sequence_classification": classification,
                "log_lines": format_logs_for_review(record["input"], raw_logs, session_based),
                "explanation": record["explanation"],
                "human": {k: bool(human[k]) for k in CRITERIA_KEYS},
            })
    return items


DEFAULT_SPLIT_FILE = "dataset_short/judge_split.json"
SPLIT_PARTS = ["all", "search", "held_out"]


def select_split(items: list[dict], part: str, split_file: str = DEFAULT_SPLIT_FILE) -> list[dict]:
    """
    Keeps the items of one part of the split written by src/sampling/split_gold.py: "search" (2/3, where
    configs are compared), "held_out" (1/3, to confirm the winner) or "all" (no filtering). Every item
    must appear in the split file, otherwise it was made from a different gold pool.
    """
    if part == "all":
        return items
    with open(split_file, "r", encoding="utf-8") as f:
        split = json.load(f)
    known = set(split["search"]) | set(split["held_out"])
    unknown = [it["key"] for it in items if it["key"] not in known]
    if unknown:
        raise ValueError(f"{len(unknown)} gold items are missing from {split_file} (e.g. {unknown[0]}); "
                         f"re-run src.sampling.split_gold.")
    wanted = set(split[part])
    return [it for it in items if it["key"] in wanted]
