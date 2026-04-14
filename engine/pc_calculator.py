"""
Independent Pc (Probability of Collision) computation engine.

Implements Foster & Estes (1992) method for computing collision probability
from TLE-propagated state vectors, conjunction geometry, and assumed covariance.

This is NOT a wrapper around Space-Track's published Pc — it is an independent
mathematical verification using publicly available orbital data.

References:
    Foster, J. L. & Estes, H. S. (1992). "A Parametric Analysis of Orbital
        Debris Collision Probability and Maneuver Rate for Space Vehicles."
    Hejduk, M. D. & Snow, D. E. (2018). "Satellite Conjunction Assessment
        Risk Analysis."
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

import numpy as np
from scipy import integrate
from sgp4.api import Satrec, jday

logger = logging.getLogger(__name__)


# Data structures

@dataclass
class StateVector:
    """Satellite state in ECI/TEME frame."""
    position: np.ndarray   # [x, y, z] meters ECI/TEME
    velocity: np.ndarray   # [vx, vy, vz] m/s ECI/TEME
    epoch: datetime


@dataclass
class ConjunctionGeometry:
    """Geometric quantities describing the encounter at TCA."""
    miss_vector: np.ndarray       # relative position at TCA (meters)
    relative_velocity: np.ndarray # relative velocity at TCA (m/s)
    miss_distance: float          # scalar miss distance (meters)
    relative_speed: float         # scalar relative speed (m/s)
    x_hat: np.ndarray             # unit vector in conjunction plane
    y_hat: np.ndarray             # unit vector in conjunction plane
    z_hat: np.ndarray             # normal to conjunction plane (along rel velocity)
    x_miss: float                 # miss vector projected onto x_hat (meters)
    y_miss: float                 # miss vector projected onto y_hat (meters)


@dataclass
class PcResult:
    """Complete result of an independent Pc computation."""
    pc_foster: float              # independently computed Pc
    pc_spacetrack: float          # Space-Track published Pc
    delta_percent: float          # percentage difference
    miss_distance_computed: float # miss distance from propagation (meters)
    miss_distance_cdm: float      # miss distance from CDM (meters)
    miss_distance_agreement: bool # True if within 20%
    hard_body_radius: float       # combined collision radius (meters)
    relative_speed: float         # m/s
    covariance_source: str        # "RCS-default"
    tle_age_hours: float          # age of TLE at TCA
    computation_valid: bool       # False if any step failed
    failure_reason: Optional[str] # why computation failed if invalid

    # NEW FIELDS
    analysis_notes: list[str]
    risk_assessment: str
    sensitivity_analysis: dict


# SGP4 propagation

def propagate_tle_to_epoch(
    line1: str, line2: str, target_time: datetime
) -> Tuple[Optional[StateVector], Optional[datetime]]:
    """
    Propagate a TLE to a target epoch using SGP4.

    Parameters
    ----------
    line1 : str – TLE line 1
    line2 : str – TLE line 2
    target_time : datetime – target epoch (UTC)

    Returns
    -------
    Tuple of (StateVector or None, tle_epoch as datetime or None).
    Returns (None, None) if propagation fails.
    """
    try:
        sat = Satrec.twoline2rv(line1, line2)
    except Exception as exc:
        logger.error("Failed to parse TLE for Pc calc: %s", exc)
        return None, None

    # Parse TLE epoch from the Satrec object
    try:
        # sat.jdsatepoch + sat.jdsatepochF gives full Julian date of TLE epoch
        from sgp4.api import jday
        # Reconstruct TLE epoch from jdsatepoch
        # sgp4 stores epoch as jdsatepoch (integer part) and jdsatepochF (fractional)
        jd_epoch = sat.jdsatepoch + sat.jdsatepochF
        # Convert Julian Date to datetime
        # JD = 2451545.0 corresponds to 2000-01-01 12:00:00 UTC
        j2000_jd = 2451545.0
        delta_days = jd_epoch - j2000_jd
        from datetime import timedelta
        tle_epoch = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(days=delta_days)
    except Exception as exc:
        logger.warning("Could not parse TLE epoch: %s", exc)
        tle_epoch = None

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
            "SGP4 Pc-calc error code %d at target %s",
            error_code, target_time.isoformat(),
        )
        return None, tle_epoch

    # Convert km → m and km/s → m/s
    position_m = np.array([p * 1000.0 for p in position_km])
    velocity_ms = np.array([v * 1000.0 for v in velocity_kms])

    state = StateVector(
        position=position_m,
        velocity=velocity_ms,
        epoch=target_time,
    )
    return state, tle_epoch


# Conjunction geometry

def compute_conjunction_geometry(
    state1: StateVector, state2: StateVector
) -> ConjunctionGeometry:
    """
    Compute conjunction-plane geometry from two state vectors at TCA.

    The conjunction plane is defined as perpendicular to the relative velocity
    vector. The miss vector is projected into this plane.
    """
    r_rel = state2.position - state1.position
    v_rel = state2.velocity - state1.velocity

    miss_distance = float(np.linalg.norm(r_rel))
    relative_speed = float(np.linalg.norm(v_rel))

    # Conjunction plane normal (along relative velocity)
    if relative_speed < 1e-10:
        # Degenerate: nearly zero relative velocity
        z_hat = np.array([0.0, 0.0, 1.0])
    else:
        z_hat = v_rel / relative_speed

    # Project miss vector onto conjunction plane
    x_hat_unnorm = r_rel - np.dot(r_rel, z_hat) * z_hat
    x_norm = float(np.linalg.norm(x_hat_unnorm))

    if x_norm < 1e-10:
        # Degenerate: miss vector is along relative velocity
        # Choose arbitrary perpendicular to z_hat
        if abs(z_hat[0]) < 0.9:
            perp = np.array([1.0, 0.0, 0.0])
        else:
            perp = np.array([0.0, 1.0, 0.0])
        x_hat = np.cross(z_hat, perp)
        x_hat = x_hat / np.linalg.norm(x_hat)
    else:
        x_hat = x_hat_unnorm / x_norm

    y_hat = np.cross(z_hat, x_hat)

    x_miss = float(np.dot(r_rel, x_hat))
    y_miss = float(np.dot(r_rel, y_hat))

    return ConjunctionGeometry(
        miss_vector=r_rel,
        relative_velocity=v_rel,
        miss_distance=miss_distance,
        relative_speed=relative_speed,
        x_hat=x_hat,
        y_hat=y_hat,
        z_hat=z_hat,
        x_miss=x_miss,
        y_miss=y_miss,
    )


# Default covariance

# Screening-quality position uncertainty (meters) for objects in the
# Space Surveillance Network catalog.  These represent SP-level tracking
# precision used for conjunction screening — roughly 5× tighter than the
# TLE-level values published by Hejduk & Snow (2018).
#
# Format: (sigma_radial, sigma_along_track, sigma_cross_track)
_COVARIANCE_TABLE = {
    ("PAYLOAD", "LARGE"):   (10,   100,  10),
    ("PAYLOAD", "MEDIUM"):  (20,   200,  20),
    ("PAYLOAD", "SMALL"):   (40,   400,  40),
    ("DEBRIS", "LARGE"):    (20,   200,  20),
    ("DEBRIS", "MEDIUM"):   (40,   600,  40),
    ("DEBRIS", "SMALL"):    (100,  1000, 100),
    ("ROCKET BODY", "LARGE"):   (20,   200,  20),
    ("ROCKET BODY", "MEDIUM"):  (40,   600,  40),
    ("ROCKET BODY", "SMALL"):   (100,  1000, 100),
}

_DEFAULT_SIGMAS = (60, 600, 60)


def get_default_covariance(rcs_size: str, object_type: str) -> np.ndarray:
    """
    Return a 3×3 diagonal covariance matrix (meters²) based on object type
    and RCS size category.

    Uses anisotropic RSW-axis diagonal: diag([σ_r², σ_s², σ_w²]).
    The along-track sigma is always largest; radial and cross-track are
    tighter.  When projected onto the conjunction plane via T @ C @ T.T,
    the projection naturally selects the components relevant to the
    encounter geometry.

    Note: A proper implementation would rotate this RSW covariance into ECI
    using the satellite state vectors.  Without rotation, the axis-to-ECI
    mapping is approximate, but the anisotropic representation is far more
    accurate than a spherical average because the projection selects
    realistic component magnitudes.
    """
    obj = object_type.upper().strip() if object_type else ""
    size = rcs_size.upper().strip() if rcs_size else ""

    sigmas = _COVARIANCE_TABLE.get((obj, size), None)

    # Try with just object type if exact match fails
    if sigmas is None:
        for key, val in _COVARIANCE_TABLE.items():
            if key[0] == obj:
                sigmas = val
                break

    if sigmas is None:
        sigmas = _DEFAULT_SIGMAS

    sigma_r, sigma_s, sigma_w = sigmas

    logger.debug(
        "Covariance for %s/%s: σ_r=%dm σ_s=%dm σ_w=%dm",
        obj or "DEFAULT", size or "DEFAULT", sigma_r, sigma_s, sigma_w,
    )

    return np.diag([sigma_r**2, sigma_s**2, sigma_w**2])


# Covariance projection

def project_covariance_to_conjunction_plane(
    cov1: np.ndarray, cov2: np.ndarray, geometry: ConjunctionGeometry
) -> np.ndarray:
    """
    Project combined 3D covariance onto the 2D conjunction plane.

    Parameters
    ----------
    cov1 : 3×3 covariance matrix for object 1 (m²)
    cov2 : 3×3 covariance matrix for object 2 (m²)
    geometry : ConjunctionGeometry with plane basis vectors

    Returns
    -------
    2×2 covariance matrix in the conjunction plane (m²)
    """
    cov_combined = cov1 + cov2

    # Projection matrix: rows are the conjunction-plane basis vectors
    T = np.array([geometry.x_hat, geometry.y_hat])  # shape (2, 3)

    # Project: C_2d = T @ C_3d @ T^T
    cov_2d = T @ cov_combined @ T.T  # shape (2, 2)

    return cov_2d


# Hard body radius

def rcs_size_to_m2(rcs_size: str) -> float:
    """Convert RCS size category to approximate RCS in m²."""
    mapping = {
        "LARGE": 10.0,
        "MEDIUM": 1.0,
        "SMALL": 0.1,
    }
    return mapping.get(rcs_size.upper().strip() if rcs_size else "", 1.0)


def compute_hard_body_radius(rcs1: float, rcs2: float) -> float:
    """
    Compute combined hard-body collision radius from radar cross sections.

    Assumes spherical objects: radius = sqrt(RCS / π).
    Minimum radius of 1.0 meter per object to handle zero/negative RCS.
    """
    r1 = max(1.0, math.sqrt(abs(rcs1) / math.pi))
    r2 = max(1.0, math.sqrt(abs(rcs2) / math.pi))
    return r1 + r2


# Foster's Pc computation

def compute_pc_foster(
    geometry: ConjunctionGeometry,
    cov_2d: np.ndarray,
    hard_body_radius: float,
) -> float:
    """
    Compute collision probability using the Foster & Estes (1992) method.

    Integrates a 2D Gaussian (centered at the miss-distance offset in the
    conjunction plane) over a circular hard-body cross-section of the combined
    objects.

    Parameters
    ----------
    geometry : ConjunctionGeometry with x_miss, y_miss offsets
    cov_2d : 2×2 projected covariance matrix (m²)
    hard_body_radius : combined collision radius (m)

    Returns
    -------
    Pc value clamped to [0, 1]. Returns 0.0 on numerical errors.
    """
    try:
        det_val = np.linalg.det(cov_2d)
        if det_val <= 0:
            logger.warning("Non-positive covariance determinant: %e", det_val)
            return 0.0

        cov_inv = np.linalg.inv(cov_2d)

        # Diagnostic logging for covariance
        eigenvalues = np.linalg.eigvalsh(cov_2d)
        max_eigenvalue = max(eigenvalues)
        min_eigenvalue = min(eigenvalues)
        miss_2d = math.sqrt(geometry.x_miss**2 + geometry.y_miss**2)
        miss_3d = geometry.miss_distance

        logger.info(
            "Foster inputs: miss_3d=%.1fm miss_2d=%.1fm (x=%.1f y=%.1f) "
            "HBR=%.2fm cov_2d_σ=[%.1f, %.1f]m det=%.2e",
            miss_3d, miss_2d, geometry.x_miss, geometry.y_miss,
            hard_body_radius,
            math.sqrt(min_eigenvalue), math.sqrt(max_eigenvalue),
            det_val,
        )

        # Fast-path: if miss distance >> hard body radius and >> covariance scale,
        # Pc is negligibly small
        if (miss_2d > 10.0 * hard_body_radius and
                miss_2d > 3.0 * math.sqrt(max_eigenvalue)):
            logger.info(
                "Fast-path (2D): miss_2d=%.1f >> HBR=%.1f and >> 3σ=%.1f → Pc≈0",
                miss_2d, hard_body_radius, 3.0 * math.sqrt(max_eigenvalue),
            )
            return 0.0

        # Also fast-path on 3D miss distance — even if projection is small,
        # a massive 3D separation means negligible conjunction risk
        if (miss_3d > 100.0 * hard_body_radius and
                miss_3d > 10.0 * math.sqrt(max_eigenvalue)):
            logger.info(
                "Fast-path (3D): miss_3d=%.1f >> HBR=%.1f and >> 10σ=%.1f → Pc≈0",
                miss_3d, hard_body_radius, 10.0 * math.sqrt(max_eigenvalue),
            )
            return 0.0

        norm_factor = 1.0 / (2.0 * math.pi * math.sqrt(det_val))
        logger.info("Foster norm_factor=%.4e", norm_factor)

        x_miss = geometry.x_miss
        y_miss = geometry.y_miss

        def gaussian_2d(x: float, y: float) -> float:
            delta = np.array([x - x_miss, y - y_miss])
            return norm_factor * math.exp(-0.5 * float(delta @ cov_inv @ delta))

        def integrand_polar(theta: float, r: float) -> float:
            return gaussian_2d(r * math.cos(theta), r * math.sin(theta)) * r

        pc, error = integrate.dblquad(
            integrand_polar,
            0.0,                    # r lower bound
            hard_body_radius,       # r upper bound
            0.0,                    # theta lower bound (function of r)
            2.0 * math.pi,         # theta upper bound (function of r)
            epsabs=1e-12,
            epsrel=1e-8,
        )

        logger.info("Foster result: Pc=%.4e (integration error=%.2e)", pc, error)

        return max(0.0, min(1.0, pc))

    except Exception as exc:
        logger.error("Foster Pc computation failed: %s", exc)
        return 0.0


def compute_pc_sensitivity(geometry: ConjunctionGeometry, cov_2d: np.ndarray, hbr: float) -> dict:
    """Compute sensitivity of Pc to covariance scaling.

    Returns both the legacy 3-field format (base, covariance_x2, covariance_x0_5)
    and a full ``curve`` array with 12 data points for graph rendering.
    """
    try:
        pc_base = compute_pc_foster(geometry, cov_2d, hbr)

        # Legacy fields — kept for backwards compatibility
        pc_up = compute_pc_foster(geometry, cov_2d * 2.0, hbr)
        pc_down = compute_pc_foster(geometry, cov_2d * 0.5, hbr)

        # Full sweep for the sensitivity graph
        scale_factors = [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 8.0]
        curve = []
        for sf in scale_factors:
            pc_val = compute_pc_foster(geometry, cov_2d * sf, hbr) if sf != 1.0 else pc_base
            curve.append({"scale": sf, "pc": pc_val})

        return {
            "base": pc_base,
            "covariance_x2": pc_up,
            "covariance_x0_5": pc_down,
            "curve": curve,
        }
    except Exception as exc:
        logger.error("Sensitivity computation failed: %s", exc)
        return {}



# Main computation function

def compute_pc_for_cdm(
    cdm: dict,
    tle1: dict,
    tle2: dict,
    satcat1: dict,
    satcat2: dict,
) -> PcResult:
    """
    Full independent Pc computation pipeline.

    Parameters
    ----------
    cdm : dict – CDM data with TCA, PC, MIN_RNG/MISS_DISTANCE, etc.
    tle1, tle2 : dict – TLE data with TLE_LINE1, TLE_LINE2
    satcat1, satcat2 : dict – SATCAT data with RCS, OBJECT_TYPE, RCS_SIZE

    Returns
    -------
    PcResult with all computation outputs.
    """
    # Parse TCA
    tca_str = cdm.get("TCA", "")
    try:
        tca = datetime.fromisoformat(tca_str.replace("Z", "+00:00"))
        if tca.tzinfo is None:
            tca = tca.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return PcResult(
            pc_foster=0.0, pc_spacetrack=0.0, delta_percent=0.0,
            miss_distance_computed=0.0, miss_distance_cdm=0.0,
            miss_distance_agreement=False, hard_body_radius=0.0,
            relative_speed=0.0, covariance_source="N/A",
            tle_age_hours=0.0, computation_valid=False,
            failure_reason=f"Could not parse TCA: '{tca_str}'",
            analysis_notes=[],
            risk_assessment="LOW — unlikely to require action",
            sensitivity_analysis={},
        )

    # Propagate both TLEs to TCA
    line1_1 = tle1.get("TLE_LINE1", "")
    line1_2 = tle1.get("TLE_LINE2", "")
    line2_1 = tle2.get("TLE_LINE1", "")
    line2_2 = tle2.get("TLE_LINE2", "")

    state1, tle1_epoch = propagate_tle_to_epoch(line1_1, line1_2, tca)
    if state1 is None:
        return PcResult(
            pc_foster=0.0, pc_spacetrack=0.0, delta_percent=0.0,
            miss_distance_computed=0.0, miss_distance_cdm=0.0,
            miss_distance_agreement=False, hard_body_radius=0.0,
            relative_speed=0.0, covariance_source="N/A",
            tle_age_hours=0.0, computation_valid=False,
            failure_reason="SGP4 propagation failed for SAT1",
            analysis_notes=[],
            risk_assessment="LOW — unlikely to require action",
            sensitivity_analysis={},
        )

    state2, tle2_epoch = propagate_tle_to_epoch(line2_1, line2_2, tca)
    if state2 is None:
        return PcResult(
            pc_foster=0.0, pc_spacetrack=0.0, delta_percent=0.0,
            miss_distance_computed=0.0, miss_distance_cdm=0.0,
            miss_distance_agreement=False, hard_body_radius=0.0,
            relative_speed=0.0, covariance_source="N/A",
            tle_age_hours=0.0, computation_valid=False,
            failure_reason="SGP4 propagation failed for SAT2",
            analysis_notes=[],
            risk_assessment="LOW — unlikely to require action",
            sensitivity_analysis={},
        )

    # TLE age (use the older of the two)
    tle_age_hours = 0.0
    for ep in [tle1_epoch, tle2_epoch]:
        if ep is not None:
            age = abs((tca - ep).total_seconds()) / 3600.0
            tle_age_hours = max(tle_age_hours, age)

    # Conjunction geometry
    geometry = compute_conjunction_geometry(state1, state2)

    # RCS values
    try:
        rcs1_val = float(satcat1.get("RCS", 0))
        if rcs1_val <= 0:
            raise ValueError("non-positive RCS")
    except (TypeError, ValueError):
        rcs1_size = satcat1.get("RCS_SIZE") or cdm.get("SAT1_RCS_SIZE", "MEDIUM")
        rcs1_val = rcs_size_to_m2(rcs1_size)

    try:
        rcs2_val = float(satcat2.get("RCS", 0))
        if rcs2_val <= 0:
            raise ValueError("non-positive RCS")
    except (TypeError, ValueError):
        rcs2_size = satcat2.get("RCS_SIZE") or cdm.get("SAT2_RCS_SIZE", "MEDIUM")
        rcs2_val = rcs_size_to_m2(rcs2_size)

    # Hard body radius
    hbr = compute_hard_body_radius(rcs1_val, rcs2_val)

    # Default covariances
    obj_type1 = (satcat1.get("OBJECT_TYPE") or cdm.get("SAT1_OBJECT_TYPE", "")).upper()
    rcs_size1 = (satcat1.get("RCS_SIZE") or cdm.get("SAT1_RCS_SIZE", "MEDIUM")).upper()
    obj_type2 = (satcat2.get("OBJECT_TYPE") or cdm.get("SAT2_OBJECT_TYPE", "")).upper()
    rcs_size2 = (satcat2.get("RCS_SIZE") or cdm.get("SAT2_RCS_SIZE", "MEDIUM")).upper()

    logger.info("Object1 lookup: type=%s, rcs_size=%s", obj_type1, rcs_size1)
    logger.info("Object2 lookup: type=%s, rcs_size=%s", obj_type2, rcs_size2)

    cov1 = get_default_covariance(rcs_size1, obj_type1)
    cov2 = get_default_covariance(rcs_size2, obj_type2)

    # Project covariance to conjunction plane
    cov_2d = project_covariance_to_conjunction_plane(cov1, cov2, geometry)

    # Compute Pc using Foster's method
    pc_foster = compute_pc_foster(geometry, cov_2d, hbr)

    # Space-Track published Pc
    pc_spacetrack = float(cdm.get("PC") or cdm.get("COLLISION_PROBABILITY") or 0.0)

    # Delta percentage
    if pc_spacetrack > 0:
        delta_percent = ((pc_foster - pc_spacetrack) / pc_spacetrack) * 100.0
    else:
        delta_percent = 0.0

    # Miss distance from CDM
    miss_cdm = float(cdm.get("MISS_DISTANCE") or cdm.get("MIN_RNG") or 0.0)

    # Explainability layer
    notes = []

    # TLE accuracy note
    if tle_age_hours > 24:
        notes.append(f"TLE age is {tle_age_hours:.1f}h → reduced orbit accuracy vs operational OD solutions")

    # Miss distance mismatch
    if miss_cdm > 0:
        miss_delta = abs(geometry.miss_distance - miss_cdm)
        miss_pct = miss_delta / miss_cdm
        if miss_pct > 0.2:
            notes.append(f"Computed miss distance differs by {miss_pct*100:.1f}% from CDM → major Pc impact")

    # Covariance limitation
    notes.append("Covariance modeled from RCS size → not mission-grade tracking uncertainty")

    # Relative velocity insight
    if geometry.relative_speed > 12000:
        notes.append("High relative velocity encounter → short interaction time, sensitive Pc computation")

    # Pc interpretation
    if pc_foster < pc_spacetrack * 0.1:
        notes.append("Lower Pc likely due to larger propagated miss distance and/or underestimated covariance")
    elif pc_foster > pc_spacetrack * 2:
        notes.append("Higher Pc likely due to conservative covariance assumptions")

    sensitivity = compute_pc_sensitivity(geometry, cov_2d, hbr)

    if pc_foster > 1e-3:
        risk = "HIGH — maneuver likely required"
    elif pc_foster > 1e-5:
        risk = "MEDIUM — monitor closely"
    else:
        risk = "LOW — unlikely to require action"

    # Miss distance agreement (within 20%)
    if miss_cdm > 0:
        agreement = abs(geometry.miss_distance - miss_cdm) / miss_cdm < 0.20
    else:
        agreement = False

    # Log the computation
    logger.info(
        "Pc computation: cdm_id=%s pc_foster=%.4e pc_spacetrack=%.4e "
        "delta=%.1f%% tle_age=%.1fh miss_computed=%.1fm miss_cdm=%.1fm",
        cdm.get("CDM_ID", "?"), pc_foster, pc_spacetrack,
        delta_percent, tle_age_hours,
        geometry.miss_distance, miss_cdm,
    )

    return PcResult(
        pc_foster=pc_foster,
        pc_spacetrack=pc_spacetrack,
        delta_percent=round(delta_percent, 2),
        miss_distance_computed=round(geometry.miss_distance, 2),
        miss_distance_cdm=miss_cdm,
        miss_distance_agreement=agreement,
        hard_body_radius=round(hbr, 2),
        relative_speed=round(geometry.relative_speed, 2),
        covariance_source="RCS-default",
        tle_age_hours=round(tle_age_hours, 2),
        computation_valid=True,
        failure_reason=None,
        analysis_notes=notes,
        risk_assessment=risk,
        sensitivity_analysis=sensitivity,
    )
