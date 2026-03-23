"""CI check: D-weights in config.yaml must sum to exactly 1.0."""
import yaml, sys
cfg = yaml.safe_load(open("config.yaml"))
w = cfg["distortion"]["weights"]
total = sum(w.values())
if abs(total - 1.0) >= 1e-6:
    print(f"WEIGHT CHECK FAILED: sum={total:.10f} (must be 1.0)")
    sys.exit(1)
print(f"✓ D-weights sum = {total:.10f}")
