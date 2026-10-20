"""
Writes `gold_all_relabeled.json` per dataset: the merged human-reviewed gold pool with the label rules below
applied, leaving `gold_all_human_reviewed.json` untouched.

Rule 1 (confirmed by the reviewer 2026-10-16): if sentence 1 of an abnormal sequence's explanation names a
[normal]-tagged line as part of the cause -- even next to the real driver -- criterion 1 is FAIL. 39 existing
labels already followed it; the records below were the PASS ones that did not. They were found by matching each
explanation's sentence 1 against the [normal]-tagged templates and then read by hand (docs/llm_judge_grid_search_run1.md).

Rule 2 (confirmed by the reviewer 2026-10-20): the same for criterion 3 -- if sentence 3 of an abnormal sequence's
explanation offers a [normal]-tagged line as part of what rules out the normal verdict, the contrast does not
discriminate and criterion 3 is FAIL. Applied only to records whose sentence 3 does this itself; a sentence 3
that names only the real driver stays PASS even when sentence 1 was mixed. Found by reading the 24 abnormal
BGL/Thunderbird records that had criterion 1 FAIL and criterion 3 PASS.

Every changed record gets a `label_revisions` entry in its hallucination-check block, so the file says which
labels are no longer the reviewer's original click. Datasets with no changes are copied as is, so the judge
search can read one file name for all three.

Run from the repo root:  uv run python -m src.help_functions.relabel_gold
"""

import argparse
import json

from src.help_functions.human_review_io import failed_criteria_flags

# Each rule: criterion changed PASS -> FAIL, the rule text, who/when, and per dataset the record-id prefixes
# (first 8 characters) it applies to. Records may appear under several rules.
RULES = [
    {
        "criterion": "root_cause_correctness",
        "rule": ("Criterion 1 fails when sentence 1 names a [normal]-tagged line as part of the cause, even "
                 "alongside the real abnormal driver (ambiguous cause -> fail)."),
        "revised_on": "2026-10-16",
        "applied_by": "Claude (Sonnet 5.5); rule confirmed by Kristian Rusnak",
        "records": {
            "bgl": ["10d9fc41", "a9933c38", "57355eea", "6551600f"],
            "thunderbird": ["3163b498", "1258081d", "dcd69dc0", "de635f21"],
            "hdfs": [],
        },
    },
    {
        "criterion": "contrast_correctness",
        "rule": ("Criterion 3 fails when sentence 3 offers a [normal]-tagged line as part of what rules out the "
                 "normal verdict (the contrast then does not discriminate). A sentence 3 that names only the real "
                 "driver stays PASS even if sentence 1 was mixed."),
        "revised_on": "2026-10-20",
        "applied_by": "Claude (Sonnet 5.5); rule confirmed by Kristian Rusnak",
        "records": {
            "bgl": ["99d5c12a", "0aa40e03", "25201a95", "6551600f", "a52021e0"],
            "thunderbird": ["dcd69dc0", "1258081d"],
            "hdfs": [],
        },
    },
]
DATASETS = ["bgl", "hdfs", "thunderbird"]


def relabel(dataset: str, source: str, target: str) -> int:
    with open(source, "r", encoding="utf-8") as f:
        records = json.load(f)

    changed = 0
    for rule in RULES:
        criterion = rule["criterion"]
        prefixes = rule["records"][dataset]
        applied = 0
        for record in records:
            record_id = record["metadata"]["identity"]["id"]
            if not any(record_id.startswith(prefix) for prefix in prefixes):
                continue
            check = record["metadata"]["hallucination-check"]
            if not check["criteria_scores"][criterion]:
                raise ValueError(f"{dataset}:{record_id} {criterion} is already FAIL; the revision list is stale.")
            check["criteria_scores"][criterion] = False
            check["hallucination_flags"] = failed_criteria_flags(check["criteria_scores"])
            check.setdefault("label_revisions", []).append({
                "criterion": criterion, "from": True, "to": False, "rule": rule["rule"],
                "revised_on": rule["revised_on"], "applied_by": rule["applied_by"],
            })
            applied += 1
        if applied != len(prefixes):
            raise ValueError(f"{dataset}: {criterion} expected {len(prefixes)} revisions, applied {applied}.")
        changed += applied

    with open(target, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply the criterion-1 and criterion-3 mixing rules to the gold pool.")
    parser.add_argument("--root", default="dataset_short")
    parser.add_argument("--source_name", default="gold_all_human_reviewed.json")
    parser.add_argument("--target_name", default="gold_all_relabeled.json")
    args = parser.parse_args()

    for dataset in DATASETS:
        n = relabel(dataset, f"{args.root}/{dataset}/{args.source_name}", f"{args.root}/{dataset}/{args.target_name}")
        print(f"{dataset}: {n} labels changed -> {args.root}/{dataset}/{args.target_name}")
