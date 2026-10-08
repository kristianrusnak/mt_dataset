"""
Turns a JudgeConfig into a fitness number: run the judge over the gold pool, compare to the
human verdicts, log the run.

Every search method goes through Evaluator.evaluate(), so they share one on-disk cache and one
scoring rule. Per config, the judge's raw output lives in its own file (`<runs_dir>/<config.key>.json`)
and doubles as the resume point:
  - results are checkpointed every `checkpoint_every` calls (atomic write), so a crash or Ctrl-C
    loses at most that many calls;
  - a result is reused only if the prompt template and the item's content still hash the same;
    if the prompt changed, the old file is set aside as `<name>.stale-<timestamp>.json`;
  - transport failures are stored but retried next run; invalid model output is final.

Scoring of failures: an item whose output stayed invalid after the retry counts as wrong on all 5
criteria (the model failed the task). Items with only transport errors are left out, and if more than
MAX_ERROR_RATE of the pool is missing the config is discarded (fitness 0).
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from src.help_functions.manifest_log import append_manifest_entry
from src.review.validate_judge.judge import (
    InvalidJudgeOutput, JudgeConfig, call_judge, item_fingerprint, prompt_fingerprint,
)
from src.review.validate_judge.metrics import score_config

MAX_ERROR_RATE = 0.05


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(path: str, data) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


class Evaluator:
    def __init__(self, items, runs_dir="dataset_short/judge_runs", manifest_path="docs/llm_judge_validation_log.json",
                 judge_fn=call_judge, max_workers=8, fn_weight=0.7, search_algorithm=None, gold_inputs=None,
                 checkpoint_every=20):
        self.items = items
        self.runs_dir = runs_dir
        self.manifest_path = manifest_path
        self.judge_fn = judge_fn
        self.max_workers = max_workers
        self.fn_weight = fn_weight
        self.search_algorithm = search_algorithm
        self.gold_inputs = gold_inputs or []
        self.checkpoint_every = checkpoint_every
        self._memo: dict[str, dict] = {}
        self._fingerprints = {it["key"]: item_fingerprint(it) for it in items}
        os.makedirs(runs_dir, exist_ok=True)

    def run_path(self, config: JudgeConfig) -> str:
        return os.path.join(self.runs_dir, f"{config.key}.json")

    def _load_run(self, config: JudgeConfig) -> dict:
        path = self.run_path(config)
        template_hash = prompt_fingerprint(config.prompt_id)
        fresh = {"config": config.as_params(), "prompt_fingerprint": template_hash, "results": {}}
        if not os.path.exists(path):
            return fresh
        with open(path, "r", encoding="utf-8") as f:
            run = json.load(f)
        if run.get("prompt_fingerprint") != template_hash:
            stale = path.replace(".json", f".stale-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json")
            os.replace(path, stale)
            print(f"  prompt wording changed for {config.key}; old results kept as {os.path.basename(stale)}")
            return fresh
        return run

    def _is_done(self, run: dict, item: dict) -> bool:
        r = run["results"].get(item["key"])
        if not r or r.get("input_fingerprint") != self._fingerprints[item["key"]]:
            return False
        return "scores" in r or r.get("invalid_output", False)

    def _judge_one(self, config: JudgeConfig, item: dict) -> tuple[str, dict]:
        base = {"input_fingerprint": self._fingerprints[item["key"]]}
        try:
            return item["key"], {**base, **self.judge_fn(config, item)}
        except InvalidJudgeOutput as e:
            return item["key"], {**base, "invalid_output": True, "error": str(e), "raw": e.raw[:2000]}
        except Exception as e:  # transport trouble: stored, retried next run
            return item["key"], {**base, "error": f"{type(e).__name__}: {e}"}

    def _run_missing(self, config: JudgeConfig, run: dict, todo: list) -> None:
        pool = ThreadPoolExecutor(max_workers=self.max_workers)
        futures = [pool.submit(self._judge_one, config, it) for it in todo]
        done = 0
        try:
            for future in as_completed(futures):
                key, result = future.result()
                run["results"][key] = result
                done += 1
                if done % self.checkpoint_every == 0:
                    atomic_write_json(self.run_path(config), run)
                    print(f"  {config.key}: {done}/{len(todo)} calls done")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)  # on Ctrl-C, drop queued calls and save what finished
            atomic_write_json(self.run_path(config), run)

    def _already_logged(self, config: JudgeConfig) -> bool:
        if not os.path.exists(self.manifest_path):
            return False
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return any(e.get("action") == "llm_as_judge_run" and self.run_path(config) in e.get("outputs", [])
                       for e in json.load(f))

    def evaluate(self, config: JudgeConfig) -> dict:
        if config.key in self._memo:
            return self._memo[config.key]

        run = self._load_run(config)
        todo = [it for it in self.items if not self._is_done(run, it)]
        if todo:
            self._run_missing(config, run, todo)

        verdicts, invalid = {}, 0
        for it in self.items:
            r = run["results"].get(it["key"], {})
            if "scores" in r:
                verdicts[it["key"]] = r["scores"]
            elif r.get("invalid_output"):
                verdicts[it["key"]] = {c: not v for c, v in it["human"].items()}  # wrong on every criterion
                invalid += 1
        missing = sum(1 for it in self.items if it["key"] not in verdicts)
        error_rate = missing / max(len(self.items), 1)

        metrics = score_config(self.items, verdicts, self.fn_weight)
        natural = [it for it in self.items if it["stratum"] == "natural"]
        metrics["natural_only"] = score_config(natural, verdicts, self.fn_weight)["overall"]
        metrics["by_dataset"] = {
            ds: score_config([it for it in self.items if it["dataset"] == ds], verdicts, self.fn_weight)["overall"]
            for ds in sorted({it["dataset"] for it in self.items})
        }
        metrics["invalid_output_rate"] = invalid / max(len(self.items), 1)
        metrics["error_rate"] = error_rate
        if error_rate > MAX_ERROR_RATE or metrics["overall"]["fitness"] is None:
            metrics["overall"]["fitness"] = 0.0
            metrics["discarded"] = f"{error_rate:.2%} of items unscored (transport errors), above {MAX_ERROR_RATE:.0%}"

        # One manifest entry per config's real work; a pure cache read only logs if nothing was logged before.
        if todo or not self._already_logged(config):
            append_manifest_entry(self.manifest_path, {
                "step": 3,
                "action": "llm_as_judge_run",
                "timestamp": _now_iso(),
                "dataset": "all" if len({it["dataset"] for it in self.items}) > 1 else self.items[0]["dataset"],
                "params": {**config.as_params(), "search_algorithm": self.search_algorithm, "fn_weight": self.fn_weight},
                "inputs": self.gold_inputs,
                "outputs": [self.run_path(config)],
                "metrics": {
                    "agreement": metrics["overall"]["agreement"],
                    "kappa": metrics["overall"]["kappa"],
                    "false_negative_rate": metrics["overall"]["false_negative_rate"],
                    "fitness": metrics["overall"]["fitness"],
                    "detail": metrics,
                },
                "notes": f"{len(todo)} judge calls made this time, {len(self.items) - len(todo)} served from the run file.",
            })

        self._memo[config.key] = metrics
        return metrics

    def fitness(self, config: JudgeConfig) -> float:
        return self.evaluate(config)["overall"]["fitness"]
