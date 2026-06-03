#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""Kalman filter — trajectory smoothing for noisy drone telemetry (REAL numpy, NO mock).

Drone Remote-ID / ADS-B position reports arrive jittered by GPS noise and packet loss.
Killinchu smooths the (lat, lon, alt) track with a constant-velocity Kalman filter before
any geofence / Λ verdict is computed, so a single noisy fix cannot flip a HALT decision.

State x = [pos, vel] per axis; constant-velocity model:
    x_k = F x_{k-1} + w,   z_k = H x_k + v
    Predict:  x⁻ = F x,         P⁻ = F P Fᵀ + Q
    Update:   K  = P⁻ Hᵀ (H P⁻ Hᵀ + R)⁻¹
              x  = x⁻ + K (z − H x⁻)
              P  = (I − K H) P⁻

R. E. Kalman, "A New Approach to Linear Filtering and Prediction Problems",
J. Basic Eng. 82(1):35–45 (1960).

Lean theorem: ``Lutar/Innovations/round11/FrontierKalmanGain.lean :: gain_in_unit_interval``
(L72, gain K ∈ [0,1]) and ``posterior_le_prior`` (L84, P_post ≤ P_prior — the update never
increases uncertainty). Permalink pinned at round11-frontier commit f3153a68.

CITATION: thesis_v22.pdf §2  ·  LEAN: FrontierKalmanGain.lean::gain_in_unit_interval
"""
from __future__ import annotations

import numpy as np

CITATION = "thesis_v22.pdf §2"
LEAN_THEOREM = "Lutar/Innovations/round11/FrontierKalmanGain.lean::gain_in_unit_interval"
LEAN_PERMALINK = (
    "https://github.com/szl-holdings/lutar-lean/blob/"
    "f3153a684e7d9b77462d58185bd1eae0aeacd1bc/"
    "Lutar/Innovations/round11/FrontierKalmanGain.lean#L72"
)


class ConstantVelocityKalman1D:
    """Scalar constant-velocity Kalman filter (state = [position, velocity])."""

    def __init__(self, dt: float = 1.0, process_var: float = 0.01,
                 meas_var: float = 1.0, x0: float = 0.0):
        self.dt = float(dt)
        self.F = np.array([[1.0, self.dt], [0.0, 1.0]])
        self.H = np.array([[1.0, 0.0]])
        self.Q = process_var * np.array([[self.dt ** 3 / 3, self.dt ** 2 / 2],
                                         [self.dt ** 2 / 2, self.dt]])
        self.R = np.array([[float(meas_var)]])
        self.x = np.array([[float(x0)], [0.0]])
        self.P = np.eye(2) * 500.0

    def step(self, z: float) -> tuple[float, float, float]:
        """One predict+update. Returns (smoothed_pos, velocity, kalman_gain_pos)."""
        # Predict
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        # Update
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        y = np.array([[float(z)]]) - self.H @ self.x
        self.x = self.x + K @ y
        self.P = (np.eye(2) - K @ self.H) @ self.P
        return float(self.x[0, 0]), float(self.x[1, 0]), float(K[0, 0])


def smooth_track(measurements, dt: float = 1.0, process_var: float = 0.01,
                 meas_var: float = 1.0) -> dict:
    """Smooth a 1-D sequence of noisy position measurements.

    Returns the smoothed track, residual RMS reduction, and proof that every Kalman
    gain stayed in [0,1] (matching the Lean theorem gain_in_unit_interval).
    """
    z = np.asarray(measurements, dtype=float).ravel()
    if z.size == 0:
        raise ValueError("measurements must be non-empty")
    kf = ConstantVelocityKalman1D(dt=dt, process_var=process_var,
                                  meas_var=meas_var, x0=float(z[0]))
    smoothed, gains, vels = [], [], []
    for zi in z:
        pos, vel, k = kf.step(zi)
        smoothed.append(pos)
        vels.append(vel)
        gains.append(k)
    smoothed = np.asarray(smoothed)
    # Honest residual metric: variance of first-difference (jitter) before vs after.
    raw_jitter = float(np.std(np.diff(z))) if z.size > 1 else 0.0
    smooth_jitter = float(np.std(np.diff(smoothed))) if smoothed.size > 1 else 0.0
    gains_in_unit = bool(np.all((np.asarray(gains) >= -1e-9) & (np.asarray(gains) <= 1.0 + 1e-9)))
    return {
        "value": smoothed.tolist(),
        "smoothed": smoothed.tolist(),
        "velocity": vels,
        "kalman_gains": [round(g, 6) for g in gains],
        "raw_jitter_std": round(raw_jitter, 6),
        "smoothed_jitter_std": round(smooth_jitter, 6),
        "jitter_reduction": round(raw_jitter - smooth_jitter, 6),
        "gains_in_unit_interval": gains_in_unit,
        "n": int(z.size),
        "citation": CITATION,
        "lean_theorem": LEAN_THEOREM,
    }


def smooth_track_3d(points, dt: float = 1.0, process_var: float = 0.01,
                    meas_var: float = 1.0) -> dict:
    """Smooth a sequence of [lat, lon, alt] points with one filter per axis."""
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError("points must be Nx3 [lat,lon,alt]")
    axes = {}
    for i, name in enumerate(("lat", "lon", "alt")):
        axes[name] = smooth_track(pts[:, i], dt=dt, process_var=process_var,
                                  meas_var=meas_var)
    smoothed = list(zip(axes["lat"]["smoothed"], axes["lon"]["smoothed"],
                        axes["alt"]["smoothed"]))
    return {
        "value": [list(p) for p in smoothed],
        "smoothed_track": [list(p) for p in smoothed],
        "per_axis": axes,
        "gains_in_unit_interval": all(axes[a]["gains_in_unit_interval"] for a in axes),
        "n": int(pts.shape[0]),
        "citation": CITATION,
        "lean_theorem": LEAN_THEOREM,
    }


__all__ = ["ConstantVelocityKalman1D", "smooth_track", "smooth_track_3d",
           "CITATION", "LEAN_THEOREM", "LEAN_PERMALINK"]

# Doctrine v11 LOCKED — 749/14/163 — c7c0ba17 · Λ = Conjecture 1 (NEVER a theorem)
# SLSA L1 honest (killinchu never claims L2 unless independently verified).
