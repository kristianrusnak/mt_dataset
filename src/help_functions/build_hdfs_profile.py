"""
Builds the HDFS "reference profile" the judge prompt uses in place of per-line tags: for every parsed log
template, the share of normal blocks and of anomalous blocks that contain it.

HDFS has no per-line ground truth, so a judge reading one block cannot tell that e.g. `invalidSet` lines
(in most normal blocks) are routine while a replication request (rare in normal blocks) is not. The profile
gives it that missing picture.

Counted the same way the gold/production draws are built (see dedup_pool.py): each distinct ordered template
sequence counts at most K times per class, and sequences that occur under both classes are dropped. Without
the cap, a few mega-clusters of identical simple blocks would make every basic event look "routine". Gold
ids are skipped so the profile is not derived from the records the judge is scored on.

Usage (from the repo root; streams a ~3 GB file once, expect several minutes):
    uv run python -m src.help_functions.build_hdfs_profile
"""

import argparse
import hashlib
import json
from collections import defaultdict

import json_stream


def build_profile(dataset_path: str, used_ids_path: str, k: int = 3, abnormal_label: str = "anomaly") -> dict:
    with open(used_ids_path, "r", encoding="utf-8") as f:
        skip = {str(e["id"]) for e in json.load(f)}

    seen = defaultdict(lambda: {"count": defaultdict(int), "templates": None})
    with open(dataset_path, "r", encoding="utf-8") as f:
        for n, item in enumerate(json_stream.load(f), 1):
            # key order matters for json_stream: input, classification, ..., metadata
            templates = list(item["input"])
            classification = item["classification"]
            seq_id = str(item["metadata"]["identity"]["id"])
            if seq_id in skip:
                continue
            h = hashlib.md5("\n".join(templates).encode("utf-8")).hexdigest()
            entry = seen[h]
            entry["count"][classification] += 1
            if entry["templates"] is None:
                entry["templates"] = sorted(set(templates))
            if n % 100000 == 0:
                print(f"  {n} records read")

    totals = {"normal": 0, abnormal_label: 0}
    present = {"normal": defaultdict(int), abnormal_label: defaultdict(int)}
    dropped = 0
    for entry in seen.values():
        if len(entry["count"]) > 1:
            dropped += 1
            continue
        (cls, count), = entry["count"].items()
        if cls not in totals:
            continue
        weight = min(count, k)
        totals[cls] += weight
        for t in entry["templates"]:
            present[cls][t] += weight

    templates = sorted(set(present["normal"]) | set(present[abnormal_label]))
    return {
        "k": k,
        "cross_class_sequences_dropped": dropped,
        "blocks_counted": totals,
        "templates": [
            {
                "template": t,
                "normal_share": present["normal"][t] / totals["normal"],
                "anomaly_share": present[abnormal_label][t] / totals[abnormal_label],
            }
            for t in templates
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the HDFS template-prevalence profile for the judge prompt.")
    parser.add_argument("--dataset", default="dataset_short/hdfs/full_not_explained.json")
    parser.add_argument("--used_ids", default="dataset_short/hdfs/used_ids.json")
    parser.add_argument("--output", default="src/prompts/judge_criteria/hdfs_profile.json")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()

    profile = build_profile(args.dataset, args.used_ids, args.k)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    print(f"wrote {len(profile['templates'])} templates to {args.output}; blocks counted {profile['blocks_counted']}")
