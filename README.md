# PlantaOS — Physical AI Building Operating System

**Planta Smart Homes** · CEO: Gonçalo Melo de Magalhães · [hi@planta.design](mailto:hi@planta.design)

> ⚠️ ALL RESULTS SIMULATION-BASED · F=P/D IS A HYPOTHESIS UNDER TEST · Not a proven law.

---

## What It Is

PlantaOS is a Physical AI operating system for buildings. It computes per-room Freedom (F) and Distortion (D) scores in real time, routes groups to optimal rooms, detects environmental breaches, and quantifies the economic cost of sub-optimal conditions.

**Pilot:** HORSE CFT, Cacia, Aveiro, Portugal · 950 m² · 24 rooms · 3,219 users/year

**FCT Grant:** 2025.00020.AIVLAB.DEUCALION · Deucalion Supercomputer (MACC, Guimarães)

---

## Core Formula

```
F = P / D     (hypothesis under test — NOT proven law)

P = BFS spatial topology score (0–1, Hall_GF = reference)
D = exp(Σ wₖ · ln(dₖ))   [geometric mean — Deucalion R²=0.993]
```

D-weights (config.yaml, sum = 1.0):
`thermal 40% · co2 22% · humidity 16% · light 12% · noise 5% · occupancy 3% · spatial 2%`

---

## Quick Start (3 commands)

```bash
# 1. Install
pip install -r requirements.txt

# 2. Seed 24h simulation (zero real sensors needed)
python scripts/demo_simulation.py

# 3. Launch
uvicorn backend.api:app --reload
# → http://localhost:8000/health
# → ws://localhost:8000/ws
```

---

## Architecture

```
config.yaml          ← ALL parameters. Never hardcode in Python.
backend/
  config.py          ← Pydantic loader + weight-sum assertion
  rooms.py           ← 24-room ground truth (David Fleury data)
  distortion.py      ← D geometric formula + attribution %
  freedom.py         ← BFS P_spatial + F = clip(P/D, 0, 1)
  economic.py        ← F-debt €/h model (non-linear, exponent 1.5)
  digital_twin.py    ← RC thermal + CO₂ mass balance × 24 rooms
  memory.py          ← SQLite 7d → DuckDB 30d → Parquet
  claude_interface.py ← 4 agents: MONITOR(€0) · ALERT · OPTIMISER · CHATBOT
  api.py             ← FastAPI REST + WebSocket (60s tick)
scripts/
  demo_simulation.py ← Seeds DB, validates assertions
tests/               ← pytest ≥70% coverage required
```

---

## Four AI Agents (< €7/month total)

| Agent | Trigger | Cost |
|---|---|---|
| MONITOR | Every 60s tick | **€0 — ZERO AI** |
| ALERT | alert_level=4 or fire_fusion≥0.8 | €0.36/mo |
| OPTIMISER | After PSO (15 min async) | €0.18/mo |
| CHATBOT | User question (max 10 turns) | €4.88/mo |

---

## Critical Room Facts

- **Pintassilgo**: 0 AC, 85 lux → F≈0.15 winter mornings. **ACO never assigns groups here.**
- **Quintanilha**: Highest D in building (1.3548). Thermal dominant 52%.
- **Vasco_da_Gama**: CO₂ breach risk in 15 min at full occupancy.

---

## Standards & Sources

| Standard | Applies to |
|---|---|
| Portaria 353-A/2013 Portugal | CO₂ legal limit 1000 ppm |
| ISO 7730 | Thermal comfort (PMV/PPD), humidity |
| EN 12464-1 | Lighting (300–500 lux classrooms) |
| ISO 11690-1 | Noise (max 45 dB) |
| EN 15251 | CO₂ reference (700 ppm = Cat I) |

Building data confirmed by: **David Fleury, Dpt. Central Fluidos, HORSE Aveiro** (emails 3 Mar 2026 + 12 Mar 2026).

---

## Research

- ORCID: [0009-0008-6255-7724](https://orcid.org/0009-0008-6255-7724)
- DOI 1: [10.5281/zenodo.18636095](https://doi.org/10.5281/zenodo.18636095)
- DOI 2: [10.5281/zenodo.18845574](https://doi.org/10.5281/zenodo.18845574)
- SSRN: [6304936](https://ssrn.com/abstract=6304936)

---

## Acknowledgments

This work was supported by the Portuguese Foundation for Science and Technology (FCT) through Project 2025.00020.AIVLAB.DEUCALION, providing access to the Deucalion supercomputer at MACC, Guimarães, Portugal.

AI Disclosure: During the preparation of this work, the author used Claude (Anthropic) for code development and manuscript preparation. The author reviewed all content and takes full responsibility.

---

*"I design to free." — Gonçalo Melo*
