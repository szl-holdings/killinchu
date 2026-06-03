"""FAA Remote ID session validity — INN-10.
Lean theorem: FAARIDSessionValidity (omega proof, 0 sorry).
Doctrine v11 LOCKED 749/14/163 c7c0ba17.
"""
import time

RID_FRESHNESS_WINDOW_SEC: int = 30  # FAA RID §89.305(a)(3)


def is_fresh_rid_timestamp(packet_timestamp_sec: float) -> bool:
    """Return True iff timestamp is within FAA RID 30s freshness window.

    Lean theorem INN-10: rid_stale_timestamp_rejected and rid_boundary_fresh
    proved via omega at Lutar/Innovations/FAARIDSessionValidity.lean.
    """
    age = time.time() - packet_timestamp_sec
    return 0.0 <= age <= float(RID_FRESHNESS_WINDOW_SEC)


def validate_rid_session(telemetry: dict) -> tuple[bool, str]:
    """Validate RID session freshness. Returns (valid, message)."""
    ts = float(telemetry.get("timestamp_sec", 0))
    if not is_fresh_rid_timestamp(ts):
        age = time.time() - ts
        return False, f"FAA RID stale: age={age:.1f}s > {RID_FRESHNESS_WINDOW_SEC}s"
    return True, "FAA RID timestamp valid"
