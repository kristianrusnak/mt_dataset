"""
The (model x temperature x prompt) space the searches explore.

Temperature is a continuous axis: a search position maps linearly onto [temp_min, temp_max] and is
rounded to TEMP_DECIMALS decimals (so a config still has a stable name and cache file). The grid
search cannot enumerate a continuous axis, so it uses `temp_step` instead and visits only those values.
A "genome" is the index-based form the GA and random search work in: (model index, temperature, prompt index).
"""

import itertools
import json
from dataclasses import dataclass

from src.review.validate_judge.judge import JudgeConfig

TEMP_DECIMALS = 2


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
        """The grid search's temperatures: temp_min to temp_max in steps of temp_step."""
        n = round((self.temp_max - self.temp_min) / self.temp_step)
        return [round(self.temp_min + i * self.temp_step, TEMP_DECIMALS) for i in range(n + 1)]

    @property
    def fine_temperatures(self) -> list:
        """Every temperature the continuous searches can produce (all values at TEMP_DECIMALS decimals)."""
        scale = 10 ** TEMP_DECIMALS
        lo, hi = round(self.temp_min * scale), round(self.temp_max * scale)
        return [i / scale for i in range(lo, hi + 1)]

    def all_configs(self) -> list:
        """Grid search's configs (temperatures at temp_step)."""
        return [JudgeConfig(m, t, p) for m, t, p in
                itertools.product(self.models, self.temperatures, self.prompt_ids)]

    def all_genomes(self) -> list:
        """Every (model index, temperature, prompt index) the continuous searches can reach."""
        return list(itertools.product(range(len(self.models)), self.fine_temperatures, range(len(self.prompt_ids))))

    def signature(self) -> list:
        """What a saved algorithm state depends on; a state made for a different space must not be resumed."""
        return [len(self.models), self.temp_min, self.temp_max, len(self.prompt_ids)]

    def decode(self, position: list) -> JudgeConfig:
        """Maps a point in the unit cube [0,1]^3 to a config: model and prompt by nearest cell,
        temperature linearly onto [temp_min, temp_max]."""
        def pick(values, x):
            return values[min(int(x * len(values)), len(values) - 1)]
        x = min(max(position[1], 0.0), 1.0)
        temperature = round(self.temp_min + x * (self.temp_max - self.temp_min), TEMP_DECIMALS)
        return JudgeConfig(pick(self.models, position[0]), temperature, pick(self.prompt_ids, position[2]))

    def encode(self, genome) -> list:
        """Inverse of decode for a (model index, temperature, prompt index) genome: the centre of the
        model and prompt cells, and the temperature's relative position in its range."""
        model_index, temperature, prompt_index = genome
        span = self.temp_max - self.temp_min
        return [(model_index + 0.5) / len(self.models),
                (temperature - self.temp_min) / span if span else 0.0,
                (prompt_index + 0.5) / len(self.prompt_ids)]
