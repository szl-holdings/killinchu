# NOAA / MarineCadastre AIS — August 2024 (coastal US) — bounded REAL-ROW sample

This directory holds the WarHacker **"Maritime AIS Data August 2024 (coastal US)"**
dataset wired into killinchu as a selectable governed source.

## What is shipped here (honest label — doctrine v11)

`AIS_2024_08_01_sample_coastal_ne.csv` — a **bounded SAMPLE of REAL rows** extracted
from the real NOAA daily file `AIS_2024_08_01.csv`:

- **Source:** NOAA / Marine Cadastre AIS vessel transit data
  (`https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/AIS_2024_08_01.zip`)
- **Schema (verbatim):** `MMSI, BaseDateTime, LAT, LON, SOG, COG, Heading,
  VesselName, IMO, CallSign, VesselType, Status, Length, Width, Draft, Cargo,
  TransceiverClass`
- **Bound:** US Northeast / Mid-Atlantic coastal bbox
  (lat 38–43, lon −75 to −68), first hour of 2024-08-01, one row per vessel.
- **Size:** ~120 real vessels (~13 KB) — demo-fast, repo-light.

**This is a SAMPLE of ONE DAY, not the full multi-GB August 2024 month.** It is
labelled `(sample)` everywhere in the API and UI. The rows are GENUINE NOAA AIS
records (not synthetic).

## Full / real ingest path

The parser (`szl_connectors/data_sources/ais_noaa_aug2024.py`) is written to the
real NOAA schema. Pointing it at a full `AIS_2024_08_*.csv`, or calling the
connector with `{"fetch": true}`, range-downloads and stream-inflates the real
NOAA zip and ingests real rows directly — same code path, no fabrication.
