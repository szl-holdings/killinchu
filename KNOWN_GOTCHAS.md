# KNOWN_GOTCHAS.md — killinchu

> Doctrine v11 LOCKED · 749/14/163.

---

## 1. OTel middleware crash-loop (HARD-DISABLED)

The `szl_otel` / `vsp_otel` middleware was **crash-looping** the killinchu
HF Space when enabled. It is hard-disabled in `serve.py`:

```python
# HOTFIX 2026-06-01 Yachay: OTel middleware crash-looping the Space.
def _szl_otel_setup(*a, **kw): pass
_OTEL_ENABLED = False
```

**Do NOT re-enable without testing.** The crash was silent — the Space appeared
to start but returned 500 on all routes. Root cause: the OTel middleware
registered before the FastAPI app was fully initialized.

---

## 2. GitHub ↔ HF Space drift

Same as a11oy: `hf-sync.yml` only syncs `README.md`.
Space: `SZLHOLDINGS/killinchu` (https://szlholdings-killinchu.hf.space).

---

## 3. Protocol decoders require optional deps

`killinchu_protocols.py` uses:
- `pyModeS` for ADS-B decoding (`adsb_decode`)
- `pymavlink` for MAVLink parsing (`mavlink_parse`)

Both are imported with `try/except` and degrade to honest errors if absent.
If you see `{"ok": false, "error": "pyModeS not installed"}` in responses,
add `pyModeS` to the Dockerfile.

---

## 4. Remote-ID/ADS-B fields are CLAIMS, not ground truth

All decoded Remote-ID, ADS-B, and MAVLink fields are unauthenticated broadcast
data. A drone can spoof its own Remote-ID. The counter-UAS Λ-gate evaluates these
claims under policy — it does NOT verify authenticity. Never document the system
as providing "authenticated drone identity".

---

## 5. Dockerfile per-file COPY discipline

Same as a11oy: every module needs a `COPY` line. Particularly:
`killinchu_protocols.py`, `killinchu_edge_formulas.py`, `killinchu_kalman.py`,
`szl_be_hardening.py`, `szl_dsse.py`.

---

## 6. Shallow clone risk

`git ls-files | wc -l` should be ~594 for killinchu. If < 50, partial checkout.

---

## 7. `from __future__ import annotations` FastAPI gotcha

Same as a11oy: avoid in files defining FastAPI routes or Pydantic models.

---

## 8. SLSA L1 + L2 — verify the attestation, not just the signature

The killinchu GHCR image is cosign-signed and ships a signed SLSA provenance
attestation. SLSA Build L2 has been independently verified: run
`cosign verify-attestation --type slsaprovenance` (keyless Fulcio + Rekor,
strict per-organ identity scoped to `https://github.com/szl-holdings/killinchu/`)
to get the `slsa.dev/provenance` payload. Plain `cosign verify` only checks the
image signature (L1) — use `verify-attestation` to confirm L2. L3 is not claimed.

---

*Signed-off-by: stephenlutar2-hash <stephenlutar2@gmail.com>*
*Doctrine v11 LOCKED · 749/14/163.*
