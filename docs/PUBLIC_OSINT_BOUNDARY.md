# Killinchu Public Source Fabric v1

## Mission

Give Killinchu a real, repeatable public-source intelligence plane without
crossing into intrusion, covert collection, targeting, or data theft.

The fabric ingests only deliberately public information from a fixed registry
of official sources. Every fetch is HTTPS GET-only, size- and time-bounded,
content-hashed, cached, and labeled. A failed refresh serves an identified cache
or returns `UNAVAILABLE`; it never fabricates a feed.

## Non-negotiable boundary

The system does **not**:

- discover, probe, scan, exploit, or connect through “back doors”;
- bypass authentication, CAPTCHAs, robots rules, access controls, or protected
  government resources;
- collect credentials, leaked or stolen datasets, private communications,
  malware payloads, exploit code, dark-web material, or personal dossiers;
- ingest active troop/unit locations, equipment movements, coordinates,
  strike/target packages, or other data that could facilitate physical harm;
- treat public statements as independently verified truth;
- authorize automated targeting, interdiction, sanctions enforcement, or any
  other operational action.

Sanctions results are exact normalized list matches for compliance triage. A
match is `POSSIBLE_MATCH`; a miss is `NO_EXACT_MATCH`, never definitive
“clearance.” Human review remains mandatory.

## Admitted sources

| ID | Authority | Retained data | Explicit exclusion |
|---|---|---|---|
| `cisa-kev` | U.S. CISA | CVE identifiers, vendor/product, dates, defensive action, ransomware-use label | Exploit payloads, scanning, weaponization |
| `nsa-advisories` | U.S. NSA | Public advisory-index titles, dates, and public links | Any CAC/access-controlled `cyber.mil` material; document-body harvesting |
| `cia-public-stories` | U.S. CIA | Public news/story index metadata | Classified/non-public material; the retired World Factbook is not represented as live |
| `ofac-sdn` | U.S. Treasury OFAC | Public SDN names, aliases, programs, and maritime/aircraft identifiers | Automated enforcement or targeting; personal dossier fields |
| `un-dprk-1718` | UN Security Council | Public 1718 designation names, aliases, references, and listing dates | Targeting or operational intelligence |
| `cert-ua-advisories` | CERT-UA | Public defensive article/recommendation index metadata | Contact/reporting channels and any operational location-reporting content |
| `ukraine-open-data-metadata` | Data.gov.ua | Bounded CKAN catalog metadata for cyber, sanctions, and procurement themes | Resource downloads, active-force location/movement data, and personal-data registers |
| `china-cac-notices` | Cyberspace Administration of China | Public regulatory-notice titles, dates, and official links | Authentication, hidden endpoints, personal data, or document-body crawling |

### Source-specific evidence decisions

- CISA describes the Known Exploited Vulnerabilities Catalog as an authoritative
  input for vulnerability-management prioritization and publishes machine-readable
  formats. Killinchu retains defensive metadata only.
- OFAC’s Sanctions List Service is the primary public delivery application for
  sanctions files. OFAC’s current distribution redirects to a named public
  government-cloud S3 host and requires an explicit User-Agent; only that exact
  redirect host is accepted.
- The UN 1718 materials page publishes the DPRK sanctions list in XML. The fixed
  XML endpoint is admitted for compliance screening.
- NSA’s public index states that some additional documents have access
  requirements. Those protected resources are not admitted.
- Data.gov.ua documents CKAN GET endpoints and warns callers to inspect the JSON
  `success` field rather than trusting HTTP status alone. The connector enforces
  that rule and stores catalog metadata only.
- The CIA announced on February 4, 2026 that the World Factbook had sunset.
  Killinchu therefore does not claim a live Factbook feed.
- CERT-UA’s public site contains separate operational reporting instructions.
  The connector admits only article/recommendation links and explicitly excludes
  the reporting/contact surface.

## Routes

All routes are read-only and set `Cache-Control: no-store` on the Killinchu
response. Upstream freshness is controlled by bounded internal TTLs.

| Route | Function |
|---|---|
| `GET /api/killinchu/v1/osint/public/policy` | Machine-readable legal/safety and action-authority boundary |
| `GET /api/killinchu/v1/osint/public/sources` | Fixed registry; no network request |
| `GET /api/killinchu/v1/osint/public/health` | Cache/provenance status only; no forced refresh |
| `GET /api/killinchu/v1/osint/public/source/{source_id}` | Read one admitted source; unknown IDs return 404 |
| `GET /api/killinchu/v1/osint/public/sanctions/screen?name=...` | Exact normalized OFAC + UN compliance screen |

There is no arbitrary-URL route, no upstream query proxy, and no public
force-refresh switch.

## Truth vocabulary

- `LIVE`: the official source was fetched and parsed during the current call.
- `CACHED`: a previously hashed, source-bound result is being served.
- `UNTESTED`: no local cache exists; no claim is made about upstream health.
- `UNAVAILABLE`: no current fetch or usable cache exists.
- `PUBLIC_OFFICIAL_CLAIM`: the record came from the named official public source;
  the underlying assertion was not independently proven by Killinchu.
- `MEASURED_LIST_MATCH`: exact normalization and membership comparison performed
  by Killinchu over the identified list bytes.

## Provenance

Each source response includes:

- canonical source identity and classification;
- fetch time and cache age;
- HTTP/content-type metadata;
- SHA-256 of the exact upstream bytes;
- SHA-256 for every normalized record;
- excluded-item count and policy reason class;
- downstream sanctions-list loading state;
- `action_authority: NONE`.

Errors are bounded and scrubbed so signed redirect query strings, tokens, or
other sensitive URL parameters cannot enter logs or API responses.

## Runtime and deployment

`apply_killinchu_public_osint_frontier.py` performs a fail-closed source patch:

1. copies the connector, tests, registry, and this boundary document;
2. registers the connector before the existing OSINT block in `serve.py`;
3. extends the vessels screening loader with explicit source provenance while
   preserving existing operator-list behavior;
4. adds both runtime modules to the canonical Dockerfile;
5. runs `scripts/image_contract.py` to regenerate the byte-identical Hugging
   Face Dockerfile mirror and deterministic image manifest;
6. runs the focused test suite and `git diff --check` when requested.

The patch never reads or writes a secret. External egress can be disabled by
setting `KILLINCHU_PUBLIC_SOURCE_WARM=0`; routes still fetch lazily within their
TTL contract.
