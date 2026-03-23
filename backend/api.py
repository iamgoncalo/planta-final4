"""
api.py — FastAPI REST + WebSocket broadcast.
All 22 views connect here. WebSocket pushes state every 60s tick.
"""
from __future__ import annotations
import asyncio, json, datetime, uuid
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import cfg
from .digital_twin import DigitalTwin
from .memory import (
    init_db, write_readings, get_current_room_states,
    get_room_history, get_fdbt_weekly, get_daily_ai_cost, write_alert
)
from .claude_interface import call_chatbot_agent, call_alert_agent

# ── State ────────────────────────────────────────────────────────────────────
twin = DigitalTwin()
_ws_clients: set[WebSocket] = set()
_sessions: dict[str, list[dict]] = {}   # session_id → conversation history


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    twin.initialize()
    asyncio.create_task(_tick_loop())
    yield


app = FastAPI(title="PlantaOS API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Tick loop (60s) — ZERO AI CALLS ─────────────────────────────────────────

async def _tick_loop():
    """Master 60s tick. Pure Python. No AI. Ever."""
    while True:
        now = datetime.datetime.utcnow()
        states = twin.tick(
            month=now.month, hour=now.hour,
            day_of_week=now.weekday(), dt_min=1.0,
        )
        write_readings(states)
        summary = twin.get_building_summary()

        # Check for critical alerts → fire Agent 2 (async, never blocks tick)
        for rid, s in states.items():
            if s.alert_level >= 4:
                alert_id = write_alert(rid, s.alert_level, s.dominant_channel,
                                       getattr(s, s.dominant_channel + "_ppm", None))
                asyncio.create_task(_run_alert_agent(rid, s, alert_id))

        # Broadcast to all WebSocket clients
        payload = {
            "event": "tick", "ts": now.isoformat() + "Z",
            "source": "simulation",
            **summary,
            "rooms": [
                {"id": s.room_id, "F": s.F, "D": s.D_total,
                 "alert_level": s.alert_level,
                 "top_distortion": s.dominant_channel,
                 "top_pct": s.dominant_pct,
                 "f_debt_eur_h": s.f_debt_eur_h,
                 "occupancy": s.occupancy,
                 "hvac_state": s.hvac_state,
                 "co2_ppm": s.co2_ppm,
                 "temp_c": s.temp_c}
                for s in states.values()
            ]
        }
        await _broadcast(json.dumps(payload))
        await asyncio.sleep(cfg.lbm["tick_seconds"])


async def _run_alert_agent(room_id: str, state, alert_id: int):
    """Async Agent 2 call — never blocks the 60s tick."""
    try:
        history_1h = get_room_history(room_id, hours=1)
        F_avg = sum(r["F"] for r in history_1h) / max(len(history_1h), 1)
        hist_summary = {"F_avg": round(F_avg, 3), "readings": len(history_1h),
                        "trend": "deteriorating" if F_avg > state.F else "stable"}
        attribution = {
            "thermal": state.attr_thermal, "co2": state.attr_co2,
            "humidity": state.attr_humidity, "light": state.attr_light,
        }
        diagnosis = call_alert_agent(
            room_id, state.__dict__, hist_summary, attribution
        )
        await _broadcast(json.dumps({
            "event": "alert_diagnosis", "alert_id": alert_id,
            "room_id": room_id, **diagnosis
        }))
    except Exception as e:
        await _broadcast(json.dumps({
            "event": "alert_diagnosis_error", "room_id": room_id,
            "error": str(e)
        }))


async def _broadcast(msg: str):
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


# ── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        _ws_clients.discard(ws)


# ── REST endpoints ───────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "source": "simulation", "version": "1.0.0"}


@app.get("/rooms")
def get_rooms():
    states = get_current_room_states()
    if not states:
        states = [
            {"room_id": rid, "F": s.F_sim, "D_total": s.D_sim,
             "alert_level": 0, "source": "simulation",
             "attr_thermal": s.top_distortion_pct if s.top_distortion == "thermal" else 0,
             "f_debt_eur_h": s.f_debt_eur_h_sim or 0}
            for rid, s in __import__("backend.rooms", fromlist=["ROOMS"]).ROOMS.items()
        ]
    return {"rooms": states, "source": "simulation", "count": len(states)}


@app.get("/rooms/{room_id}")
def get_room(room_id: str):
    history = get_room_history(room_id, hours=1)
    if not history:
        raise HTTPException(404, f"No data for room '{room_id}'. Run simulation first.")
    return {"room_id": room_id, "current": history[0], "history_1h": history,
            "source": "simulation"}


@app.get("/alerts")
def get_alerts(active: bool = True):
    from .memory import get_db
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE resolved_ts IS NULL ORDER BY ts DESC LIMIT 50"
            if active else "SELECT * FROM alerts ORDER BY ts DESC LIMIT 100"
        ).fetchall()
    return {"alerts": [dict(r) for r in rows]}


@app.get("/economic/fdbt")
def get_fdbt():
    rows = get_fdbt_weekly()
    total = sum(r["f_debt_eur_total"] for r in rows)
    annual = total * 52  # project weekly → annual
    return {"rooms": rows, "week_eur": round(total, 2),
            "annual_projected_eur": round(annual, 2),
            "source": "simulation",
            "label": "[SIMULATED] — pending sensor validation"}


@app.get("/ai/cost")
def get_ai_cost():
    daily = get_daily_ai_cost()
    return {"today_eur": round(daily, 4),
            "limit_day_eur": cfg.ai.cost_limit_day_eur,
            "limit_month_eur": cfg.ai.cost_limit_month_eur,
            "status": "ok" if daily < cfg.ai.cost_limit_day_eur else "LIMIT_REACHED"}


@app.get("/building/summary")
def building_summary():
    summary = twin.get_building_summary()
    return {**summary, "label": "[SIMULATED]"}


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


@app.post("/chat")
def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    if session_id not in _sessions:
        _sessions[session_id] = []
    history = _sessions[session_id]
    if len(history) >= cfg.ai.chatbot_max_turns * 2:
        return {"error": "Session limit reached. Start a new session.",
                "session_id": session_id, "new_session_required": True}
    building_state = twin.get_building_summary()
    response = call_chatbot_agent(req.message, building_state, session_id, history)
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": response.get("answer", "")})
    _sessions[session_id] = history
    return {**response, "session_id": session_id, "turn": len(history) // 2}
