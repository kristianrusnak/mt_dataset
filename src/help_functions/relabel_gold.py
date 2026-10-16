"""
Writes `gold_all_relabeled.json` per dataset: the merged human-reviewed gold pool with the criterion-1
"ambiguous cause" rule applied, leaving `gold_all_human_reviewed.json` untouched.

The rule (confirmed by the reviewer 2026-10-16): if sentence 1 of an abnormal sequence's explanation names a
[normal]-tagged line as part of the cause -- even next to the real driver -- criterion 1 is FAIL. 39 existing
labels already followed it; the records below were the PASS ones that did not. They were found by matching each
explanation's sentence 1 against the [normal]-tagged templates and then read by hand (docs/llm_judge_grid_search_run1.md).

Every changed record gets a `label_revisions` entry in its hallucination-check block, so the file says which
labels are no longer the reviewer's original click. Datasets with no changes are copied as is, so the judge
search can read one file name for all three.

Run from the repo root:  uv run python -m src.help_functions.relabel_gold
"""

import argparse
import json

from src.help_functions.human_review_io import failed_criteria_flags

RULE = ("Criterion 1 fails when sentence 1 names a [normal]-tagged line as part of the cause, even alongside "
        "the real abnormal driver (ambiguous cause -> fail).")
REVISED_ON = "2026-10-16"
APPLIED_BY = "Claude (Sonnet 5.5); rule confirmed by Kristian Rusnak"

# Record-id prefixes (first 8 characters) whose criterion 1 changes PASS -> FAIL.
REVISIONS = {
    "bgl": ["10d9fc41", "a9933c38", "57355eea", "6551600f"],
    "thunderbird": ["3163b498", "1258081d", "dcd69dc0", "de635f21"],
    "hdfs": [],
}
CRITERION = "root_cause_correctness"


def relabel(dataset: str, source: str, target: str) -> int:
    with open(source, "r", encoding="utf-8") as f:
        records = json.load(f)

    changed = 0
    for record in records:
        record_id = record["metadata"]["identity"]["id"]
        if not any(record_id.startswith(prefix) for prefix in REVISIONS[dataset]):
            continue
        check = record["metadata"]["hallucination-check"]
        if not check["criteria_scores"][CRITERION]:
            raise ValueError(f"{dataset}:{record_id} criterion 1 is already FAIL; the revision list is stale.")
        check["criteria_scores"][CRITERION] = False
        check["hallucination_flags"] = failed_criteria_flags(check["criteria_scores"])
        check.setdefault("label_revisions", []).append({
            "criterion": CRITERION, "from": True, "to": False, "rule": RULE,
            "revised_on": REVISED_ON, "applied_by": APPLIED_BY,
        })
        changed += 1

    expected = len(REVISIONS[dataset])
    if changed != expected:
        raise ValueError(f"{dataset}: expected {expected} revisions, applied {changed}.")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply the criterion-1 ambiguous-cause rule to the gold pool.")
    parser.add_argument("--root", default="dataset_short")
    parser.add_argument("--source_name", default="gold_all_human_reviewed.json")
    parser.add_argument("--target_name", default="gold_all_relabeled.json")
    args = parser.parse_args()

    for dataset in REVISIONS:
        n = relabel(dataset, f"{args.root}/{dataset}/{args.source_name}", f"{args.root}/{dataset}/{args.target_name}")
        print(f"{dataset}: {n} labels changed -> {args.root}/{dataset}/{args.target_name}")
