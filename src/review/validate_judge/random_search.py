"""
Random-search baseline: every round evaluates `pop_size` random configs that were not tried before.

Same rounds and batch size as the GA, so the two are compared on the same budget (use the
`unique_configs_evaluated` column of the history, since the GA re-asks its elites for free).
Same resume contract as the other algorithms: ask() reads saved state, tell() draws the next batch.
"""

import random
from dataclasses import asdict, dataclass

from src.review.validate_judge.search_algorithm import SearchAlgorithm, rng_state_from_json, rng_state_to_json
from src.review.validate_judge.search_space import SearchSpace


@dataclass
class RandomParams:
    pop_size: int = 8
    generations: int = 6  # rounds after the first
    seed: int = 0


class RandomSearch(SearchAlgorithm):
    name = "random"

    def __init__(self, params: RandomParams, space: SearchSpace):
        self.p = params
        self.space = space
        self.genomes = space.all_genomes()
        self.rng = random.Random(params.seed)
        self.generation = 0
        self.seen = set()
        self.batch = self._draw()

    def _draw(self) -> list:
        free = [g for g in self.genomes if g not in self.seen]
        return [list(g) for g in self.rng.sample(free, min(self.p.pop_size, len(free)))]

    def ask(self) -> list:
        return [self.space.encode(g) for g in self.batch]

    def tell(self, fitnesses: list) -> None:
        self.seen.update(tuple(g) for g in self.batch)
        self.generation += 1
        if not self.is_done():
            self.batch = self._draw()

    def is_done(self) -> bool:
        return self.generation > self.p.generations or len(self.seen) >= len(self.genomes)

    def state_dict(self) -> dict:
        return {"params": asdict(self.p), "space": self.space.signature(), "generation": self.generation,
                "batch": self.batch, "seen": sorted(list(g) for g in self.seen),
                "rng": rng_state_to_json(self.rng)}

    def load_state_dict(self, state: dict) -> None:
        if state["params"] != asdict(self.p) or state["space"] != self.space.signature():
            raise ValueError("Saved random-search state was made with different parameters or a different "
                             "search space; use another --state_path or delete the old one.")
        self.generation = state["generation"]
        self.batch = state["batch"]
        self.seen = {tuple(g) for g in state["seen"]}
        rng_state_from_json(self.rng, state["rng"])

    def params(self) -> dict:
        return asdict(self.p)
