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

## 8. SLSA L1 honest — no public Rekor entry

The killinchu GHCR image is signed by the GitHub private Fulcio (no public
Rekor log entry). This means SLSA L1 (honest). NOT L2. This is tracked as a
known gap in the README.

---

## 9. HF Space and GitHub `main` are SEPARATE repos — deploy-sync gap

The HF Space (`szlholdings-killinchu.hf.space`) git repo is **distinct** from
the GitHub mirror. A merge to GitHub `main` does **not** update the Space — the
Space serve.py must be pushed separately and the Space rebuilt.

Symptom seen 2026-06-05: `/beyond`, `/elite`, and the
`/api/killinchu/v1/{autonomy,hotl,swarm}` + `/borrowed-powers` routes returned
**404 on the live Space** while GitHub `main` had them wired and passing. The
modules and Dockerfile COPYs were present in BOTH repos, so the instinct was
"register() throws at runtime." It does NOT.

Diagnosis method that settled it (no HF token needed):
1. `curl .../api/killinchu/openapi.json` on the live Space → count `paths`.
   Live = **231**; a faithful local repro of the Dockerfile env = **250**.
   The 404 routes were simply absent from the deployed openapi.
2. The inline `/api/killinchu/v1/doctrine` route (same serve.py, just above the
   register blocks) returned **200** on the Space — proving the deployed
   serve.py was an OLDER serve.py that stopped before the register blocks.

So: **404 on a Space route whose code exists on `main` ⇒ first check the Space's
deployed openapi path count vs. a local repro, before suspecting a runtime
exception.** register() failing would still leave a `NOT registered: <repr>`
line + traceback in the Space RUN logs; absence of routes from openapi with a
clean boot points to a stale deploy, not an exception.

Fix is always: push `main` to the Space + factory rebuild + re-probe (retry 3-6x
for transient egress flake; a `000` is egress, not a crashed app).

---

*Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>*
*Doctrine v11 LOCKED · 749/14/163.*
