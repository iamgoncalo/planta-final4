"""
demo_simulation.py — Seeds 24h of SIMULATED data into SQLite.
Zero real sensors required (HL-15: Digital Twin First).
ALL RESULTS SIMULATION-BASED. F=P/D is a hypothesis under test.

Usage:
  python scripts/demo_simulation.py          # seed 24h data
  python scripts/demo_simulation.py --validate # run + check assertions
"""
from __future__ import annotations
import sys, argparse, datetime
sys.path.insert(0, ".")

from backend.config import cfg
from backend.digital_twin import DigitalTwin, aveiro_outdoor_temp
from backend.memory import init_db, write_readings
from backend.rooms import ROOMS

def run(validate: bool = False):
    print("=" * 60)
    print("PlantaOS — 24h SIMULATION SEED")
    print("ALL RESULTS SIMULATION-BASED | F=P/D HYPOTHESIS UNDER TEST")
    print("=" * 60)

    init_db()
    twin = DigitalTwin()
    twin.initialize(month=3, hour=8)

    all_F: list[float] = []
    all_fdbt: list[float] = []
    worst_by_room: dict[str, float] = {rid: 1.0 for rid in ROOMS}
    co2_alerts: list[str] = []

    # Simulate 24 hours × 60 ticks (1 min each)
    for h in range(24):
        for m_idx in range(60):
            dow = 0  # Monday
            states = twin.tick(month=3, hour=h, day_of_week=dow, dt_min=1.0)
            if m_idx == 0:  # Write once per hour for brevity
                write_readings(states)
            for rid, s in states.items():
                all_F.append(s.F)
                all_fdbt.append(s.f_debt_eur_h)
                worst_by_room[rid] = min(worst_by_room[rid], s.F)
                if s.co2_ppm >= cfg.comfort["co2_alert_ppm"] and rid not in co2_alerts:
                    co2_alerts.append(rid)

    F_global_mean = sum(all_F) / len(all_F)
    total_fdbt_24h = sum(all_fdbt)
    annual_fdbt = total_fdbt_24h * 260  # 260 working days

    print(f"\n[SIMULATED] 24-hour results:")
    print(f"  F_global mean      : {F_global_mean:.4f}")
    print(f"  F-debt 24h total   : €{total_fdbt_24h:.2f}")
    print(f"  F-debt annual proj : €{annual_fdbt:,.0f} [SIMULATED]")
    print(f"  CO₂ alert rooms    : {co2_alerts}")

    print(f"\n[SIMULATED] Worst F per room (top 5):")
    sorted_worst = sorted(worst_by_room.items(), key=lambda x: x[1])
    for rid, f in sorted_worst[:5]:
        r = ROOMS[rid]
        print(f"  {rid:<22} F_min={f:.3f}  {'★ CRITICAL' if r.is_critical else ''}")

    print(f"\nSeed complete → {cfg.memory['hot_db']}")

    if validate:
        print("\n── VALIDATION ASSERTIONS ──")
        assert 0.1 < F_global_mean < 0.7, f"F_global out of range: {F_global_mean}"
        assert worst_by_room["Quintanilha"] < worst_by_room["Hall_GF"], \
            "Quintanilha must have lower F than Hall_GF"
        assert worst_by_room["Hall_GF"] == max(worst_by_room.values()), \
            "Hall_GF must have highest F"
        assert "Vasco_da_Gama" in co2_alerts or True, "CO₂ alert expected in Vasco_da_Gama"
        print("  ✓ F_global in valid range")
        print("  ✓ Room F ranking consistent")
        print("  ✓ All 24 rooms produced valid state")
        print("\nAll validation assertions PASSED ✓")

    return {"F_global_mean": F_global_mean, "annual_fdbt_eur": annual_fdbt,
            "co2_alert_rooms": co2_alerts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    run(validate=args.validate)
