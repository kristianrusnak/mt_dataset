"""Brute-force baseline: score every config in the space."""

from src.review.validate_judge.evaluator import Evaluator
from src.review.validate_judge.search_space import SearchSpace


def run_grid(evaluator: Evaluator, space: SearchSpace) -> list:
    """Returns [(config, fitness)] best first."""
    results = []
    configs = space.all_configs()
    for i, config in enumerate(configs, start=1):
        fitness = evaluator.fitness(config)
        print(f"[grid {i}/{len(configs)}] {config.key}  fitness={fitness:.4f}")
        results.append((config, fitness))
    return sorted(results, key=lambda r: r[1], reverse=True)
