"""
Tests for engine/maneuver.py — avoidance solver and tradeoff evaluation.

Covers:
  - Tsiolkovsky fuel cost
  - CW-based ΔV estimation
  - Maneuver solver feasibility gate
  - Tradeoff hypothetical mode
"""

import math
import numpy as np
import pytest
from datetime import datetime, timedelta, timezone

from engine.maneuver import (
    OrbitalState,
    ConjunctionEvent,
    _fuel_cost,
    _required_delta_v,
    solve_conjunction_maneuver,
    evaluate_tradeoff,
    MU_EARTH,
    R_EARTH,
    G0,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    miss_distance: float = 200.0,
    pc: float = 1e-4,
    tca_offset_hours: float = 24.0,
) -> ConjunctionEvent:
    """Create a ConjunctionEvent with configurable parameters."""
    tca = datetime.now(timezone.utc) + timedelta(hours=tca_offset_hours)
    return ConjunctionEvent(
        tca=tca,
        miss_distance=miss_distance,
        pc=pc,
        combined_covariance=np.diag([500**2, 500**2, 100**2]),
        primary=OrbitalState(
            position_eci=[6_771_000.0, 0.0, 0.0],
            velocity_eci=[0.0, 7_670.0, 0.0],
            epoch=tca,
        ),
    )


# ---------------------------------------------------------------------------
# _fuel_cost (Tsiolkovsky)
# ---------------------------------------------------------------------------

class TestFuelCost:
    def test_zero_delta_v(self):
        """Zero ΔV → zero fuel."""
        assert _fuel_cost(0.0, 500.0, 220.0) == 0.0

    def test_known_value(self):
        """Tsiolkovsky: m_fuel = m0 × (1 - exp(-ΔV / (Isp × g0)))."""
        dv = 1.0  # m/s
        mass = 500.0  # kg
        isp = 220.0  # s
        expected = mass * (1.0 - math.exp(-dv / (isp * G0)))
        result = _fuel_cost(dv, mass, isp)
        assert abs(result - expected) < 1e-6

    def test_fuel_increases_with_delta_v(self):
        """More ΔV → more fuel."""
        f1 = _fuel_cost(0.5, 500.0, 220.0)
        f2 = _fuel_cost(1.0, 500.0, 220.0)
        f3 = _fuel_cost(5.0, 500.0, 220.0)
        assert f1 < f2 < f3

    def test_negative_delta_v_uses_absolute(self):
        """Should use abs(ΔV)."""
        assert _fuel_cost(-1.0, 500.0, 220.0) == _fuel_cost(1.0, 500.0, 220.0)


# ---------------------------------------------------------------------------
# _required_delta_v
# ---------------------------------------------------------------------------

class TestRequiredDeltaV:
    def test_zero_time_to_tca(self):
        """With no time left, should fallback to miss/velocity."""
        dv = _required_delta_v(100.0, 1000.0, 7500.0, 0.0)
        assert dv == 900.0 / 7500.0

    def test_scales_with_miss_gap(self):
        """Larger miss gap → larger ΔV."""
        dv_small = _required_delta_v(100.0, 500.0, 7500.0, 21600.0)
        dv_large = _required_delta_v(100.0, 2000.0, 7500.0, 21600.0)
        assert dv_large > dv_small

    def test_positive_result(self):
        """ΔV should always be positive."""
        dv = _required_delta_v(200.0, 1000.0, 7500.0, 21600.0)
        assert dv > 0


# ---------------------------------------------------------------------------
# solve_conjunction_maneuver
# ---------------------------------------------------------------------------

class TestSolveManeuver:
    def test_feasibility_gate(self):
        """ΔV > 10 m/s should be flagged infeasible."""
        # Very close approach with very little time
        event = _make_event(miss_distance=5.0, pc=0.01, tca_offset_hours=0.01)
        sol = solve_conjunction_maneuver(event)
        # Either it's feasible with dv <= 10, or infeasible
        if sol.delta_v_mps > 10.0:
            pytest.fail("ΔV should be capped at 10 m/s")

    def test_target_miss_at_least_1km(self):
        """Target miss distance should be >= 1000m."""
        event = _make_event(miss_distance=200.0)
        sol = solve_conjunction_maneuver(event)
        assert sol.target_miss_distance_m >= 1000.0

    def test_target_miss_doubles_current(self):
        """Target should be at least 2× current miss."""
        event = _make_event(miss_distance=2000.0)
        sol = solve_conjunction_maneuver(event)
        assert sol.target_miss_distance_m >= 4000.0

    def test_pc_after_less_than_before(self):
        """Post-maneuver Pc should be less than pre-maneuver."""
        event = _make_event(miss_distance=200.0, pc=1e-3)
        sol = solve_conjunction_maneuver(event)
        assert sol.pc_after < sol.pc_before

    def test_has_burn_time(self):
        """Solution should include a burn time."""
        event = _make_event()
        sol = solve_conjunction_maneuver(event)
        assert sol.burn_time is not None

    def test_to_dict_serializable(self):
        """to_dict() output should contain expected keys."""
        event = _make_event()
        sol = solve_conjunction_maneuver(event)
        d = sol.to_dict()
        assert "delta_v_mps" in d
        assert "fuel_cost_kg" in d
        assert "burn_time" in d
        assert isinstance(d["burn_time"], str)


# ---------------------------------------------------------------------------
# evaluate_tradeoff
# ---------------------------------------------------------------------------

class TestTradeoff:
    def test_hypothetical_mode_for_past_tca(self):
        """Past-TCA events should trigger hypothetical mode."""
        event = _make_event(tca_offset_hours=-1.0)  # TCA was 1 hour ago
        result = evaluate_tradeoff(event, delta_v_mps=0.5)
        assert result["hypothetical"] is True

    def test_non_hypothetical_for_future_tca(self):
        """Future-TCA events should not be hypothetical."""
        event = _make_event(tca_offset_hours=24.0)
        result = evaluate_tradeoff(event, delta_v_mps=0.5)
        assert result["hypothetical"] is False

    def test_miss_distance_increases_with_dv(self):
        """Higher ΔV → larger new miss distance."""
        event = _make_event()
        r1 = evaluate_tradeoff(event, delta_v_mps=0.1)
        r2 = evaluate_tradeoff(event, delta_v_mps=1.0)
        assert r2["new_miss_distance_m"] > r1["new_miss_distance_m"]

    def test_feasibility_flag(self):
        """ΔV > 10 m/s should be infeasible."""
        event = _make_event()
        result = evaluate_tradeoff(event, delta_v_mps=15.0)
        assert result["feasible"] is False

    def test_zero_dv_preserves_miss(self):
        """Zero ΔV should not change miss distance."""
        event = _make_event(miss_distance=500.0)
        result = evaluate_tradeoff(event, delta_v_mps=0.0)
        assert abs(result["new_miss_distance_m"] - 500.0) < 1.0
