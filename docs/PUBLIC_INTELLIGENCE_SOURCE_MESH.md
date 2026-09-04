# Killinchu Public-Intelligence Source Mesh

## Purpose

This mesh gives Killinchu a governed view of **official, public information** without turning the product into an unrestricted web proxy. It is designed for defensive situational awareness, compliance, research, and provenance-backed analysis.

It does **not** search for private systems, evade access controls, submit forms, authenticate to third-party services, scan networks, execute source content, or accept a caller-supplied URL.

## Sources

| Source ID | Authority | Jurisdiction | Material |
|---|---|---:|---|
| `cisa-kev` | CISA official KEV GitHub mirror | US | Known exploited vulnerability catalogue |
| `nvd-recent` | NIST NVD | US | CVE records through API 2.0 |
| `ofac-sdn` | US Treasury OFAC SLS | Global | SDN XML |
| `un-dprk-1718` | UN Security Council | DPRK-related | Consolidated-list records whose permanent reference begins `KPi.` or `KPe.` |
| `cia-world-leaders` | CIA World Leaders | Global | Public foreign-government directory |
| `nsa-advisories` | NSA | US | Public cybersecurity advisories and guidance only |
| `cert-ua` | CERT-UA | Ukraine | Public recommendations and notices |
| `ukraine-open-data` | Data.gov.ua | Ukraine | CKAN metadata for recently changed datasets |
| `china-mfa` | PRC Ministry of Foreign Affairs | China | Public English-language press conferences |
| `china-state-council` | PRC State Council | China | Public English-language policy releases |

The registry uses neutral jurisdiction labels. It does not encode a political designation such as ally, adversary, or enemy.

## API

- `GET /api/killinchu/v1/public-intel/sources` — declared registry and policy.
- `GET /api/killinchu/v1/public-intel/status` — measured in-process cache state; does not trigger network access.
- `GET /api/killinchu/v1/public-intel/{source_id}?limit=50` — one fixed source, bounded to 1–100 returned records.
- `GET /api/killinchu/v1/public-intel/digest?jurisdiction=all&limit=50` — bounded multi-source digest with at most three concurrent reads.

Unknown source IDs return `404`. Unknown jurisdictions return `400`. Upstream failure returns `503` for a single-source read and an explicit per-source state in a digest.

## Security envelope

Each source has an immutable URL, exact host allowlist, allowed redirect hosts, payload limit, parser, format, and TTL. Runtime retrieval enforces:

1. HTTPS only, standard port 443, and no URL user information.
2. DNS resolution to public addresses only; private, loopback, link-local, reserved, multicast, and unspecified addresses fail closed.
3. No caller-controlled destination, request body, cookie jar, authentication header, or environment proxy.
4. Redirect validation before following the redirect and validation of the final response URL.
5. `GET` only, `Accept-Encoding: identity`, a twelve-second timeout, a content-type allowlist, and a maximum byte count.
6. A per-source lock, source-specific TTL, and maximum digest concurrency of three.
7. Parsers that handle data as inert JSON, XML, or link-index text. Downloaded code and binaries are never executed.

## Evidence and honesty

A successful read is `MEASURED` for the transport and payload evidence. Individual content remains a `REPORTED` claim from the named source. Every successful envelope carries:

- source ID, authority, URL, jurisdiction, and category;
- fetch time, HTTP status, final URL, media type, ETag, and Last-Modified when supplied;
- byte count and SHA-256 hash of the exact payload;
- normalized records with a deterministic content hash.

A failed read is `UNAVAILABLE`, contains no invented count, and returns an empty item list. Cached results are explicitly marked `HIT`; a network read is `MISS`.

## Adding a source

A new source requires all of the following in one reviewed change:

- an official public authority and stable HTTPS URL;
- an exact host and redirect allowlist;
- a bounded payload and TTL;
- a deterministic parser with fixture tests;
- a neutral jurisdiction and category;
- confirmation that no authentication, protected resource, form submission, active scan, or arbitrary URL capability is introduced.
