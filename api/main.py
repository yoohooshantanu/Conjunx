"""
FastAPI application — Conjunction Analysis & Maneuver Decision Engine API.

Routes:
  GET  /conjunctions              — all CDMs with risk scores
  GET  /conjunctions/{cdm_id}     — full detail for one conjunction
  POST /conjunctions/{cdm_id}/maneuver — recompute with custom mass/isp
  GET  /health                    — status, timestamps, cache stats, sample data
"""

from __future__ import annotations

import logging
import os
import time as _time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from data.demo import get_sample_conjunction
from data.fetcher import SpaceTrackFetcher
from engine.processor import process_conjunction, get_fetcher
from engine.risk_scorer import score_conjunction
from ai.explainer import generate_explanation

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# In-memory result cache — avoids re-running the full pipeline on every
# tradeoff slider drag, maneuver recompute, and pc-analysis request.

_conjunction_cache: dict[str, tuple[float, dict]] = {}
CONJUNCTION_CACHE_TTL = 300  # 5 minutes


async def get_cached_conjunction(cdm_id: str) -> dict:
    """Return cached process_conjunction result, or compute and cache it."""
    now = _time.monotonic()
    if cdm_id in _conjunction_cache:
        ts, result = _conjunction_cache[cdm_id]
        if now - ts < CONJUNCTION_CACHE_TTL:
            logger.debug("Pipeline cache hit for %s", cdm_id)
            return result

    result = await process_conjunction(cdm_id)
    _conjunction_cache[cdm_id] = (now, result)
    return result


# Lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Conjunx API starting up")
    yield
    # Cleanup
    fetcher = get_fetcher()
    await fetcher.close()
    logger.info("Conjunx API shut down")


# App Setup

app = FastAPI(
    title="Conjunx — Conjunction Analysis Engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request / Response models

class ManeuverRequest(BaseModel):
    satellite_mass_kg: float = 500.0
    isp: float = 220.0

class TradeoffRequest(BaseModel):
    delta_v_mps: float
    satellite_mass_kg: float = 500.0
    isp: float = 220.0


# Shared helpers — build ConjunctionEvent from cached result dicts

def _parse_tca_str(tca_str: str) -> datetime:
    """Parse a TCA string into a timezone-aware datetime."""
    if tca_str.endswith("Z"):
        tca_str = tca_str[:-1]
    try:
        tca = datetime.fromisoformat(tca_str)
        if tca.tzinfo is None:
            tca = tca.replace(tzinfo=timezone.utc)
        return tca
    except ValueError:
        return datetime.now(timezone.utc)


def _build_event_from_result(result: dict):
    """Build a ConjunctionEvent from a process_conjunction result dict."""
    from engine.maneuver import ConjunctionEvent, OrbitalState
    import numpy as np

    tca = _parse_tca_str(result.get("TCA", ""))
    miss = float(result.get("MISS_DISTANCE") or result.get("MIN_RNG") or 1000.0)
    pc = float(result.get("PC") or result.get("COLLISION_PROBABILITY") or 1e-7)

    primary = result.get("primary_state")
    if primary:
        epo = _parse_tca_str(primary["epoch"])
        primary_state = OrbitalState(
            position_eci=primary["position_eci"],
            velocity_eci=primary["velocity_eci"],
            epoch=epo,
        )
    else:
        primary_state = OrbitalState(
            position_eci=[6_771_000.0, 0.0, 0.0],
            velocity_eci=[0.0, 7_670.0, 0.0],
            epoch=tca,
        )

    return ConjunctionEvent(
        tca=tca,
        miss_distance=miss,
        pc=pc,
        combined_covariance=np.diag([500**2, 500**2, 100**2]),
        primary=primary_state,
    )


def _build_event_from_dict(sample: dict):
    """Build a ConjunctionEvent from a demo/sample dict (has primary_state)."""
    from engine.maneuver import ConjunctionEvent, OrbitalState
    import numpy as np

    return ConjunctionEvent(
        tca=datetime.fromisoformat(sample["TCA"].replace("Z", "+00:00")),
        miss_distance=float(sample["MISS_DISTANCE"]),
        pc=float(sample["PC"]),
        combined_covariance=np.diag([500**2, 500**2, 100**2]),
        primary=OrbitalState(
            position_eci=sample["primary_state"]["position_eci"],
            velocity_eci=sample["primary_state"]["velocity_eci"],
            epoch=datetime.fromisoformat(
                sample["primary_state"]["epoch"].replace("Z", "+00:00")
            ),
        ),
    )


# Routes

@app.get("/health")
async def health():
    """Health check with cache stats and a sample conjunction for demo."""
    fetcher = get_fetcher()
    stats = fetcher.get_cache_stats()
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "cache_stats": stats,
        "sample_conjunction": get_sample_conjunction(),
    }


@app.get("/conjunctions")
async def list_conjunctions():
    """
    Fetch CDMs, run risk scorer on each, return sorted by risk score desc.
    Groups by unique conjunction pair — only the latest CDM per pair is shown,
    with a count of total CDM updates and Pc evolution history.
    Falls back to demo data if no CDMs are available.
    """
    fetcher = get_fetcher()

    try:
        cdms = await fetcher.fetch_cdms()
    except Exception as exc:
        logger.error("Failed to fetch CDMs: %s", exc)
        cdms = []

    if not cdms:
        # Return demo data so frontend always has something
        sample = get_sample_conjunction()
        return [sample]

    # Group CDMs by conjunction pair (normalize pair order alphabetically)
    pair_groups: dict[str, list[dict]] = {}
    for cdm in cdms:
        name1 = cdm.get("SAT_1_NAME", cdm.get("SAT1_OBJECT_NAME", "?"))
        name2 = cdm.get("SAT_2_NAME", cdm.get("SAT2_OBJECT_NAME", "?"))
        # Normalize pair key so A-vs-B and B-vs-A are the same group
        pair_key = tuple(sorted([name1, name2]))
        key_str = f"{pair_key[0]}|{pair_key[1]}"
        if key_str not in pair_groups:
            pair_groups[key_str] = []
        pair_groups[key_str].append(cdm)

    results = []
    for key_str, group in pair_groups.items():
        # Sort group by CREATED timestamp descending — latest CDM first
        group.sort(key=lambda c: c.get("CREATED", ""), reverse=True)
        latest = group[0]

        cdm_id = str(latest.get("CDM_ID") or latest.get("MESSAGE_ID", ""))
        pc = float(latest.get("PC") or latest.get("COLLISION_PROBABILITY") or 1e-7)

        miss_raw = latest.get("MISS_DISTANCE")
        if miss_raw is None:
            miss_raw = latest.get("MIN_RNG")
        miss = float(miss_raw) if miss_raw is not None else 9999.0

        # Quick risk score without full processing
        risk = score_conjunction(
            latest,
            maneuver={"delta_v_mps": 0},
            satcat_1={"OBJECT_TYPE": latest.get("SAT1_OBJECT_TYPE", "UNKNOWN")},
            satcat_2={"OBJECT_TYPE": latest.get("SAT2_OBJECT_TYPE", "UNKNOWN")},
        )

        # Build Pc evolution history (all CDMs for this pair)
        pc_history = []
        for cdm_item in sorted(group, key=lambda c: c.get("CREATED", "")):
            pc_history.append({
                "cdm_id": str(cdm_item.get("CDM_ID", "")),
                "pc": float(cdm_item.get("PC", 0)),
                "created": cdm_item.get("CREATED", ""),
                "miss_distance": float(cdm_item.get("MISS_DISTANCE") or cdm_item.get("MIN_RNG") or 0),
            })

        results.append({
            "cdm_id": cdm_id,
            "sat1_name": latest.get("SAT_1_NAME", latest.get("SAT1_OBJECT_NAME", "?")),
            "sat2_name": latest.get("SAT_2_NAME", latest.get("SAT2_OBJECT_NAME", "?")),
            "sat1_id": str(latest.get("SAT_1_ID") or latest.get("SAT1_NORAD_CAT_ID") or ""),
            "sat2_id": str(latest.get("SAT_2_ID") or latest.get("SAT2_NORAD_CAT_ID") or ""),
            "sat1_object_type": latest.get("SAT1_OBJECT_TYPE", latest.get("SAT_1_OBJECT_TYPE", "")),
            "sat2_object_type": latest.get("SAT2_OBJECT_TYPE", latest.get("SAT_2_OBJECT_TYPE", "")),
            "tca": latest.get("TCA", ""),
            "miss_distance": miss,
            "pc": pc,
            "risk_score": risk.score,
            "risk_level": risk.level,
            "recommended_action": risk.recommended_action,
            "cdm_count": len(group),
            "pc_history": pc_history,
        })

    # Sort by risk score descending
    results.sort(key=lambda r: r["risk_score"], reverse=True)
    return results


@app.get("/conjunctions/{cdm_id}")
async def conjunction_detail(cdm_id: str):
    """Full detail: CDM + ManeuverSolution + RiskAssessment + AI explanation."""
    # Handle demo conjunction
    if cdm_id == "DEMO-001":
        return get_sample_conjunction()

    try:
        result = await get_cached_conjunction(cdm_id)
    except Exception as exc:
        logger.error("process_conjunction failed for %s: %s", cdm_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    # Risk scoring
    satcat_1 = result.get("satcat_1", {})
    satcat_2 = result.get("satcat_2", {})
    maneuver = result.get("maneuver", {})

    # Add mock covariance dimensions to result
    result["covariance_radii_1"] = [1500.0, 1500.0, 300.0]
    result["covariance_radii_2"] = [1500.0, 1500.0, 300.0]

    risk = score_conjunction(result, maneuver, satcat_1, satcat_2)
    result["risk"] = risk.to_dict()

    # AI explanation
    try:
        explanation = await generate_explanation(
            result, maneuver, risk.to_dict(), satcat_1, satcat_2
        )
        result["explanation"] = explanation
    except Exception as exc:
        logger.error("AI explanation failed: %s", exc)
        result["explanation"] = {
            "situation_summary": "Explanation unavailable.",
            "risk_rationale": "N/A",
            "maneuver_recommendation": "N/A",
            "no_action_scenario": "N/A",
            "operator_urgency": "MONITOR",
        }

    return result


@app.get("/conjunctions/{cdm_id}/pc-history")
async def pc_history(cdm_id: str):
    """Return Pc evolution history for a conjunction pair.

    Reads from the SQLite cache only — no Space-Track calls.
    This avoids the frontend having to fetch the entire conjunction
    list just to get pc_history for one pair.
    """
    fetcher = get_fetcher()

    # Read CDMs from cache (no network)
    import json
    import sqlite3
    from data.fetcher import _init_db

    conn = _init_db(fetcher.db_path)
    try:
        rows = conn.execute("SELECT raw_json FROM cdm_cache").fetchall()
        cdms = [json.loads(r["raw_json"]) for r in rows]
    finally:
        conn.close()

    # Find the target CDM to identify its pair
    target = None
    for c in cdms:
        cid = str(c.get("CDM_ID") or c.get("MESSAGE_ID", ""))
        if cid == cdm_id:
            target = c
            break

    if not target:
        return []

    # Identify the pair
    name1 = target.get("SAT_1_NAME", target.get("SAT1_OBJECT_NAME", "?"))
    name2 = target.get("SAT_2_NAME", target.get("SAT2_OBJECT_NAME", "?"))
    pair_key = tuple(sorted([name1, name2]))

    # Collect all CDMs for this pair
    history = []
    for c in cdms:
        n1 = c.get("SAT_1_NAME", c.get("SAT1_OBJECT_NAME", "?"))
        n2 = c.get("SAT_2_NAME", c.get("SAT2_OBJECT_NAME", "?"))
        if tuple(sorted([n1, n2])) == pair_key:
            history.append({
                "cdm_id": str(c.get("CDM_ID", "")),
                "pc": float(c.get("PC", 0)),
                "created": c.get("CREATED", ""),
                "miss_distance": float(c.get("MISS_DISTANCE") or c.get("MIN_RNG") or 0),
            })

    history.sort(key=lambda h: h["created"])
    return history

@app.get("/conjunctions/{cdm_id}/pc-analysis")
async def pc_analysis(cdm_id: str):
    """
    Independent Pc verification using Foster's method.

    Returns Pc computed from TLE propagation + assumed covariance,
    compared against Space-Track's published value.
    """
    if cdm_id == "DEMO-001":
        return {
            "cdm_id": "DEMO-001",
            "pc_foster": 4.87e-3,
            "pc_spacetrack": 5.24e-3,
            "delta_percent": -7.1,
            "miss_distance_computed": 14.8,
            "miss_distance_cdm": 15.0,
            "miss_distance_agreement": True,
            "hard_body_radius": 2.3,
            "relative_speed": 14250,
            "tle_age_hours": 6.2,
            "covariance_source": "RCS-default (public CDM lacks covariance data)",
            "computation_valid": True,
            "failure_reason": None,
            "interpretation": (
                "Conjunx Foster method result is within 7.1% of "
                "Space-Track official Pc. Difference attributable to "
                "assumed vs actual covariance."
            ),
            "analysis_notes": [
                "TLE age is 6.2h → good orbit accuracy",
                "Covariance modeled from RCS size → not mission-grade tracking uncertainty"
            ],
            "risk_assessment": "HIGH — maneuver likely required",
            "sensitivity_analysis": {
                "base": 4.87e-3,
                "covariance_x2": 6.1e-3,
                "covariance_x0_5": 1.2e-4,
                "curve": [
                    {"scale": 0.1, "pc": 0.0},
                    {"scale": 0.25, "pc": 2.1e-7},
                    {"scale": 0.5, "pc": 1.2e-4},
                    {"scale": 0.75, "pc": 1.8e-3},
                    {"scale": 1.0, "pc": 4.87e-3},
                    {"scale": 1.5, "pc": 5.6e-3},
                    {"scale": 2.0, "pc": 6.1e-3},
                    {"scale": 2.5, "pc": 5.9e-3},
                    {"scale": 3.0, "pc": 5.4e-3},
                    {"scale": 4.0, "pc": 4.2e-3},
                    {"scale": 5.0, "pc": 3.3e-3},
                    {"scale": 8.0, "pc": 1.8e-3}
                ]
            }
        }

    try:
        result = await get_cached_conjunction(cdm_id)
    except Exception as exc:
        logger.error("pc-analysis: process_conjunction failed for %s: %s", cdm_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    ipc = result.get("independent_pc")
    if ipc is None:
        return {
            "cdm_id": cdm_id,
            "computation_valid": False,
            "failure_reason": "Independent Pc computation was not performed",
            "interpretation": "Pc analysis unavailable — computation was not performed.",
            "analysis_notes": [],
            "risk_assessment": "LOW — unlikely to require action",
            "sensitivity_analysis": {},
        }

    # Generate interpretation
    interpretation = _generate_pc_interpretation(ipc)

    return {
        "cdm_id": cdm_id,
        "pc_foster": ipc.get("pc_foster", 0.0),
        "pc_spacetrack": ipc.get("pc_spacetrack", 0.0),
        "delta_percent": ipc.get("delta_percent", 0.0),
        "miss_distance_computed": ipc.get("miss_distance_computed", 0.0),
        "miss_distance_cdm": ipc.get("miss_distance_cdm", 0.0),
        "miss_distance_agreement": ipc.get("miss_distance_agreement", False),
        "hard_body_radius": ipc.get("hard_body_radius", 0.0),
        "relative_speed": ipc.get("relative_speed", 0.0),
        "tle_age_hours": ipc.get("tle_age_hours", 0.0),
        "covariance_source": ipc.get("covariance_source", "RCS-default")
            + " (public CDM lacks covariance data)",
        "computation_valid": ipc.get("computation_valid", False),
        "failure_reason": ipc.get("failure_reason"),
        "interpretation": interpretation,
        "analysis_notes": ipc.get("analysis_notes", []),
        "risk_assessment": ipc.get("risk_assessment", "LOW — unlikely to require action"),
        "sensitivity_analysis": ipc.get("sensitivity_analysis", {}),
    }


def _generate_pc_interpretation(ipc: dict) -> str:
    """Generate a plain-language interpretation of the Pc comparison."""
    if not ipc.get("computation_valid", False):
        reason = ipc.get("failure_reason", "Unknown error")
        return f"Pc analysis could not be completed: {reason}"

    delta = ipc.get("delta_percent", 0.0)
    abs_delta = abs(delta)
    pc_foster = ipc.get("pc_foster", 0.0)
    pc_st = ipc.get("pc_spacetrack", 0.0)

    if pc_st == 0:
        return (
            f"Conjunx Foster method computed Pc = {pc_foster:.2e}. "
            "Space-Track Pc is zero or unavailable — cannot compute delta."
        )

    if abs_delta < 20:
        agreement = "good agreement"
        attribution = "Difference attributable to assumed vs actual covariance."
    elif abs_delta < 50:
        agreement = "moderate agreement"
        attribution = (
            "Difference likely due to covariance assumptions and TLE propagation uncertainty."
        )
    else:
        agreement = "significant disagreement"
        attribution = (
            "Large difference may indicate stale TLEs, maneuver history, "
            "or substantially different covariance data."
        )

    direction = "lower" if delta < 0 else "higher"

    return (
        f"Conjunx Foster method result is within {abs_delta:.1f}% of "
        f"Space-Track official Pc ({direction}). "
        f"This represents {agreement}. {attribution}"
    )

@app.post("/conjunctions/{cdm_id}/maneuver")
async def recompute_maneuver(cdm_id: str, body: ManeuverRequest):
    """Recompute maneuver with custom satellite mass and Isp.

    Uses the cached pipeline result to extract the ConjunctionEvent,
    then re-solves only the maneuver with the new mass/Isp.
    """
    from engine.maneuver import ConjunctionEvent, OrbitalState, solve_conjunction_maneuver
    import numpy as np

    if cdm_id == "DEMO-001":
        sample = get_sample_conjunction()
        event = _build_event_from_dict(sample)
        sol = solve_conjunction_maneuver(
            event, mass_kg=body.satellite_mass_kg, isp=body.isp
        )
        return sol.to_dict()

    try:
        result = await get_cached_conjunction(cdm_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    # Re-solve just the maneuver with new mass/Isp (no full pipeline re-run)
    event = _build_event_from_result(result)
    sol = solve_conjunction_maneuver(
        event, mass_kg=body.satellite_mass_kg, isp=body.isp
    )
    return sol.to_dict()


@app.post("/conjunctions/{cdm_id}/tradeoff")
async def evaluate_tradeoff_endpoint(cdm_id: str, body: TradeoffRequest):
    """Evaluate maneuver tradeoff for an arbitrary delta-V.

    Uses the cached pipeline result so the full pipeline is NOT re-run
    on every slider tick.
    """
    from engine.maneuver import evaluate_tradeoff

    if cdm_id == "DEMO-001":
        sample = get_sample_conjunction()
        event = _build_event_from_dict(sample)
        return evaluate_tradeoff(event, body.delta_v_mps, body.satellite_mass_kg, body.isp)

    try:
        result = await get_cached_conjunction(cdm_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    try:
        event = _build_event_from_result(result)
        tradeoff_result = evaluate_tradeoff(
            event,
            delta_v_mps=body.delta_v_mps,
            mass_kg=body.satellite_mass_kg,
            isp=body.isp
        )

        # Ghost Orbit offset for frontend 3D viz
        tradeoff_result["ghost_offset_m"] = body.delta_v_mps * tradeoff_result.get("effective_time_s", 21600.0)

        return tradeoff_result
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=traceback.format_exc())


@app.get("/conjunctions/{cdm_id}/orbit-data")
async def orbit_data(cdm_id: str):
    """
    Pre-computed ECEF orbit points for Cesium visualization.
    Propagates both satellite TLEs for 95 minutes at 60-second intervals,
    with proper TEME → ECEF frame conversion via GMST rotation.
    """
    import math
    from sgp4.api import Satrec, jday
    from datetime import timedelta

    fetcher = get_fetcher()

    # Get CDM from cache (direct SQLite lookup, no network call)
    cdm = fetcher.get_cached_cdm(cdm_id)
    if cdm is None:
        # Cache miss — fetch CDMs first to populate cache, then retry
        try:
            await fetcher.fetch_cdms()
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to fetch CDMs")
        cdm = fetcher.get_cached_cdm(cdm_id)

    if not cdm:
        raise HTTPException(status_code=404, detail="CDM not found")

    # Extract NORAD IDs and fetch TLEs
    norad_1 = cdm.get("SAT_1_ID") or cdm.get("SAT1_NORAD_CAT_ID")
    norad_2 = cdm.get("SAT_2_ID") or cdm.get("SAT2_NORAD_CAT_ID")
    tca_str = cdm.get("TCA", "")

    tle_map = {}
    for norad in [norad_1, norad_2]:
        if norad:
            try:
                tles = await fetcher.fetch_tles([int(norad)])
                if tles:
                    tle_map[str(norad)] = tles[0]
            except Exception as e:
                logger.error(f"Failed to fetch TLEs for {norad}: {e}")
                pass

    def gmst_rad(jd_ut1: float, jd_frac: float) -> float:
        """Compute Greenwich Mean Sidereal Time in radians from Julian Date."""
        t_ut1 = ((jd_ut1 - 2451545.0) + jd_frac) / 36525.0
        # IAU 1982 formula for GMST in seconds
        gmst_sec = (
            67310.54841
            + (876600.0 * 3600.0 + 8640184.812866) * t_ut1
            + 0.093104 * t_ut1 ** 2
            - 6.2e-6 * t_ut1 ** 3
        )
        # Convert to radians (mod 2π)
        return (gmst_sec % 86400.0) / 86400.0 * 2.0 * math.pi

    def teme_to_ecef(pos_teme_km: tuple, jd: float, fr: float) -> dict:
        """Rotate TEME position to ECEF using R_z(-GMST)."""
        theta = gmst_rad(jd, fr)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        x_t, y_t, z_t = pos_teme_km
        # R_z(-theta) rotation
        x_ecef = x_t * cos_t + y_t * sin_t
        y_ecef = -x_t * sin_t + y_t * cos_t
        z_ecef = z_t
        # Convert km → meters
        return {
            "x": x_ecef * 1000.0,
            "y": y_ecef * 1000.0,
            "z": z_ecef * 1000.0,
        }

    def propagate_ecef(tle_line1: str, tle_line2: str, start: datetime, minutes: int = 95, step_s: int = 30) -> list:
        """Propagate TLE and return ECEF positions."""
        try:
            sat = Satrec.twoline2rv(tle_line1, tle_line2)
        except Exception:
            return []

        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

        points = []
        for i in range(0, minutes * 60 + 1, step_s):
            t = start + timedelta(seconds=i)
            jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute,
                          t.second + t.microsecond / 1e6)
            err, pos_km, vel_kms = sat.sgp4(jd, fr)
            if err == 0:
                ecef = teme_to_ecef(pos_km, jd, fr)
                points.append({
                    "time_iso": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "x_ecef": round(ecef["x"], 1),
                    "y_ecef": round(ecef["y"], 1),
                    "z_ecef": round(ecef["z"], 1),
                })
        return points

    # Parse TCA
    tca_dt = datetime.now(timezone.utc)
    if tca_str:
        try:
            tca_dt = datetime.fromisoformat(tca_str.replace("Z", "+00:00"))
        except Exception:
            pass

    # Start propagation 10 minutes before TCA for context
    prop_start = tca_dt - timedelta(minutes=10)

    result = {
        "tca": tca_str,
        "sat1_name": cdm.get("SAT_1_NAME", cdm.get("SAT1_OBJECT_NAME", "SAT-1")),
        "sat2_name": cdm.get("SAT_2_NAME", cdm.get("SAT2_OBJECT_NAME", "SAT-2")),
        "sat1_track": [],
        "sat2_track": [],
        "tca_position_ecef": None,
    }

    norad_1_str = str(norad_1) if norad_1 else None
    norad_2_str = str(norad_2) if norad_2 else None

    if norad_1_str and norad_1_str in tle_map:
        tle = tle_map[norad_1_str]
        result["sat1_track"] = propagate_ecef(
            tle["TLE_LINE1"], tle["TLE_LINE2"], prop_start
        )
        # Compute TCA position for SAT1
        try:
            sat = Satrec.twoline2rv(tle["TLE_LINE1"], tle["TLE_LINE2"])
            jd, fr = jday(tca_dt.year, tca_dt.month, tca_dt.day,
                          tca_dt.hour, tca_dt.minute,
                          tca_dt.second + tca_dt.microsecond / 1e6)
            err, pos_km, _ = sat.sgp4(jd, fr)
            if err == 0:
                result["tca_position_ecef"] = teme_to_ecef(pos_km, jd, fr)
        except Exception:
            pass

    if norad_2_str and norad_2_str in tle_map:
        tle = tle_map[norad_2_str]
        result["sat2_track"] = propagate_ecef(
            tle["TLE_LINE1"], tle["TLE_LINE2"], prop_start
        )
        # Compute TCA position for SAT2
        try:
            sat = Satrec.twoline2rv(tle["TLE_LINE1"], tle["TLE_LINE2"])
            jd, fr = jday(tca_dt.year, tca_dt.month, tca_dt.day,
                          tca_dt.hour, tca_dt.minute,
                          tca_dt.second + tca_dt.microsecond / 1e6)
            err, pos_km, _ = sat.sgp4(jd, fr)
            if err == 0:
                result["sat2_tca_position_ecef"] = teme_to_ecef(pos_km, jd, fr)
        except Exception:
            pass

    return result

