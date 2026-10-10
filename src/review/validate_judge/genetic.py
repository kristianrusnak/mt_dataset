"""
Genetic algorithm over the judge-config space.

A config ("genome") is (mode index, temperature, effort index); a mode is a model + prompt pair, the effort
index points into that mode's own list of efforts, and temperature is a real number in the space's range,
rounded to TEMP_DECIMALS. Each generation keeps the best configs, then breeds the rest
from the fitter ones:
  - elitism: the top `elite_count` configs carry over unchanged (their results are cached, so free)
  - selection: a parent is the best of `tournament_size` randomly drawn configs
  - crossover: mode and effort come from one parent or the other with equal chance; temperature is a
    random point between the two parents' temperatures. Effort is carried over by name ("high" stays
    "high"); if the child's mode doesn't offer that effort, a random one of its efforts is used instead
  - mutation: mode and effort are unordered, so a mutated one is swapped for a different random value
    (a new mode keeps the current effort by name where it can); temperature is a number, so it gets a
    small random nudge (std. dev. = `temp_sigma` x the range)
Children never repeat a config that was already evaluated while an unseen one exists, so the
budget is spent on new configs. The search also stops early once every config has been tried.

Positions are handed to the driver with SearchSpace.encode and come back out through decode unchanged.
Resume contract (search_algorithm.py): ask() reads saved state only, all randomness is in tell().
"""

import random
from dataclasses import asdict, dataclass

from src.review.validate_judge.search_algorithm import SearchAlgorithm, rng_state_from_json, rng_state_to_json
from src.review.validate_judge.search_space import TEMP_DECIMALS, SearchSpace

MODE_GENE, TEMPERATURE_GENE, EFFORT_GENE = 0, 1, 2  # positions in a genome; mode and effort are indices


@dataclass
class GAParams:
    pop_size: int = 8
    generations: int = 6  # rounds after the initial population
    seed: int = 0
    tournament_size: int = 3
    crossover_rate: float = 0.8
    mutation_rate: float = 1 / 3  # per gene, so about one change per child
    temp_sigma: float = 0.15  # std. dev. of a temperature mutation, as a fraction of the temperature range
    elite_count: int = 2
    max_rerolls: int = 10  # tries to breed a child that is new before falling back to a random unseen config


class GeneticAlgorithm(SearchAlgorithm):
    name = "ga"

    def __init__(self, params: GAParams, space: SearchSpace):
        self.p = params
        self.space = space
        self.genomes = space.all_genomes()
        self.rng = random.Random(params.seed)
        self.generation = 0  # completed rounds
        self.seen = set()  # every config tried so far, as genome tuples
        self.population = [list(g) for g in self.rng.sample(self.genomes, min(params.pop_size, len(self.genomes)))]

    # -- driver interface ------------------------------------------------------------------

    def ask(self) -> list:
        return [self.space.encode(g) for g in self.population]

    def tell(self, fitnesses: list) -> None:
        self.seen.update(tuple(g) for g in self.population)
        self.generation += 1
        if self.is_done():
            return

        order = sorted(range(len(self.population)), key=lambda i: -fitnesses[i])  # stable on ties
        scored = list(zip(self.population, fitnesses))
        next_population = [list(self.population[i]) for i in order[:self.p.elite_count]]
        taken = set(self.seen)
        while len(next_population) < self.p.pop_size:
            child = self._new_child(scored, taken)
            taken.add(tuple(child))
            next_population.append(child)
        self.population = next_population

    def is_done(self) -> bool:
        return self.generation > self.p.generations or len(self.seen) >= len(self.genomes)

    def state_dict(self) -> dict:
        return {"params": asdict(self.p), "space": self.space.signature(), "generation": self.generation,
                "population": self.population, "seen": sorted(list(g) for g in self.seen),
                "rng": rng_state_to_json(self.rng)}

    def load_state_dict(self, state: dict) -> None:
        if state["params"] != asdict(self.p) or state["space"] != self.space.signature():
            raise ValueError("Saved GA state was made with different parameters or a different search space; "
                             "use another --state_path or delete the old one.")
        self.generation = state["generation"]
        self.population = state["population"]
        self.seen = {tuple(g) for g in state["seen"]}
        rng_state_from_json(self.rng, state["rng"])

    def params(self) -> dict:
        return asdict(self.p)

    # -- breeding --------------------------------------------------------------------------

    def _tournament(self, scored: list) -> list:
        contenders = self.rng.sample(scored, min(self.p.tournament_size, len(scored)))
        return max(contenders, key=lambda gf: gf[1])[0]

    def _breed(self, scored: list) -> list:
        a, b = self._tournament(scored), self._tournament(scored)
        child = list(a)
        if self.rng.random() < self.p.crossover_rate:
            child[MODE_GENE] = a[MODE_GENE] if self.rng.random() < 0.5 else b[MODE_GENE]
            donor = a if self.rng.random() < 0.5 else b
            child[EFFORT_GENE] = self._carry_effort(donor, child[MODE_GENE])
            child[TEMPERATURE_GENE] = round(a[TEMPERATURE_GENE] + self.rng.random() * (b[TEMPERATURE_GENE] - a[TEMPERATURE_GENE]),
                                            TEMP_DECIMALS)
        n_modes = len(self.space.modes)
        if n_modes > 1 and self.rng.random() < self.p.mutation_rate:
            new_mode = self.rng.choice([m for m in range(n_modes) if m != child[MODE_GENE]])
            child[EFFORT_GENE] = self._carry_effort(child, new_mode)
            child[MODE_GENE] = new_mode
        n_efforts = len(self.space.modes[child[MODE_GENE]].efforts)
        if n_efforts > 1 and self.rng.random() < self.p.mutation_rate:
            child[EFFORT_GENE] = self.rng.choice([e for e in range(n_efforts) if e != child[EFFORT_GENE]])
        if self.space.temp_max > self.space.temp_min and self.rng.random() < self.p.mutation_rate:
            child[TEMPERATURE_GENE] = self._nudge(child[TEMPERATURE_GENE])
        return child

    def _carry_effort(self, genome: list, mode_index: int) -> int:
        """Effort index in `mode_index` for the effort `genome` uses: the same effort by name if that mode
        offers it, otherwise a random one."""
        efforts = self.space.modes[mode_index].efforts
        name = self.space.effort_of(genome)
        return efforts.index(name) if name in efforts else self.rng.randrange(len(efforts))

    def _nudge(self, temperature: float) -> float:
        sigma = self.p.temp_sigma * (self.space.temp_max - self.space.temp_min)
        moved = self.rng.gauss(temperature, sigma)
        return round(min(max(moved, self.space.temp_min), self.space.temp_max), TEMP_DECIMALS)

    def _new_child(self, scored: list, taken: set) -> list:
        for _ in range(self.p.max_rerolls + 1):
            child = self._breed(scored)
            if tuple(child) not in taken:
                return child
        free = [g for g in self.genomes if g not in taken]
        return list(self.rng.choice(free)) if free else child
