# Vessels Domain — Consolidated into Killinchu

**Status:** RETIRED-INTO-KILLINCHU · **Date:** 2026-09-03 · **Doctrine:** v11 LOCKED · **Truth labels:** MEASURED / REPORTED / MODELED

## Declaration

Killinchu is the SZL Holdings defense vertical: **counter-UAS (air) + vessels (sea) in one governed operator picture.** The vessels vertical is consolidated here as a domain of killinchu, not a separate product. This charter makes the product story match the code that already ships in this repository.

## Retirement (2026-09-03)

The standalone vessels vertical is **retired**:

- `szl-holdings/vessels` (GitHub) — deleted from the organization.
- `SZLHOLDINGS/vessels` (Hugging Face Space) — probe shell, to be retired by the owner (connector tokens cannot write or delete pre-existing Spaces).
- All vessels capability now lives here, in killinchu.

With this retirement, the former capability gaps are closed:

| Capability | Status | Where |
|---|---|---|
| Dark-vessel detection | SHIPPED | `killinchu_maritime_risk.py` |
| Voyage analytics | SHIPPED | `killinchu_maritime_intel.py` |
| Fleet view | SHIPPED | `killinchu_fleet_vessels.py` + `killinchu_maritime_globe.py` |
| AIS ingest | SHIPPED | `killinchu_ais_aug2024.py` + connectors |
| Sanctions screening | SHIPPED (2026-09-03) | `killinchu_vessels_screening.py` — operator-supplied lists, fail-closed, MEASURED list-match. No live OFAC/EU/UN feed is connected or claimed. |
| Ownership graph analysis | SHIPPED (2026-09-03) | `killinchu_vessels_screening.py` — declared-ownership graph with effective-percentage beneficial-owner walk, REPORTED. Declarations are operator-supplied and not independently verified. |

**Wire-up note:** `killinchu_vessels_screening.py` requires registration in `serve.py` and a `COPY` line in the Space Dockerfile before it serves on the live surface (see KNOWN_GOTCHAS.md). Until wired, it is validated source, not a live endpoint.

## Existing maritime modules (MEASURED — in this repo today)

| Module | Role |
|---|---|
| `killinchu_maritime_globe.py` (122.5 KB) | Maritime globe visualization surface |
| `killinchu_maritime_intel.py` (46.4 KB) | Maritime intelligence / voyage analytics |
| `killinchu_maritime_risk.py` (42.0 KB) | Maritime risk assessment, dark-vessel detection |
| `killinchu_maritime_view.py` (49.8 KB) | Maritime operator view |
| `killinchu_fleet_vessels.py` (11.5 KB) | Fleet vessel surface |
| `fleet_vessels_data.json` (61.9 KB) | Fleet vessel dataset |
| `killinchu_ais_aug2024.py` (17.6 KB) | AIS ingestion (NOAA Aug 2024 corpus) |
| `szl_connectors/data_sources/ais_noaa_aug2024.py` | AIS data-source connector |
| `szl_connectors/data_sources/maritime_air.py` | Maritime/air fused data source |
| `killinchu_asw.py` (37.0 KB) | Anti-submarine warfare surface |
| `killinchu_naval_haps.py` (15.2 KB) | Naval HAPS (high-altitude platform) surface |
| `test_maritime_overlays.py` | Maritime overlay regression tests |
| `killinchu_vessels_screening.py` (9.5 KB) | Sanctions screening + ownership graph (retirement close-out) |

## Standalone vessels engine (transitional)

The standalone vessels API engine (position ingestion, haversine implied-speed anomalies, >1h dark-activity gaps, low-SOG loitering, fleet risk ranking) remains available at the [SZLHOLDINGS/vertical-services Space](https://huggingface.co/spaces/SZLHOLDINGS/vertical-services) under `/vessels/*`:

- `GET /vessels/healthz`
- `POST /vessels/v1/positions`
- `GET /vessels/v1/vessel/risk?imo=...`
- `GET /vessels/v1/fleet/risk`

Source: `szl-holdings/vertical-services` (GitHub canonical, Hub mirror). This is a transitional engine; the killinchu surface above is the product.

## Provenance

- Charter declared 2026-09-03 by betterwithage via connector.
- Retirement declared 2026-09-03 by betterwithage via connector.
- Module inventory measured from the repository file listing at commit `fa81186`.
- Screening/ownership module logic validated by test before commit (list-match, fail-closed, effective-pct walk, combined risk drivers).
- Λ = Conjecture 1 (advisory). Nothing here claims a proven Λ.
