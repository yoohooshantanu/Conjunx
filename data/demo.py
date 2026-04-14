"""
Demo / hardcoded sample data so the frontend always has something to render,
even without Space-Track credentials or when the API is rate-limited.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_NOW = datetime.now(timezone.utc)
_TCA = _NOW + timedelta(hours=18)

SAMPLE_CDM = {
    "CDM_ID": "DEMO-001",
    "MESSAGE_ID": "DEMO-001",
    "TCA": _TCA.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    "MISS_DISTANCE": "93.0",
    "PC": "5.84e-3",
    "COLLISION_PROBABILITY": "5.84e-3",
    "SAT1_OBJECT_DESIGNATOR": "60214",
    "SAT1_OBJECT_NAME": "STARLINK-31337",
    "SAT1_CATALOG_NAME": "60214",
    "SAT1_RCS_SIZE": "MEDIUM",
    "SAT2_OBJECT_DESIGNATOR": "67245",
    "SAT2_OBJECT_NAME": "CZ-6A DEB",
    "SAT2_CATALOG_NAME": "67245",
    "SAT2_RCS_SIZE": "SMALL",
    "EMERGENCY_REPORTABLE": "Y",
    "CREATED": (_NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
}

SAMPLE_SATCAT_1 = {
    "NORAD_CAT_ID": "60214",
    "OBJECT_NAME": "STARLINK-31337",
    "OBJECT_TYPE": "PAYLOAD",
    "RCS_SIZE": "MEDIUM",
    "LAUNCH": "2024-06-15",
    "COUNTRY": "US",
}

SAMPLE_SATCAT_2 = {
    "NORAD_CAT_ID": "67245",
    "OBJECT_NAME": "CZ-6A DEB",
    "OBJECT_TYPE": "DEBRIS",
    "RCS_SIZE": "SMALL",
    "LAUNCH": "2023-11-02",
    "COUNTRY": "PRC",
}

SAMPLE_MANEUVER = {
    "delta_v_mps": 0.0247,
    "delta_v_direction": [0.0, 1.0, 0.0],
    "burn_duration_s": 1235.0,
    "burn_time": (_TCA - timedelta(hours=6)).isoformat() + "Z",
    "fuel_cost_kg": 0.06,
    "pc_before": 5.84e-3,
    "pc_after": 1.2e-7,
    "maneuver_feasible": True,
    "reason": (
        "Along-track burn of 0.0247 m/s to increase miss distance "
        "from 93 m to 1000 m. Fuel cost: 0.06 kg. "
        "Pc reduction: 5.84e-03 → 1.20e-07."
    ),
    "target_miss_distance_m": 1000.0,
}

SAMPLE_RISK = {
    "score": 80,
    "level": "CRITICAL",
    "breakdown": {
        "pc_score": 40,
        "miss_distance_score": 20,
        "maneuverability_score": 15,
        "time_urgency_score": 5,
    },
    "recommended_action": (
        "IMMEDIATE maneuver required. Execute 0.0247 m/s burn within 12 hours."
    ),
}

SAMPLE_EXPLANATION = {
    "situation_summary": (
        "STARLINK-31337 and CZ-6A DEB are predicted to pass within 93 meters "
        "with a 1 in 171 chance of collision. This is a CRITICAL-risk event "
        "requiring immediate operator action."
    ),
    "risk_rationale": (
        "A collision probability of 5.84e-3 is roughly 30× above the "
        "typical 1e-4 maneuver threshold. At 93m miss distance, positional "
        "uncertainty alone could bridge the gap."
    ),
    "maneuver_recommendation": (
        "Execute a 0.0247 m/s along-track burn 6 hours prior to TCA. "
        "This uses 0.06 kg of propellant and reduces Pc to 1.2e-7. "
        "The debris object cannot maneuver — STARLINK-31337 must act."
    ),
    "no_action_scenario": (
        "Without action, the objects pass within 93 meters at 7.5 km/s "
        "relative velocity. At 1-in-171 odds, this represents a serious "
        "collision risk that could generate 1000+ trackable debris fragments "
        "in a congested LEO shell."
    ),
    "operator_urgency": "ACT_NOW",
}


def get_sample_conjunction() -> dict:
    """Return a fully-processed sample conjunction for demo purposes."""
    return {
        **SAMPLE_CDM,
        "cdm_id": "DEMO-001",
        "norad_id_1": 60214,
        "norad_id_2": 67245,
        "satcat_1": SAMPLE_SATCAT_1,
        "satcat_2": SAMPLE_SATCAT_2,
        "maneuver": SAMPLE_MANEUVER,
        "risk": SAMPLE_RISK,
        "explanation": SAMPLE_EXPLANATION,
        "primary_state": {
            "position_eci": [6_771_000.0, 0.0, 0.0],
            "velocity_eci": [0.0, 7_670.0, 0.0],
            "epoch": _TCA.isoformat() + "Z",
        },
        "secondary_state": {
            "position_eci": [6_771_093.0, 0.0, 0.0],
            "velocity_eci": [0.0, -7_500.0, 0.0],
            "epoch": _TCA.isoformat() + "Z",
        },
    }
