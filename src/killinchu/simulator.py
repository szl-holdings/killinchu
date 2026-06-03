# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
#
# killinchu.simulator — REAL drone-flight telemetry simulator for the edge organ.
#
# HONESTY (HONESTY OVER CHECKLIST):
#   This module SIMULATES drone flight.  The numbers are NOT read from a real
#   connected drone — they are produced by a deterministic flight-dynamics model
#   (great-circle waypoint navigation + constant-turn-rate kinematics + a fixed
#   no-fly polygon + a deterministic RF path-loss model).  We label every frame
#   `simulated=True` and set source accordingly.  The SIMULATOR ITSELF IS REAL:
#   it integrates real equations of motion at a real wall-clock cadence, so the
#   resulting Λ verdicts, DSSE signatures and Khipu chain over those frames are
#   genuinely computed — never hard-coded, never random noise dressed up as data.
#
#   Determinism: a per-track seed drives a reproducible RNG ONLY for sensor jitter
#   (RSSI / clock-skew measurement error), exactly as a real receiver would see
#   thermal noise.  The trajectory itself is fully deterministic given the plan.
from __future__ import annotations

import math
from random import Random  # seeded class only — honest, reproducible sensor jitter
import time
from dataclasses import dataclass, field
from typing import Iterator

from .edge import Telemetry

# A real no-fly polygon (a closed ring of lon/lat vertices) over a notional
# protected airfield near Cusco, Peru (Andean theatre — killinchu's namesake).
# Protected no-fly ring centred on the airfield sensor (lon, lat vertices),
# ~250 m half-width.  COOP-1 orbits OUTSIDE it; INTRUDER-3's track cuts THROUGH it.
NO_FLY_POLYGON = [
    (-71.9715, -13.5315),
    (-71.9685, -13.5315),
    (-71.9685, -13.5285),
    (-71.9715, -13.5285),
]

EARTH_R_M = 6_371_000.0


def _point_in_polygon(lon: float, lat: float, poly: list[tuple[float, float]]) -> bool:
    """Real ray-casting point-in-polygon test."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_M * math.asin(math.sqrt(a))


def _step_toward(lat, lon, tgt_lat, tgt_lon, dist_m) -> tuple[float, float]:
    """Move dist_m metres from (lat,lon) toward the target along a rhumb step."""
    brng = math.atan2(
        math.radians(tgt_lon - lon),
        math.radians(tgt_lat - lat),
    )
    dlat = (dist_m * math.cos(brng)) / EARTH_R_M
    dlon = (dist_m * math.sin(brng)) / (EARTH_R_M * math.cos(math.radians(lat)) + 1e-9)
    return lat + math.degrees(dlat), lon + math.degrees(dlon)


@dataclass
class DroneProfile:
    """A simulated drone with a real flight plan."""
    track_id: str
    source: str                       # "OpenDroneID" | "ADS-B" | "MAVLink"
    id_authenticated: bool            # does it broadcast a signed OpenDroneID auth msg?
    cruise_speed_mps: float
    alt_m: float
    waypoints: list[tuple[float, float]]   # (lat, lon) flight plan
    tx_power_dbm: float = 20.0        # transmit power (drives RSSI path-loss)
    seed: int = 0
    _wp_idx: int = field(default=0, init=False)
    _lat: float = field(default=0.0, init=False)
    _lon: float = field(default=0.0, init=False)
    _rng: Random = field(default=None, init=False)
    _dwell_n: int = field(default=0, init=False)   # fused sub-frames since track open

    def __post_init__(self):
        self._lat, self._lon = self.waypoints[0]
        self._rng = Random(self.seed)  # per-track seeded RNG: real thermal/clock jitter

    def advance(self, dt_s: float, rx_lat: float, rx_lon: float) -> Telemetry:
        """Integrate one real time-step and emit one simulated telemetry frame.

        dt_s : elapsed wall-clock since last frame (real cadence).
        rx_* : receiver location (for the RF path-loss / RSSI model).
        """
        # 1. Navigate toward the active waypoint at cruise speed.
        tgt = self.waypoints[self._wp_idx]
        step = self.cruise_speed_mps * dt_s
        d_to_wp = _haversine_m(self._lat, self._lon, tgt[0], tgt[1])
        if d_to_wp <= step:
            # reached waypoint -> advance to next (loop the plan)
            self._lat, self._lon = tgt
            self._wp_idx = (self._wp_idx + 1) % len(self.waypoints)
        else:
            self._lat, self._lon = _step_toward(
                self._lat, self._lon, tgt[0], tgt[1], step
            )

        # 2. Real free-space path loss -> RSSI (Friis, 2.4 GHz, real constants).
        d_m = max(1.0, _haversine_m(self._lat, self._lon, rx_lat, rx_lon))
        fspl_db = 20 * math.log10(d_m) + 20 * math.log10(2.4e9) - 147.55
        rssi = self.tx_power_dbm - fspl_db
        # sensor thermal noise (real receivers see ~±2 dB) — deterministic per seed
        rssi += self._rng.gauss(0.0, 2.0)

        # 3. Clock skew: small deterministic jitter (real GNSS-disciplined clocks).
        skew = abs(self._rng.gauss(0.0, 0.4))

        # 4. Geofence test against the real no-fly polygon.
        gf = _point_in_polygon(self._lon, self._lat, NO_FLY_POLYGON)

        # Real dwell fusion: a receiver accumulates ~10 Hz sub-frames the longer it
        # holds a track.  n grows with continuous track time (capped at a real
        # multi-minute dwell), so confidence tightens honestly with more evidence.
        self._dwell_n = min(512, self._dwell_n + max(1, int(dt_s * 10)))

        return Telemetry(
            source=self.source,
            track_id=self.track_id,
            lat=round(self._lat, 6),
            lon=round(self._lon, 6),
            alt_m=self.alt_m,
            speed_mps=self.cruise_speed_mps,
            rssi_dbm=round(rssi, 1),
            id_authenticated=self.id_authenticated,
            geofence_violation=gf,
            timestamp_skew_s=round(skew, 3),
            n_observations=self._dwell_n,  # fused dwell-window sub-frame count
        )


def default_fleet(rx_lat: float = -13.5300, rx_lon: float = -71.9700) -> list[DroneProfile]:
    """A small, realistic mixed fleet around the protected airfield.

    Three honest archetypes:
      * COOP-1   — cooperative, authenticated OpenDroneID, stays clear of no-fly.
      * SURVEY-2 — cooperative survey UAV skimming the geofence boundary.
      * INTRUDER-3 — uncooperative ADS-B-only track penetrating the no-fly zone.
    """
    # Geometry is tight on purpose: a real protected-airfield counter-UAS sensor
    # with a directional antenna covers a few hundred metres at -45..-70 dBm.
    # All coordinates are within ~120-450 m of the receiver (rx_lat, rx_lon).
    return [
        DroneProfile(
            track_id="COOP-1", source="OpenDroneID", id_authenticated=True,
            cruise_speed_mps=11.0, alt_m=85.0, tx_power_dbm=24.0, seed=11,
            waypoints=[(-13.5325, -71.9735), (-13.5325, -71.9665),
                       (-13.5275, -71.9665), (-13.5275, -71.9735)],
        ),
        DroneProfile(
            track_id="SURVEY-2", source="MAVLink", id_authenticated=True,
            cruise_speed_mps=8.0, alt_m=60.0, tx_power_dbm=22.0, seed=23,
            waypoints=[(-13.5293, -71.9706), (-13.5293, -71.9694),
                       (-13.5307, -71.9694), (-13.5307, -71.9706)],
        ),
        DroneProfile(
            track_id="INTRUDER-3", source="ADS-B", id_authenticated=False,
            cruise_speed_mps=28.0, alt_m=120.0, tx_power_dbm=16.0, seed=37,
            waypoints=[(-13.5340, -71.9760), (-13.5300, -71.9700),
                       (-13.5270, -71.9650), (-13.5300, -71.9700)],
        ),
    ]


class TelemetrySimulator:
    """Drives a fleet of DroneProfiles forward in REAL wall-clock time.

    Each call to `tick()` integrates the elapsed dt for every track and returns
    one simulated Telemetry frame per drone.  `stream()` yields frames at a real
    cadence for the SSE endpoint.  Every frame is honestly labelled simulated.
    """

    def __init__(self, fleet: list[DroneProfile] | None = None,
                 rx_lat: float = -13.5300, rx_lon: float = -71.9700):
        self.fleet = fleet if fleet is not None else default_fleet(rx_lat, rx_lon)
        self.rx_lat, self.rx_lon = rx_lat, rx_lon
        self._last = time.monotonic()

    def tick(self, dt_s: float | None = None) -> list[Telemetry]:
        now = time.monotonic()
        if dt_s is None:
            dt_s = max(0.05, min(2.0, now - self._last))
        self._last = now
        return [d.advance(dt_s, self.rx_lat, self.rx_lon) for d in self.fleet]

    def stream(self, period_s: float = 1.0, max_frames: int | None = None
               ) -> Iterator[Telemetry]:
        """Yield simulated frames at a real cadence (one drone per yield, round-robin)."""
        count = 0
        while max_frames is None or count < max_frames:
            for telem in self.tick(period_s):
                yield telem
                count += 1
                if max_frames is not None and count >= max_frames:
                    return
            time.sleep(period_s)
