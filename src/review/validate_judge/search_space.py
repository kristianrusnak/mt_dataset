"""
The (model x temperature x prompt) space both search methods explore.

Temperature is snapped to `step`, so the space is finite: it is what lets the grid enumerate it,
and what lets PSO's continuous positions land on configs that are cached and comparable.
"""

import itertools
import json
from dataclasses import dataclass

from src.review.validate_judge.judge import JudgeConfig


@dataclass(frozen=True)
class SearchSpace:
    models: list
    temp_min: float
    temp_max: float
    temp_step: float
    prompt_ids: list

    @classmethod
    def from_json(cls, path: str) -> "SearchSpace":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        t = raw["temperature"]
        return cls(raw["models"], t["min"], t["max"], t["step"], raw["prompt_ids"])

    @property
    def temperatures(self) -> list:
        n = round((self.temp_max - self.temp_min) / self.temp_step)
        return [round(self.temp_min + i * self.temp_step, 4) for i in range(n + 1)]

    def all_configs(self) -> list:
        return [JudgeConfig(m, t, p) for m, t, p in
                itertools.product(self.models, self.temperatures, self.prompt_ids)]

    def decode(self, position: list) -> JudgeConfig:
        """Maps a point in the unit cube [0,1]^3 to the nearest config."""
        def pick(values, x):
            return values[min(int(x * len(values)), len(values) - 1)]
        return JudgeConfig(pick(self.models, position[0]), pick(self.temperatures, position[1]),
                           pick(self.prompt_ids, position[2]))
