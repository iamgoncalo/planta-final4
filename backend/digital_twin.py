"""
digital_twin.py — 24-room RC thermal + CO₂ mass balance simulation.
Source: David Fleury HORSE CFT data. Confirmed values from email 3 Mar 2026.
ALL OUTPUTS SIMULATION-BASED until physical sensors validate.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from .config import cfg
from .rooms import ROOMS, Room
from .distortion import build_channels, compute_D, DistortionResult
from .freedom import P_SPATIAL, compute_F
from .economic import compute_fdbt, FDebtResult

rng = np.random.default_rng(cfg.pso.seed)  # seed=2026, always


@dataclass
class RoomState:
    room_id: str
    ts: str
    source: str = "simulation"
    # Environmental
    temp_c: float = 20.0
    humidity_pct: float = 50.0
    co2_ppm: float = 600.0
    lux: float = 300.0
    noise_db: float = 40.0
    occupancy: int = 0
    # Computed
    D_total: float = 1.0
    P_spatial: float = 0.5
    F: float = 0.5
    d_thermal: float = 1.0
    d_humidity: float = 1.0
    d_co2: float = 1.0
    d_light: float = 1.0
    d_noise: float = 1.0
    d_occupancy: float = 1.0
    d_spatial: float = 1.0
    attr_thermal: float = 0.0
    attr_co2: float = 0.0
    attr_humidity: float = 0.0
    attr_light: float = 0.0
    attr_noise: float = 0.0
    attr_occupancy: float = 0.0
    attr_spatial: float = 0.0
    dominant_channel: str = "thermal"
    dominant_pct: float = 0.0
    # HVAC
    hvac_state: str = "off"        # 'running'|'off'|'fault'
    hvac_kwh: float = 0.0
    lights_kwh: float = 0.0
    setpoint_c: float = 20.0
    # Economic
    f_debt_eur_h: float = 0.0
    space_waste_eur_h: float = 0.0
    # Alerts
    alert_level: int = 0
    co2_legal_breach: bool = False
    pmv: float = 0.0
    ppd: float = 5.0


def aveiro_outdoor_temp(month: int, hour: int) -> float:
    """Monthly mean outdoor temperature for Aveiro, Portugal."""
    monthly_mean = [10, 11, 13, 15, 17, 20, 22, 22, 20, 17, 13, 10]
    base = monthly_mean[month - 1]
    variation = 5 * math.sin(math.pi * (hour - 6) / 12)
    return base + variation


def hvac_setpoint(month: int, hour: int) -> float:
    """Return HVAC setpoint from config based on season."""
    if 6 <= month <= 9:
        return cfg.comfort["summer_setpoint_c"]
    return cfg.comfort["winter_setpoint_c"]


def occupancy_profile(hour: int, month: int, day_of_week: int) -> float:
    """Return fraction of max capacity. 0.0–1.0."""
    if day_of_week >= 5:  # weekend
        return 0.0
    if month == 7:        # July closed (David Fleury confirmed)
        return 0.0
    if 8 <= hour <= 17:
        peak = 0.85 if 9 <= hour <= 16 else 0.50
        noise = float(rng.normal(0, 0.05))
        return min(1.0, max(0.0, peak + noise))
    return 0.0


def thermal_step(
    T_in: float, T_out: float, T_sp: float,
    n_people: int, area_m2: float, n_ac: int,
    month: int, hour: int, dt_min: float = 1.0,
) -> tuple[float, str, float]:
    """
    RC thermal model. Returns (new_T, hvac_state, hvac_kwh).
    Time constant from config.yaml.
    """
    tau = cfg.thermal["rc_time_constant_min"]
    u_wall = cfg.thermal["wall_u_value"]
    solar = 0.0
    if 8 <= hour <= 16 and month in range(4, 10):
        solar = cfg.thermal["solar_gain_factor"] * area_m2 * 200  # W

    people_heat = n_people * cfg.thermal["people_heat_w"]  # W
    envelope_loss = u_wall * area_m2 * 0.3 * (T_in - T_out)  # simplified

    # Natural drift
    dT_natural = (-(T_in - T_out) / tau + (people_heat + solar - envelope_loss) / (area_m2 * 3000)) * dt_min

    hvac_state = "off"
    hvac_power_w = 0.0
    if n_ac > 0:
        tolerance = 1.0
        if T_in > T_sp + tolerance:
            hvac_state = "running"
            hvac_power_w = n_ac * cfg.hvac["electrical_w_per_unit"]
            dT_natural -= (cfg.hvac["capacity_w_thermal"] * n_ac) / (area_m2 * 3000) * dt_min
        elif T_in < T_sp - tolerance:
            hvac_state = "running"
            hvac_power_w = n_ac * cfg.hvac["electrical_w_per_unit"]
            dT_natural += (cfg.hvac["capacity_w_thermal"] * n_ac) / (area_m2 * 3000) * dt_min

    new_T = T_in + dT_natural
    new_T = max(5.0, min(45.0, new_T))  # physical bounds
    hvac_kwh = hvac_power_w * dt_min / 60000  # Wmin → kWh
    return new_T, hvac_state, hvac_kwh


def co2_step(
    co2_ppm: float, n_people: int, vol_m3: float,
    ach: float = 0.8, dt_min: float = 1.0,
) -> float:
    """CO₂ mass balance. Generation=0.004 m³/min/person."""
    outdoor = cfg.comfort["outdoor_co2_ppm"]
    gen_rate = cfg.lbm["co2_generation_m3_min_person"]
    generation = n_people * gen_rate
    ventilation_removal = ach / 60 * vol_m3 * (co2_ppm - outdoor) / 1e6
    delta_ppm = (generation - ventilation_removal) / vol_m3 * 1e6 * dt_min
    new_ppm = co2_ppm + delta_ppm
    return max(float(outdoor), min(5000.0, new_ppm))


def humidity_step(
    rh: float, n_people: int, vol_m3: float,
    ach: float = 0.8, rh_out: float = 65.0, dt_min: float = 1.0,
) -> float:
    """Simple humidity step. Each person adds ~50g/h moisture."""
    moisture_per_person_g_h = 50.0
    room_air_kg = vol_m3 * 1.2  # air density ~1.2 kg/m³
    moisture_added = n_people * moisture_per_person_g_h * dt_min / 60
    ventilation_delta = ach / 60 * (rh_out - rh) * dt_min
    delta_rh = (moisture_added / room_air_kg * 0.5) + ventilation_delta * 0.1
    return max(10.0, min(95.0, rh + delta_rh))


def compute_pmv(T: float, rh: float, met: float = 1.2, clo: float = 1.0) -> tuple[float, float]:
    """Simplified PMV/PPD (ISO 7730). Returns (pmv, ppd)."""
    # Simplified Fanger model
    ta = T
    tr = T  # assume tr ≈ ta for office
    pmv = (0.303 * math.exp(-0.036 * met * 58.15) + 0.028) * (
        (met * 58.15 - 3.05e-3 * (5733 - 6.99 * met * 58.15 - 101.325 * (rh / 100))) -
        0.42 * (met * 58.15 - 58.15) -
        1.7e-5 * met * 58.15 * (5867 - 101.325 * (rh / 100)) -
        0.0014 * met * 58.15 * (34 - ta) -
        3.96e-8 * 0.95 * ((tr + 273)**4 - (ta + 273)**4) -
        (ta - 22)
    )
    pmv = max(-4.0, min(4.0, pmv))
    ppd = 100 - 95 * math.exp(-0.03353 * pmv**4 - 0.2179 * pmv**2)
    return round(pmv, 3), round(ppd, 1)


class DigitalTwin:
    """24-room building state manager. Simulation-first."""

    def __init__(self):
        self._states: dict[str, RoomState] = {}
        self._tick_count = 0

    def initialize(self, month: int = 3, hour: int = 9) -> None:
        """Seed initial state for all 24 rooms."""
        import datetime
        ts = datetime.datetime.utcnow().isoformat() + "Z"
        T_out = aveiro_outdoor_temp(month, hour)

        for rid, room in ROOMS.items():
            sp = hvac_setpoint(month, hour)
            T0 = sp + float(rng.normal(0, 1.5))
            co2_0 = 580.0 + float(rng.normal(0, 40))
            rh_0 = 55.0 + float(rng.normal(0, 5))

            state = RoomState(room_id=rid, ts=ts, source="simulation",
                              temp_c=T0, humidity_pct=rh_0, co2_ppm=co2_0,
                              lux=room.lux_measured, noise_db=40.0,
                              occupancy=0, setpoint_c=sp)
            self._update_computed(state, room)
            self._states[rid] = state

    def _update_computed(self, state: RoomState, room: Room) -> None:
        """Recompute D, P, F, economic, alert for a room state."""
        from .distortion import d_thermal, d_co2, d_humidity, d_light, d_noise, d_occupancy, d_spatial
        from freedom import P_SPATIAL, _DISTANCES, _MAX_DIST

        sp = state.setpoint_c
        channels = {
            "thermal":   d_thermal(state.temp_c, sp),
            "co2":       d_co2(state.co2_ppm),
            "humidity":  d_humidity(state.humidity_pct),
            "light":     d_light(state.lux),
            "noise":     d_noise(state.noise_db),
            "occupancy": d_occupancy(state.occupancy, room.capacity),
            "spatial":   d_spatial(_DISTANCES.get(room.id, _MAX_DIST), _MAX_DIST),
        }
        dr = compute_D(channels)
        P = P_SPATIAL.get(room.id, 0.5)
        F = compute_F(P, dr.D_total)

        # Write channels
        state.d_thermal   = channels["thermal"]
        state.d_co2       = channels["co2"]
        state.d_humidity  = channels["humidity"]
        state.d_light     = channels["light"]
        state.d_noise     = channels["noise"]
        state.d_occupancy = channels["occupancy"]
        state.d_spatial   = channels["spatial"]

        state.D_total        = round(dr.D_total, 4)
        state.P_spatial      = round(P, 4)
        state.F              = round(F, 4)
        state.dominant_channel = dr.dominant_channel
        state.dominant_pct   = round(dr.dominant_pct, 1)

        state.attr_thermal   = round(dr.attribution.get("thermal", 0), 1)
        state.attr_co2       = round(dr.attribution.get("co2", 0), 1)
        state.attr_humidity  = round(dr.attribution.get("humidity", 0), 1)
        state.attr_light     = round(dr.attribution.get("light", 0), 1)
        state.attr_noise     = round(dr.attribution.get("noise", 0), 1)

        # Economic
        fdbt = compute_fdbt(F, P, state.occupancy, room.area_m2)
        state.f_debt_eur_h     = fdbt.f_debt_eur_h
        state.space_waste_eur_h = fdbt.space_waste_eur_h

        # PMV/PPD
        pmv, ppd = compute_pmv(state.temp_c, state.humidity_pct)
        state.pmv = pmv
        state.ppd = ppd

        # Alert
        state.co2_legal_breach = state.co2_ppm >= cfg.comfort["co2_legal_ppm"]
        state.alert_level = self._compute_alert_level(state)

    def _compute_alert_level(self, state: RoomState) -> int:
        """5-level alert cascade. Level 4 triggers Agent 2 (Claude)."""
        if state.co2_ppm >= cfg.comfort["co2_legal_ppm"]:
            return 4
        if state.F < 0.15:
            return 4
        if state.co2_ppm >= cfg.comfort["co2_alert_ppm"]:
            return 3
        if state.F < 0.25:
            return 3
        if state.F < 0.35:
            return 2
        if state.F < 0.50:
            return 1
        return 0

    def tick(self, month: int, hour: int, day_of_week: int, dt_min: float = 1.0) -> dict[str, RoomState]:
        """Single 60s tick. Updates all 24 rooms. ZERO AI calls here."""
        import datetime
        ts = datetime.datetime.utcnow().isoformat() + "Z"
        T_out = aveiro_outdoor_temp(month, hour)
        occ_frac = occupancy_profile(hour, month, day_of_week)

        for rid, state in self._states.items():
            room = ROOMS[rid]
            state.ts = ts
            occupants = int(occ_frac * room.capacity)
            state.occupancy = occupants

            # Thermal RC step
            new_T, hvac_s, hvac_kwh = thermal_step(
                state.temp_c, T_out, state.setpoint_c,
                occupants, room.area_m2, room.ac_units, month, hour, dt_min,
            )
            state.temp_c  = round(new_T, 2)
            state.hvac_state = hvac_s
            state.hvac_kwh   = round(hvac_kwh, 6)

            # CO₂ step
            state.co2_ppm = round(co2_step(state.co2_ppm, occupants, room.volume_m3, dt_min=dt_min), 1)

            # Humidity step
            state.humidity_pct = round(humidity_step(state.humidity_pct, occupants, room.volume_m3, dt_min=dt_min), 1)

            # Lux: static from David Fleury data (no sensor variation in simulation)
            noise_level = 38.0 + occupants * 1.5 + float(rng.normal(0, 2))
            state.noise_db = round(min(75.0, noise_level), 1)

            self._update_computed(state, room)

        self._tick_count += 1
        return dict(self._states)

    def get_state(self) -> dict[str, RoomState]:
        return dict(self._states)

    def get_building_summary(self) -> dict:
        states = self._states
        if not states:
            return {}
        Fs = [s.F for s in states.values()]
        return {
            "F_global": round(sum(Fs) / len(Fs), 4),
            "F_min": round(min(Fs), 4),
            "F_max": round(max(Fs), 4),
            "rooms_critical": sum(1 for s in states.values() if s.alert_level >= 4),
            "rooms_amber": sum(1 for s in states.values() if 2 <= s.alert_level < 4),
            "active_alerts": sum(1 for s in states.values() if s.alert_level > 0),
            "f_debt_total_eur_h": round(sum(s.f_debt_eur_h for s in states.values()), 2),
            "energy_tick_kwh": round(sum(s.hvac_kwh for s in states.values()), 4),
            "source": "simulation",
        }
