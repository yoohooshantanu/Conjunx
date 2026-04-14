"""
Conjunction processor — ties together fetcher, propagator, and maneuver solver.

process_conjunction(cdm_id) is the main pipeline entry point.
"""

from __future__ import annotations

import logging
import traceback
import re
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from data.fetcher import SpaceTrackFetcher
from engine.maneuver import (
    ConjunctionEvent,
    ManeuverSolution,
    OrbitalState,
    solve_conjunction_maneuver,
)
from engine.propagator import propagate_to_epoch
from engine.pc_calculator import compute_pc_for_cdm, PcResult

logger = logging.getLogger(__name__)

# Default covariance — cdm_public doesn't provide covariance fields
DEFAULT_COVARIANCE = np.diag([500**2, 500**2, 100**2])

# Shared fetcher instance (created lazily)
_fetcher: Optional[SpaceTrackFetcher] = None


def get_fetcher() -> SpaceTrackFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = SpaceTrackFetcher()
    return _fetcher


def _extract_norad_id(cdm: dict, prefix: str) -> Optional[int]:
    """Extract NORAD ID from CDM for SAT1 or SAT2."""
    # Try direct NORAD_CAT_ID field first
    key_norad = f"{prefix}_OBJECT_DESIGNATOR"
    key_id = f"{prefix}_OBJECT_ID"
    key_catalog = f"{prefix}_CATALOG_NAME"

    raw = cdm.get(key_norad) or cdm.get(key_id) or cdm.get(key_catalog) or ""
    raw = str(raw).strip()

    # If it looks like a number, use it directly
    if raw.isdigit():
        return int(raw)

    # Try to extract digits
    match = re.search(r"(\d{4,})", raw)
    if match:
        return int(match.group(1))

    return None


def _parse_tca(cdm: dict) -> datetime:
    """Parse TCA from CDM dict."""
    tca_str = cdm.get("TCA", "")
    try:
        tca = datetime.fromisoformat(tca_str.replace("Z", "+00:00"))
        if tca.tzinfo is None:
            tca = tca.replace(tzinfo=timezone.utc)
        return tca
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)


async def process_conjunction(
    cdm_id: str,
    mass_kg: float = 500.0,
    isp: float = 220.0,
) -> dict:
    """Full conjunction processing pipeline."""
    fetcher = get_fetcher()

    cdm = fetcher.get_cached_cdm(cdm_id)
    if cdm is None:
        # Try fetching fresh CDMs first
        await fetcher.fetch_cdms()
        cdm = fetcher.get_cached_cdm(cdm_id)
        if cdm is None:
            return {"error": f"CDM {cdm_id} not found in cache"}

    # cdm_public uses SAT_1_ID and SAT_2_ID directly
    norad_1 = None
    norad_2 = None
    sat1_id = cdm.get("SAT_1_ID")
    sat2_id = cdm.get("SAT_2_ID")
    if sat1_id and str(sat1_id).strip().isdigit():
        norad_1 = int(sat1_id)
    else:
        norad_1 = _extract_norad_id(cdm, "SAT1")
    if sat2_id and str(sat2_id).strip().isdigit():
        norad_2 = int(sat2_id)
    else:
        norad_2 = _extract_norad_id(cdm, "SAT2")

    if norad_1 is None and norad_2 is None:
        logger.warning("Could not extract NORAD IDs from CDM %s", cdm_id)

    norad_ids = [n for n in [norad_1, norad_2] if n is not None]

    tles = await fetcher.fetch_tles(norad_ids) if norad_ids else []
    satcats = await fetcher.fetch_satcat(norad_ids) if norad_ids else []

    tle_map = {int(t["NORAD_CAT_ID"]): t for t in tles}
    satcat_map = {int(s["NORAD_CAT_ID"]): s for s in satcats}

    satcat_1 = satcat_map.get(norad_1, {}) if norad_1 else {}
    satcat_2 = satcat_map.get(norad_2, {}) if norad_2 else {}

    tca = _parse_tca(cdm)

    primary_state = None
    secondary_state = None

    if norad_1 and norad_1 in tle_map:
        tle1 = tle_map[norad_1]
        primary_state = propagate_to_epoch(
            tle1["TLE_LINE1"], tle1["TLE_LINE2"], tca
        )

    if norad_2 and norad_2 in tle_map:
        tle2 = tle_map[norad_2]
        secondary_state = propagate_to_epoch(
            tle2["TLE_LINE1"], tle2["TLE_LINE2"], tca
        )

    miss_raw = cdm.get("MISS_DISTANCE") or cdm.get("MIN_RNG", 1000)
    miss_distance = float(miss_raw)
    pc = float(cdm.get("PC") or cdm.get("COLLISION_PROBABILITY") or 1e-7)

    # Use default covariance since cdm_public doesn't provide it
    covariance = DEFAULT_COVARIANCE

    # If we don't have a primary state, create a synthetic one
    if primary_state is None:
        primary_state = OrbitalState(
            position_eci=[6_771_000.0, 0.0, 0.0],  # ~400km altitude
            velocity_eci=[0.0, 7_670.0, 0.0],       # ~LEO velocity
            epoch=tca,
        )

    event = ConjunctionEvent(
        tca=tca,
        miss_distance=miss_distance,
        pc=pc,
        combined_covariance=covariance,
        primary=primary_state,
        secondary=secondary_state,
    )

    solution = solve_conjunction_maneuver(event, mass_kg=mass_kg, isp=isp)

    debris_types = {"DEBRIS", "ROCKET BODY", "TBA", "UNKNOWN"}
    type_1 = satcat_1.get("OBJECT_TYPE", "").upper()
    type_2 = satcat_2.get("OBJECT_TYPE", "").upper()

    sat1_is_debris = type_1 in debris_types
    sat2_is_debris = type_2 in debris_types

    if sat1_is_debris and sat2_is_debris:
        solution = ManeuverSolution(
            delta_v_mps=solution.delta_v_mps,
            delta_v_direction=solution.delta_v_direction,
            burn_duration_s=solution.burn_duration_s,
            burn_time=solution.burn_time,
            fuel_cost_kg=solution.fuel_cost_kg,
            pc_before=solution.pc_before,
            pc_after=solution.pc_after,
            maneuver_feasible=False,
            reason="Both objects are debris — no maneuver capability.",
            target_miss_distance_m=solution.target_miss_distance_m,
        )
    elif sat1_is_debris:
        solution = ManeuverSolution(
            delta_v_mps=solution.delta_v_mps,
            delta_v_direction=solution.delta_v_direction,
            burn_duration_s=solution.burn_duration_s,
            burn_time=solution.burn_time,
            fuel_cost_kg=solution.fuel_cost_kg,
            pc_before=solution.pc_before,
            pc_after=solution.pc_after,
            maneuver_feasible=solution.maneuver_feasible,
            reason=f"Primary (SAT1) is {type_1} — cannot maneuver. "
                   f"Secondary must act. {solution.reason}",
            target_miss_distance_m=solution.target_miss_distance_m,
        )

    from engine.propagator import propagate_orbit_track
    orbit_track_1 = []
    orbit_track_2 = []
    if norad_1 and norad_1 in tle_map:
        tle1 = tle_map[norad_1]
        orbit_track_1 = propagate_orbit_track(
            tle1["TLE_LINE1"], tle1["TLE_LINE2"], tca, periods=1.0, steps=90
        )
    if norad_2 and norad_2 in tle_map:
        tle2 = tle_map[norad_2]
        orbit_track_2 = propagate_orbit_track(
            tle2["TLE_LINE1"], tle2["TLE_LINE2"], tca, periods=1.0, steps=90
        )

    independent_pc = None
    tle_1_data = tle_map.get(norad_1) if norad_1 else None
    tle_2_data = tle_map.get(norad_2) if norad_2 else None

    if tle_1_data and tle_2_data:
        try:
            pc_result = compute_pc_for_cdm(
                cdm=cdm,
                tle1=tle_1_data,
                tle2=tle_2_data,
                satcat1=satcat_1,
                satcat2=satcat_2,
            )
            independent_pc = {
                "pc_foster": pc_result.pc_foster,
                "pc_spacetrack": pc_result.pc_spacetrack,
                "delta_percent": pc_result.delta_percent,
                "miss_distance_computed": pc_result.miss_distance_computed,
                "miss_distance_cdm": pc_result.miss_distance_cdm,
                "miss_distance_agreement": pc_result.miss_distance_agreement,
                "hard_body_radius": pc_result.hard_body_radius,
                "relative_speed": pc_result.relative_speed,
                "covariance_source": pc_result.covariance_source,
                "tle_age_hours": pc_result.tle_age_hours,
                "computation_valid": pc_result.computation_valid,
                "failure_reason": pc_result.failure_reason,
                "analysis_notes": pc_result.analysis_notes,
                "risk_assessment": pc_result.risk_assessment,
                "sensitivity_analysis": pc_result.sensitivity_analysis,
            }
        except Exception as exc:
            logger.error("Independent Pc computation failed: %s", traceback.format_exc())
            independent_pc = {
                "computation_valid": False,
                "failure_reason": f"Exception: {exc}",
            }
    else:
        independent_pc = {
            "computation_valid": False,
            "failure_reason": "TLE data unavailable for one or both objects",
        }

    result = {
        **cdm,
        "cdm_id": cdm_id,
        "norad_id_1": norad_1,
        "norad_id_2": norad_2,
        "satcat_1": satcat_1,
        "satcat_2": satcat_2,
        "maneuver": solution.to_dict(),
        "independent_pc": independent_pc,
        "primary_state": {
            "position_eci": primary_state.position_eci,
            "velocity_eci": primary_state.velocity_eci,
            "epoch": primary_state.epoch.isoformat() + "Z",
        } if primary_state else None,
        "secondary_state": {
            "position_eci": secondary_state.position_eci,
            "velocity_eci": secondary_state.velocity_eci,
            "epoch": secondary_state.epoch.isoformat() + "Z",
        } if secondary_state else None,
        "tle_1": tle_map.get(norad_1) if norad_1 else None,
        "tle_2": tle_map.get(norad_2) if norad_2 else None,
        "orbit_track_1": orbit_track_1,
        "orbit_track_2": orbit_track_2,
    }

    return result
