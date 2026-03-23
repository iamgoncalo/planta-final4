"""Full simulation smoke test."""
import sys
sys.path.insert(0, ".")
from scripts.demo_simulation import run

def test_simulation_runs_cleanly():
    result = run(validate=True)
    assert 0.1 < result["F_global_mean"] < 0.8
    assert result["annual_fdbt_eur"] > 0
