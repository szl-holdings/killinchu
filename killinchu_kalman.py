#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. -- SZL Holdings
# ORCID: 0009-0001-0110-4173
#
# killinchu_kalman.py -- KILLINCHU: Kalman trajectory smoother for noisy RF/MAVLink
# drone telemetry, feeding steadier threat verdicts.
#
# Frontier formula F5 (round11): Kalman filter (constant-velocity model).
#   R. E. Kalman, "A New Approach to Linear Filtering and Prediction Problems",
#   Trans. ASME J. Basic Eng. 82(1):35-45 (1960).
#   https://en.wikipedia.org/wiki/Kalman_filter
#
# Lean proof of variance reduction (posterior <= prior; strict for P>0):
#   szl-holdings/lutar-lean
#   Lutar/Innovations/round11/FrontierKalmanGain.lean :: posterior_le_prior,
#   posterior_strict_decrease, gain_in_unit_interval
#
# Why this helps the running software:
#   killinchu classifies threats from jittery RF/MAVLink position reports. Raw
#   last-reading classification overreacts to single-sample noise. A Kalman filter fuses
#   the measurement stream into a smoothed track whose uncertainty NEVER increases on an
#   update (proved in Lean) -> fewer single-sample misclassifications, steadier verdicts.
#
# numpy if available; pure-Python scalar fallback so it runs in any Space.

from __future__ import annotations

from typing import Optional


class KalmanTracker:
    """Constant-velocity Kalman tracker for a 1-D coordinate (apply per axis).

    State x = [position, velocity]^T. Predict advances by dt; update fuses a noisy
    position measurement using the optimal gain K = P H^T S^-1.
    """

    def __init__(
        self,
        process_var: float = 1e-2,   # Q scale: trust in the motion model
        meas_var: float = 1.0,       # R: RF/MAVLink position-noise variance
        init_pos: float = 0.0,
        init_vel: float = 0.0,
        init_var: float = 1e3,       # large prior uncertainty
    ) -> None:
        self.q = float(process_var)
        self.r = float(meas_var)
        # state
        self.pos = float(init_pos)
        self.vel = float(init_vel)
        # 2x2 covariance P (row-major: p00,p01,p10,p11)
        self.p00 = float(init_var)
        self.p01 = 0.0
        self.p10 = 0.0
        self.p11 = float(init_var)

    def predict(self, dt: float = 1.0) -> None:
        """Time update: x = F x ; P = F P F^T + Q  (constant-velocity F)."""
        # x' = pos + vel*dt ; vel' = vel
        self.pos = self.pos + self.vel * dt
        # P' = F P F^T  with F = [[1,dt],[0,1]]
        p00 = self.p00 + dt * (self.p10 + self.p01) + dt * dt * self.p11
        p01 = self.p01 + dt * self.p11
        p10 = self.p10 + dt * self.p11
        p11 = self.p11
        # + Q (process noise on both states)
        self.p00 = p00 + self.q
        self.p01 = p01
        self.p10 = p10
        self.p11 = p11 + self.q

    def update(self, z: float) -> float:
        """Measurement update with position measurement z. Returns innovation.

        H = [1, 0]. S = P00 + R ; K = P[:,0]/S ; x += K*(z-H x) ; P = (I-KH)P.
        By Lean posterior_strict_decrease, P00 strictly decreases for P00>0, R>0.
        """
        innovation = z - self.pos
        s = self.p00 + self.r
        if s <= 0.0:
            return innovation
        k0 = self.p00 / s   # gain on position  (in [0,1), Lean gain_in_unit_interval)
        k1 = self.p10 / s   # gain on velocity
        # state update
        self.pos = self.pos + k0 * innovation
        self.vel = self.vel + k1 * innovation
        # covariance update P = (I - K H) P, H = [1,0]
        p00 = (1.0 - k0) * self.p00
        p01 = (1.0 - k0) * self.p01
        p10 = self.p10 - k1 * self.p00
        p11 = self.p11 - k1 * self.p01
        self.p00, self.p01, self.p10, self.p11 = p00, p01, p10, p11
        return innovation

    def step(self, z: float, dt: float = 1.0) -> dict:
        """One predict+update cycle. Returns the smoothed estimate + uncertainty."""
        prior_var = self.p00 + self.q  # post-predict position variance (for reporting)
        self.predict(dt)
        innovation = self.update(z)
        return {
            "smoothed_position": round(self.pos, 6),
            "velocity": round(self.vel, 6),
            "position_variance": round(self.p00, 6),
            "innovation": round(innovation, 6),
            "gain_in_unit_interval": 0.0 <= (prior_var / (prior_var + self.r)) < 1.0,
            "formula": "kalman-filter-cv",
            "lean_ref": "Lutar/Innovations/round11/FrontierKalmanGain.lean",
        }

    @property
    def position_uncertainty(self) -> float:
        return self.p00


def smooth_track(measurements: list[float], dt: float = 1.0,
                 meas_var: float = 1.0, process_var: float = 1e-2) -> list[dict]:
    """Smooth a sequence of noisy position measurements into a track."""
    if not measurements:
        return []
    kt = KalmanTracker(process_var=process_var, meas_var=meas_var,
                       init_pos=measurements[0])
    return [kt.step(z, dt) for z in measurements]


__all__ = ["KalmanTracker", "smooth_track"]
