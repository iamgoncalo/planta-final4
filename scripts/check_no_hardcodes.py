"""CI check: no numeric literals from config.yaml in backend/ Python files."""
import re, sys
from pathlib import Path

# Values that must only live in config.yaml
FORBIDDEN = [
    "0.40", "0.22", "0.16", "0.12", "0.05", "0.03", "0.02",  # D-weights
    "7034", "24000", "2198",                                    # HVAC
    "5.44", "942", "0.2375",                                    # Economics
    "0.218", "0.185", "0.138", "0.202",                        # Energy
    "= 1000", "= 800",                                         # CO2 limits (as assignments)
]

EXCLUDE_PATTERNS = [
    r"^#",          # comments
    r'"""',         # docstrings
    r"config\.yaml",
    r"check_no_hardcodes",
]

errors = []
for py_file in Path("backend").rglob("*.py"):
    if py_file.name in ("config.py",):
        continue  # config.py is the loader — allowed to reference values
    text = py_file.read_text()
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if any(re.search(p, stripped) for p in EXCLUDE_PATTERNS):
            continue
        for forbidden in FORBIDDEN:
            if forbidden in stripped and "cfg." not in stripped and "config" not in stripped.lower():
                errors.append(f"{py_file}:{i}: hardcoded '{forbidden}' → use cfg.* from config.yaml")

if errors:
    print("HARDCODE CHECK FAILED:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("✓ No hardcoded values found in backend/")
