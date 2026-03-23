"""
claude_interface.py — 4 Claude agents with hard cost guard.
HL-03: ZERO AI calls in the 60s monitoring tick.
HL-04: Hard stop if daily cost > €2.00.
"""
from __future__ import annotations
import os, json, datetime
from typing import Optional
from .config import cfg
from .memory import get_daily_ai_cost, write_ai_cost

_MODEL = cfg.ai.model
_COST_PER_1K_IN  = 0.003   # claude-sonnet-4-5 input
_COST_PER_1K_OUT = 0.015   # claude-sonnet-4-5 output

SYSTEM_PROMPT = """<s>
  <identity>PlantaOS — Physical AI Smart Space Operating System</identity>
  <building>
    <n>HORSE CFT — Centro de Formacao Tecnica</n>
    <location>Rua da Junqueira, Cacia, 3800-640 Aveiro, Portugal</location>
    <area_m2>950</area_m2><floors>2</floors><rooms>24</rooms>
  </building>
  <framework>
    <law>F = P / D  (hypothesis under test — NOT proven law)</law>
    <D>D = exp(sum(w_k * ln(d_k))) — geometric mean, Deucalion R2=0.993</D>
  </framework>
  <honesty_rules>
    <rule>Mark ALL simulation outputs [SIMULATED]</rule>
    <rule>Never claim F=P/D is a proven law</rule>
    <rule>Always report D attribution: dominant channel and %</rule>
    <rule>Report confidence score 0.0-1.0 explicitly</rule>
  </honesty_rules>
  <output_format>JSON only. No markdown. No prose outside JSON fields.</output_format>
  <language>PT if user writes PT. EN otherwise.</language>
</s>"""


def _cost_guard(agent: str) -> None:
    daily = get_daily_ai_cost()
    if daily >= cfg.ai.cost_limit_day_eur:
        raise RuntimeError(
            f"AI daily cost limit reached: €{daily:.4f} >= €{cfg.ai.cost_limit_day_eur}. "
            f"Agent '{agent}' blocked until tomorrow."
        )


def _call(prompt: str, system: str, agent: str,
          max_tokens: int, room_id: str = None, session_id: str = None) -> str:
    """Core Claude API call with cost tracking. Raises on limit exceeded."""
    _cost_guard(agent)

    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text if msg.content else ""
    tin  = msg.usage.input_tokens
    tout = msg.usage.output_tokens
    cost = (tin / 1000 * _COST_PER_1K_IN) + (tout / 1000 * _COST_PER_1K_OUT)
    write_ai_cost(agent, tin, tout, cost, room_id, session_id)
    return text


# ── Agent 2 — ALERT ─────────────────────────────────────────────────────────

ALERT_SCHEMA = '{"diagnosis":str,"root_cause":str,"dominant_channel":str,"recommended_actions":[str,str,str],"urgency_minutes":int,"confidence":float,"legal_breach":bool}'

def call_alert_agent(room_id: str, state: dict, history_1h: dict, attribution: dict) -> dict:
    """Agent 2: diagnose critical alert. Fires only on alert_level=4 or fire_fusion≥0.8."""
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    legal_text = "CO2_BREACH: Portaria 353-A/2013 exceeded" if state.get("co2_ppm", 0) >= 1000 else "OK"
    prompt = f"""<query agent='alert' version='1.0'>
  <ts>{ts}</ts><room>{room_id}</room><alert_level>4</alert_level>
  <state>
    <F>{state.get('F', 0)}</F><D>{state.get('D_total', 0)}</D>
    <temp_c>{state.get('temp_c', 0)}</temp_c>
    <co2_ppm>{state.get('co2_ppm', 0)}</co2_ppm>
    <humidity_pct>{state.get('humidity_pct', 0)}</humidity_pct>
    <lux>{state.get('lux', 0)}</lux>
    <occupants>{state.get('occupancy', 0)}</occupants>
    <hvac_state>{state.get('hvac_state', 'off')}</hvac_state>
  </state>
  <attribution>{json.dumps(attribution)}</attribution>
  <history_1h>{json.dumps(history_1h)}</history_1h>
  <legal_status>{legal_text}</legal_status>
  <task>Diagnose root cause. Provide max 3 immediate actions.</task>
  <schema>{ALERT_SCHEMA}</schema>
</query>"""
    raw = _call(prompt, SYSTEM_PROMPT, "alert", cfg.ai.alert_max_tokens, room_id)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"diagnosis": raw, "confidence": 0.5, "legal_breach": False,
                "recommended_actions": [], "urgency_minutes": 30}


# ── Agent 3 — OPTIMISER ──────────────────────────────────────────────────────

def call_optimiser_agent(pso_result: dict, rooms_improved: list[str]) -> dict:
    """Agent 3: short summary of PSO setpoint changes. Max 200 tokens."""
    prompt = f"""<query agent='optimiser'>
  <pso_result>{json.dumps(pso_result)}</pso_result>
  <rooms_improved>{json.dumps(rooms_improved)}</rooms_improved>
  <task>Summarise setpoint changes in max 3 sentences. JSON only.</task>
  <schema>{{"setpoint_summary":str,"rooms_improved":int,"energy_saved_kwh":float,"confidence":float}}</schema>
</query>"""
    raw = _call(prompt, SYSTEM_PROMPT, "optimiser", cfg.ai.optimiser_max_tokens)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"setpoint_summary": raw, "rooms_improved": len(rooms_improved),
                "energy_saved_kwh": 0.0, "confidence": 0.5}


# ── Agent 4 — CHATBOT ────────────────────────────────────────────────────────

def call_chatbot_agent(user_question: str, building_state: dict,
                       session_id: str, conversation_history: list[dict]) -> dict:
    """Agent 4: natural language Q&A. Max 10 turns, 200 words."""
    context = f"""<building_state ts='{datetime.datetime.utcnow().isoformat()}Z'>
  <F_global>{building_state.get('F_global', 0)}</F_global>
  <rooms_critical>{building_state.get('rooms_critical', 0)}</rooms_critical>
  <rooms_amber>{building_state.get('rooms_amber', 0)}</rooms_amber>
  <active_alerts>{building_state.get('active_alerts', 0)}</active_alerts>
  <f_debt_today_eur>{building_state.get('f_debt_total_eur_h', 0)}</f_debt_today_eur>
  <source>simulation [ALL VALUES SIMULATED]</source>
</building_state>
<user_question>{user_question}</user_question>
<constraint>Max 200 words. Max 3 recommendations. State confidence 0-1. JSON only.</constraint>
<schema>{{"answer":str,"recommendations":[str],"confidence":float,"source":"simulation"}}</schema>"""

    history = [{"role": m["role"], "content": m["content"]} for m in conversation_history[-8:]]
    history.append({"role": "user", "content": context})

    _cost_guard("chatbot")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = client.messages.create(
            model=_MODEL, max_tokens=cfg.ai.max_tokens,
            system=SYSTEM_PROMPT, messages=history,
        )
        raw = msg.content[0].text if msg.content else ""
        tin = msg.usage.input_tokens; tout = msg.usage.output_tokens
        cost = (tin/1000*_COST_PER_1K_IN) + (tout/1000*_COST_PER_1K_OUT)
        write_ai_cost("chatbot", tin, tout, cost, session_id=session_id)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"answer": raw, "recommendations": [], "confidence": 0.5, "source": "simulation"}
    except Exception as e:
        return {"answer": f"Error: {e}", "recommendations": [], "confidence": 0.0, "source": "simulation"}
