"""
SGP4 orbital propagator.

Propagates TLE elements to a target time, returning ECI position (m)
and velocity (m/s).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sgp4.api import Satrec, WGS72
from sgp4.api import jday

from engine.maneuver import OrbitalState

logger = logging.getLogger(__name__)


def propagate_to_epoch(
    line1: str,
    line2: str,
    target_time: datetime,
) -> Optional[OrbitalState]:
    """
    Propagate a TLE to a target epoch using SGP4.

    Parameters
    ----------
    line1 : str – TLE line 1
    line2 : str – TLE line 2
    target_time : datetime – target epoch (UTC)

    Returns
    -------
    OrbitalState with position in meters and velocity in m/s (TEME frame),
    or None if propagation fails (decayed object, bad TLE, etc.)
    """
    try:
        sat = Satrec.twoline2rv(line1, line2, WGS72)
    except Exception as exc:
        logger.error("Failed to parse TLE: %s", exc)
        return None

    # Ensure UTC timezone
    if target_time.tzinfo is None:
        target_time = target_time.replace(tzinfo=timezone.utc)

    jd, fr = jday(
        target_time.year,
        target_time.month,
        target_time.day,
        target_time.hour,
        target_time.minute,
        target_time.second + target_time.microsecond / 1e6,
    )

    error_code, position_km, velocity_kms = sat.sgp4(jd, fr)

    if error_code != 0:
        logger.warning(
            "SGP4 propagation error code %d for TLE epoch %.2f at target %s",
            error_code, sat.jdsatepoch, target_time.isoformat(),
        )
        return None

    # Convert km → m and km/s → m/s
    position_m = [p * 1000.0 for p in position_km]
    velocity_ms = [v * 1000.0 for v in velocity_kms]

    return OrbitalState(
        position_eci=position_m,
        velocity_eci=velocity_ms,
        epoch=target_time,
    )


def propagate_orbit_track(
    line1: str,
    line2: str,
    start_time: datetime,
    periods: float = 1.5,
    steps: int = 180,
) -> list[dict]:
    """
    Propagate an orbit track for Cesium visualization.

    Returns a list of {epoch_iso, position_eci, altitude_km} dicts
    spanning `periods` orbital periods starting from `start_time`.
    """
    try:
        sat = Satrec.twoline2rv(line1, line2, WGS72)
    except Exception:
        return []

    # Estimate orbital period from mean motion (rev/day)
    if sat.no_kozai > 0:
        period_min = 1440.0 / (sat.no_kozai * 60.0 / (2.0 * 3.14159265))
        # Actually: period = 2π / n  where n is in rad/min
        period_min = 2.0 * 3.14159265 / sat.no_kozai  # minutes
    else:
        period_min = 90.0  # default ~LEO

    total_minutes = period_min * periods
    dt_minutes = total_minutes / steps

    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    track = []
    from datetime import timedelta
    for i in range(steps + 1):
        t = start_time + timedelta(minutes=i * dt_minutes)
        jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute,
                       t.second + t.microsecond / 1e6)
        err, pos_km, vel_kms = sat.sgp4(jd, fr)
        if err == 0:
            pos_m = [p * 1000.0 for p in pos_km]
            alt = (sum(p ** 2 for p in pos_m) ** 0.5 - 6_371_000.0) / 1000.0
            track.append({
                "epoch_iso": t.isoformat(),
                "position_eci": pos_m,
                "altitude_km": round(alt, 2),
            })

    return track
