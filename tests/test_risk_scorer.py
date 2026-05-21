"""
Tests for engine/risk_scorer.py — 4-axis conjunction risk scoring.

Covers:
  - Sub-score thresholds matching README documentation
  - Level assignment from total score
  - Recommended action generation
  - Debris maneuverability logic
"""

import pytest
from datetime import datetime, timedelta, timezone

from engine.risk_scorer import (
    RiskAssessment,
    score_conjunction,
    _pc_score,
    _miss_distance_score,
    _maneuverability_score,
    _time_urgency_score,
    _level_from_score,
)


# ---------------------------------------------------------------------------
# Sub-score thresholds (must match README table)
# ---------------------------------------------------------------------------

class TestPcScore:
    def test_critical_threshold(self):
        assert _pc_score(1e-3) == 40
        assert _pc_score(5e-3) == 40

    def test_high_threshold(self):
        assert _pc_score(1e-4) == 30
        assert _pc_score(5e-4) == 30

    def test_medium_threshold(self):
        assert _pc_score(1e-5) == 20
        assert _pc_score(5e-5) == 20

    def test_low(self):
        assert _pc_score(1e-6) == 10
        assert _pc_score(1e-8) == 10


class TestMissDistanceScore:
    def test_under_100m(self):
        assert _miss_distance_score(50) == 20
        assert _miss_distance_score(99) == 20

    def test_under_500m(self):
        assert _miss_distance_score(100) == 15
        assert _miss_distance_score(499) == 15

    def test_under_1km(self):
        assert _miss_distance_score(500) == 10
        assert _miss_distance_score(999) == 10

    def test_over_1km(self):
        assert _miss_distance_score(1000) == 5
        assert _miss_distance_score(5000) == 5


class TestManeuverabilityScore:
    def test_both_debris(self):
        """Both debris → worst score (20)."""
        assert _maneuverability_score("DEBRIS", "ROCKET BODY") == 20

    def test_one_debris(self):
        """One debris → 15."""
        assert _maneuverability_score("PAYLOAD", "DEBRIS") == 15
        assert _maneuverability_score("DEBRIS", "PAYLOAD") == 15

    def test_both_payload(self):
        """Both payloads → best (5)."""
        assert _maneuverability_score("PAYLOAD", "PAYLOAD") == 5

    def test_unknown_treated_as_debris(self):
        assert _maneuverability_score("UNKNOWN", "TBA") == 20


class TestTimeUrgencyScore:
    def test_under_24h(self):
        tca = datetime.now(timezone.utc) + timedelta(hours=12)
        assert _time_urgency_score(tca) == 20

    def test_under_48h(self):
        tca = datetime.now(timezone.utc) + timedelta(hours=30)
        assert _time_urgency_score(tca) == 15

    def test_under_72h(self):
        tca = datetime.now(timezone.utc) + timedelta(hours=60)
        assert _time_urgency_score(tca) == 10

    def test_over_72h(self):
        tca = datetime.now(timezone.utc) + timedelta(hours=100)
        assert _time_urgency_score(tca) == 5


# ---------------------------------------------------------------------------
# Level assignment
# ---------------------------------------------------------------------------

class TestLevelAssignment:
    def test_critical(self):
        assert _level_from_score(70) == "CRITICAL"
        assert _level_from_score(100) == "CRITICAL"

    def test_high(self):
        assert _level_from_score(50) == "HIGH"
        assert _level_from_score(69) == "HIGH"

    def test_medium(self):
        assert _level_from_score(30) == "MEDIUM"
        assert _level_from_score(49) == "MEDIUM"

    def test_low(self):
        assert _level_from_score(0) == "LOW"
        assert _level_from_score(29) == "LOW"


# ---------------------------------------------------------------------------
# Full scoring integration
# ---------------------------------------------------------------------------

class TestScoreConjunction:
    def _make_cdm(self, pc=1e-3, miss=50.0, tca_hours=12.0):
        tca = datetime.now(timezone.utc) + timedelta(hours=tca_hours)
        return {
            "PC": str(pc),
            "MISS_DISTANCE": str(miss),
            "TCA": tca.isoformat(),
        }

    def test_critical_scenario(self):
        """High Pc + close miss + soon TCA + debris → CRITICAL."""
        cdm = self._make_cdm(pc=1e-3, miss=50.0, tca_hours=12.0)
        risk = score_conjunction(
            cdm,
            maneuver={"delta_v_mps": 0.5},
            satcat_1={"OBJECT_TYPE": "PAYLOAD"},
            satcat_2={"OBJECT_TYPE": "DEBRIS"},
        )
        assert risk.level == "CRITICAL"
        assert risk.score >= 70

    def test_low_scenario(self):
        """Low Pc + far miss + distant TCA → LOW or MEDIUM."""
        cdm = self._make_cdm(pc=1e-7, miss=5000.0, tca_hours=200.0)
        risk = score_conjunction(
            cdm,
            maneuver={"delta_v_mps": 0.01},
            satcat_1={"OBJECT_TYPE": "PAYLOAD"},
            satcat_2={"OBJECT_TYPE": "PAYLOAD"},
        )
        assert risk.level in ("LOW", "MEDIUM")

    def test_breakdown_sums_to_score(self):
        """Sub-scores should add up to total."""
        cdm = self._make_cdm()
        risk = score_conjunction(cdm, maneuver={"delta_v_mps": 0.1})
        b = risk.breakdown
        total = b["pc_score"] + b["miss_distance_score"] + b["maneuverability_score"] + b["time_urgency_score"]
        assert total == risk.score

    def test_to_dict(self):
        """to_dict should return a dict with expected keys."""
        cdm = self._make_cdm()
        risk = score_conjunction(cdm, maneuver={"delta_v_mps": 0.1})
        d = risk.to_dict()
        assert "score" in d
        assert "level" in d
        assert "breakdown" in d
        assert "recommended_action" in d

    def test_both_debris_mentions_no_maneuver(self):
        """When both objects are debris, action should mention no capability."""
        cdm = self._make_cdm(pc=1e-3, miss=50.0, tca_hours=12.0)
        risk = score_conjunction(
            cdm,
            maneuver={"delta_v_mps": 0.5},
            satcat_1={"OBJECT_TYPE": "DEBRIS"},
            satcat_2={"OBJECT_TYPE": "ROCKET BODY"},
        )
        assert "no maneuver" in risk.recommended_action.lower() or "potential collision" in risk.recommended_action.lower()
