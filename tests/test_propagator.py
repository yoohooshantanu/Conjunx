"""
Tests for engine/propagator.py — SGP4 orbital propagation.

Covers:
  - Known TLE propagation (ISS)
  - Error handling for invalid TLEs
  - Orbit track generation
  - propagate_tle_to_epoch returning state + epoch
"""

import pytest
import numpy as np
from datetime import datetime, timedelta, timezone

from engine.propagator import (
    propagate_to_epoch,
    propagate_tle_to_epoch,
    propagate_orbit_track,
)


# ISS TLE (epoch 2024-01-01, representative — may be stale but structure is valid)
ISS_LINE1 = "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9005"
ISS_LINE2 = "2 25544  51.6400 200.0000 0007417  50.0000 310.0000 15.49560000    19"


# ---------------------------------------------------------------------------
# propagate_to_epoch
# ---------------------------------------------------------------------------

class TestPropagateToEpoch:
    def test_valid_tle_returns_state(self):
        """Should return an OrbitalState for a valid TLE."""
        target = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        state = propagate_to_epoch(ISS_LINE1, ISS_LINE2, target)
        assert state is not None
        assert len(state.position_eci) == 3
        assert len(state.velocity_eci) == 3

    def test_altitude_is_leo(self):
        """ISS should be at ~400 km altitude."""
        target = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        state = propagate_to_epoch(ISS_LINE1, ISS_LINE2, target)
        assert state is not None
        alt = state.altitude_km()
        assert 200 < alt < 600, f"ISS altitude {alt} km out of LEO range"

    def test_speed_is_orbital(self):
        """ISS orbital speed should be ~7.5 km/s."""
        target = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        state = propagate_to_epoch(ISS_LINE1, ISS_LINE2, target)
        assert state is not None
        speed_kms = state.speed() / 1000.0
        assert 6.5 < speed_kms < 8.5, f"Speed {speed_kms} km/s out of range"

    def test_invalid_tle_returns_none(self):
        """Invalid TLE should return None."""
        result = propagate_to_epoch("INVALID", "ALSO INVALID", datetime.now(timezone.utc))
        assert result is None

    def test_naive_datetime_handled(self):
        """Should handle timezone-naive datetimes without crashing."""
        target = datetime(2024, 1, 1, 12, 0, 0)  # no tzinfo
        state = propagate_to_epoch(ISS_LINE1, ISS_LINE2, target)
        assert state is not None


# ---------------------------------------------------------------------------
# propagate_tle_to_epoch (returns state + tle_epoch)
# ---------------------------------------------------------------------------

class TestPropagateTleToEpoch:
    def test_returns_tuple(self):
        """Should return (OrbitalState, datetime) tuple."""
        target = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        state, tle_epoch = propagate_tle_to_epoch(ISS_LINE1, ISS_LINE2, target)
        assert state is not None
        assert tle_epoch is not None

    def test_tle_epoch_is_near_tle_date(self):
        """TLE epoch should be near 2024-01-01."""
        target = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        _, tle_epoch = propagate_tle_to_epoch(ISS_LINE1, ISS_LINE2, target)
        assert tle_epoch is not None
        delta = abs((tle_epoch - datetime(2024, 1, 1, tzinfo=timezone.utc)).total_seconds())
        assert delta < 86400 * 2  # within 2 days

    def test_invalid_tle_returns_none_none(self):
        state, epoch = propagate_tle_to_epoch("BAD", "TLE", datetime.now(timezone.utc))
        assert state is None
        # epoch may or may not be None depending on whether Satrec could
        # parse the epoch field before propagation fails


# ---------------------------------------------------------------------------
# propagate_orbit_track
# ---------------------------------------------------------------------------

class TestOrbitTrack:
    def test_returns_list_of_dicts(self):
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        track = propagate_orbit_track(ISS_LINE1, ISS_LINE2, start, periods=0.5, steps=20)
        assert isinstance(track, list)
        assert len(track) > 0
        assert "epoch_iso" in track[0]
        assert "position_eci" in track[0]
        assert "altitude_km" in track[0]

    def test_track_length_matches_steps(self):
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        track = propagate_orbit_track(ISS_LINE1, ISS_LINE2, start, periods=0.5, steps=10)
        assert len(track) == 11  # steps + 1

    def test_invalid_tle_returns_empty(self):
        track = propagate_orbit_track("BAD", "TLE", datetime.now(timezone.utc))
        assert track == []

    def test_altitudes_are_leo(self):
        """All points should be at LEO altitude."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        track = propagate_orbit_track(ISS_LINE1, ISS_LINE2, start, periods=0.5, steps=10)
        for point in track:
            assert 200 < point["altitude_km"] < 600
