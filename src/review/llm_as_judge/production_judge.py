"""
Runs the validated judge config over a whole explained dataset file and stores its verdicts in
`metadata.hallucination-check`, in the same shape the human reviewer writes (`criteria_scores` with the 5
criteria, derived `hallucination_flags`), plus the judge's own evidence per criterion and its config. For every criterion that FAILED, a short reason
is stored in `fail_reasons` ({criterion: reason}) and, joined, in `review_notes` (null when all five pass).
The reason is the judge's own justification for that criterion, not a second call.

This is the judge that was validated against the human gold set (src/review/validate_judge/): same prompt
builder, same call, same input rendering (`gold.judge_view`). It replaces the older per-dataset
`llm_as_judge.py` scripts for production, which use a different, unvalidated prompt and flag vocabulary.

It only records what the judge said. It does NOT decide accept/reject: how the 5 verdicts roll up into a
keep/drop rule is decided later, from the stored `criteria_scores`. `hallucination_flags` is just the
failed criteria keys (or ["valid"] when all five pass), kept so the record looks like a human-reviewed one.

Resumable: each finished verdict is appended to `<output_path>.verdicts.jsonl` right away. Re-running the
same command reuses them; a changed explanation, prompt or config is judged again. Records whose call
failed get `verification_status: "judge_failed"` and are retried on the next run. Records with no
explanation yet are passed through untouched.

Needs LITELLM_API_KEY and LITELLM_API_BASE (a local .env works).

    uv run python -m src.review.llm_as_judge.production_judge --dataset bgl
"""

import argparse
import itertools
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from json_stream import load, streamable_list

from src.help_functions.cached_parallel import process_records
from src.help_functions.json_deep_convert import deep_convert
from src.help_functions.human_review_io import failed_criteria_flags
from src.help_functions.manifest_log import append_manifest_entry
from src.help_functions.review_criteria import CRITERIA_KEYS
from src.review.validate_judge.gold import DATASETS, judge_view
from src.review.validate_judge.judge import JudgeConfig, call_judge, item_fingerprint, prompt_fingerprint

load_dotenv()

# The config chosen in the manifest's step-5 "decision" entry.
FINAL_CONFIG = JudgeConfig(model="deepseek-v4.1-flash", temperature=0.25, prompt_id="deepseek_v7", effort="high")


def _check_from_verdict(payload: dict, config: JudgeConfig, prompt_fp: str) -> dict:
    scores = payload["scores"]
    # Why each failed criterion failed: the judge's own per-criterion justification (1-2 sentences, written
    # before its verdict), reused as-is so the validated call is not changed or repeated.
    fail_reasons = {key: payload["evidence"][key] for key, passed in scores.items() if not passed}
    return {
        "verification_status": "verified",
        "verification_method": "llm_as_judge",
        "verifier_model": config.model,
        "criteria_scores": scores,
        "criteria_evidence": payload["evidence"],
        "judge_scratchpad": payload["scratchpad"],
        "judge_config": {**config.as_params(), "prompt_fingerprint": prompt_fp},
        "fail_reasons": fail_reasons,
        "hallucination_flags": failed_criteria_flags(scores),
        "corrected_reasoning_text": None,
        "human_reviewed": False,
        "reviewer_id": config.model,
        "review_notes": "\n".join(f"{key}: {reason}" for key, reason in fail_reasons.items()) or None,
        "review_timestamp": payload["judged_at"],
    }


def _check_from_failure(error: Exception, config: JudgeConfig, prompt_fp: str) -> dict:
    return {
        "verification_status": "judge_failed",
        "verification_method": "llm_as_judge",
        "verifier_model": config.model,
        "criteria_scores": None,
        "judge_config": {**config.as_params(), "prompt_fingerprint": prompt_fp},
        "hallucination_flags": None,
        "corrected_reasoning_text": None,
        "human_reviewed": False,
        "reviewer_id": config.model,
        "review_notes": f"{type(error).__name__}: {str(error)[:500]}",
        "review_timestamp": str(datetime.now()),
    }


def judge_records(records, dataset: str, config: JudgeConfig, cache_path: str, stats: dict, tally: dict,
                  max_workers: int = 8, judge_fn=call_judge):
    """Yields every record in order with `metadata.hallucination-check` filled in. `tally` collects, per
    criterion, how many verdicts passed and how many were given (for the manifest entry)."""
    prompt_fp = prompt_fingerprint(config.prompt_id)

    def key_fn(record):
        view = judge_view(dataset, record)
        return f"{record['metadata']['identity']['id']}|{item_fingerprint(view)}|{config.key}|{prompt_fp}"

    def compute(record):
        verdict = judge_fn(config, judge_view(dataset, record))
        return {**verdict, "judged_at": str(datetime.now())}

    def apply(record, payload):
        record["metadata"]["hallucination-check"] = _check_from_verdict(payload, config, prompt_fp)
        for key, passed in payload["scores"].items():
            tally[key]["given"] += 1
            tally[key]["passed"] += int(passed)
        return record

    def on_failure(record, error):
        print(f"  judge failed for {record['metadata']['identity']['id']}: {type(error).__name__}: {error}")
        record["metadata"]["hallucination-check"] = _check_from_failure(error, config, prompt_fp)
        return record

    return process_records(
        records, key_fn=key_fn, compute=compute, apply=apply, on_failure=on_failure,
        cache_path=cache_path, stats=stats, max_workers=max_workers,
        skip=lambda record: not record.get("explanation"),
    )


@streamable_list
def _stream(input_path, dataset, config, cache_path, stats, tally, max_workers, limit):
    with open(input_path, "r", encoding="utf-8") as f:
        records = (deep_convert(item) for item in load(f).persistent())
        if limit > 0:
            records = itertools.islice(records, limit)
        yield from judge_records(records, dataset, config, cache_path, stats, tally, max_workers)


def main(dataset: str, input_path: str, output_path: str, config: JudgeConfig, manifest_path: str,
         max_workers: int = 8, limit: int = -1):
    for var in ("LITELLM_API_KEY", "LITELLM_API_BASE"):
        if not os.environ.get(var):
            raise SystemExit(f"{var} is not set (put it in .env or export it).")

    cache_path = f"{output_path}.verdicts.jsonl"
    stats = {"total": 0, "skipped": 0, "from_cache": 0, "computed": 0, "failed": 0}
    tally = {key: {"given": 0, "passed": 0} for key in CRITERIA_KEYS}

    tmp_path = f"{output_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_stream(input_path, dataset, config, cache_path, stats, tally, max_workers, limit), f, indent=4)
    os.replace(tmp_path, output_path)  # a crash mid-run leaves any earlier output intact; the cache lets it resume

    print(f"Done: {stats}. Wrote {output_path}")

    append_manifest_entry(manifest_path, {
        "step": 6,
        "action": "llm_as_judge_production_run",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset": dataset,
        "params": {**config.as_params(), "prompt_fingerprint": prompt_fingerprint(config.prompt_id)},
        "inputs": [input_path],
        "outputs": [output_path, cache_path],
        "metrics": {
            "detail": {
                "records": stats,
                "pass_rate_per_criterion": {
                    key: (round(t["passed"] / t["given"], 4) if t["given"] else None) for key, t in tally.items()
                },
                "verdicts_per_criterion": {key: t["given"] for key, t in tally.items()},
            }
        },
        "notes": (
            f"Final judge config over a {dataset} file. Verdicts are stored as-is in "
            f"metadata.hallucination-check.criteria_scores; no accept/reject rule applied (decided later). "
            f"{stats['failed']} records failed (status judge_failed, retried on re-run); "
            f"{stats['skipped']} had no explanation and were passed through; "
            f"{stats['from_cache']} verdicts reused from the cache file. pass_rate_per_criterion counts only "
            f"the records judged in this file (cached ones included). Descriptive only: the judge's "
            f"agreement with humans is in the step-5 decision entry."
        ),
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the final (validated) judge config over an explained dataset file.")
    parser.add_argument("--dataset", required=True, choices=DATASETS)
    parser.add_argument("--input_path", default=None,
                        help="Explained dataset JSON. Default: dataset_short/<dataset>/production_explained.json")
    parser.add_argument("--output_path", default=None,
                        help="Where to write the judged dataset. Default: dataset_short/<dataset>/production_judged.json")
    parser.add_argument("--model", default=FINAL_CONFIG.model)
    parser.add_argument("--temperature", type=float, default=FINAL_CONFIG.temperature)
    parser.add_argument("--prompt_id", default=FINAL_CONFIG.prompt_id)
    parser.add_argument("--effort", default=FINAL_CONFIG.effort)
    parser.add_argument("--max_workers", type=int, default=8, help="Parallel judge calls.")
    parser.add_argument("--limit", type=int, default=-1,
                        help="Only judge the first N records of the input (smoke test). -1 for all. The output "
                             "then holds only those N records, so give it a different --output_path.")
    parser.add_argument("--manifest_path", default="docs/llm_judge_validation_log.json")
    args = parser.parse_args()

    main(
        dataset=args.dataset,
        input_path=args.input_path or f"dataset_short/{args.dataset}/production_explained.json",
        output_path=args.output_path or f"dataset_short/{args.dataset}/production_judged.json",
        config=JudgeConfig(args.model, args.temperature, args.prompt_id, args.effort),
        manifest_path=args.manifest_path,
        max_workers=args.max_workers,
        limit=args.limit,
    )
