"""
CLI for the judge-config search (plan steps 3-5). Run from the repo root:

    uv run python -m src.review.validate_judge.search estimate
    uv run python -m src.review.validate_judge.search grid
    uv run python -m src.review.validate_judge.search pso --seed 0   # once pso.py is filled in

Both searches resume where they left off if interrupted (judge calls via the per-config run files,
PSO's swarm via --state_path).

The judge needs LITELLM_API_KEY / LITELLM_API_BASE in the environment (same as the existing
llm_as_judge scripts). `estimate` makes no LLM calls.
"""

import argparse
from datetime import datetime, timezone

from dotenv import load_dotenv

from src.help_functions.manifest_log import append_manifest_entry
from src.review.validate_judge.evaluator import Evaluator
from src.review.validate_judge.gold import DATASETS, load_gold
from src.review.validate_judge.grid_search import run_grid
from src.review.validate_judge.pso import PSO, PSOParams
from src.review.validate_judge.search_algorithm import run_search
from src.review.validate_judge.search_space import SearchSpace


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    parser = argparse.ArgumentParser(description="Search the llm_as_judge config space against human verdicts.")
    parser.add_argument("mode", choices=["estimate", "grid", "pso"])
    parser.add_argument("--space", default="src/review/validate_judge/search_space.json")
    parser.add_argument("--root", default="dataset_short")
    parser.add_argument("--runs_dir", default="dataset_short/judge_runs")
    parser.add_argument("--manifest", default="docs/llm_judge_validation_log.json")
    parser.add_argument("--datasets", nargs="+", default=DATASETS)
    parser.add_argument("--max_workers", type=int, default=8, help="Parallel judge calls per config.")
    parser.add_argument("--fn_weight", type=float, default=0.7,
                        help="Weight of a missed fail vs a false alarm in the fitness (0.5 = equal).")
    parser.add_argument("--state_path", default="dataset_short/judge_runs/pso_state.json")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--swarm_size", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=6)
    args = parser.parse_args()

    load_dotenv()
    space = SearchSpace.from_json(args.space)
    items = load_gold(args.datasets, args.root)
    n_configs = len(space.all_configs())

    if args.mode == "estimate":
        print(f"Gold pool: {len(items)} items across {args.datasets}")
        print(f"Space: {len(space.models)} models x {len(space.temperatures)} temperatures x "
              f"{len(space.prompt_ids)} prompts = {n_configs} configs")
        print(f"Grid: {n_configs * len(items)} judge calls")
        print(f"Search algorithm upper bound (swarm x rounds, ignoring repeats): "
              f"{args.swarm_size * (args.iterations + 1) * len(items)} judge calls")
        return

    gold_inputs = [f"{args.root}/{d}/gold_all_human_reviewed.json" for d in args.datasets]
    evaluator = Evaluator(items, args.runs_dir, args.manifest, max_workers=args.max_workers,
                          fn_weight=args.fn_weight, search_algorithm=args.mode, gold_inputs=gold_inputs)

    if args.mode == "grid":
        ranked = run_grid(evaluator, space)
        best, best_fit = ranked[0]
        search_notes = {"configs_evaluated": len(ranked), "top5": [(c.key, f) for c, f in ranked[:5]]}
        params = {"fn_weight": args.fn_weight}
    else:
        algo = PSO(PSOParams(swarm_size=args.swarm_size, iterations=args.iterations, seed=args.seed))
        result = run_search(algo, evaluator, space, args.state_path)
        best, best_fit = result["best_config"], result["best_fitness"]
        search_notes = {"unique_configs_evaluated": result["unique_configs_evaluated"],
                        "space_size": n_configs, "history": result["history"]}
        params = {**algo.params(), "fn_weight": args.fn_weight}

    print(f"\nBest: {best.key}  fitness={best_fit:.4f}")
    append_manifest_entry(args.manifest, {
        "step": 3,
        "action": f"{args.mode}_search",
        "timestamp": _now_iso(),
        "dataset": "all" if len(args.datasets) > 1 else args.datasets[0],
        "params": {**best.as_params(), "search_algorithm": args.mode, "search_params": params},
        "inputs": [args.space] + gold_inputs,
        "outputs": [args.runs_dir],
        "metrics": {"fitness": best_fit, "detail": search_notes},
        "notes": "Best config found by this search run (params above are the winner's, search_params the search's).",
    })


if __name__ == "__main__":
    main()
