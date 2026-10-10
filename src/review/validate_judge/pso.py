"""
PSO slot -- template only, the algorithm is deliberately not written yet (variant still undecided).

Fill in the four methods; run_search (search_algorithm.py) handles evaluation, caching, logging and
resume. See the resume contract there: ask() repeatable and RNG-free, all randomness inside tell(),
RNG state saved via rng_state_to_json.

Search space notes for whoever implements it:
  - Positions live in the unit cube [0,1]^3 (mode, temperature, effort) and are mapped to a config
    by SearchSpace.decode. A mode is a model + prompt pair. Mode and effort are categories encoded as a
    position on an axis, so list order in search_space.json has no real meaning; the effort axis is
    also relative to the chosen mode (each mode has its own list of efforts). A variant that handles
    categorical axes natively (e.g. discrete/binary PSO) avoids that.
  - Fitness is higher-is-better, in [-1, 1] (mean Youden's J; 0 = no better than ignoring the input).
  - Repeated configs are free (cached), so a swarm converging onto one config costs nothing extra.
"""

import random
from dataclasses import asdict, dataclass

from src.review.validate_judge.search_algorithm import SearchAlgorithm


@dataclass
class PSOParams:
    swarm_size: int = 8
    iterations: int = 6
    seed: int = 0
    # add the variant's own hyperparameters here (inertia, acceleration coefficients, ...)


class PSO(SearchAlgorithm):
    name = "pso"

    def __init__(self, params: PSOParams):
        self.p = params
        self.rng = random.Random(params.seed)
        # TODO: initial positions/velocities, per-particle best, global best, round counter

    def ask(self) -> list:
        raise NotImplementedError("PSO is not implemented yet")

    def tell(self, fitnesses: list) -> None:
        raise NotImplementedError("PSO is not implemented yet")

    def is_done(self) -> bool:
        raise NotImplementedError("PSO is not implemented yet")

    def state_dict(self) -> dict:
        raise NotImplementedError("PSO is not implemented yet")

    def load_state_dict(self, state: dict) -> None:
        raise NotImplementedError("PSO is not implemented yet")

    def params(self) -> dict:
        return asdict(self.p)
