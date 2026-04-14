"""
AI-powered conjunction explainer using Azure OpenAI GPT-4o.

Generates human-readable, actionable explanations for satellite operators.
Falls back to template-based explanations if API is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _build_prompt(
    cdm: dict,
    maneuver: dict,
    risk: dict,
    satcat_1: dict,
    satcat_2: dict,
) -> str:
    """Build a structured prompt with all conjunction context."""
    pc = float(cdm.get("PC") or cdm.get("COLLISION_PROBABILITY") or 1e-7)
    miss = float(cdm.get("MISS_DISTANCE") or cdm.get("MIN_RNG") or 9999)
    tca_str = cdm.get("TCA", "unknown")
    dv = float(maneuver.get("delta_v_mps", 0))
    fuel = float(maneuver.get("fuel_cost_kg", 0))
    feasible = maneuver.get("maneuver_feasible", False)
    pc_after = float(maneuver.get("pc_after", pc))

    name_1 = satcat_1.get("OBJECT_NAME", cdm.get("SAT1_OBJECT_DESIGNATOR", "SAT-1"))
    name_2 = satcat_2.get("OBJECT_NAME", cdm.get("SAT2_OBJECT_DESIGNATOR", "SAT-2"))
    type_1 = satcat_1.get("OBJECT_TYPE", "UNKNOWN")
    type_2 = satcat_2.get("OBJECT_TYPE", "UNKNOWN")
    rcs_1 = satcat_1.get("RCS_SIZE", "UNKNOWN")
    rcs_2 = satcat_2.get("RCS_SIZE", "UNKNOWN")

    # Human-readable Pc
    if pc > 0:
        pc_odds = f"1 in {int(1 / pc):,}" if pc < 1 else "certain"
    else:
        pc_odds = "negligible"

    # Miss distance context
    if miss < 10:
        miss_context = f"{miss:.1f} meters — closer than a bus length"
    elif miss < 100:
        miss_context = f"{miss:.0f} meters — roughly the length of a football field"
    elif miss < 500:
        miss_context = f"{miss:.0f} meters — about five football fields"
    elif miss < 1000:
        miss_context = f"{miss:.0f} meters — under 1 kilometer"
    else:
        miss_context = f"{miss:.0f} meters ({miss / 1000:.1f} km)"

    # TCA countdown
    try:
        tca_dt = datetime.fromisoformat(tca_str.replace("Z", "+00:00"))
        if tca_dt.tzinfo is None:
            tca_dt = tca_dt.replace(tzinfo=timezone.utc)
        hours_until = (tca_dt - datetime.now(timezone.utc)).total_seconds() / 3600
        countdown = f"{hours_until:.1f} hours from now"
    except (ValueError, AttributeError):
        countdown = "unknown"

    # ΔV context
    if dv < 0.01:
        dv_context = f"{dv * 100:.1f} cm/s — a tiny nudge"
    elif dv < 0.1:
        dv_context = f"{dv:.4f} m/s — a small station-keeping-size burn"
    elif dv < 1.0:
        dv_context = f"{dv:.3f} m/s — a moderate avoidance maneuver"
    else:
        dv_context = f"{dv:.2f} m/s — a significant maneuver"

    # Typical satellite fuel budget context
    fuel_context = (
        f"{fuel:.2f} kg of propellant — "
        f"roughly {fuel / 50 * 100:.1f}% of a typical smallsat's total fuel budget"
    )

    prompt = f"""Analyze this conjunction event:

**Objects:**
- Primary: {name_1} (Type: {type_1}, RCS: {rcs_1})
- Secondary: {name_2} (Type: {type_2}, RCS: {rcs_2})

**Conjunction Parameters:**
- TCA: {tca_str} ({countdown})
- Miss distance: {miss_context}
- Collision probability: {pc:.2e} ({pc_odds} chance of collision)
- Risk level: {risk.get('level', 'UNKNOWN')} (score: {risk.get('score', 0)}/100)

**Maneuverability:**
- Primary can maneuver: {type_1 not in ('DEBRIS', 'ROCKET BODY', 'TBA', 'UNKNOWN')}
- Secondary can maneuver: {type_2 not in ('DEBRIS', 'ROCKET BODY', 'TBA', 'UNKNOWN')}

**Proposed Maneuver:**
- ΔV required: {dv_context}
- Fuel cost: {fuel_context}
- Pc after maneuver: {pc_after:.2e}
- Maneuver feasible: {feasible}

Respond with ONLY valid JSON (no markdown, no code blocks) with these exact fields:
{{
  "situation_summary": "2 sentences max describing the conjunction",
  "risk_rationale": "why this probability level matters for operations",
  "maneuver_recommendation": "specific action with timing",
  "no_action_scenario": "what happens if ignored",
  "operator_urgency": "ACT_NOW or MONITOR or WATCH"
}}"""

    return prompt


SYSTEM_PROMPT = (
    "You are a space operations analyst. Explain conjunction events clearly "
    "to satellite operators who understand orbital mechanics but need fast, "
    "actionable summaries. Be direct and specific. No hedging."
)


# ---------------------------------------------------------------------------
# Singleton Azure OpenAI client — avoids re-creating HTTP client per request
# ---------------------------------------------------------------------------

_ai_client = None
_ai_deployment: str = ""


def _get_ai_client():
    """Return a reusable AsyncAzureOpenAI client, or None if not configured."""
    global _ai_client, _ai_deployment

    if _ai_client is not None:
        return _ai_client

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    api_key = os.getenv("AZURE_OPENAI_KEY", "")
    _ai_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

    if not endpoint or not api_key:
        return None

    try:
        from openai import AsyncAzureOpenAI

        _ai_client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version="2024-10-21",
        )
        return _ai_client
    except Exception as exc:
        logger.error("Failed to create Azure OpenAI client: %s", exc)
        return None


async def generate_explanation(
    cdm: dict,
    maneuver: dict,
    risk: dict,
    satcat_1: dict,
    satcat_2: dict,
) -> dict:
    """
    Generate an AI explanation for a conjunction event.

    Uses Azure OpenAI if credentials are available, otherwise falls back
    to a template-based explanation.
    """
    prompt = _build_prompt(cdm, maneuver, risk, satcat_1, satcat_2)

    client = _get_ai_client()
    if client is not None:
        try:
            response = await client.chat.completions.create(
                model=_ai_deployment,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"},
            )

            text = response.choices[0].message.content.strip()
            result = json.loads(text)

            # Validate required fields
            required = [
                "situation_summary", "risk_rationale",
                "maneuver_recommendation", "no_action_scenario",
                "operator_urgency",
            ]
            for field in required:
                if field not in result:
                    result[field] = "N/A"

            return result

        except Exception as exc:
            logger.error("Azure OpenAI call failed: %s", exc)

    # Fallback template-based explanation
    return _template_explanation(cdm, maneuver, risk, satcat_1, satcat_2)


def _template_explanation(
    cdm: dict,
    maneuver: dict,
    risk: dict,
    satcat_1: dict,
    satcat_2: dict,
) -> dict:
    """Generate a template-based explanation when AI is unavailable."""
    pc = float(cdm.get("PC") or cdm.get("COLLISION_PROBABILITY") or 1e-7)
    miss = float(cdm.get("MISS_DISTANCE") or cdm.get("MIN_RNG") or 9999)
    level = risk.get("level", "UNKNOWN")
    dv = float(maneuver.get("delta_v_mps", 0))
    feasible = maneuver.get("maneuver_feasible", False)

    name_1 = satcat_1.get("OBJECT_NAME", cdm.get("SAT1_OBJECT_DESIGNATOR", "SAT-1"))
    name_2 = satcat_2.get("OBJECT_NAME", cdm.get("SAT2_OBJECT_DESIGNATOR", "SAT-2"))

    if pc > 0:
        pc_odds = f"1 in {int(1 / pc):,}"
    else:
        pc_odds = "negligible"

    urgency_map = {
        "CRITICAL": "ACT_NOW",
        "HIGH": "ACT_NOW",
        "MEDIUM": "MONITOR",
        "LOW": "WATCH",
    }

    summary = (
        f"{name_1} and {name_2} are predicted to pass within "
        f"{miss:.0f} meters with a {pc_odds} chance of collision. "
        f"This event is rated {level} risk."
    )

    if feasible:
        recommendation = (
            f"Execute a {dv:.4f} m/s along-track burn to increase miss "
            f"distance. Fuel cost: {maneuver.get('fuel_cost_kg', 0):.2f} kg."
        )
    else:
        recommendation = (
            "No maneuver capability available for the primary object. "
            "Coordinate with the secondary operator if possible."
        )

    return {
        "situation_summary": summary,
        "risk_rationale": (
            f"A collision probability of {pc:.2e} ({pc_odds}) at {miss:.0f}m "
            f"miss distance places this in the {level} category. "
            f"Events above 1e-4 Pc require immediate operator attention."
        ),
        "maneuver_recommendation": recommendation,
        "no_action_scenario": (
            f"Without action, the objects will pass within {miss:.0f} meters. "
            f"At {pc_odds} probability, this represents a non-negligible "
            f"collision risk that could generate debris affecting the "
            f"orbital regime."
        ),
        "operator_urgency": urgency_map.get(level, "MONITOR"),
    }
