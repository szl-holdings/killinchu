---
license: other
license_name: mixed-source-terms
license_link: https://github.com/szl-holdings/killinchu/blob/main/datasets/killinchu-osint-corpus/LICENSE.md
pretty_name: killinchu live intel archive
tags:
  - osint
  - adsb
  - ais
  - aviation
  - maritime
  - szl-holdings
configs:
  - config_name: archive_manifest
    default: true
    data_files:
      - split: train
        path: "viewer/archive_manifest.jsonl"
---

# killinchu — live intel archive

Append-only, content-addressed archive of the live intelligence streams the
**killinchu** demo ingests, published by SZL Holdings. The shared
`szl_hf_bucket` client writes one NDJSON shard per UTC day under
`{{ARCHIVE_PREFIX}}/`.

Each row is `{schema, id, ts, source, kind, payload}`.

## Viewer-safe contract

The default Dataset Viewer configuration is the homogeneous
`archive_manifest`, one row per immutable raw shard. It exposes path, byte
count, Git blob hash, rights state, and training eligibility. The mixed raw
NDJSON remains available under `{{ARCHIVE_PREFIX}}/*.ndjson` but is deliberately not
coerced into one table: historical shards contain schema drift, and mixing
numbers and strings in fields such as `alt_baro` breaks strict dataset loaders.

This is a usability repair, not a rewrite of append-only history. Every raw
manifest row is `training_eligible: false` until row-level rights and privacy
admission are established.

## License and attribution

This dataset is intentionally declared `license: other` because its records come
from independent upstream sources under different terms. The complete,
source-specific contract is in [LICENSE.md](./LICENSE.md).

- `kind: adsb-aircraft` (`source: adsb`) — public aircraft data from
  [adsb.lol](https://adsb.lol/), distributed by adsb.lol under the
  [Open Data Commons Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
- `kind: ais-vessel` (`source: ais`) — vessel-position data from
  [Fintraffic Digitraffic](https://www.digitraffic.fi/), licensed under
  [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
  Attribution: **Fintraffic / digitraffic.fi**. The archive is a transformed,
  coarsened projection; changes are identified below.
- `kind: osint-item` (`source: <vertical>`) — normalized open-web reports. Each
  record preserves its source URL and host.
  Rights remain with the original publisher; inclusion here does not grant
  additional reuse rights.

The Apache-2.0 license for Killinchu's software and projection code does **not**
relicense the third-party records in this dataset.

## Streams

- `adsb-aircraft` — rotating-pseudonym, coarsened aircraft observations.
- `ais-vessel` — rotating-pseudonym, coarsened vessel observations.
- `osint-item` — normalized public-web claims, active only when a search key is
  configured.

## Transformation notice

For new platform rows, Killinchu:

- replaces raw aircraft/vessel identifiers with rotating, secret-keyed **HMAC pseudonyms**;
- rounds positions to approximately `{{ARCHIVE_CELL}}°` cells;
- normalizes selected kinematic fields;
- adds source, observation-window, and honesty metadata;
- deduplicates by pseudonym, UTC hour, and cell.

New platform rows declare projection schema `{{PROJECTION_SCHEMA}}`. Historical
pre-v2 rows may remain in append-only shards and may contain raw platform
identifiers. The public `/osint/archive/recent` API withholds those legacy rows;
this card does not claim that historical backing shards were rewritten.

## Honesty boundary

- No "proven" or "verified" claim is made about the truth of any item.
- Every record is a **third-party CLAIM or broadcast self-report**, not attested
  truth. Positions and reports can be spoofed, delayed, incomplete, or wrong.
- `track_id` is a rotating HMAC pseudonym. The record `id` and `prov_hash` values
  are SHA-256 content addresses for deduplication and integrity, **not a DSSE / Ed25519 signature**.
- The archive is append-only and bounded; re-observation does not imply
  independent corroboration.
