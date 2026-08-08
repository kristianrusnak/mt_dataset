import json
import argparse
from datetime import datetime, timezone

from src.help_functions.json_deep_convert import deep_convert
from src.help_functions.manifest_log import append_manifest_entry
from src.help_functions.human_review_io import (
    get_user_input,
    format_logs_for_review,
    prompt_criteria_scores,
    failed_criteria_flags,
)
from json_stream import streamable_list, load

DATASET_NAME = "hdfs"
SESSION_BASED = True  # HDFS blocks only carry a block-level label, no per-line ground truth (see judge_prompt.py)


@streamable_list
def review_sequences(input_path: str, reviewer_id: str, stats: dict):
    """
    Iterates through every sequence in input_path (already the pre-selected
    gold/production set -- see docs/llm_judge_validation_plan.md -- no
    re-sampling happens here), prompts the human reviewer to score the
    5-criterion binary vector, and yields updated sequences. Sequences
    already human-reviewed are skipped so an interrupted review session can
    be resumed by re-running against the same input/output pair.
    """
    with open(input_path, 'r', encoding='utf-8') as input_file:
        for sequence_data_raw in load(input_file).persistent():
            sequence_data = deep_convert(sequence_data_raw)
            stats["total"] += 1

            sequence_id = sequence_data.get("metadata", {}).get("identity", {}).get("id")
            hallucination_check = sequence_data.get('metadata', {}).get('hallucination-check', {}) or {}

            if hallucination_check.get("verification_method") == "human" and hallucination_check.get("human_reviewed"):
                stats["skipped"] += 1
                yield sequence_data
                continue

            if not sequence_data.get('explanation'):
                print(f"Skipping sequence_id: {sequence_id} -- no explanation to review yet.")
                stats["skipped"] += 1
                yield sequence_data
                continue

            parsed_logs = sequence_data.get('input')
            logs = format_logs_for_review(parsed_logs, raw_logs=None, session_based=SESSION_BASED)

            print("\n" + "=" * 70)
            print(f"Reviewing sequence_id: {sequence_id}")
            print(f"Classification: {sequence_data.get('classification')}")
            print("Input (session-based -- no per-line ground truth, block-level label only):")
            print("\n".join(logs))
            print(f"\nExplanation: {sequence_data.get('explanation')}")
            print("=" * 70)

            criteria_scores = prompt_criteria_scores(hallucination_check.get('criteria_scores'))
            hallucination_flags = failed_criteria_flags(criteria_scores)

            corrected_reasoning_text = get_user_input(
                "Enter corrected_reasoning_text (blank if not needed)",
                hallucination_check.get('corrected_reasoning_text')
            )
            review_notes = get_user_input(
                "Enter review_notes",
                hallucination_check.get('review_notes')
            )

            sequence_data['metadata']['hallucination-check'] = {
                "verification_status": "verified",
                "verification_method": "human",
                "verifier_model": "review/human/hdfs/human_reviewer.py",
                "criteria_scores": criteria_scores,
                "hallucination_flags": hallucination_flags,
                "corrected_reasoning_text": corrected_reasoning_text or None,
                "human_reviewed": True,
                "reviewer_id": reviewer_id,
                "review_notes": review_notes or None,
                "review_timestamp": str(datetime.now())
            }
            stats["reviewed"] += 1

            yield sequence_data


def main(input_path: str, output_path: str, reviewer_id: str, manifest_path: str, stratum: str = None):
    stats = {"total": 0, "reviewed": 0, "skipped": 0}

    reviewed_data_stream = review_sequences(input_path, reviewer_id, stats)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(reviewed_data_stream, f, indent=4)

    print(f"\nReview process complete. Reviewed data saved to {output_path}")

    append_manifest_entry(manifest_path, {
        "step": 2,
        "action": "human_review_run",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset": DATASET_NAME,
        "stratum": stratum,
        "params": {
            "reviewer_id": reviewer_id,
            "criteria": "5-binary-criteria (see docs/llm_judge_validation_plan.md)",
        },
        "inputs": [input_path],
        "outputs": [output_path],
        "metrics": {},
        "notes": (
            f"{stats['reviewed']} sequences scored, {stats['skipped']} skipped "
            f"(already reviewed, or no explanation yet) out of {stats['total']} records read. "
            "Feeds step 3/4 judge-vs-human agreement scoring."
        ),
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Human review of HDFS log-sequence explanations against the 5-criterion binary vector.")
    parser.add_argument("--input", default="dataset_short/hdfs/gold_natural_explained.json", help="Input JSON file path")
    parser.add_argument("--output", default="dataset_short/hdfs/gold_natural_human_reviewed.json", help="Output JSON file path")
    parser.add_argument("--reviewer_id", default="Kristian Rusnak", help="Identifier of the human reviewer, logged per-record and to the manifest.")
    parser.add_argument("--manifest_path", default="docs/llm_judge_validation_log.json", help="Path to the append-only sampling/validation manifest.")
    parser.add_argument(
        "--stratum",
        default=None,
        choices=[None, "natural", "supplemental", "production"],
        help="Which gold stratum (or 'production') this input file is, logged to the manifest."
    )

    args = parser.parse_args()

    main(
        input_path=args.input,
        output_path=args.output,
        reviewer_id=args.reviewer_id,
        manifest_path=args.manifest_path,
        stratum=args.stratum,
    )