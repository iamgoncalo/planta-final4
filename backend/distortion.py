"""
distortion.py — D = geometric mean of distortion channels.
Formula: D = exp(sum(w_k * ln(max(d_k, 1.0))))
Deucalion evidence: R²(geometric)=0.993 vs R²(additive)=0.860 — confirmed 3×, seed=2026.
ALL RESULTS SIMULATION-BASED until sensor validation.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from .config import cfg

W = cfg.D_weights  # loaded from config.yaml, sum validated at import


@dataclass
class DistortionResult:
    D_total: float
    attribution: dict[str, float]   # channel -> % of total D
    channels: dict[str, float]      # channel -> d_k raw value
    dominant_channel: str
    dominant_pct: float


def compute_D(channels: dict[str, float]) -> DistortionResult:
    """
    D = exp(sum(w_k * ln(max(d_k, 1.0))))
    Returns D_total and per-channel attribution %.
    All d_k must be >= 1.0 (clipped at floor).
    """
    clamped = {k: max(channels[k], 1.0) for k in W}
    ln_terms = {k: W[k] * math.log(clamped[k]) for k in W}
    ln_D = sum(ln_terms.values())
    D = math.exp(ln_D)

    if ln_D < 1e-10:
        attribution = {k: 0.0 for k in W}
    else:
        attribution = {k: ln_terms[k] / ln_D * 100.0 for k in W}

    dominant = max(attribution, key=lambda k: attribution[k])
    return DistortionResult(
        D_total=D,
        attribution=attribution,
        channels=clamped,
        dominant_channel=dominant,
        dominant_pct=attribution[dominant],
    )


# ── Channel formulas (all from regulations, all in config.yaml) ────────────

def d_thermal(T_c: float, T_setpoint: float) -> float:
    """ISO 7730 thermal distortion. Setpoint from config."""
    dev = abs(T_c - T_setpoint)
    return max(1.0, 1.0 + dev / 2.5)


def d_co2(ppm: float) -> float:
    """Portaria 353-A/2013. Reference: 700 ppm clean (EN 15251 Cat I)."""
    ref = cfg.comfort["co2_clean_ppm"]
    return max(1.0, ppm / ref)


def d_humidity(rh_pct: float) -> float:
    """ISO 7730 humidity comfort. Target 50%."""
    target = cfg.comfort["humidity_target_pct"]
    return max(1.0, 1.0 + abs(rh_pct - target) / 15.0)


def d_light(lux: float) -> float:
    """EN 12464-1. Target 400 lux classrooms."""
    target = cfg.comfort["lux_classroom_target"]
    return max(1.0, target / max(lux, 10.0))


def d_noise(db: float) -> float:
    """ISO 11690-1. Max 45 dB."""
    limit = cfg.comfort["noise_max_db"]
    return max(1.0, 1.0 + max(0.0, db - limit) / 10.0)


def d_occupancy(n: int, capacity: int) -> float:
    """EN 13779. Ratio of actual to design capacity."""
    return max(1.0, n / max(capacity, 1))


def d_spatial(bfs_distance: float, max_distance: float) -> float:
    """BFS-derived spatial distortion. Hall_GF = reference (distance=0)."""
    return 1.0 + bfs_distance / max(max_distance, 1.0)


def build_channels(
    temp_c: float,
    setpoint_c: float,
    co2_ppm: float,
    humidity_pct: float,
    lux: float,
    noise_db: float,
    occupancy: int,
    capacity: int,
    bfs_distance: float,
    max_bfs_distance: float,
) -> dict[str, float]:
    """Convenience: build channel dict from raw sensor/simulation values."""
    return {
        "thermal":   d_thermal(temp_c, setpoint_c),
        "co2":       d_co2(co2_ppm),
        "humidity":  d_humidity(humidity_pct),
        "light":     d_light(lux),
        "noise":     d_noise(noise_db),
        "occupancy": d_occupancy(occupancy, capacity),
        "spatial":   d_spatial(bfs_distance, max_bfs_distance),
    }
