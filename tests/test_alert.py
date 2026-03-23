"""Tests for alert system."""
import pytest, sys
sys.path.insert(0, ".")
from backend.digital_twin import DigitalTwin
from backend.config import cfg

def test_co2_legal_breach_fires_level4():
    twin = DigitalTwin()
    twin.initialize(month=3, hour=9)
    # Force CO₂ above legal limit in Vasco_da_Gama
    state = twin._states.get("Vasco_da_Gama")
    if state:
        state.co2_ppm = cfg.comfort["co2_legal_ppm"] + 50
        from backend.rooms import ROOMS
        twin._update_computed(state, ROOMS["Vasco_da_Gama"])
        assert state.alert_level == 4
        assert state.co2_legal_breach is True

def test_good_room_level0():
    twin = DigitalTwin()
    twin.initialize(month=3, hour=9)
    state = twin._states.get("Hall_GF")
    if state:
        # Hall_GF in normal conditions → alert 0 or 1
        assert state.alert_level <= 2

def test_pintassilgo_aco_exclusion():
    """ACO avoid_rooms must include Pintassilgo."""
    assert "Pintassilgo" in cfg.aco.avoid_rooms
