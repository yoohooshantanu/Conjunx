"""
Tests for engine/pc_calculator.py — the Foster Pc computation pipeline.

Covers:
  - Conjunction geometry computation
  - RSW-to-ECI rotation matrix properties
  - Covariance lookup and rotation
  - Covariance projection to conjunction plane
  - Foster Pc integration (known-answer and fast-path)
  - Sensitivity sweep
"""

import math
import numpy as np
import pytest

from engine.pc_calculator import (
    StateVector,
    ConjunctionGeometry,
    compute_conjunction_geometry,
    rsw_to_eci_rotation,
    get_default_covariance,
    get_default_covariance_rsw,
    project_covariance_to_conjunction_plane,
    compute_pc_foster,
    compute_pc_sensitivity,
    compute_hard_body_radius,
    rcs_size_to_m2,
)
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(pos, vel):
    """Create a StateVector from lists."""
    return StateVector(
        position=np.array(pos, dtype=float),
        velocity=np.array(vel, dtype=float),
        epoch=datetime(2025, 6, 1, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# compute_conjunction_geometry
# ---------------------------------------------------------------------------

class TestConjunctionGeometry:
    def test_miss_distance_correct(self):
        """Miss distance should equal |r2 - r1|."""
        s1 = _make_state([7_000_000, 0, 0], [0, 7500, 0])
        s2 = _make_state([7_000_100, 0, 0], [0, -7500, 0])
        geom = compute_conjunction_geometry(s1, s2)
        assert abs(geom.miss_distance - 100.0) < 0.01

    def test_basis_vectors_orthogonal(self):
        """x_hat, y_hat, z_hat must form an orthonormal basis."""
        s1 = _make_state([7_000_000, 0, 0], [0, 7500, 0])
        s2 = _make_state([7_000_500, 200, 0], [100, -7400, 100])
        geom = compute_conjunction_geometry(s1, s2)

        assert abs(np.dot(geom.x_hat, geom.y_hat)) < 1e-10
        assert abs(np.dot(geom.x_hat, geom.z_hat)) < 1e-10
        assert abs(np.dot(geom.y_hat, geom.z_hat)) < 1e-10
        assert abs(np.linalg.norm(geom.x_hat) - 1.0) < 1e-10
        assert abs(np.linalg.norm(geom.y_hat) - 1.0) < 1e-10
        assert abs(np.linalg.norm(geom.z_hat) - 1.0) < 1e-10

    def test_z_hat_along_relative_velocity(self):
        """z_hat should be parallel to the relative velocity vector."""
        s1 = _make_state([7_000_000, 0, 0], [0, 7500, 0])
        s2 = _make_state([7_000_100, 0, 0], [0, -7500, 0])
        geom = compute_conjunction_geometry(s1, s2)

        v_rel = s2.velocity - s1.velocity
        v_hat = v_rel / np.linalg.norm(v_rel)
        assert abs(abs(np.dot(geom.z_hat, v_hat)) - 1.0) < 1e-10

    def test_degenerate_zero_relative_velocity(self):
        """Should handle zero relative velocity without crashing."""
        s1 = _make_state([7_000_000, 0, 0], [0, 7500, 0])
        s2 = _make_state([7_000_100, 0, 0], [0, 7500, 0])  # same velocity
        geom = compute_conjunction_geometry(s1, s2)
        assert geom.miss_distance > 0
        assert np.linalg.norm(geom.z_hat) > 0


# ---------------------------------------------------------------------------
# rsw_to_eci_rotation
# ---------------------------------------------------------------------------

class TestRSWRotation:
    def test_rotation_matrix_is_orthogonal(self):
        """R @ R.T should be identity."""
        pos = np.array([7_000_000.0, 0.0, 0.0])
        vel = np.array([0.0, 7500.0, 0.0])
        R = rsw_to_eci_rotation(pos, vel)

        identity = R @ R.T
        np.testing.assert_allclose(identity, np.eye(3), atol=1e-10)

    def test_determinant_is_one(self):
        """Rotation matrix should have det = 1 (proper rotation)."""
        pos = np.array([7_000_000.0, 100_000.0, 50_000.0])
        vel = np.array([-500.0, 7400.0, 200.0])
        R = rsw_to_eci_rotation(pos, vel)
        assert abs(np.linalg.det(R) - 1.0) < 1e-10

    def test_radial_column_is_position_direction(self):
        """First column of R (radial) should be along the position vector."""
        pos = np.array([7_000_000.0, 0.0, 0.0])
        vel = np.array([0.0, 7500.0, 0.0])
        R = rsw_to_eci_rotation(pos, vel)

        r_hat = pos / np.linalg.norm(pos)
        np.testing.assert_allclose(R[:, 0], r_hat, atol=1e-10)

    def test_degenerate_zero_position(self):
        """Should return identity for zero position."""
        R = rsw_to_eci_rotation(np.zeros(3), np.array([0, 7500, 0]))
        np.testing.assert_allclose(R, np.eye(3))


# ---------------------------------------------------------------------------
# get_default_covariance
# ---------------------------------------------------------------------------

class TestCovariance:
    def test_lookup_known_entry(self):
        """PAYLOAD/LARGE should return (10, 100, 10) sigmas."""
        cov = get_default_covariance_rsw("LARGE", "PAYLOAD")
        expected = np.diag([10**2, 100**2, 10**2])
        np.testing.assert_array_equal(cov, expected)

    def test_fallback_default(self):
        """Unknown type/size should use _DEFAULT_SIGMAS (60, 600, 60)."""
        cov = get_default_covariance_rsw("XLARGE", "ALIEN")
        expected = np.diag([60**2, 600**2, 60**2])
        np.testing.assert_array_equal(cov, expected)

    def test_rotated_covariance_is_symmetric(self):
        """ECI covariance should be symmetric."""
        pos = np.array([7_000_000.0, 0.0, 0.0])
        vel = np.array([0.0, 7500.0, 0.0])
        cov = get_default_covariance("MEDIUM", "PAYLOAD", pos, vel)
        np.testing.assert_allclose(cov, cov.T, atol=1e-6)

    def test_rotated_covariance_is_positive_definite(self):
        """ECI covariance eigenvalues should all be positive."""
        pos = np.array([7_000_000.0, 100_000.0, 50_000.0])
        vel = np.array([-500.0, 7400.0, 200.0])
        cov = get_default_covariance("SMALL", "DEBRIS", pos, vel)
        eigenvalues = np.linalg.eigvalsh(cov)
        assert all(ev > 0 for ev in eigenvalues)

    def test_unrotated_fallback(self):
        """Without state vectors, should return RSW diagonal as-is."""
        cov = get_default_covariance("MEDIUM", "PAYLOAD")
        expected = get_default_covariance_rsw("MEDIUM", "PAYLOAD")
        np.testing.assert_array_equal(cov, expected)


# ---------------------------------------------------------------------------
# project_covariance_to_conjunction_plane
# ---------------------------------------------------------------------------

class TestCovarianceProjection:
    def test_output_is_2x2(self):
        s1 = _make_state([7_000_000, 0, 0], [0, 7500, 0])
        s2 = _make_state([7_000_100, 0, 0], [0, -7500, 0])
        geom = compute_conjunction_geometry(s1, s2)
        cov = np.diag([100.0**2, 500.0**2, 100.0**2])
        cov_2d = project_covariance_to_conjunction_plane(cov, cov, geom)
        assert cov_2d.shape == (2, 2)

    def test_output_is_positive_definite(self):
        s1 = _make_state([7_000_000, 0, 0], [0, 7500, 0])
        s2 = _make_state([7_000_100, 50, 0], [0, -7500, 100])
        geom = compute_conjunction_geometry(s1, s2)
        cov = np.diag([100.0**2, 500.0**2, 100.0**2])
        cov_2d = project_covariance_to_conjunction_plane(cov, cov, geom)
        eigenvalues = np.linalg.eigvalsh(cov_2d)
        assert all(ev > 0 for ev in eigenvalues)


# ---------------------------------------------------------------------------
# compute_pc_foster
# ---------------------------------------------------------------------------

class TestFosterPc:
    def test_pc_zero_for_huge_miss_distance(self):
        """Fast-path: miss >> HBR and >> sigma should return 0."""
        s1 = _make_state([7_000_000, 0, 0], [0, 7500, 0])
        s2 = _make_state([7_100_000, 0, 0], [0, -7500, 0])  # 100 km miss
        geom = compute_conjunction_geometry(s1, s2)
        cov_2d = np.diag([500.0**2, 500.0**2])
        pc = compute_pc_foster(geom, cov_2d, hard_body_radius=5.0)
        assert pc == 0.0

    def test_pc_bounded_zero_to_one(self):
        """Pc should always be in [0, 1]."""
        s1 = _make_state([7_000_000, 0, 0], [0, 7500, 0])
        s2 = _make_state([7_000_010, 0, 0], [0, -7500, 0])  # 10m miss
        geom = compute_conjunction_geometry(s1, s2)
        cov_2d = np.diag([100.0**2, 100.0**2])
        pc = compute_pc_foster(geom, cov_2d, hard_body_radius=5.0)
        assert 0.0 <= pc <= 1.0

    def test_pc_increases_with_smaller_miss(self):
        """Pc should be higher for smaller miss distances."""
        cov_2d = np.diag([200.0**2, 200.0**2])
        hbr = 3.0

        s1 = _make_state([7_000_000, 0, 0], [0, 7500, 0])

        # 500m miss
        s2_far = _make_state([7_000_500, 0, 0], [0, -7500, 0])
        geom_far = compute_conjunction_geometry(s1, s2_far)
        pc_far = compute_pc_foster(geom_far, cov_2d, hbr)

        # 50m miss
        s2_close = _make_state([7_000_050, 0, 0], [0, -7500, 0])
        geom_close = compute_conjunction_geometry(s1, s2_close)
        pc_close = compute_pc_foster(geom_close, cov_2d, hbr)

        assert pc_close >= pc_far

    def test_spherical_covariance_known_answer(self):
        """For spherical covariance and zero miss, Pc = HBR^2 / (2*sigma^2)."""
        # Head-on encounter at origin of conjunction plane
        s1 = _make_state([7_000_000, 0, 0], [0, 7500, 0])
        s2 = _make_state([7_000_000, 0, 0], [0, -7500, 0])  # 0 miss
        geom = compute_conjunction_geometry(s1, s2)

        sigma = 1000.0
        hbr = 5.0
        cov_2d = np.diag([sigma**2, sigma**2])

        pc = compute_pc_foster(geom, cov_2d, hbr)

        # Analytical: Pc = 1 - exp(-HBR^2 / (2*sigma^2))
        pc_analytical = 1.0 - math.exp(-(hbr**2) / (2.0 * sigma**2))
        assert abs(pc - pc_analytical) < 1e-6, f"Got {pc}, expected {pc_analytical}"


# ---------------------------------------------------------------------------
# compute_pc_sensitivity
# ---------------------------------------------------------------------------

class TestSensitivity:
    def test_curve_has_12_points(self):
        s1 = _make_state([7_000_000, 0, 0], [0, 7500, 0])
        s2 = _make_state([7_000_100, 0, 0], [0, -7500, 0])
        geom = compute_conjunction_geometry(s1, s2)
        cov_2d = np.diag([200.0**2, 200.0**2])
        result = compute_pc_sensitivity(geom, cov_2d, 3.0)
        assert "curve" in result
        assert len(result["curve"]) == 12

    def test_base_matches_scale_1(self):
        s1 = _make_state([7_000_000, 0, 0], [0, 7500, 0])
        s2 = _make_state([7_000_100, 0, 0], [0, -7500, 0])
        geom = compute_conjunction_geometry(s1, s2)
        cov_2d = np.diag([200.0**2, 200.0**2])
        result = compute_pc_sensitivity(geom, cov_2d, 3.0)

        scale_1_point = next(p for p in result["curve"] if p["scale"] == 1.0)
        assert scale_1_point["pc"] == result["base"]


# ---------------------------------------------------------------------------
# Hard-body radius and RCS helpers
# ---------------------------------------------------------------------------

class TestHardBodyRadius:
    def test_rcs_size_mapping(self):
        assert rcs_size_to_m2("LARGE") == 10.0
        assert rcs_size_to_m2("MEDIUM") == 1.0
        assert rcs_size_to_m2("SMALL") == 0.1

    def test_hbr_from_rcs(self):
        """HBR should be sum of two radii, each >= 1m."""
        hbr = compute_hard_body_radius(10.0, 1.0)
        r1 = math.sqrt(10.0 / math.pi)
        r2 = max(1.0, math.sqrt(1.0 / math.pi))
        assert abs(hbr - (r1 + r2)) < 0.001

    def test_hbr_minimum_floor(self):
        """Each object radius should be at least 1m."""
        hbr = compute_hard_body_radius(0.0, 0.0)
        assert hbr == 2.0  # 1m + 1m
