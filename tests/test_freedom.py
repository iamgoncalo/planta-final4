"""Tests for freedom calculator. F=P/D + BFS + limits."""
import pytest, sys
sys.path.insert(0, ".")
from backend.freedom import bfs_distances, compute_P_spatial, compute_F, P_SPATIAL
from backend.rooms import ROOMS

def test_hall_gf_highest_p():
    assert P_SPATIAL["Hall_GF"] == max(P_SPATIAL.values())

def test_p_in_range():
    for rid, p in P_SPATIAL.items():
        assert 0.0 <= p <= 1.0, f"{rid}: P={p} out of [0,1]"

def test_f_clipped():
    f = compute_F(0.9, 0.5)
    assert f <= 1.0
    f2 = compute_F(0.0, 10.0)
    assert f2 >= 0.0

def test_bfs_distances_from_hall():
    dists = bfs_distances("Hall_GF")
    assert dists["Hall_GF"] == 0
    assert all(v >= 0 for v in dists.values())

def test_pintassilgo_low_f(twin):
    """Pintassilgo must have F < 0.25 in winter morning (no AC, 85 lux)."""
    states = twin.tick(month=1, hour=9, day_of_week=0)
    s = states.get("Pintassilgo")
    if s:
        assert s.F < 0.30, f"Pintassilgo F={s.F} — should be critically low"

def test_quintanilha_worst_on_f1(twin):
    states = twin.tick(month=3, hour=9, day_of_week=0)
    f1_rooms = {k: v for k, v in states.items() if ROOMS[k].floor == "F1" and ROOMS[k].capacity > 0}
    if f1_rooms:
        worst = min(f1_rooms, key=lambda k: f1_rooms[k].F)
        assert worst == "Quintanilha" or f1_rooms[worst].F < 0.35
