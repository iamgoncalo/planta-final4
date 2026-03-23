"""
config.py — Pydantic config loader.
Validates types. Asserts weight sum = 1.0.
Single import point for all backend modules.
"""
from __future__ import annotations
import yaml
from pathlib import Path
from pydantic import BaseModel, field_validator, model_validator
from typing import Optional

_ROOT = Path(__file__).parent.parent
_CFG_PATH = _ROOT / "config.yaml"


def _load() -> dict:
    with open(_CFG_PATH) as f:
        return yaml.safe_load(f)


class DistortionWeights(BaseModel):
    thermal:   float
    co2:       float
    humidity:  float
    light:     float
    noise:     float
    occupancy: float
    spatial:   float

    @model_validator(mode="after")
    def weights_sum_to_one(self):
        total = sum([
            self.thermal, self.co2, self.humidity, self.light,
            self.noise, self.occupancy, self.spatial
        ])
        assert abs(total - 1.0) < 1e-6, (
            f"D-weights must sum to 1.0, got {total:.8f}. "
            "Edit config.yaml only — never backend code."
        )
        return self


class SalarySegment(BaseModel):
    pct: float
    gross_month: float
    employer_hourly: float
    label: str


class PSO(BaseModel):
    n_particles: int
    n_iterations: int
    inertia_w: float
    c1: float
    c2: float
    search_T_min: float
    search_T_max: float
    search_fan_min: float
    search_fan_max: float
    energy_penalty_weight: float
    seed: int


class ACO(BaseModel):
    alpha: float
    beta: float
    rho: float
    initial_pheromone: float
    avoid_rooms: list[str]


class AI(BaseModel):
    model: str
    max_tokens: int
    cost_limit_day_eur: float
    cost_limit_month_eur: float
    alert_max_calls_day: int
    chatbot_max_turns: int
    chatbot_max_words: int
    optimiser_max_tokens: int
    alert_max_tokens: int


class Memory(BaseModel):
    hot_db: str
    warm_db: str
    cold_dir: str
    hot_days: int
    warm_days: int
    rgpd_raw_discard_seconds: int


class PlantaConfig(BaseModel):
    building: dict
    hvac: dict
    comfort: dict
    distortion: dict
    economics: dict
    pso: PSO
    aco: ACO
    lbm: dict
    fire_fusion: dict
    ai: AI
    memory: Memory
    thermal: dict
    standards: dict
    research: dict

    @model_validator(mode="after")
    def validate_weights(self):
        w = self.distortion.get("weights", {})
        DistortionWeights(**w)  # raises if sum != 1.0
        return self

    # Convenience accessors
    @property
    def D_weights(self) -> dict[str, float]:
        return self.distortion["weights"]

    @property
    def salary_segments(self) -> dict[str, SalarySegment]:
        raw = self.economics.get("salary_segments", {})
        return {k: SalarySegment(**v) for k, v in raw.items()}

    @property
    def employer_hourly_weighted(self) -> float:
        return sum(s.pct * s.employer_hourly for s in self.salary_segments.values())


# Singleton — import cfg from here everywhere
_raw = _load()
cfg = PlantaConfig(**_raw)

# Hard assertions at import time
assert abs(sum(cfg.D_weights.values()) - 1.0) < 1e-6, "D-weights sum check FAILED"
assert cfg.pso.seed == 2026, "Seed must be 2026"
assert "Pintassilgo" in cfg.aco.avoid_rooms, "Pintassilgo must be in ACO avoid_rooms"
