"""
Plug-in interface for metaheuristic searches over the judge-config space, plus the loop that drives them.

An algorithm only decides *where to look next*; scoring, caching and logging stay in the Evaluator.
The loop is "ask, evaluate, tell":

    positions = algo.ask()                  # points in the unit cube [0,1]^3: (model, temperature, prompt)
    fitnesses = [evaluator.fitness(space.decode(p)) for p in positions]
    algo.tell(fitnesses)                    # algorithm updates itself (best points, velocities, ...)

Resume contract: after every round the driver saves `algo.state_dict()` (atomically). On restart it
calls `load_state_dict()` and continues. For that to work:
  - `ask()` must be repeatable: derive positions from saved state and consume no randomness,
    so re-asking after a crash returns the same points (their judge calls are cached anyway).
  - all randomness (and the update of positions) happens in `tell()`; keep the RNG state inside
    `state_dict()` (see rng_state_to_json / rng_state_from_json).
  - `state_dict()` must be JSON-serialisable.
"""

import json
import os
import random
from abc import ABC, abstractmethod

from src.review.validate_judge.evaluator import Evaluator, atomic_write_json
from src.review.validate_judge.judge import JudgeConfig
from src.review.validate_judge.search_space import SearchSpace


class SearchAlgorithm(ABC):
    name: str = "unnamed"

    @abstractmethod
    def ask(self) -> list:
        """Positions (each a list of 3 floats in [0,1]) to evaluate this round."""

    @abstractmethod
    def tell(self, fitnesses: list) -> None:
        """Fitness for each position returned by the last ask(), in the same order."""

    @abstractmethod
    def is_done(self) -> bool: ...

    @abstractmethod
    def state_dict(self) -> dict: ...

    @abstractmethod
    def load_state_dict(self, state: dict) -> None: ...

    def params(self) -> dict:
        """Hyperparameters, for the manifest entry."""
        return {}


def rng_state_to_json(rng: random.Random) -> list:
    version, internal, gauss = rng.getstate()
    return [version, list(internal), gauss]


def rng_state_from_json(rng: random.Random, state: list) -> None:
    version, internal, gauss = state
    rng.setstate((version, tuple(internal), gauss))


def run_search(algo: SearchAlgorithm, evaluator: Evaluator, space: SearchSpace, state_path: str) -> dict:
    """Drives `algo` to completion (resuming from state_path if it exists). Returns
    {"best_config", "best_fitness", "history", "unique_configs_evaluated"}."""
    progress = {"round": 0, "best_fitness": float("-inf"), "best_config": None, "history": [], "evaluated": []}
    if os.path.exists(state_path):
        with open(state_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        algo.load_state_dict(saved["algorithm"])
        progress = saved["progress"]
        print(f"Resuming {algo.name} at round {progress['round']} from {state_path}")

    while not algo.is_done():
        configs = [space.decode(p) for p in algo.ask()]
        fitnesses = [evaluator.fitness(c) for c in configs]
        algo.tell(fitnesses)

        for config, fit in zip(configs, fitnesses):
            if config.key not in progress["evaluated"]:
                progress["evaluated"].append(config.key)
            if fit > progress["best_fitness"]:
                progress["best_fitness"], progress["best_config"] = fit, config.as_params()
        progress["round"] += 1
        progress["history"].append({"round": progress["round"], "best_fitness": progress["best_fitness"],
                                    "best_config": progress["best_config"],
                                    "unique_configs_evaluated": len(progress["evaluated"])})
        print(f"[{algo.name} round {progress['round']}] best={progress['best_fitness']:.4f} "
              f"{JudgeConfig(**progress['best_config']).key} (unique configs: {len(progress['evaluated'])})")

        atomic_write_json(state_path, {"algorithm": algo.state_dict(), "progress": progress})

    return {"best_config": JudgeConfig(**progress["best_config"]), "best_fitness": progress["best_fitness"],
            "history": progress["history"], "unique_configs_evaluated": len(progress["evaluated"])}
