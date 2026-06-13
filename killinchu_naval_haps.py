"""
killinchu_naval_haps.py — HAPS (stratospheric) tier + Maritime/Naval mode.
Doctrine v11, ADDITIVE. Final Sweep — Yachay, 2026-06-01.

Closes two gaps flagged in killinchu/yachay_dome/WHAT_FOUNDER_IS_MISSING.md:
  - Gap 5 (HAPS tier): stratospheric platforms (Aalto Zephyr 8, BAE PHASA-35) are
    both a threat surface and a persistent-sensor opportunity above conventional UAS groups.
  - Gap 4 (Maritime adjacency): uncrewed surface/undersea vessels (USVs/UUVs) are now a
    primary threat (Houthi, Ukraine Black Sea). Same detect-classify-cue pipeline applies
    to drone boats threatening ports / LNG / cargo — sells to USCG and port authorities.

HARD LEGAL BOUNDARY (unchanged): WE SENSE, WE EVIDENCE — passive detection and
auditable cue packages only. We do NOT operate these platforms or engage targets.
All catalog numbers carry primary-source citations.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Callable

from fastapi import Request
from fastapi.responses import JSONResponse


# ---------------------------------------------------------------------------
# HAPS — High-Altitude Pseudo-Satellite tier (stratospheric, >18 km).
# Sits ABOVE conventional UAS Group 1-5 ceilings; persistent sensor opportunity.
# ---------------------------------------------------------------------------
HAPS_PLATFORMS = [
    {
        "id": "aalto_zephyr8",
        "name": "AALTO Zephyr 8 (formerly Airbus Zephyr)",
        "operator": "AALTO HAPS (Airbus subsidiary), Farnborough UK",
        "class": "Solar-electric fixed-wing HAPS",
        "ceiling_m": 23200,            # ~76,100 ft
        "wingspan_m": 25,
        "mass_kg": 62,                 # 62-65 kg, ~40% batteries
        "payload_kg": 5,
        "endurance": "Record 64 days continuous; target 200+ days on station",
        "killinchu_use": "Persistent stratospheric ISR host above conventional UAS traffic; "
                         "one platform covers ~20x30 km footprint at 18 cm-class optical resolution, "
                         "or a comms relay. Also a THREAT SURFACE: a hostile HAPS is a long-dwell sensor we must track.",
        "modality": "EO/IR + comms relay (Strat-Observer 18 cm optical; ~7,500 km^2 connectivity reach)",
        "source": "https://www.airbus.com/en/products-services/defence/uas/zephyr  |  https://en.wikipedia.org/wiki/Airbus_Zephyr",
    },
    {
        "id": "bae_phasa35",
        "name": "BAE Systems PHASA-35",
        "operator": "BAE Systems (UK/US); 5-yr AFRL contract Dec 2025",
        "class": "Solar-electric HALE/HAPS UAS",
        "ceiling_m": 20000,            # stratospheric, ~65,000 ft class
        "wingspan_m": 35,
        "mass_kg": 150,                # ~weight of a motorbike
        "payload_kg": 15,
        "endurance": "Designed for up to 12 months airborne (day solar / night battery)",
        "killinchu_use": "Higher-payload (15 kg) stratospheric sensor host for border, maritime, and "
                         "military surveillance; AFRL-funded so a credible allied platform to integrate cues from.",
        "modality": "Sensing + communications relay; advanced composites + solar arrays",
        "source": "https://www.baesystems.com/en-us/product/phasa-35  |  https://en.wikipedia.org/wiki/BAE_Systems_PHASA-35",
    },
    {
        "id": "airbus_zephyr_line",
        "name": "Airbus Zephyr line (heritage + 2026 larger variant)",
        "operator": "Airbus Defence and Space / AALTO (commercialized via AALTO since Jan 2023)",
        "class": "Solar-electric fixed-wing HAPS family",
        "ceiling_m": 23200,
        "wingspan_m": 25,
        "mass_kg": 60,
        "payload_kg": 5,
        "endurance": "Months on station; larger 2x-payload variant expected 2026",
        "killinchu_use": "Reference baseline for the stratospheric T-HAPS tier; NTT Docomo / Space Compass "
                         "$100M consortium commercializing connectivity HAPS in Asia (2026 target).",
        "modality": "EO + direct-to-device connectivity ('tower in the sky')",
        "source": "https://en.wikipedia.org/wiki/Airbus_Zephyr  |  https://www.gpsworld.com/uas-updates-advancements-in-integration-new-uav-approvals-and-more/",
    },
]


# ---------------------------------------------------------------------------
# Maritime / Naval drone catalog — Uncrewed Surface & Undersea Vessels.
# Same four-color gate + /v1/cue pipeline; surface-track kinematics.
# ---------------------------------------------------------------------------
NAVAL_DRONES = [
    {
        "id": "saronic_spyglass",
        "name": "Saronic Spyglass (6')",
        "country": "USA",
        "side": "allied",
        "type": "USV (small autonomous surface vessel)",
        "length_m": 1.8,
        "kinematics": {"top_speed_kn": 35, "range_nm": "see Saronic small-ASV line"},
        "killinchu_use": "Allied reference USV — baseline for friendly-track classification and IFF de-confliction in the naval gate.",
        "source": "https://www.saronic.com/vessels  |  https://thedefensepost.com/2024/10/24/saronic-unmanned-vessel-pentagons/",
    },
    {
        "id": "saronic_corsair",
        "name": "Saronic Corsair (24')",
        "country": "USA",
        "side": "allied",
        "type": "USV (medium autonomous surface vessel)",
        "length_m": 7.31,
        "kinematics": {"top_speed_kn": 35, "range_nm": 1000, "payload_lb": 1000},
        "killinchu_use": "Allied blue-water USV; maritime domain awareness + effects delivery (customer-operated, not us).",
        "source": "https://www.navalnews.com/naval-news/2025/04/saronic-unveils-two-new-autonomous-surface-vessels-mirage-and-cipher/",
    },
    {
        "id": "anduril_dive_ld",
        "name": "Anduril Dive-LD",
        "country": "USA",
        "side": "allied",
        "type": "UUV (autonomous undersea vehicle)",
        "length_m": None,
        "kinematics": {"max_depth_m": 6000, "submerged_endurance_days": 10},
        "killinchu_use": "Allied UUV — extends the catalog to the subsurface domain (ISR, MCM, ASW, seafloor mapping).",
        "source": "https://www.worlddefenseshow.com/en/media/news/45  |  https://navyleaders.com/news/anduril-selected-to-field-next-generation-autonomous-submarines-for-u-s-navy/",
    },
    {
        "id": "houthi_toofan",
        "name": "Houthi Toofan-class USV",
        "country": "Yemen (Houthi)",
        "side": "adversary",
        "type": "USV (one-way attack / explosive surface drone)",
        "length_m": None,
        "kinematics": {"note": "Red Sea / Bab-el-Mandeb attack profile; explosive payload"},
        "killinchu_use": "ADVERSARY surface-track exemplar threatening shipping lanes; passive detect-classify-cue only.",
        "source": "https://www.hisutton.com/Ukrainian-USVs-Russo-Ukraine-War.html",
    },
    {
        "id": "ukraine_magura_v5",
        "name": "Magura V5",
        "country": "Ukraine",
        "side": "adversary_model",   # adversary-capability model (used by Ukraine vs Russian fleet) — kinematic exemplar
        "type": "USV (long-range attack surface drone; air-defense 'Sea Dragon' variant exists)",
        "length_m": 5.5,
        "kinematics": {"top_speed_kn": 42, "cruise_kn": 22, "range_nm": 450, "payload_kg": 320, "endurance_h": 60},
        "killinchu_use": "Kinematic exemplar of a fast, long-range one-way-attack USV — drives the surface-track "
                         "predict-impact envelope (450 nm range, 42 kn dash). First USV class to down aircraft.",
        "source": "https://en.wikipedia.org/wiki/MAGURA_V5  |  https://www.hisutton.com/Ukrainian-USVs-Russo-Ukraine-War.html",
    },
    {
        "id": "ukraine_sea_baby",
        "name": "Sea Baby",
        "country": "Ukraine",
        "side": "adversary_model",
        "type": "USV (large-payload attack surface drone)",
        "length_m": 6.0,
        "kinematics": {"width_m": 2.0, "note": "Large explosive payload; SBU-operated against Black Sea Fleet"},
        "killinchu_use": "Large-payload USV exemplar; widens the predict-impact payload range for port-threat modeling.",
        "source": "https://www.hisutton.com/Ukrainian-USVs-Russo-Ukraine-War.html",
    },
]

# Cited real leader sources surfaced in every maritime/HAPS tab payload.
# AIS live feeds are mostly key-gated (Spire / aisstream.io / MarineTraffic) so the
# vessel catalog stays a cited SAMPLE — but each tab carries primary leader sources.
MARITIME_SOURCES = [
    {"leader": "IMO (International Maritime Organization)", "kind": "SOLAS Ch.V AIS carriage + maritime safety standards",
     "url": "https://www.imo.org/", "data_kind": "standard"},
    {"leader": "ITU-R M.1371", "kind": "AIS technical broadcast standard",
     "url": "https://www.itu.int/rec/R-REC-M.1371", "data_kind": "standard"},
    {"leader": "U.S. Coast Guard NAVCEN", "kind": "AIS overview + MMSI authority",
     "url": "https://www.navcen.uscg.gov/automatic-identification-system-overview", "data_kind": "standard"},
    {"leader": "H I Sutton (Covert Shores)", "kind": "open-source USV/UUV order-of-battle reporting",
     "url": "https://www.hisutton.com/", "data_kind": "osint_reporting"},
]

HAPS_SOURCES = [
    {"leader": "Airbus / AALTO HAPS", "kind": "Zephyr stratospheric platform (primary spec source)",
     "url": "https://www.airbus.com/en/products-services/defence/uas/zephyr", "data_kind": "primary_spec"},
    {"leader": "BAE Systems", "kind": "PHASA-35 HALE/HAPS platform (primary spec source)",
     "url": "https://www.baesystems.com/en-us/product/phasa-35", "data_kind": "primary_spec"},
    {"leader": "ICAO", "kind": "stratospheric/upper-airspace operations framework",
     "url": "https://www.icao.int/", "data_kind": "standard"},
]

# AIS integration — cooperative maritime identity (analogue of ADS-B for ships).
AIS_INTEGRATION = {
    "standard": "ITU-R M.1371 AIS (Automatic Identification System)",
    "cooperative_provider": "Spire Global (Maritime / satellite AIS)",
    "killinchu_use": "Cross-check a surface track against cooperative AIS. An UNCOOPERATIVE / 'dark' "
                     "contact (no AIS, or AIS inconsistent with radar/RF) raises the threat color — exactly "
                     "the maritime analogue of a Remote-ID-OFF 'dark drone'.",
    "honesty": "AIS is an UNAUTHENTICATED broadcast: a decoded MMSI/position is a CLAIM, not attested truth "
               "(same posture as ADS-B / Remote-ID). Spoofed/absent AIS is itself a detection signal, not ground truth.",
    "source": "https://spire.com/maritime/  |  https://www.itu.int/rec/R-REC-M.1371",
}


def register_naval_haps(app, *, emit_receipt: Callable, json_body: Callable, doctrine: str) -> None:
    """Wire HAPS + naval-mode endpoints onto the existing FastAPI app (ADDITIVE)."""

    def _sha(*parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    # ---- HAPS tier (T-HAPS) ----
    @app.get("/api/killinchu/v1/haps")
    async def haps():
        return JSONResponse({
            "ok": True,
            "tier": "T-HAPS",
            "definition": "Stratospheric high-altitude pseudo-satellites (>18 km), ABOVE conventional UAS Group 1-5 ceilings.",
            "count": len(HAPS_PLATFORMS),
            "platforms": HAPS_PLATFORMS,
            "data_kind": "catalog_sample_cited",
            "sources": HAPS_SOURCES,
            "dual_role": "Each HAPS is BOTH a threat surface (long-dwell hostile sensor to track) AND a "
                         "persistent-sensor opportunity (allied ISR/comms host above the weather and air traffic).",
            "doctrine": doctrine,
            "honesty": "Killinchu does not operate HAPS platforms; it would consume cues/feeds from allied "
                       "HAPS and treat hostile HAPS as tracks. Catalog is a cited SAMPLE — specs attributed "
                       "to operator/primary sources (Airbus/AALTO, BAE); not a live telemetry feed.",
        })

    # ---- Maritime / Naval mode ----
    @app.get("/api/killinchu/v1/naval-mode")
    async def naval_mode():
        return JSONResponse({
            "ok": True,
            "mode": "naval",
            "definition": "Same four-color gate + /v1/cue pipeline applied to UNCREWED SURFACE/UNDERSEA "
                          "VESSELS (USVs/UUVs) threatening ports, LNG terminals, and cargo.",
            "catalog_count": len(NAVAL_DRONES),
            "catalog": NAVAL_DRONES,
            "data_kind": "catalog_sample_cited",
            "sources": MARITIME_SOURCES,
            "ais_integration": AIS_INTEGRATION,
            "cued_engagement": {
                "pipeline": "detect -> classify (four-color) -> predict-impact (surface-track kinematics) -> "
                            "Khipu-receipted cue package -> authorized customer (USCG / port authority / .mil) acts.",
                "kinematics_note": "Surface tracks use 2-D great-circle (haversine) motion + wake/radar/RF/EO fusion; "
                                   "predict-impact envelope driven by exemplar speeds/ranges (e.g. Magura V5: 42 kn, 450 nm).",
                "legal": "WE SENSE, WE EVIDENCE. Counter-USV mitigation is a customer-effector function under "
                         "the customer's own authority — Killinchu delivers the signed cue, never the kinetic act.",
            },
            "buyers": ["U.S. Coast Guard", "Port authorities / MTSA facilities", "Navy / MARFOR (cue consumer)"],
            "doctrine": doctrine,
            "honesty": "USV/UUV catalog mixes allied reference platforms and adversary-capability exemplars; "
                       "AIS and RF are unauthenticated broadcasts (claims, not attested truth).",
        })

    # ---- Naval cue (passive, receipted) — surface-track Body-of-Evidence ----
    @app.api_route("/api/killinchu/v1/naval-mode/cue", methods=["POST"])
    async def naval_cue(request: Request):
        body = await json_body(request)
        track_id = str(body.get("track_id", "unknown"))
        lat = body.get("lat")
        lon = body.get("lon")
        ais_present = bool(body.get("ais_present", False))
        color = str(body.get("color", "unknown"))  # white/green/yellow/red four-color
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        cue_id = _sha("naval-cue", track_id, str(lat), str(lon), ts)
        receipt = emit_receipt("naval_cue", {
            "track_id": track_id, "lat": lat, "lon": lon,
            "ais_present": ais_present, "color": color, "ts": ts, "cue_id": cue_id,
        })
        return JSONResponse({
            "ok": True,
            "cue_id": cue_id,
            "track_id": track_id,
            "color": color,
            "ais_present": ais_present,
            "dark_contact": (not ais_present),
            "receipt": receipt,
            "legal": "WE SENSE, WE EVIDENCE — signed cue handed to the authorized customer; we do not engage.",
            "doctrine": doctrine,
            "honesty": "Cue is a Khipu-receipted Body-of-Evidence package; AIS/RF inputs are claims, not attested truth.",
        })

    print("[killinchu] naval + HAPS endpoints registered", file=__import__("sys").stderr)
