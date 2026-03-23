"""
rooms.py — Ground-truth room registry for HORSE CFT.
Source: David Fleury emails 3 Mar 2026 + 12 Mar 2026.
Do not modify without a new email from David.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class Room:
    id: str
    floor: str          # 'GF' | 'F1'
    area_m2: float
    capacity: int
    ac_units: int
    lux_measured: float
    ceiling_h_m: float
    has_windows: bool
    # Simulation-derived F/D (labeled SIMULATED — not from sensors)
    F_sim: float
    D_sim: float
    top_distortion: str
    top_distortion_pct: float
    f_debt_eur_h_sim: Optional[float] = None
    notes: str = ""

    @property
    def volume_m3(self) -> float:
        return self.area_m2 * self.ceiling_h_m

    @property
    def is_critical(self) -> bool:
        return self.id in {"Pintassilgo", "Quintanilha", "Vasco_da_Gama"}

    @property
    def has_ac(self) -> bool:
        return self.ac_units > 0


ROOMS: dict[str, Room] = {r.id: r for r in [
    # ── GROUND FLOOR ───────────────────────────────────────────────
    Room("Hall_GF",          "GF", 40,  10, 0, 280, 2.8, True,  0.8144, 1.2279, "thermal",   63, 4.71),
    Room("Cantina",          "GF", 65,  30, 0, 320, 2.8, True,  0.4485, 1.4865, "thermal",   40, 36.43),
    Room("Chaveiro",         "GF", 15,   2, 0, 200, 2.8, False, 0.5333, 1.2501, "thermal",   39, None),
    Room("Egas_Moniz",       "GF", 78,  17, 1, 409, 2.8, True,  0.4207, 1.1884, "thermal",   35, 5.61),
    Room("Sacadura_Cabral",  "GF", 52,  10, 1, 245, 2.8, True,  0.4009, 1.2473, "thermal",   60, 5.20),
    Room("Antonio_Damasio",  "GF", 65,  15, 1, 230, 2.8, True,  0.3876, 1.2901, "thermal",   37, 8.68),
    Room("Gago_Coutinho",    "GF", 52,  12, 1, 205, 2.8, True,  0.4166, 1.2003, "light",     44, 5.04),
    Room("Pintassilgo",      "GF", 78,  12, 0,  85, 2.8, True,  0.3848, 1.2994, "light",     71, 8.17,
         notes="CRITICAL: 0 AC, 85 lux=71.6% below EN 12464-1 min. ACO NEVER assigns groups here."),
    Room("Reunioes_1",       "GF", 52,   8, 0, 280, 2.8, True,  0.4487, 1.1143, "thermal",   40, 2.72),
    Room("Reunioes_2",       "GF", 39,   6, 0, 270, 2.8, True,  0.4029, 1.2410, "thermal",   55, 3.54),
    Room("Administracao",    "GF", 35,   4, 0, 260, 2.8, True,  0.4267, 1.1718, "light",     33, None),
    Room("Corredor_GF",      "GF", 68,   0, 0, 180, 2.8, False, 0.5466, 1.2197, "light",     48, None),
    Room("WC_GF",            "GF", 20,   0, 0, 150, 2.4, False, 0.4082, 1.2248, "light",     58, None),
    Room("Arrecadacao_GF",   "GF", 30,   0, 0, 100, 2.8, False, 0.3862, 1.2947, "light",     64, None),
    # ── FIRST FLOOR ────────────────────────────────────────────────
    Room("Hall_F1",          "F1", 35,  10, 0, 260, 2.8, True,  0.4189, 1.1936, "thermal",   57, 3.85),
    Room("Dojo_EMotor",      "F1", 65,  10, 1, 290, 2.8, True,  0.2746, 1.2141, "thermal",   51, 4.36),
    Room("Dojo_PEB",         "F1", 65,  10, 1, 290, 2.8, True,  0.2887, 1.1547, "thermal",   40, 2.89),
    Room("Eiffage",          "F1", 65,  14, 1, 295, 2.8, True,  0.2877, 1.1586, "light",     25, 3.74),
    Room("Vasco_da_Gama",    "F1", 65,  20, 2, 305, 2.8, True,  0.2640, 1.2626, "co2",       28, 11.07,
         notes="CO2 breach risk in 15 min at full occupancy without ventilation."),
    Room("Automacao",        "F1", 65,   8, 1, 290, 2.8, True,  0.3042, 1.0959, "light",     42, 1.33),
    Room("Quintanilha",      "F1", 65,  15, 2, 384, 2.8, True,  0.2460, 1.3548, "thermal",   52, 10.91,
         notes="Highest D in building. Thermal dominant."),
    Room("Corredor_F1",      "F1", 68,   0, 0, 180, 2.8, False, 0.3564, 1.1224, "light",     83, None),
    Room("WC_F1",            "F1", 18,   0, 0, 150, 2.4, False, 0.2660, 1.2532, "light",     52, None),
    Room("Arrecadacao_F1",   "F1", 25,   0, 0, 100, 2.8, False, 0.2264, 1.4721, "thermal",   44, None),
]}

CRITICAL_ROOMS = {rid: r for rid, r in ROOMS.items() if r.is_critical}
CLASSROOMS = {rid: r for rid, r in ROOMS.items() if r.capacity > 0 and rid not in ("Cantina", "Administracao")}
GF_ROOMS = {rid: r for rid, r in ROOMS.items() if r.floor == "GF"}
F1_ROOMS = {rid: r for rid, r in ROOMS.items() if r.floor == "F1"}

# BFS adjacency — corridor connects all rooms per floor
# Hall_GF is source (P_spatial reference = 0.814)
ADJACENCY: dict[str, list[str]] = {
    "Hall_GF":       ["Corredor_GF", "Cantina", "Egas_Moniz"],
    "Corredor_GF":   ["Hall_GF", "Antonio_Damasio", "Sacadura_Cabral",
                      "Gago_Coutinho", "Pintassilgo", "Reunioes_1",
                      "Reunioes_2", "Administracao", "WC_GF",
                      "Arrecadacao_GF", "Chaveiro", "Hall_F1"],
    "Hall_F1":       ["Corredor_F1", "Corredor_GF"],
    "Corredor_F1":   ["Hall_F1", "Dojo_EMotor", "Dojo_PEB", "Eiffage",
                      "Vasco_da_Gama", "Automacao", "Quintanilha",
                      "WC_F1", "Arrecadacao_F1"],
    # All other rooms connect only through their corridor
    **{rid: ["Corredor_GF"] for rid in GF_ROOMS if rid not in ("Hall_GF", "Corredor_GF", "Cantina")},
    **{rid: ["Corredor_F1"] for rid in F1_ROOMS if rid not in ("Hall_F1", "Corredor_F1")},
    "Cantina": ["Hall_GF"],
}
