#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
verify_onebit.py — DEPLOY-AGNOSTIC correctness proof for the 1-bit sovereign inference organ.

Exercises all 4 onebit endpoints (/onebit/{manifest,estimate,methodology,fleet-readiness})
by calling the organ's pure functions directly (no server, no network, no Hugging Face Space)
and asserts every Doctrine-v11 honesty invariant that matters for THIS organ:

  * label == "MODELED" verbatim on all 4 endpoints
  * a SZL-MODELED energy number is NEVER labeled measured
  * the MEASURED (Microsoft, instrument-unstated) vs ESTIMATED (Microsoft, analytical) vs
    SZL-MODELED channels are ALWAYS present and separated
  * the honest independent-RAPL counter-figure is present
  * provenance / citation on EVERY methodology claim (full coverage)
  * fleet-readiness is OFFLINE with NO fabricated measured joules
  * determinism (same inputs => identical), input-sensitivity
  * register() returns the 4 exact paths
  * Λ stays Conjecture 1; bitnet cited not claimed as SZL's own; banned-token guard works

Run:  python3 verify_onebit.py
Exit: 0 = all invariants hold (prints RESULT: ALL PASS); non-zero = a real violation.
"""
import sys

import szl_kc_onebit as OB

FAILS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    if not cond:
        FAILS.append(name + (" — " + detail if detail else ""))
    print(f"  [{status}] {name}" + (f"  ({detail})" if detail and not cond else ""))


def main() -> int:
    print("1-bit sovereign inference — deploy-agnostic Doctrine-v11 verifier\n")

    # Deploy-agnostic + NETWORK-INDEPENDENT: the honesty invariants are exercised on the
    # OFFLINE (read_meter=False) path so this verifier is deterministic whether or not the
    # live meter is reachable (Doctrine v11: meter down => graceful MODELED/OFFLINE). The
    # MEASURED-live path is proven separately below with a synthetic live meter (no network).
    mf = OB.onebit_manifest()
    est = OB.onebit_estimate(model_params_b=2.4, n_tokens=512, read_meter=False)
    meth = OB.onebit_methodology()
    fleet = OB.onebit_fleet_readiness(read_meter=False)
    c = est["channels"]
    szl = c["c_szl_modeled"]

    # ---- label == "MODELED" verbatim on all 4 endpoints ----
    print("label (MODELED verbatim on all 4 endpoints):")
    check("manifest label MODELED", mf["label"] == "MODELED", f"got {mf['label']!r}")
    check("estimate label MODELED", est["label"] == "MODELED", f"got {est['label']!r}")
    check("methodology label MODELED", meth["label"] == "MODELED", f"got {meth['label']!r}")
    check("fleet label MODELED", fleet["label"] == "MODELED", f"got {fleet['label']!r}")

    # ---- SZL-MODELED number NEVER measured ----
    print("SZL-MODELED number is NEVER measured:")
    check("szl is_measured is False", szl["is_measured"] is False)
    check("measured_vs_modeled szl not measured",
          est["measured_vs_modeled"]["szl_number_is_measured"] is False)
    check("measured_vs_modeled MS Table6 not measured",
          est["measured_vs_modeled"]["microsoft_table6_is_measured"] is False)
    check("measured_vs_modeled MS 12x not measured",
          est["measured_vs_modeled"]["microsoft_12x_is_measured"] is False)

    # ---- measured vs modeled separation present (three distinct channels) ----
    print("MEASURED vs ESTIMATED vs SZL-MODELED separation present:")
    check("three canonical channels present + separated",
          {"a_measured_by_microsoft", "b_estimated_by_microsoft",
           "c_szl_modeled"}.issubset(set(c.keys())),
          f"got {sorted(c.keys())}")
    check("measured-live channel absent when meter down (never fabricated)",
          c.get("d_szl_measured_live") is None and est["measured_context"] is None
          and est["meter_reachable"] is False)
    check("MS Table6 baseline is vs llama.cpp not FP16",
          "NOT vs FP16" in c["a_measured_by_microsoft"]["baseline"])
    check("MS Table6 instrument UNDISCLOSED",
          "UNDISCLOSED" in c["a_measured_by_microsoft"]["instrument"])
    check("MS 12x column literally 'Estimated'",
          "Estimated" in c["b_estimated_by_microsoft"]["column_header_verbatim"])
    check("82.2% headline maps to x86 7B cell",
          c["a_measured_by_microsoft"]["j_per_token"]["intel_i7_13700h"]["7B"]["saving_pct"] == 82.2)

    # ---- honest independent-RAPL counter-figure present ----
    print("honest independent-RAPL counter-figure present:")
    r = est["independent_rapl_counter_figure"]
    check("RAPL same-class ~1.26x-1.7x", "1.26x-1.7x" in r["finding_same_class"])
    check("RAPL matched-quality ~42%", "42%" in r["finding_matched_quality"])
    check("RAPL throughput-driven not watts", "throughput" in r["why"].lower())
    check("RAPL cited to Zenn study", r["citation"].startswith("https://zenn.dev/"))

    # ---- SZL-MODELED estimate sanity (ternary cheaper, compression>1, footprints ordered) ----
    print("SZL-MODELED estimate sanity:")
    check("ternary joules/token < fp16",
          szl["joules_per_token_modeled"] < szl["joules_per_token_fp16_modeled"])
    check("speedup_vs_fp16 > 1", szl["speedup_vs_fp16_modeled"] > 1.0,
          f"got {szl['speedup_vs_fp16_modeled']}")
    check("energy_reduction_pct in (0,100)",
          0.0 < szl["energy_reduction_pct_vs_fp16_modeled"] < 100.0,
          f"got {szl['energy_reduction_pct_vs_fp16_modeled']}")
    check("tokens_per_joule > 0", szl["tokens_per_joule_modeled"] > 0.0)
    fp = szl["memory_footprint_modeled"]
    check("compression_x > 1", fp["compression_x"] > 1.0, f"got {fp['compression_x']}")
    check("ternary footprint < fp16 footprint",
          fp["footprint_gib_ternary"] < fp["footprint_gib_fp16"])
    check("bits_per_param_ternary == 1.58", fp["bits_per_param_ternary"] == 1.58)

    # ---- provenance full: every methodology claim cited ----
    print("provenance full (every methodology claim cited):")
    check("every_claim_has_citation True", meth["every_claim_has_citation"] is True)
    check("all claims have non-empty citation list",
          all(c2.get("citation") for c2 in meth["claims"]),
          "some claim missing citation")
    check("real + modeled + measurable all represented",
          meth["real_count"] >= 1 and meth["modeled_count"] >= 1 and meth["measurable_count"] >= 1,
          f"real={meth['real_count']} modeled={meth['modeled_count']} measurable={meth['measurable_count']}")
    check("100B claim flagged as extrapolation/modeled",
          any("100B" in c2["claim"] and "MODELED" in c2["status"] for c2 in meth["claims"]))
    check("contested-SOTA claim present (Intel PyTorch-TPP)",
          any("uncontested SOTA" in c2["claim"] for c2 in meth["claims"]))

    # ---- fleet-readiness: OFFLINE when meter down, NO fabricated measured joules ----
    print("fleet-readiness OFFLINE (meter down) with NO fabricated measured joules:")
    check("fleet_status OFFLINE", fleet["fleet_status"] == "OFFLINE")
    check("measured_joules_available False", fleet["measured_joules_available"] is False)
    check("measured_joules is None", fleet["measured_joules"] is None)
    check("measured_channel is None", fleet["measured_channel"] is None)
    check("measured_evidence empty", fleet["measured_evidence"] == {})
    check("all current numbers labeled MODELED", fleet["all_current_numbers_are"] == "MODELED")
    check(">=3 flip conditions (modeled->measured)",
          len(fleet["what_flips_modeled_to_measured"]) >= 3,
          f"got {len(fleet['what_flips_modeled_to_measured'])}")
    check("flip conditions name RAPL/wall-power",
          all(("RAPL" in x["instrument"] or "wall" in x["instrument"].lower())
              for x in fleet["what_flips_modeled_to_measured"]))

    # ---- manifest honesty_invariants block all True ----
    print("manifest honesty_invariants block:")
    inv = mf["honesty_invariants"]
    for k in ("label_is_MODELED", "szl_number_never_measured", "measured_and_modeled_separated",
              "microsoft_12x_labeled_estimated", "microsoft_table6_instrument_unstated",
              "independent_rapl_counter_present", "every_claim_has_citation",
              "fleet_offline_no_measured_when_meter_down", "lambda_is_conjecture_not_theorem",
              "bitnet_cited_not_claimed_as_own",
              # NEW measured-live discipline invariants
              "measured_channel_only_when_live_true", "never_fabricate_when_meter_down"):
        check(f"invariant {k}", inv.get(k) is True, f"got {inv.get(k)}")

    # ---- Λ stays Conjecture 1; bitnet cited not owned ----
    print("Λ Conjecture 1 untouched; bitnet cited not owned:")
    check("manifest lambda is Conjecture 1", "Conjecture 1" in mf["lambda"])
    check("estimate lambda is Conjecture 1", "Conjecture 1" in est["lambda"])
    check("bitnet repo cited to microsoft",
          OB.CITATIONS["bitnet_cpp_repo"].startswith("https://github.com/microsoft"))
    check("builds_on szl_kc_ternary (no duplication)", "szl_kc_ternary" in mf["builds_on"])

    # ---- determinism + input sensitivity ----
    print("determinism (same inputs => identical) + input sensitivity:")
    check("estimate deterministic (offline path)",
          OB.onebit_estimate(2.4, 512, read_meter=False)
          == OB.onebit_estimate(2.4, 512, read_meter=False))
    check("manifest deterministic", OB.onebit_manifest() == OB.onebit_manifest())
    check("methodology deterministic", OB.onebit_methodology() == OB.onebit_methodology())
    check("fleet deterministic (offline path)",
          OB.onebit_fleet_readiness(read_meter=False) == OB.onebit_fleet_readiness(read_meter=False))
    check("estimate responds to model size",
          OB.onebit_estimate(7.0, 512, read_meter=False)
          != OB.onebit_estimate(2.4, 512, read_meter=False))

    # ---- banned-token guard works ----
    print("banned-token guard:")
    _rejected = False
    try:
        OB._assert_no_banned("this is a " + "yranoitulover"[::-1] + " " + "hguorhtkaerb"[::-1])
    except ValueError:
        _rejected = True
    check("banned tokens rejected", _rejected)
    _clean = True
    try:
        OB._assert_no_banned(OB._HONEST_NOTE)
    except ValueError:
        _clean = False
    check("own honesty note is clean", _clean)

    # ---- registration returns the 4 exact paths ----
    print("registration:")
    class _App:
        class _R:
            def __init__(self): self.routes = []
        def __init__(self): self.router = self._R()
        def add_api_route(self, p, fn, methods=None): self.router.routes.append(p)
    routes = OB.register(_App(), ns="killinchu")
    check("register returns 4 exact paths", routes == [
        "/api/killinchu/v1/onebit/manifest",
        "/api/killinchu/v1/onebit/estimate",
        "/api/killinchu/v1/onebit/methodology",
        "/api/killinchu/v1/onebit/fleet-readiness",
    ], f"got {routes}")

    # ---- MEASURED-live path (synthetic live meter — no network, deterministic) ----
    print("MEASURED-live path with a synthetic live meter (only measured on live=true):")
    synthetic = {
        "url": OB.CITATIONS["szl_live_joule_meter"],
        "exporter": "omen-joule-exporter (real NVML via nvidia-smi)",
        "ts": 1783435960.47, "fetched_at": 1783435961.0,
        "totals": {"joules": 6937.669},
        "engines": [{"engine": "omen", "joules": 6937.669, "gpus": [
            {"index": 0, "name": "NVIDIA GeForce RTX 4060 Ti",
             "power_w": 6.17, "joules": 6937.669, "live": True}]}],
        "live": True,
    }
    est_on = OB.onebit_estimate(2.4, 512, meter=synthetic)
    est_off = OB.onebit_estimate(2.4, 512, read_meter=False)
    mc = est_on["measured_context"]
    check("measured_context populates on live=true", mc is not None and mc["is_measured"] is True)
    check("measured_context has real 4060 Ti watts",
          mc is not None and mc["total_power_w_measured"] == 6.17, f"got {mc}")
    check("SZL_MEASURED_LIVE channel names the real GPU",
          est_on["channels"]["d_szl_measured_live"]["engines"][0]["gpus"][0]["name"]
          == "NVIDIA GeForce RTX 4060 Ti")
    check("live measured context NEVER changes the MODELED number",
          est_on["channels"]["c_szl_modeled"]["joules_per_token_modeled"]
          == est_off["channels"]["c_szl_modeled"]["joules_per_token_modeled"])
    check("measured_vs_modeled marks measured_context measured only when live",
          est_on["measured_vs_modeled"]["measured_context_is_measured"] is True
          and est_off["measured_vs_modeled"]["measured_context_is_measured"] is False)
    flr_on = OB.onebit_fleet_readiness(meter=synthetic)
    check("fleet ONLINE on live meter", flr_on["fleet_status"] == "ONLINE")
    check("fleet reports real measured joules (not null, not hardcoded)",
          flr_on["measured_joules"] == 6937.669)
    check("fleet lists engines present (omen)", "omen" in flr_on["engines_present"])
    check("fleet real per-engine 4060 Ti watts from live read",
          flr_on["measured_per_engine"][0]["gpus"][0]["power_w_measured"] == 6.17)
    # Guard: unreachable/garbage meter never yields a measured number.
    check("unreachable meter reads None (guarded, no crash)",
          OB.read_live_meter(url="http://127.0.0.1:1/", timeout=0.2) is None)
    check("None meter => no measured channel", OB._measured_live_channel(None) is None)

    print()
    if FAILS:
        print(f"RESULT: {len(FAILS)} INVARIANT(S) VIOLATED:")
        for f in FAILS:
            print("  - " + f)
        return 1
    print("RESULT: ALL PASS — the 1-bit sovereign inference organ is correct at the source, "
          "with the MEASURED-vs-MODELED distinction enforced, independent of any deploy host.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
