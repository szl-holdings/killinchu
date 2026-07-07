# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_energy.py — FRONTIER WAVE C. ADDITIVE governed SIGNED ENERGY RECEIPT backend
for the killinchu Space (GET /api/killinchu/v1/energy/receipt).

WHAT THIS IS
------------
The founder's frontier ask: "energy-metered inference — joules per token, on every
receipt." This backend emits a deterministic, HASH-CHAINED signed energy receipt for
a modeled inference request: tokens/joule, joules/token and gCO2/token, each carrying
an HONEST signed marker (REAL ECDSA/DSSE only in-Space when the cosign key is present;
an explicit UNSIGNED marker otherwise — never a fabricated signature). Receipts are
HASH-CHAINED (each receipt commits to the previous receipt's hash), so the energy
ledger is tamper-evident like a khipu.

HONEST POSTURE ON "MEASURED":
  * The a11oy flagship Energy·Harvest surface (static/3d/surfaces/energy.js) meters
    REAL joules on-box via an NVML exporter and labels them MEASURED. Off-box, and on
    THIS killinchu module, there is NO on-box NVML sample, so every energy figure here
    is explicitly MODELED — an order-of-magnitude estimate from a documented power
    model, NOT a live wattmeter. We NEVER upgrade MODELED to MEASURED and NEVER
    fabricate a joule reading.

CLOSED-FORM ENERGY MODEL (shown verbatim in the receipt):
  energy_j        = (power_w · latency_s)                      (E = P·t)
  joules_per_token= energy_j / tokens
  tokens_per_joule= tokens / energy_j
  gco2_per_token  = joules_per_token · (grid_gco2_per_kwh / 3.6e6)   (J→kWh = /3.6e6)
  carbon_saving   = (dirty_gco2 - clean_gco2) / dirty_gco2 · 100%     (carbon-aware shift)

HONESTY SPINE (Doctrine v11):
  * MODELED. No NVML on this Space; power/latency are a documented MODELED profile,
    grid carbon intensity is a SAMPLE constant (not a live Electricity Maps / carbon
    feed). Order-of-magnitude only.
  * The hash-chain + signed-receipt structure is REAL (sha256 chain; ECDSA in-Space).
  * Adds NOTHING to the locked-8. Λ stays Conjecture 1 — the carbon-aware "shift now?"
    verdict is ADVISORY, never "green".

Route (NEW; never collides):
  GET /api/{ns}/v1/energy/receipt  — signed, hash-chained energy receipt for a modeled request

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.

LEADERS ADOPTED & CITED (clean-room; NOT claimed as SZL's own):
  NVIDIA Management Library (NVML) — per-GPU power/energy telemetry
    — https://developer.nvidia.com/management-library-nvml
  Patterson et al. (2021) "Carbon Emissions and Large Neural Network Training"
    — arXiv:2104.10350
  Google (2020) "Carbon-Intelligent Computing" — carbon-aware datacenter load shifting
    — https://blog.google/inside-google/infrastructure/data-centers-work-harder-sun-shines-rain-pours/
  Electricity Maps — real-time grid carbon intensity — https://www.electricitymaps.com/
"""
from __future__ import annotations

import hashlib as _hashlib
import json as _json
from datetime import datetime, timezone

# --- signed receipts: the SINGLE source of truth (never fabricate a signature) ----
try:
    from szl_dsse import sign_payload as _sign_payload  # REAL ECDSA when key present
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover — honest UNSIGNED marker otherwise
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.energy+json"):  # type: ignore
        body = _json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()
        return {
            "payloadType": payload_type,
            "payload": __import__("base64").b64encode(body).decode("ascii"),
            "_dsse": "DSSEv1",
            "_pae_sha256": _hashlib.sha256(body).hexdigest(),
            "_signed_at": datetime.now(timezone.utc).isoformat(),
            "signatures": [],
            "signed": False,
            "honesty": ("UNSIGNED — szl_dsse not importable in this runtime; "
                        "no signature fabricated."),
        }

_ENERGY_PAYLOAD_TYPE = "application/vnd.szl.kc.energy+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "nvml": ("NVIDIA Management Library (NVML) — per-GPU power/energy telemetry "
             "— developer.nvidia.com/management-library-nvml"),
    "patterson": ("Patterson et al. (2021) Carbon Emissions and Large Neural Network "
                  "Training — arXiv:2104.10350"),
    "carbon_intelligent": ("Google (2020) Carbon-Intelligent Computing — carbon-aware "
                           "datacenter load shifting"),
    "electricity_maps": "Electricity Maps — real-time grid carbon intensity — electricitymaps.com",
}

# MODELED label — NO NVML on this Space; MODELED order-of-magnitude, never MEASURED here.
MODELED_LABEL = "MODELED"
MODELED_LABEL_LONG = "MODELED | NO_ONBOX_NVML | NOT_MEASURED | ORDER_OF_MAGNITUDE"

# MODELED power/latency profile (documented; NOT a live wattmeter)
_POWER_W = 350.0        # MODELED sustained accelerator draw during decode (order of magnitude)
_LATENCY_S = 0.020      # MODELED wall-clock per output token (s/token)
# SAMPLE grid carbon intensities (gCO2 per kWh) — constants, NOT a live carbon feed
_GCO2_DIRTY = 480.0     # coal/gas-heavy grid (SAMPLE)
_GCO2_CLEAN = 45.0      # renewable-rich window (SAMPLE)
_J_PER_KWH = 3.6e6      # 1 kWh = 3.6e6 J

# genesis chain anchor (deterministic; a hash-chained energy ledger like a khipu)
_GENESIS = "szl-kc-energy-genesis"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(s: str) -> str:
    return _hashlib.sha256(s.encode("utf-8")).hexdigest()


def energy_receipt(tokens: int = 512, power_w: float = _POWER_W,
                   latency_s: float = _LATENCY_S, grid_gco2_per_kwh: float = _GCO2_DIRTY,
                   prev_hash: str = None, seed: int = 42) -> dict:
    """Deterministic, hash-chained, signed MODELED energy receipt for one request.

    Returns a JSON shape the frontier energy organ can render:
      { label, tokens, joules_total, joules_per_token, tokens_per_joule,
        gco2_per_token, carbon{...}, chain{prev_hash,this_hash}, signed_receipt, ... }
    """
    # ---- bounds (defensive) ----
    tokens = max(1, min(1_000_000, int(tokens)))
    power_w = max(0.1, min(2000.0, float(power_w)))
    latency_s = max(1e-4, min(10.0, float(latency_s)))
    grid_gco2_per_kwh = max(0.0, min(2000.0, float(grid_gco2_per_kwh)))
    prev_hash = str(prev_hash) if prev_hash else _sha256(_GENESIS)

    # ---- closed-form energy metering (E = P·t per token, summed) ----
    energy_per_token_j = power_w * latency_s
    joules_total = energy_per_token_j * tokens
    joules_per_token = joules_total / tokens
    tokens_per_joule = tokens / joules_total if joules_total > 0 else 0.0

    # ---- carbon: gCO2 per token on this grid, plus carbon-aware shift verdict ----
    kwh_per_token = joules_per_token / _J_PER_KWH
    gco2_per_token = kwh_per_token * grid_gco2_per_kwh
    gco2_total = gco2_per_token * tokens

    gco2_per_token_clean = kwh_per_token * _GCO2_CLEAN
    gco2_per_token_dirty = kwh_per_token * _GCO2_DIRTY
    carbon_saving_pct = (0.0 if gco2_per_token_dirty <= 0 else
                         (gco2_per_token_dirty - gco2_per_token_clean) / gco2_per_token_dirty * 100.0)
    # ADVISORY (never "green"): shift to a clean window if this grid is dirtier than clean
    shift_now = bool(grid_gco2_per_kwh > (_GCO2_CLEAN * 2.0))

    carbon = {
        "grid_gco2_per_kwh": round(grid_gco2_per_kwh, 3),
        "gco2_per_token": round(float(gco2_per_token), 9),
        "gco2_total": round(float(gco2_total), 6),
        "gco2_per_token_clean_window": round(float(gco2_per_token_clean), 9),
        "gco2_per_token_dirty_window": round(float(gco2_per_token_dirty), 9),
        "carbon_saving_if_shifted_pct": round(float(carbon_saving_pct), 3),
        "carbon_aware_shift_advice": ("SHIFT to a cleaner window (ADVISORY, never 'green')"
                                      if shift_now else "grid already clean-ish (ADVISORY)"),
        "label": "MODELED (SAMPLE grid intensity — NOT a live carbon feed)",
    }

    # ---- the receipt (hash-chained; signed) ----
    receipt = {
        "window_timestamp": _now_iso(),
        "organ": "signed-energy-receipt",
        "organ_version": "szl-kc-energy-v0.1",
        "data_source": "MODELED_POWER_PROFILE",
        "tokens": tokens,
        "power_w_modeled": round(power_w, 3),
        "latency_s_per_token_modeled": round(latency_s, 6),
        "joules_total": round(float(joules_total), 4),
        "joules_per_token": round(float(joules_per_token), 6),
        "tokens_per_joule": round(float(tokens_per_joule), 6),
        "gco2_per_token": round(float(gco2_per_token), 9),
        "carbon_saving_if_shifted_pct": round(float(carbon_saving_pct), 3),
        "signed_marker": "HONEST — MODELED energy, REAL hash-chain, ECDSA only in-Space",
        "label": MODELED_LABEL_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem) — carbon-shift verdict never 'green'",
        "effector_posture": "N/A (metering receipt — never an engage)",
        "citations": [CITATIONS["nvml"], CITATIONS["patterson"],
                      CITATIONS["carbon_intelligent"], CITATIONS["electricity_maps"]],
        "honesty": ("MODELED joules/token + gCO2/token. NO on-box NVML on this Space, so figures "
                    "are order-of-magnitude from a documented power profile, NOT a live wattmeter; "
                    "grid carbon is a SAMPLE constant, NOT a live carbon feed. Hash-chain is REAL; "
                    "signatures REAL ECDSA only in-Space, honest UNSIGNED marker otherwise — never "
                    "fabricated. MEASURED joules are the a11oy on-box NVML exporter's job, not this."),
    }
    # hash-chain: this receipt commits to prev_hash (tamper-evident energy ledger)
    body = _json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    this_hash = _sha256(prev_hash + "|" + body)
    chain = {
        "prev_hash": prev_hash,
        "this_hash": this_hash,
        "chained": True,
        "scheme": "sha256(prev_hash | canonical_receipt) — khipu-style tamper-evident ledger",
    }
    receipt_signed = dict(receipt, chain=chain)
    dsse = _sign_payload(receipt_signed, _ENERGY_PAYLOAD_TYPE)

    return {
        "service": "signed-energy-receipt",
        "label": MODELED_LABEL,
        "tokens": tokens,
        "joules_total": round(float(joules_total), 4),
        "joules_per_token": round(float(joules_per_token), 6),
        "tokens_per_joule": round(float(tokens_per_joule), 6),
        "gco2_per_token": round(float(gco2_per_token), 9),
        "carbon": carbon,
        "chain": chain,
        "power_w_modeled": round(power_w, 3),
        "latency_s_per_token_modeled": round(latency_s, 6),
        "formulas": {
            "energy": "energy_j = power_w · latency_s (E = P·t)",
            "joules_per_token": "joules_per_token = energy_j / tokens",
            "tokens_per_joule": "tokens_per_joule = tokens / energy_j",
            "gco2_per_token": "gco2_per_token = joules_per_token · (grid_gco2_per_kwh / 3.6e6)",
            "carbon_saving": "carbon_saving_pct = (dirty - clean)/dirty · 100",
        },
        "compute_backend": {
            "backend": "CPU pure-Python (stdlib)",
            "label": "MODELED",
            "honest_note": ("Closed-form power model + REAL sha256 hash-chain. NO NVML on this "
                            "Space; joules are MODELED order-of-magnitude, never MEASURED here."),
        },
        "measured_vs_modeled": ("MODELED here (no on-box NVML). MEASURED joules are labeled by the "
                                "a11oy on-box NVML exporter (harvest/posture) — we never upgrade."),
        "wired_into": "frontier ring · signed-energy-receipt organ",
        "citations": [CITATIONS["nvml"], CITATIONS["carbon_intelligent"]],
        "signed_receipt": {"receipt": receipt_signed, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/energy" % ns

    @app.get("%s/receipt" % base)
    async def _kc_energy(tokens: int = 512, power_w: float = _POWER_W,
                         latency_s: float = _LATENCY_S,
                         grid_gco2_per_kwh: float = _GCO2_DIRTY,
                         prev_hash: str = None, seed: int = 42):  # noqa: ANN202
        try:
            return JSONResponse(energy_receipt(tokens=tokens, power_w=power_w,
                                               latency_s=latency_s,
                                               grid_gco2_per_kwh=grid_gco2_per_kwh,
                                               prev_hash=prev_hash, seed=seed))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "signed-energy-receipt", "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "joules_per_token": None, "tokens_per_joule": None,
                                 "gco2_per_token": None}, status_code=200)

    return {"ok": True, "ns": ns, "routes": ["%s/receipt" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = energy_receipt(tokens=512, seed=42)
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("tokens", "joules_total", "joules_per_token", "tokens_per_joule",
              "gco2_per_token", "carbon", "chain"):
        assert f in r, f
    # E = P·t sanity: 350 W · 0.020 s = 7 J/token; 512 tokens => 3584 J
    assert abs(r["joules_per_token"] - 7.0) < 1e-6, r["joules_per_token"]
    assert abs(r["joules_total"] - 3584.0) < 1e-3, r["joules_total"]
    assert abs(r["tokens_per_joule"] - (512 / 3584.0)) < 1e-6, r["tokens_per_joule"]
    assert r["gco2_per_token"] > 0, r["gco2_per_token"]
    out["metrics"] = {"jpt": r["joules_per_token"], "tpj": r["tokens_per_joule"],
                      "gco2pt": r["gco2_per_token"]}

    # carbon-aware saving is positive when comparing dirty->clean window
    assert r["carbon"]["carbon_saving_if_shifted_pct"] > 0, r["carbon"]
    assert "ADVISORY" in r["carbon"]["carbon_aware_shift_advice"], r["carbon"]

    # hash-chain: chained, and links a second receipt to the first
    assert r["chain"]["chained"] is True, r["chain"]
    r2 = energy_receipt(tokens=256, prev_hash=r["chain"]["this_hash"], seed=42)
    assert r2["chain"]["prev_hash"] == r["chain"]["this_hash"], "chain not linked"
    assert r2["chain"]["this_hash"] != r["chain"]["this_hash"], "hash collision"
    out["chain_linked"] = True

    # determinism (same inputs incl. genesis prev_hash omitted)
    ra = energy_receipt(tokens=512, seed=42)
    assert ra["joules_total"] == r["joules_total"], "non-deterministic"

    # signed receipt present + honest label; never fabricated; NEVER "MEASURED"
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_MEASURED" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    out["signed"] = d.get("signed")
    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
