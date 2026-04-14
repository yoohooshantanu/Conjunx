"""
Conjunction risk scorer.

Scores a conjunction event on 4 axes (Pc, miss distance, maneuverability,
time urgency) and assigns a risk level with recommended action.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class RiskAssessment:
    """Scored risk assessment for a conjunction event."""
    score: int                  # 0–100
    level: str                  # CRITICAL | HIGH | MEDIUM | LOW
    breakdown: dict             # per-axis scores
    recommended_action: str     # human-readable recommendation

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Sub-scorers
# ---------------------------------------------------------------------------

def _pc_score(pc: float) -> int:
    """Collision probability score (max 40 pts)."""
    if pc >= 1e-3:
        return 40
    if pc >= 1e-4:
        return 30
    if pc >= 1e-5:
        return 20
    return 10


def _miss_distance_score(miss_m: float) -> int:
    """Miss distance score (max 20 pts)."""
    if miss_m < 100:
        return 20
    if miss_m < 500:
        return 15
    if miss_m < 1000:
        return 10
    return 5


def _maneuverability_score(type_1: str, type_2: str) -> int:
    """
    Maneuverability score (max 20 pts).

    Higher score = worse (less ability to maneuver).
    """
    debris_types = {"DEBRIS", "ROCKET BODY", "TBA", "UNKNOWN", ""}
    is_debris_1 = type_1.upper() in debris_types
    is_debris_2 = type_2.upper() in debris_types

    if is_debris_1 and is_debris_2:
        return 20  # worst — neither can maneuver
    if is_debris_1 or is_debris_2:
        return 15
    return 5   # both payloads — best scenario


def _time_urgency_score(tca: datetime) -> int:
    """Time urgency score (max 20 pts)."""
    now = datetime.now(timezone.utc)
    if tca.tzinfo is None:
        tca = tca.replace(tzinfo=timezone.utc)
    hours_until = (tca - now).total_seconds() / 3600.0

    if hours_until < 24:
        return 20
    if hours_until < 48:
        return 15
    if hours_until < 72:
        return 10
    return 5


def _level_from_score(score: int) -> str:
    if score >= 70:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def _recommended_action(level: str, can_maneuver: bool,
                         dv: float, hours_until: float) -> str:
    """Generate a recommended action string."""
    if level == "CRITICAL":
        if can_maneuver:
            return (
                f"IMMEDIATE maneuver required. Execute {dv:.4f} m/s "
                f"burn within {hours_until:.0f} hours."
            )
        return (
            "CRITICAL risk but no maneuver capability. "
            "Alert all operators and prepare for potential collision."
        )
    if level == "HIGH":
        if can_maneuver:
            return (
                f"Plan avoidance maneuver ({dv:.4f} m/s). "
                f"Execute within {max(hours_until - 6, 1):.0f} hours."
            )
        return "Elevated risk. Monitor closely and coordinate with operator."
    if level == "MEDIUM":
        return "Monitor conjunction. Prepare contingency maneuver plan."
    return "Low risk. Continue monitoring with standard cadence."


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def score_conjunction(
    cdm: dict,
    maneuver: dict,
    satcat_1: dict | None = None,
    satcat_2: dict | None = None,
) -> RiskAssessment:
    """
    Score a conjunction event and produce a RiskAssessment.

    Parameters
    ----------
    cdm : dict – CDM fields (must contain PC, MISS_DISTANCE, TCA)
    maneuver : dict – ManeuverSolution fields
    satcat_1 : dict – SATCAT for primary object
    satcat_2 : dict – SATCAT for secondary object
    """
    # Extract values with safe defaults
    pc = float(cdm.get("PC") or cdm.get("COLLISION_PROBABILITY") or 1e-7)
    miss = float(cdm.get("MISS_DISTANCE") or 9999)

    tca_str = cdm.get("TCA") or cdm.get("tca") or ""
    try:
        tca = datetime.fromisoformat(tca_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        tca = datetime.now(timezone.utc)

    type_1 = (satcat_1 or {}).get("OBJECT_TYPE", "PAYLOAD")
    type_2 = (satcat_2 or {}).get("OBJECT_TYPE", "PAYLOAD")

    dv = float(maneuver.get("delta_v_mps", 0))
    now = datetime.now(timezone.utc)
    if tca.tzinfo is None:
        tca = tca.replace(tzinfo=timezone.utc)
    hours_until = max((tca - now).total_seconds() / 3600.0, 0)

    # Compute sub-scores
    s_pc = _pc_score(pc)
    s_miss = _miss_distance_score(miss)
    s_man = _maneuverability_score(type_1, type_2)
    s_time = _time_urgency_score(tca)

    total = s_pc + s_miss + s_man + s_time
    level = _level_from_score(total)

    # Can this pair maneuver?
    debris_types = {"DEBRIS", "ROCKET BODY", "TBA", "UNKNOWN", ""}
    can_maneuver = (
        type_1.upper() not in debris_types
        or type_2.upper() not in debris_types
    )

    action = _recommended_action(level, can_maneuver, dv, hours_until)

    return RiskAssessment(
        score=total,
        level=level,
        breakdown={
            "pc_score": s_pc,
            "miss_distance_score": s_miss,
            "maneuverability_score": s_man,
            "time_urgency_score": s_time,
        },
        recommended_action=action,
    )
