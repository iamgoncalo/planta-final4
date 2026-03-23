"""Tests for distortion calculator. All D-formula + attribution + weights."""
import math, pytest, sys
sys.path.insert(0, ".")
from backend.config import cfg
from backend.distortion import (
    compute_D, d_thermal, d_co2, d_humidity, d_light, d_noise,
    d_occupancy, d_spatial, build_channels
)

def test_weights_sum_to_one():
    w = cfg.D_weights
    assert abs(sum(w.values()) - 1.0) < 1e-6

def test_weights_all_positive():
    for k, v in cfg.D_weights.items():
        assert v > 0, f"Weight {k} must be positive"

def test_d_thermal_at_setpoint():
    T = 20.0
    d = d_thermal(T, T)
    assert d == 1.0, "At setpoint, thermal distortion = 1.0"

def test_d_thermal_increases_with_deviation():
    d1 = d_thermal(20.0, 20.0)
    d2 = d_thermal(23.0, 20.0)
    d3 = d_thermal(26.0, 20.0)
    assert d1 < d2 < d3

def test_d_co2_clean_air():
    d = d_co2(cfg.comfort["co2_clean_ppm"])
    assert d == pytest.approx(1.0, rel=1e-3)

def test_d_co2_legal_breach():
    d = d_co2(cfg.comfort["co2_legal_ppm"])
    assert d > 1.4  # 1000/700 ≈ 1.43

def test_d_light_at_target():
    d = d_light(400.0)
    assert d == pytest.approx(1.0, rel=1e-3)

def test_d_light_critical():
    d = d_light(85.0)  # Pintassilgo lux
    assert d > 4.0

def test_compute_D_returns_valid():
    channels = build_channels(
        temp_c=21.0, setpoint_c=20.0, co2_ppm=650.0,
        humidity_pct=50.0, lux=350.0, noise_db=42.0,
        occupancy=10, capacity=15,
        bfs_distance=1, max_bfs_distance=5
    )
    result = compute_D(channels)
    assert result.D_total >= 1.0
    assert 0 <= sum(result.attribution.values()) <= 101  # ~100%
    assert result.dominant_channel in channels

def test_attribution_sums_to_100():
    channels = build_channels(22.0, 20.0, 700.0, 55.0, 380.0, 43.0, 8, 12, 2, 5)
    result = compute_D(channels)
    total_pct = sum(result.attribution.values())
    assert abs(total_pct - 100.0) < 1.0

def test_pintassilgo_light_dominant():
    """Pintassilgo: 85 lux → light must be dominant distortion."""
    channels = build_channels(20.0, 20.0, 600.0, 50.0, 85.0, 38.0, 8, 12, 3, 5)
    result = compute_D(channels)
    assert result.dominant_channel == "light"
    assert result.dominant_pct > 50.0

def test_geometric_formula():
    """D = exp(sum(w_k * ln(d_k))). Verify manually."""
    import math
    channels = {"thermal": 1.5, "co2": 1.2, "humidity": 1.1,
                "light": 1.3, "noise": 1.0, "occupancy": 1.0, "spatial": 1.1}
    w = cfg.D_weights
    expected_ln = sum(w[k] * math.log(channels[k]) for k in w)
    expected_D = math.exp(expected_ln)
    result = compute_D(channels)
    assert result.D_total == pytest.approx(expected_D, rel=1e-6)

def test_all_nominal_D_near_one():
    """All channels at ideal values → D ≈ 1.0."""
    channels = {"thermal": 1.0, "co2": 1.0, "humidity": 1.0,
                "light": 1.0, "noise": 1.0, "occupancy": 1.0, "spatial": 1.0}
    result = compute_D(channels)
    assert result.D_total == pytest.approx(1.0, rel=1e-6)
