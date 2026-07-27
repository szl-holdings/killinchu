# Killinchu Live Intel Archive — source-specific license contract

This file governs the dataset repository
`SZLHOLDINGS/killinchu-osint-corpus`. It does not replace the license notices
attached to individual sources.

## 1. Killinchu-authored material

The dataset card, schema descriptions, projection logic, integrity metadata,
and other original SZL Holdings documentation are licensed under the
[Apache License 2.0](https://github.com/szl-holdings/killinchu/blob/main/LICENSE).

That software/documentation license does **not** relicense third-party data.

## 2. adsb.lol aircraft observations

Records with `kind: adsb-aircraft` and `source: adsb` are derived from the
public [adsb.lol](https://adsb.lol/) API. adsb.lol states that its public API
data is available under the
[Open Data Commons Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/)
(ODbL-1.0).

Required boundary:

- preserve attribution to adsb.lol;
- comply with ODbL share-alike requirements when publicly using an adapted
  database;
- do not infer that every individual broadcast fact is free of separate rights
  or regulatory restrictions;
- do not present broadcast positions as verified truth.

Killinchu publishes a transformed projection: raw identifiers are replaced by
rotating HMAC pseudonyms, coordinates are coarsened, fields are normalized, and
records are deduplicated by time window and cell.

## 3. Fintraffic Digitraffic AIS observations

Records with `kind: ais-vessel` and `source: ais` are derived from
[Fintraffic Digitraffic](https://www.digitraffic.fi/) open data under
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)
(CC BY 4.0).

Attribution: **Fintraffic / digitraffic.fi**.

Killinchu modifies the source observations by pseudonymizing identifiers,
coarsening positions, selecting and normalizing fields, and adding provenance
and honesty metadata. Reusers must retain the attribution, link to the license,
and indicate that changes were made.

## 4. Open-web OSINT records

Records with `kind: osint-item` are normalized references to third-party public
web reporting. Each record preserves the original URL and host when available.
Copyright and database rights remain with the original publisher. Inclusion in
this archive:

- does not grant a blanket license to reproduce the underlying article or
  database;
- does not convert a public URL into public-domain content;
- does not certify the report as correct;
- requires reusers to evaluate and follow the original source's terms.

The archive should contain only bounded metadata and summaries generated for
indexing and analysis, not wholesale copies of source publications.

## 5. Privacy and integrity boundary

New platform observations use rotating pseudonyms and coarsened coordinates.
Historical pre-v2 append-only shards may contain raw identifiers; the public
API withholds those legacy platform rows, but this license file does not claim
the historical shards were rewritten or erased.

Record IDs and provenance hashes are integrity/deduplication identifiers, not
DSSE, Ed25519, or factual-verification signatures.

## 6. No warranty

All third-party observations and reports are provided as claims or broadcast
self-reports, without warranty of accuracy, completeness, availability, or
fitness for a particular purpose. Users remain responsible for legal,
regulatory, privacy, safety, and source-license compliance.
