"""
The (mode x temperature x effort) space the searches explore.

A "mode" is a model and a prompt tied together (they are tuned as one unit, not independently). Each mode
lists the reasoning efforts it can be run at, so the effort axis is different for every mode.

Temperature is a continuous axis: a search position maps linearly onto [temp_min, temp_max] and is
rounded to TEMP_DECIMALS decimals (so a config still has a stable name and cache file). The grid
search cannot enumerate a continuous axis, so it uses `temp_step` instead and visits only those values.
A "genome" is the index-based form the GA and random search work in: (mode index, temperature, index into
that mode's efforts).
"""

import itertools
import json
from dataclasses import dataclass

from src.review.validate_judge.judge import JudgeConfig

TEMP_DECIMALS = 2


@dataclass(frozen=True)
class Mode:
    model: str
    prompt_id: str
    efforts: list  # reasoning efforts this mode is tried at, e.g. ["low", "medium", "high"]


@dataclass(frozen=True)
class SearchSpace:
    modes: list
    temp_min: float
    temp_max: float
    temp_step: float

    @classmethod
    def from_json(cls, path: str) -> "SearchSpace":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        modes = [Mode(m["model"], m["prompt_id"], m["efforts"]) for m in raw["modes"]]
        for mode in modes:
            if not mode.efforts:
                raise ValueError(f"Mode {mode.model}/{mode.prompt_id} has no efforts to try.")
        t = raw["temperature"]
        return cls(modes, t["min"], t["max"], t["step"])

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
        return [JudgeConfig(mode.model, t, mode.prompt_id, effort)
                for mode in self.modes
                for t in self.temperatures
                for effort in mode.efforts]

    def all_genomes(self) -> list:
        """Every (mode index, temperature, effort index) the continuous searches can reach."""
        return [(mi, t, ei)
                for mi, mode in enumerate(self.modes)
                for t in self.fine_temperatures
                for ei in range(len(mode.efforts))]

    def effort_of(self, genome) -> str:
        """The effort name a genome's effort index stands for (the index alone means nothing across modes)."""
        return self.modes[genome[0]].efforts[genome[2]]

    def signature(self) -> list:
        """What a saved algorithm state depends on; a state made for a different space must not be resumed."""
        return [len(self.modes), [len(m.efforts) for m in self.modes], self.temp_min, self.temp_max]

    def decode(self, position: list) -> JudgeConfig:
        """Maps a point in the unit cube [0,1]^3 (mode, temperature, effort) to a config: mode by nearest
        cell, temperature linearly onto [temp_min, temp_max], effort by nearest cell among the chosen
        mode's efforts."""
        def pick(values, x):
            return values[min(int(x * len(values)), len(values) - 1)]
        mode = pick(self.modes, position[0])
        x = min(max(position[1], 0.0), 1.0)
        temperature = round(self.temp_min + x * (self.temp_max - self.temp_min), TEMP_DECIMALS)
        return JudgeConfig(mode.model, temperature, mode.prompt_id, pick(mode.efforts, position[2]))

    def encode(self, genome) -> list:
        """Inverse of decode for a (mode index, temperature, effort index) genome: the centre of the
        mode and effort cells, and the temperature's relative position in its range."""
        mode_index, temperature, effort_index = genome
        span = self.temp_max - self.temp_min
        return [(mode_index + 0.5) / len(self.modes),
                (temperature - self.temp_min) / span if span else 0.0,
                (effort_index + 0.5) / len(self.modes[mode_index].efforts)]
