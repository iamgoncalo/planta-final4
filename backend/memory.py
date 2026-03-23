"""
memory.py — SQLite hot store (7d) → DuckDB warm (30d) → Parquet cold.
RGPD: raw data discarded within 60s. Only F, D, attribution, alert persisted.
"""
from __future__ import annotations
import sqlite3
import json
import datetime
from pathlib import Path
from contextlib import contextmanager
from .config import cfg
from .digital_twin import RoomState

DB_PATH = Path(cfg.memory.hot_db)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS readings (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ts            TEXT NOT NULL,
  room_id       TEXT NOT NULL,
  source        TEXT NOT NULL,
  temp_c        REAL,
  humidity_pct  REAL,
  co2_ppm       REAL,
  lux           REAL,
  noise_db      REAL,
  occupancy     INTEGER,
  d_thermal     REAL NOT NULL,
  d_humidity    REAL NOT NULL,
  d_co2         REAL NOT NULL,
  d_light       REAL NOT NULL,
  d_noise       REAL NOT NULL,
  d_occupancy   REAL NOT NULL,
  d_spatial     REAL NOT NULL,
  D_total       REAL NOT NULL,
  P_spatial     REAL NOT NULL,
  F             REAL NOT NULL,
  attr_thermal  REAL NOT NULL,
  attr_co2      REAL NOT NULL,
  attr_humidity REAL NOT NULL,
  attr_light    REAL NOT NULL,
  attr_noise    REAL NOT NULL,
  hvac_state    TEXT,
  hvac_kwh      REAL,
  lights_kwh    REAL,
  pmv           REAL,
  ppd           REAL,
  alert_level   INTEGER NOT NULL DEFAULT 0,
  f_debt_eur_h  REAL NOT NULL DEFAULT 0.0,
  UNIQUE(ts, room_id)
);
CREATE INDEX IF NOT EXISTS idx_ts_room ON readings(room_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_alert   ON readings(alert_level, ts DESC);
CREATE INDEX IF NOT EXISTS idx_F       ON readings(F, ts DESC);

CREATE TABLE IF NOT EXISTS alerts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT NOT NULL,
  room_id         TEXT NOT NULL,
  alert_level     INTEGER NOT NULL,
  trigger_channel TEXT,
  trigger_value   REAL,
  ai_diagnosis    TEXT,
  action_taken    TEXT,
  resolved_ts     TEXT,
  false_positive  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ai_costs (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         TEXT NOT NULL,
  agent      TEXT NOT NULL,
  tokens_in  INTEGER NOT NULL,
  tokens_out INTEGER NOT NULL,
  cost_eur   REAL NOT NULL,
  room_id    TEXT,
  session_id TEXT
);

CREATE TABLE IF NOT EXISTS algorithm_registry (
  id                TEXT PRIMARY KEY,
  family            TEXT NOT NULL,
  name              TEXT NOT NULL,
  version           TEXT NOT NULL,
  status            TEXT NOT NULL,
  owner             TEXT,
  validation_label  TEXT,
  deployment_scope  TEXT,
  test_suite        TEXT,
  rollback_to       TEXT,
  deployed_at       TEXT,
  decommissioned_at TEXT
);

CREATE TABLE IF NOT EXISTS patent_candidates (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  ts             TEXT NOT NULL,
  title          TEXT NOT NULL,
  idea_summary   TEXT NOT NULL,
  claims_json    TEXT,
  prior_art_risk TEXT,
  prior_art_notes TEXT,
  status         TEXT NOT NULL DEFAULT 'draft',
  human_review_ts TEXT,
  reviewer       TEXT,
  notes          TEXT
);
"""


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)
    _seed_algorithm_registry()


def write_readings(states: dict[str, RoomState]) -> None:
    """Write one row per room per tick. RGPD: only computed values, no raw identifiable data."""
    rows = []
    for s in states.values():
        rows.append((
            s.ts, s.room_id, s.source,
            s.temp_c, s.humidity_pct, s.co2_ppm, s.lux, s.noise_db, s.occupancy,
            s.d_thermal, s.d_humidity, s.d_co2, s.d_light, s.d_noise, s.d_occupancy, s.d_spatial,
            s.D_total, s.P_spatial, s.F,
            s.attr_thermal, s.attr_co2, s.attr_humidity, s.attr_light, s.attr_noise,
            s.hvac_state, s.hvac_kwh, s.lights_kwh if hasattr(s, 'lights_kwh') else 0.0,
            s.pmv, s.ppd, s.alert_level, s.f_debt_eur_h,
        ))
    with get_db() as conn:
        conn.executemany("""
          INSERT OR IGNORE INTO readings (
            ts, room_id, source,
            temp_c, humidity_pct, co2_ppm, lux, noise_db, occupancy,
            d_thermal, d_humidity, d_co2, d_light, d_noise, d_occupancy, d_spatial,
            D_total, P_spatial, F,
            attr_thermal, attr_co2, attr_humidity, attr_light, attr_noise,
            hvac_state, hvac_kwh, lights_kwh, pmv, ppd, alert_level, f_debt_eur_h
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
    purge_old_readings()


def purge_old_readings() -> None:
    """Keep only last 7 days. HL-09 RGPD compliance."""
    hot_days = cfg.memory.hot_days
    with get_db() as conn:
        conn.execute(
            "DELETE FROM readings WHERE ts < datetime('now', ?)",
            (f"-{hot_days} days",)
        )


def get_daily_ai_cost() -> float:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_eur), 0.0) FROM ai_costs WHERE DATE(ts)=DATE('now')"
        ).fetchone()
        return float(row[0])


def write_ai_cost(agent: str, tokens_in: int, tokens_out: int, cost_eur: float,
                  room_id: str = None, session_id: str = None) -> None:
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    with get_db() as conn:
        conn.execute(
            "INSERT INTO ai_costs (ts,agent,tokens_in,tokens_out,cost_eur,room_id,session_id) "
            "VALUES (?,?,?,?,?,?,?)",
            (ts, agent, tokens_in, tokens_out, cost_eur, room_id, session_id)
        )


def write_alert(room_id: str, level: int, channel: str = None,
                value: float = None, diagnosis: dict = None) -> int:
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO alerts (ts,room_id,alert_level,trigger_channel,trigger_value,ai_diagnosis) "
            "VALUES (?,?,?,?,?,?)",
            (ts, room_id, level, channel, value,
             json.dumps(diagnosis) if diagnosis else None)
        )
        return cur.lastrowid


def get_current_room_states() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("""
          SELECT r.* FROM readings r
          INNER JOIN (SELECT room_id, MAX(ts) ts FROM readings GROUP BY room_id) m
          ON r.room_id=m.room_id AND r.ts=m.ts
        """).fetchall()
        return [dict(r) for r in rows]


def get_room_history(room_id: str, hours: int = 1) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM readings WHERE room_id=? AND ts > datetime('now', ?) ORDER BY ts DESC",
            (room_id, f"-{hours} hours")
        ).fetchall()
        return [dict(r) for r in rows]


def get_fdbt_weekly() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("""
          SELECT room_id,
            SUM(f_debt_eur_h)/60.0 as f_debt_eur_total,
            AVG(F) as F_mean, MIN(F) as F_min,
            COUNT(*) as readings_count
          FROM readings
          WHERE source IN ('sensor','hybrid','simulation')
            AND ts > datetime('now','-7 days')
          GROUP BY room_id ORDER BY f_debt_eur_total DESC
        """).fetchall()
        return [dict(r) for r in rows]


def _seed_algorithm_registry() -> None:
    algorithms = [
        ("bfs-p-v1", "topology", "BFS P_spatial", "1.0", "active",
         "Gonçalo Melo", "simulation-only", "building", "tests/test_freedom.py", None),
        ("geo-d-v1", "distortion", "Geometric D formula", "1.0", "active",
         "Gonçalo Melo", "simulation-only", "building", "tests/test_distortion.py", None),
        ("fpd-v1", "freedom", "F=P/D hypothesis", "1.0", "active",
         "Gonçalo Melo", "simulation-only", "building", "tests/test_freedom.py", None),
        ("pso-setpoints-v1", "optimization", "PSO Setpoint Optimiser", "1.0", "active",
         "Gonçalo Melo", "simulation-only", "building", "tests/test_pso.py", None),
        ("aco-routing-v1", "routing", "ACO Room Routing", "1.0", "active",
         "Gonçalo Melo", "simulation-only", "building", "tests/test_aco.py", None),
        ("fdbt-v1", "economics", "F-debt economic model", "1.0", "active",
         "Gonçalo Melo", "simulation-only", "building", "tests/test_economic.py", None),
    ]
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    with get_db() as conn:
        for alg in algorithms:
            conn.execute(
                "INSERT OR IGNORE INTO algorithm_registry "
                "(id,family,name,version,status,owner,validation_label,deployment_scope,test_suite,rollback_to,deployed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (*alg, ts)
            )
