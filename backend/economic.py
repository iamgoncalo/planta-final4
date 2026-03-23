"""
economic.py — F-debt economic model.
F-debt = cost of sub-optimal conditions (non-linear).
Small deviations tolerated; large deviations compound (exponent 1.5 from config).
"""
from __future__ import annotations
from dataclasses import dataclass
from .config import cfg

_EXP = cfg.economics["fdbt_exponent"]          # 1.5 from config.yaml
_RENT = cfg.economics["rent_eur_m2_month"]
_TOTAL_AREA = cfg.building["area_m2"]


@dataclass
class FDebtResult:
    f_debt_eur_h: float        # productivity waste €/h
    space_waste_eur_h: float   # space cost waste €/h
    total_eur_h: float         # combined
    relative_deficit: float    # (1 - F/P) clamped to [0,1]
    comfort_impact: float      # relative_deficit ^ exponent


def compute_fdbt(
    F: float,
    P_spatial: float,
    occupants: int,
    area_m2: float,
) -> FDebtResult:
    """
    F-debt = comfort_impact × occupants × weighted_employer_hourly
    comfort_impact = max(0, 1 - F/P)^1.5  — non-linear, from config
    space_waste = (1 - F) × space_cost_proportion
    """
    # Relative deficit: how far below optimal for this space
    relative_deficit = max(0.0, 1.0 - F / max(P_spatial, 0.01))
    comfort_impact = relative_deficit ** _EXP

    # Weighted employer hourly across salary segments
    employer_hourly_weighted = cfg.employer_hourly_weighted
    f_debt_per_h = comfort_impact * occupants * employer_hourly_weighted

    # Space waste: unused comfort potential × proportional space cost
    space_fraction = area_m2 / _TOTAL_AREA
    monthly_space_cost = _RENT * area_m2
    hourly_space_cost = monthly_space_cost / (30.44 * 8)  # 8h occupancy day
    space_waste = (1.0 - F) * hourly_space_cost * space_fraction

    return FDebtResult(
        f_debt_eur_h=round(f_debt_per_h, 4),
        space_waste_eur_h=round(space_waste, 4),
        total_eur_h=round(f_debt_per_h + space_waste, 4),
        relative_deficit=round(relative_deficit, 4),
        comfort_impact=round(comfort_impact, 4),
    )


def annual_fdbt_projection(
    hourly_results: list[FDebtResult],
    occupancy_hours_per_year: int = 2080,  # ~8h/day × 260 workdays
) -> float:
    """
    Project annual F-debt from a set of hourly results.
    Returns EUR/year [SIMULATED].
    """
    if not hourly_results:
        return 0.0
    avg_hourly = sum(r.total_eur_h for r in hourly_results) / len(hourly_results)
    return round(avg_hourly * occupancy_hours_per_year, 2)
