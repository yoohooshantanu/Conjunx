"""
Conjunction maneuver decision engine.

Dataclasses for orbital state, conjunction events, and maneuver solutions.
Implements a simple avoidance-burn solver with Tsiolkovsky fuel estimation.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Dataclasses

@dataclass
class OrbitalState:
    """ECI position (m) and velocity (m/s) at a given epoch."""
    position_eci: list[float]   # [x, y, z] in meters
    velocity_eci: list[float]   # [vx, vy, vz] in m/s
    epoch: datetime

    def speed(self) -> float:
        return float(np.linalg.norm(self.velocity_eci))

    def altitude_km(self) -> float:
        """Approximate altitude above Earth's surface (km)."""
        r = float(np.linalg.norm(self.position_eci))
        return (r - 6_371_000.0) / 1_000.0


@dataclass
class ConjunctionEvent:
    """All data needed to evaluate a conjunction and plan a maneuver."""
    tca: datetime                               # Time of closest approach
    miss_distance: float                        # meters
    pc: float                                   # Collision probability
    combined_covariance: np.ndarray             # 3×3 position covariance (m²)
    primary: OrbitalState                       # Maneuverable object
    secondary: Optional[OrbitalState] = None    # Other object (may be None)


@dataclass
class ManeuverSolution:
    """Result of the maneuver computation."""
    delta_v_mps: float              # Required ΔV in m/s
    delta_v_direction: list[float]  # Unit vector in ECI [x, y, z]
    burn_duration_s: float          # Burn duration in seconds
    burn_time: datetime             # When to execute the burn
    fuel_cost_kg: float             # Propellant mass (kg)
    pc_before: float                # Pc before maneuver
    pc_after: float                 # Estimated Pc after maneuver
    maneuver_feasible: bool         # Whether the maneuver is achievable
    reason: str                     # Human-readable summary
    target_miss_distance_m: float   # Post-maneuver miss distance

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat() + "Z"
            elif isinstance(v, (list, float, int, bool, str)):
                d[k] = v
            else:
                d[k] = str(v)
        return d


# Constants

MU_EARTH = 3.986004418e14  # m³/s² — Earth gravitational parameter
R_EARTH = 6_371_000.0      # m
DEFAULT_MASS_KG = 500.0
DEFAULT_ISP = 220.0         # s — hall thruster / monoprop
G0 = 9.80665                # m/s²


# Solver

def _required_delta_v(miss_distance: float, target_miss: float,
                      velocity: float, time_to_tca_s: float) -> float:
    """
    Estimate ΔV needed to shift the miss distance from current to target.

    Uses the linear mapping:  Δmiss ≈ ΔV × time_to_tca  (for small burns
    applied along-track well before TCA).
    """
    delta_miss = target_miss - miss_distance
    if time_to_tca_s <= 0:
        return abs(delta_miss) / max(velocity, 1.0)
    # Mapping radial miss distance approximation from along-track drift.
    # We use empirical LEO geometric mapping ~ (delta_v * t_tca * 100) / velocity
    return abs(delta_miss) / (time_to_tca_s * (max(velocity, 1.0) / 100.0))


def _estimate_pc_after(pc_before: float, miss_before: float,
                       miss_after: float,
                       covariance: np.ndarray) -> float:
    """
    Rough Pc scaling using the Alfano / Foster short-encounter model.

    Pc ∝ exp(-d² / 2σ²).  We scale based on miss distance change.
    """
    sigma_sq = float(np.mean(np.diag(covariance)))
    if sigma_sq <= 0:
        sigma_sq = 500.0 ** 2

    ratio = math.exp(
        -(miss_after ** 2 - miss_before ** 2) / (2.0 * sigma_sq)
    )
    pc_after = pc_before * ratio
    return max(pc_after, 1e-12)  # floor


def _fuel_cost(delta_v: float, mass_kg: float, isp: float) -> float:
    """Tsiolkovsky rocket equation: m_fuel = m0 × (1 - exp(-ΔV / (Isp × g0)))."""
    delta_v = abs(delta_v)
    if delta_v == 0.0:
        return 0.0
    return mass_kg * (1.0 - math.exp(-delta_v / (isp * G0)))


def _burn_direction(primary: OrbitalState) -> list[float]:
    """
    Default burn direction: along-track (velocity direction).
    Along-track burns are most efficient for miss-distance changes.
    """
    v = np.array(primary.velocity_eci, dtype=float)
    norm = np.linalg.norm(v)
    if norm < 1e-10:
        return [1.0, 0.0, 0.0]
    return (v / norm).tolist()


def solve_conjunction_maneuver(
    event: ConjunctionEvent,
    mass_kg: float = DEFAULT_MASS_KG,
    isp: float = DEFAULT_ISP,
    burn_lead_hours: float = 6.0,
) -> ManeuverSolution:
    """
    Compute an avoidance maneuver for a conjunction event.

    Strategy: along-track burn applied `burn_lead_hours` before TCA to at
    least double the current miss distance (or reach 1 km minimum).

    Parameters
    ----------
    event : ConjunctionEvent
    mass_kg : float – spacecraft wet mass (kg)
    isp : float – specific impulse (s)
    burn_lead_hours : float – how many hours before TCA to execute

    Returns
    -------
    ManeuverSolution
    """
    now = datetime.now(timezone.utc)
    # Ensure event.tca is also timezone-aware
    tca = event.tca
    if tca.tzinfo is None:
        tca = tca.replace(tzinfo=timezone.utc)
    time_to_tca_s = max((tca - now).total_seconds(), 1.0)

    # Target miss distance: at least double current, minimum 1 km
    target_miss = max(event.miss_distance * 2.0, 1_000.0)

    # Burn time
    burn_lead_s = burn_lead_hours * 3600.0
    burn_epoch = event.tca
    if time_to_tca_s > burn_lead_s:
        from datetime import timedelta
        burn_epoch = event.tca - timedelta(seconds=burn_lead_s)
        effective_time = burn_lead_s
    else:
        # Not enough time — burn ASAP
        effective_time = time_to_tca_s
        burn_epoch = now

    velocity = event.primary.speed() if event.primary else 7_500.0

    dv = _required_delta_v(
        event.miss_distance, target_miss, velocity, effective_time
    )

    # Sanity cap: if ΔV > 10 m/s the scenario is extreme
    feasible = dv <= 10.0
    if not feasible:
        dv = min(dv, 10.0)

    fuel = _fuel_cost(dv, mass_kg, isp)
    direction = _burn_direction(event.primary) if event.primary else [1, 0, 0]

    # Thrust acceleration for burn duration (assuming 1 N per kg thrust-to-weight)
    thrust_N = mass_kg * 0.01  # 10 mN/kg — low-thrust approximation
    burn_duration = dv * mass_kg / max(thrust_N, 0.01)

    pc_after = _estimate_pc_after(
        event.pc, event.miss_distance, target_miss, event.combined_covariance
    )

    reason_parts = []
    if feasible:
        reason_parts.append(
            f"Along-track burn of {dv:.4f} m/s to increase miss distance "
            f"from {event.miss_distance:.0f} m to {target_miss:.0f} m."
        )
        reason_parts.append(
            f"Fuel cost: {fuel:.2f} kg.  Pc reduction: "
            f"{event.pc:.2e} → {pc_after:.2e}."
        )
    else:
        reason_parts.append(
            f"ΔV of {dv:.4f} m/s exceeds practical limits; maneuver may "
            f"not be feasible with current propulsion."
        )

    return ManeuverSolution(
        delta_v_mps=round(dv, 6),
        delta_v_direction=[round(d, 6) for d in direction],
        burn_duration_s=round(burn_duration, 2),
        burn_time=burn_epoch,
        fuel_cost_kg=round(fuel, 4),
        pc_before=event.pc,
        pc_after=pc_after,
        maneuver_feasible=feasible,
        reason=" ".join(reason_parts),
        target_miss_distance_m=round(target_miss, 1),
    )


def evaluate_tradeoff(
    event: ConjunctionEvent,
    delta_v_mps: float,
    mass_kg: float = DEFAULT_MASS_KG,
    isp: float = DEFAULT_ISP,
    burn_lead_hours: float = 6.0,
) -> dict:
    """
    Evaluate the result of a specific requested ΔV maneuver.
    Inverts the solver to return the resulting miss distance and Pc.
    """
    now = datetime.now(timezone.utc)
    tca = event.tca
    if tca.tzinfo is None:
        tca = tca.replace(tzinfo=timezone.utc)
    time_to_tca_s = max((tca - now).total_seconds(), 1.0)
    
    burn_lead_s = burn_lead_hours * 3600.0
    effective_time = min(time_to_tca_s, burn_lead_s)
    
    # Delta-V to Delta-Miss mapping (linear approximation)
    velocity = event.primary.speed() if event.primary else 7_500.0
    delta_miss = delta_v_mps * effective_time * (max(velocity, 1.0) / 100.0) ** -1
    # Assume we always thrust optimally to increase miss distance
    new_miss_distance = event.miss_distance + delta_miss
    
    new_pc = _estimate_pc_after(
        event.pc, event.miss_distance, new_miss_distance, event.combined_covariance
    )
    
    fuel = _fuel_cost(delta_v_mps, mass_kg, isp)
    
    feasible = delta_v_mps <= 10.0
    
    return {
        "delta_v_mps": delta_v_mps,
        "new_miss_distance_m": round(new_miss_distance, 1),
        "new_pc": new_pc,
        "fuel_cost_kg": round(fuel, 4),
        "feasible": feasible,
        "effective_time_s": effective_time
    }
