"""Killinchu Public Source Fabric — lawful, bounded, source-bound OSINT.

This module ingests only deliberately public, official information through a
fixed allowlist.  It is not a crawler, an exploit scanner, a credential
collector, a targeting service, or a way around authentication.  The runtime
performs HTTPS GET requests only, follows redirects only to explicitly allowed
hosts, limits response size and time, records SHA-256 provenance, and fails
closed to CACHED or UNAVAILABLE.

Operational boundaries
----------------------
* No arbitrary URL input and no user-supplied HTTP headers.
* No POST/PUT/PATCH/DELETE requests to upstream sources.
* No login, CAPTCHA, robots, access-control, or paywall bypass.
* No collection of leaked/stolen material, credentials, malware payloads,
  exploit code, private communications, personal dossiers, or dark-web data.
* No ingestion of active-force locations, movement coordinates, strike/target
  packages, or other data that could facilitate physical harm.
* Cyber records are defensive advisories and vulnerability metadata only.
* Sanctions matches support compliance/manual review only and authorize no
  operational action.
* Third-party/public records remain source claims, not independently attested
  truth.  Decorative or modeled data is never promoted to measured telemetry.

The module can publish verified public OFAC and UN names into the existing
``killinchu_vessels_screening`` exact-match store when that module is present.
The list match is measured; the source's assertions remain REPORTED.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

VERSION = "1.0.0"
SCHEMA = "szl.killinchu.public-source-fabric/v1"
USER_AGENT = os.environ.get(
    "KILLINCHU_PUBLIC_SOURCE_USER_AGENT",
    "killinchu-public-source/1.0 (+https://github.com/szl-holdings/killinchu)",
).strip()
CACHE_ROOT = Path(
    os.environ.get("KILLINCHU_PUBLIC_SOURCE_DIR", "/tmp/killinchu-public-source")
)
DEFAULT_TIMEOUT_SECONDS = min(
    20.0,
    max(2.0, float(os.environ.get("KILLINCHU_PUBLIC_SOURCE_TIMEOUT", "10"))),
)
WARM_INTERVAL_SECONDS = max(
    900,
    int(os.environ.get("KILLINCHU_PUBLIC_SOURCE_WARM_INTERVAL", "3600")),
)

MODE_LIVE = "LIVE"
MODE_CACHED = "CACHED"
MODE_UNAVAILABLE = "UNAVAILABLE"
MODE_UNTESTED = "UNTESTED"

POLICY: Mapping[str, Any] = {
    "network": {
        "method": "GET_ONLY",
        "arbitrary_url_input": False,
        "authentication_bypass": False,
        "credential_use": False,
        "protected_resources": False,
        "redirects": "EXPLICIT_HOST_ALLOWLIST",
        "response_size_bounded": True,
        "timeouts_bounded": True,
    },
    "content": {
        "public_official_sources_only": True,
        "active_force_geolocation": "PROHIBITED",
        "target_or_strike_packages": "PROHIBITED",
        "leaked_or_stolen_data": "PROHIBITED",
        "credentials_or_personal_dossiers": "PROHIBITED",
        "malware_or_exploit_payloads": "PROHIBITED",
        "dark_web_collection": "PROHIBITED",
        "cyber_scope": "DEFENSIVE_METADATA_AND_MITIGATION_ONLY",
        "sanctions_scope": "COMPLIANCE_AND_MANUAL_REVIEW_ONLY",
    },
    "authority": {
        "automated_targeting": False,
        "automated_enforcement": False,
        "action_authority": "NONE",
        "human_review_required": True,
    },
}


@dataclass(frozen=True)
class SourceSpec:
    """Immutable contract for one deliberately public official source."""

    source_id: str
    name: str
    authority: str
    jurisdiction: str
    url: str
    parser: str
    classification: str
    request_hosts: tuple[str, ...]
    redirect_hosts: tuple[str, ...] = ()
    record_hosts: tuple[str, ...] = ()
    ttl_seconds: int = 3600
    max_bytes: int = 4_000_000
    accepted_content_types: tuple[str, ...] = (
        "application/json",
        "application/xml",
        "text/xml",
        "text/html",
        "application/octet-stream",
    )
    max_items: int = 5000
    note: str = ""


SOURCES: Mapping[str, SourceSpec] = {
    "cisa-kev": SourceSpec(
        source_id="cisa-kev",
        name="CISA Known Exploited Vulnerabilities Catalog",
        authority="Cybersecurity and Infrastructure Security Agency",
        jurisdiction="United States",
        url="https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
        parser="cisa-kev",
        classification="DEFENSIVE_VULNERABILITY_METADATA",
        request_hosts=("www.cisa.gov",),
        ttl_seconds=3600,
        max_bytes=12_000_000,
        accepted_content_types=("application/json", "text/json", "application/octet-stream"),
        max_items=10_000,
        note="Prioritization metadata only; no exploit payloads or scanning.",
    ),
    "nsa-advisories": SourceSpec(
        source_id="nsa-advisories",
        name="NSA Cybersecurity Advisories and Guidance",
        authority="National Security Agency",
        jurisdiction="United States",
        url="https://www.nsa.gov/Cybersecurity/Cybersecurity-Advisories-Guidance/",
        parser="nsa-index",
        classification="DEFENSIVE_CYBER_ADVISORY_INDEX",
        request_hosts=("www.nsa.gov",),
        record_hosts=("www.nsa.gov", "media.defense.gov"),
        ttl_seconds=3600,
        max_bytes=4_000_000,
        accepted_content_types=("text/html", "application/xhtml+xml"),
        max_items=250,
        note="Public index metadata only. Access-controlled cyber.mil resources are excluded.",
    ),
    "cia-public-stories": SourceSpec(
        source_id="cia-public-stories",
        name="CIA Public News and Stories",
        authority="Central Intelligence Agency",
        jurisdiction="United States",
        url="https://www.cia.gov/stories",
        parser="cia-stories",
        classification="PUBLIC_AGENCY_NEWS_INDEX",
        request_hosts=("www.cia.gov",),
        record_hosts=("www.cia.gov",),
        ttl_seconds=7200,
        max_bytes=4_000_000,
        accepted_content_types=("text/html", "application/xhtml+xml"),
        max_items=200,
        note="Public stories only. The CIA World Factbook was sunset on 2026-02-04.",
    ),
    "ofac-sdn": SourceSpec(
        source_id="ofac-sdn",
        name="OFAC Specially Designated Nationals List",
        authority="U.S. Department of the Treasury, Office of Foreign Assets Control",
        jurisdiction="United States",
        url="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
        parser="ofac-sdn",
        classification="SANCTIONS_COMPLIANCE_LIST",
        request_hosts=("sanctionslistservice.ofac.treas.gov",),
        redirect_hosts=(
            "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com",
        ),
        ttl_seconds=21600,
        max_bytes=40_000_000,
        accepted_content_types=("application/xml", "text/xml", "application/octet-stream"),
        max_items=50_000,
        note="Exact-name compliance support; matches require manual review.",
    ),
    "un-dprk-1718": SourceSpec(
        source_id="un-dprk-1718",
        name="UN Security Council 1718 Sanctions List",
        authority="United Nations Security Council",
        jurisdiction="International",
        url="https://scsanctions.un.org/xml/en/dprk",
        parser="un-sanctions",
        classification="SANCTIONS_COMPLIANCE_LIST",
        request_hosts=("scsanctions.un.org",),
        ttl_seconds=21600,
        max_bytes=15_000_000,
        accepted_content_types=("application/xml", "text/xml", "application/octet-stream"),
        max_items=5000,
        note="DPRK sanctions compliance data; not a targeting dataset.",
    ),
    "cert-ua-advisories": SourceSpec(
        source_id="cert-ua-advisories",
        name="CERT-UA Public Cyber Advisories",
        authority="Computer Emergency Response Team of Ukraine",
        jurisdiction="Ukraine",
        url="https://cert.gov.ua/articles",
        parser="cert-ua-index",
        classification="DEFENSIVE_CYBER_ADVISORY_INDEX",
        request_hosts=("cert.gov.ua",),
        record_hosts=("cert.gov.ua",),
        ttl_seconds=3600,
        max_bytes=4_000_000,
        accepted_content_types=("text/html", "application/xhtml+xml"),
        max_items=250,
        note=(
            "Only the public article/recommendation index is collected. Contact/reporting "
            "channels and operational location reports are explicitly excluded."
        ),
    ),
    "ukraine-open-data-metadata": SourceSpec(
        source_id="ukraine-open-data-metadata",
        name="Ukraine Open Data Catalog — bounded metadata search",
        authority="Unified State Web Portal of Open Data",
        jurisdiction="Ukraine",
        url=(
            "https://data.gov.ua/api/3/action/package_search?"
            "q=%D0%BA%D1%96%D0%B1%D0%B5%D1%80%D0%B1%D0%B5%D0%B7%D0%BF%D0%B5%D0%BA%D0%B0%20"
            "OR%20%D1%81%D0%B0%D0%BD%D0%BA%D1%86%D1%96%D1%97%20OR%20"
            "%D0%B7%D0%B0%D0%BA%D1%83%D0%BF%D1%96%D0%B2%D0%BB%D1%96&rows=50"
        ),
        parser="ckan-metadata",
        classification="PUBLIC_OPEN_DATA_METADATA_ONLY",
        request_hosts=("data.gov.ua",),
        record_hosts=("data.gov.ua",),
        ttl_seconds=7200,
        max_bytes=8_000_000,
        accepted_content_types=("application/json", "text/json", "application/octet-stream"),
        max_items=50,
        note=(
            "Catalog metadata only; resource files are never downloaded. Active-force, "
            "location, movement, personnel, and personal-data records are excluded."
        ),
    ),
    "china-cac-notices": SourceSpec(
        source_id="china-cac-notices",
        name="Cyberspace Administration of China Public Notices",
        authority="Cyberspace Administration of China",
        jurisdiction="China",
        url="https://www.cac.gov.cn/",
        parser="cac-index",
        classification="PUBLIC_REGULATORY_NOTICE_INDEX",
        request_hosts=("www.cac.gov.cn",),
        record_hosts=("www.cac.gov.cn",),
        ttl_seconds=7200,
        max_bytes=5_000_000,
        accepted_content_types=("text/html", "application/xhtml+xml"),
        max_items=250,
        note="Public regulatory notices and publication metadata only.",
    ),
}

_PARSER_BY_NAME: dict[str, Callable[[bytes, SourceSpec], list[dict[str, Any]]]] = {}
_SOURCE_LOCKS = {source_id: threading.Lock() for source_id in SOURCES}
_WARM_LOCK = threading.Lock()
_WARM_THREAD: threading.Thread | None = None

# Terms indicating content that this bounded fabric must not retain.  Matching
# is intentionally phrase-based so defensive advisories can still mention
# exploitation in the abstract without importing exploit payloads.
_PROHIBITED_PHRASES = (
    "stolen credentials",
    "credential dump",
    "password dump",
    "private key dump",
    "leaked database",
    "dark web marketplace",
    "malware source code",
    "exploit source code",
    "weapon targeting coordinates",
    "strike coordinates",
    "target package",
    "live troop coordinates",
    "current troop location",
    "unit deployment coordinates",
    "active military position",
    "місця дислокації",
    "координати розташування",
    "пересування військової техніки",
    "обсяги військової техніки",
    "особового складу",
    "места дислокации",
    "координаты расположения",
    "перемещение военной техники",
)

# The Ukraine catalog receives a stricter metadata-only filter because it can
# index arbitrary resource descriptions.  False positives are safer than
# retaining current operational location metadata.
_CKAN_PROHIBITED = _PROHIBITED_PHRASES + (
    "географічні координати",
    "військова частина",
    "бойова позиція",
    "розташування підрозділу",
    "дислокація підрозділу",
    "переміщення підрозділу",
    "паспортні дані",
    "персональні дані",
    "номери телефонів фізичних осіб",
    "адреси електронної пошти фізичних осіб",
    "military unit location",
    "troop movement",
    "personnel location",
    "passport data",
    "personal data register",
)

_NAV_LABELS = {
    "home",
    "about",
    "contact",
    "contact us",
    "read more",
    "more",
    "next",
    "previous",
    "search",
    "subscribe",
    "print",
    "english",
    "中文",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize_space(value: Any, *, limit: int = 4000) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    return text[:limit]


def _normalize_name(value: str) -> str:
    folded = _normalize_space(value, limit=512).casefold()
    return re.sub(r"[^\w]+", " ", folded, flags=re.UNICODE).strip()


def _safe_exception(exc: BaseException) -> str:
    """Return a bounded error class/message with URL queries removed."""
    message = _normalize_space(str(exc), limit=300)
    message = re.sub(r"https://[^\s?]+\?[^\s]+", "[redacted-url]", message)
    message = re.sub(
        r"(?i)(token|authorization|password|secret|x-amz-[a-z-]+)=([^&\s]+)",
        r"\1=[redacted]",
        message,
    )
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _host_allowed(host: str, allowlist: Sequence[str]) -> bool:
    host = host.lower().rstrip(".")
    for allowed in allowlist:
        allowed = allowed.lower().rstrip(".")
        if allowed.startswith("*."):
            suffix = allowed[1:]
            if host.endswith(suffix) and host != suffix.lstrip("."):
                return True
        elif host == allowed:
            return True
    return False


def _validate_url(url: str, spec: SourceSpec, *, redirect: bool = False) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("upstream URL must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("userinfo is forbidden in upstream URLs")
    if parsed.port not in (None, 443):
        raise ValueError("non-standard upstream ports are forbidden")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("upstream URL has no hostname")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        raise ValueError("IP-literal upstream URLs are forbidden")
    allowed = spec.request_hosts + (spec.redirect_hosts if redirect else ())
    if not _host_allowed(host, allowed):
        raise ValueError(f"upstream host is not allowlisted for {spec.source_id}")
    return host


def _strip_url_query(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _safe_record_url(base: str, href: str, spec: SourceSpec) -> str | None:
    href = (href or "").strip()
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return None
    absolute = urllib.parse.urljoin(base, href)
    parsed = urllib.parse.urlsplit(absolute)
    if parsed.scheme.lower() != "https" or parsed.username or parsed.password:
        return None
    if parsed.port not in (None, 443):
        return None
    host = (parsed.hostname or "").lower().rstrip(".")
    allowed_hosts = spec.record_hosts or spec.request_hosts
    if not _host_allowed(host, allowed_hosts):
        return None
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    for key, _value in query:
        key_folded = key.casefold()
        if key_folded in {"token", "key", "apikey", "api_key", "auth", "password", "secret"}:
            return None
        if key_folded.startswith("x-amz-"):
            return None
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
    )


class _BoundedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, spec: SourceSpec) -> None:
        super().__init__()
        self.spec = spec

    def redirect_request(  # type: ignore[override]
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        _validate_url(newurl, self.spec, redirect=True)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.method = "GET"
            redirected.data = None
            redirected.remove_header("Authorization")
            redirected.remove_header("Cookie")
        return redirected


@dataclass(frozen=True)
class FetchBytes:
    body: bytes
    status: int
    final_url: str
    content_type: str
    etag: str | None
    last_modified: str | None


def _read_limited(response: Any, limit: int) -> bytes:
    declared = response.headers.get("Content-Length")
    if declared:
        try:
            if int(declared) > limit:
                raise ValueError("upstream body exceeds the configured size limit")
        except ValueError as exc:
            if "exceeds" in str(exc):
                raise
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(64 * 1024, limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError("upstream body exceeds the configured size limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _fetch_bytes(
    spec: SourceSpec,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
) -> FetchBytes:
    _validate_url(spec.url, spec)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": ", ".join(spec.accepted_content_types),
        "Cache-Control": "no-cache",
    }
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    request = urllib.request.Request(spec.url, headers=headers, method="GET")
    handlers: list[Any] = [
        urllib.request.ProxyHandler({}),
        _BoundedRedirectHandler(spec),
    ]
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            _validate_url(final_url, spec, redirect=final_url != spec.url)
            content_type = response.headers.get_content_type().lower()
            if content_type not in spec.accepted_content_types:
                raise ValueError(f"unexpected content type: {content_type}")
            body = _read_limited(response, spec.max_bytes)
            if not body:
                raise ValueError("upstream body is empty")
            return FetchBytes(
                body=body,
                status=int(getattr(response, "status", 200)),
                final_url=_strip_url_query(final_url),
                content_type=content_type,
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
            )
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return FetchBytes(
                body=b"",
                status=304,
                final_url=_strip_url_query(exc.geturl() or spec.url),
                content_type="",
                etag=exc.headers.get("ETag") if exc.headers else etag,
                last_modified=(
                    exc.headers.get("Last-Modified") if exc.headers else last_modified
                ),
            )
        raise


def _cache_path(source_id: str) -> Path:
    return CACHE_ROOT / f"{source_id}.json"


def _read_cache(source_id: str) -> dict[str, Any] | None:
    path = _cache_path(source_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != SCHEMA or payload.get("source_id") != source_id:
        return None
    return payload


def _write_cache(source_id: str, payload: Mapping[str, Any]) -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    target = _cache_path(source_id)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)


def _age_seconds(payload: Mapping[str, Any]) -> float | None:
    epoch = payload.get("fetched_epoch")
    if not isinstance(epoch, (int, float)):
        return None
    return max(0.0, time.time() - float(epoch))


def _cache_view(payload: Mapping[str, Any], *, error: str | None = None) -> dict[str, Any]:
    view = dict(payload)
    view["mode"] = MODE_CACHED
    view["cache_age_seconds"] = _age_seconds(payload)
    view["served_at"] = _utc_now()
    if error:
        view["fetch_error"] = error
    return view


def _unavailable(spec: SourceSpec, exc: BaseException) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "source_id": spec.source_id,
        "source": _public_source(spec),
        "mode": MODE_UNAVAILABLE,
        "truth_label": "UNAVAILABLE",
        "fetched_at": None,
        "served_at": _utc_now(),
        "content_sha256": None,
        "item_count": None,
        "excluded_item_count": None,
        "items": [],
        "fetch_error": _safe_exception(exc),
        "policy": POLICY,
        "action_authority": "NONE",
    }


def _public_source(spec: SourceSpec) -> dict[str, Any]:
    row = asdict(spec)
    # These fields are implementation details rather than public configuration.
    row.pop("request_hosts", None)
    row.pop("redirect_hosts", None)
    row.pop("record_hosts", None)
    row.pop("accepted_content_types", None)
    return row


def _record_hash(record: Mapping[str, Any]) -> str:
    body = {key: value for key, value in record.items() if key != "record_sha256"}
    return _sha256(_canonical_json(body))


def _prohibited_reason(record: Mapping[str, Any], spec: SourceSpec) -> str | None:
    text = " ".join(
        _normalize_space(record.get(key, ""), limit=5000)
        for key in ("title", "summary", "description", "tags")
    ).casefold()
    phrases = _CKAN_PROHIBITED if spec.parser == "ckan-metadata" else _PROHIBITED_PHRASES
    for phrase in phrases:
        if phrase.casefold() in text:
            return f"policy_phrase:{phrase}"
    return None


def _finalize_records(
    records: Iterable[dict[str, Any]], spec: SourceSpec
) -> tuple[list[dict[str, Any]], list[str]]:
    safe: list[dict[str, Any]] = []
    excluded: list[str] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        reason = _prohibited_reason(record, spec)
        if reason:
            excluded.append(reason)
            continue
        record["source_id"] = spec.source_id
        record["classification"] = spec.classification
        record["truth_label"] = "PUBLIC_OFFICIAL_CLAIM"
        fingerprint = _record_hash(record)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        record["record_sha256"] = fingerprint
        safe.append(record)
        if len(safe) >= spec.max_items:
            break
    return safe, excluded


class _IndexHTMLParser(HTMLParser):
    """Collect anchors and table-row context without executing page scripts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[dict[str, str]] = []
        self.rows: list[dict[str, Any]] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self._row: dict[str, Any] | None = None
        self._row_depth = 0
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "tr":
            if self._row is None:
                self._row = {"text": [], "anchors": []}
                self._row_depth = 1
            else:
                self._row_depth += 1
        if tag == "a":
            attr_map = {key.lower(): value or "" for key, value in attrs}
            self._anchor_href = attr_map.get("href", "")
            self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "a" and self._anchor_href is not None:
            anchor = {
                "href": self._anchor_href,
                "text": _normalize_space(" ".join(self._anchor_text), limit=1000),
            }
            if self._row is not None:
                self._row["anchors"].append(anchor)
            else:
                self.anchors.append(anchor)
            self._anchor_href = None
            self._anchor_text = []
        if tag == "tr" and self._row is not None:
            self._row_depth -= 1
            if self._row_depth <= 0:
                self._row["text"] = _normalize_space(
                    " ".join(self._row["text"]), limit=4000
                )
                self.rows.append(self._row)
                self._row = None
                self._row_depth = 0

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._anchor_href is not None:
            self._anchor_text.append(data)
        if self._row is not None:
            self._row["text"].append(data)


def _date_from_text(value: str) -> str | None:
    value = _normalize_space(value, limit=4000)
    match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", value)
    if match:
        month, day, year = (int(part) for part in match.groups())
        try:
            return datetime(year, month, day, tzinfo=timezone.utc).date().isoformat()
        except ValueError:
            return None
    match = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", value)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return datetime(year, month, day, tzinfo=timezone.utc).date().isoformat()
        except ValueError:
            return None
    return None


def _keep_html_link(spec: SourceSpec, url: str, title: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path
    folded = title.casefold().strip()
    if len(title) < 8 or folded in _NAV_LABELS or folded.startswith("image:"):
        return False
    if spec.parser == "nsa-index":
        return (
            host == "media.defense.gov" and path.lower().endswith(".pdf")
        ) or (
            host == "www.nsa.gov"
            and "cybersecurity-advisories-guidance" in path.casefold()
            and path.rstrip("/")
            != "/Cybersecurity/Cybersecurity-Advisories-Guidance"
        )
    if spec.parser == "cia-stories":
        return host == "www.cia.gov" and path.startswith("/stories/story/")
    if spec.parser == "cert-ua-index":
        return host == "cert.gov.ua" and bool(
            re.match(r"^/(?:article|articles|recommendations)/\d+/?$", path)
        )
    if spec.parser == "cac-index":
        return host == "www.cac.gov.cn" and bool(
            re.match(r"^/20\d{2}-\d{2}/\d{2}/c_\d+\.htm$", path)
        )
    return False


def _parse_html_index(raw: bytes, spec: SourceSpec) -> list[dict[str, Any]]:
    parser = _IndexHTMLParser()
    parser.feed(raw.decode("utf-8", "replace"))
    candidates: list[tuple[dict[str, str], str]] = []
    for row in parser.rows:
        for anchor in row.get("anchors", []):
            candidates.append((anchor, str(row.get("text", ""))))
    candidates.extend((anchor, "") for anchor in parser.anchors)

    records: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for anchor, context in candidates:
        title = _normalize_space(anchor.get("text", ""), limit=500)
        url = _safe_record_url(spec.url, anchor.get("href", ""), spec)
        if not url or url in seen_urls or not _keep_html_link(spec, url, title):
            continue
        seen_urls.add(url)
        published = _date_from_text(context)
        if not published and spec.parser == "cac-index":
            published = _date_from_text(urllib.parse.urlsplit(url).path)
        records.append(
            {
                "kind": "publication",
                "title": title,
                "url": url,
                "published_at": published,
                "summary": "",
                "retrieval_scope": "INDEX_METADATA_ONLY",
            }
        )
    return records


def _parse_cisa_kev(raw: bytes, spec: SourceSpec) -> list[dict[str, Any]]:
    payload = json.loads(raw.decode("utf-8"))
    vulnerabilities = payload.get("vulnerabilities") if isinstance(payload, dict) else None
    if not isinstance(vulnerabilities, list):
        raise ValueError("CISA KEV response has no vulnerabilities array")
    rows: list[dict[str, Any]] = []
    for item in vulnerabilities[: spec.max_items]:
        if not isinstance(item, dict):
            continue
        cve = _normalize_space(item.get("cveID"), limit=40).upper()
        if not re.fullmatch(r"CVE-\d{4}-\d{4,}", cve):
            continue
        rows.append(
            {
                "kind": "defensive_vulnerability",
                "title": _normalize_space(
                    item.get("vulnerabilityName") or cve, limit=500
                ),
                "cve": cve,
                "vendor": _normalize_space(item.get("vendorProject"), limit=200),
                "product": _normalize_space(item.get("product"), limit=200),
                "date_added": _normalize_space(item.get("dateAdded"), limit=40) or None,
                "due_date": _normalize_space(item.get("dueDate"), limit=40) or None,
                "summary": _normalize_space(item.get("shortDescription"), limit=1600),
                "required_defensive_action": _normalize_space(
                    item.get("requiredAction"), limit=1600
                ),
                "known_ransomware_campaign_use": _normalize_space(
                    item.get("knownRansomwareCampaignUse"), limit=80
                ) or None,
                "cwes": [
                    _normalize_space(value, limit=40)
                    for value in (item.get("cwes") or [])
                    if _normalize_space(value, limit=40)
                ][:20],
                "notes": _normalize_space(item.get("notes"), limit=1000),
                "action_authority": "DEFENSIVE_PRIORITIZATION_ONLY",
            }
        )
    return rows


def _xml_local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _direct_text(node: ET.Element, name: str) -> str:
    for child in list(node):
        if _xml_local(child.tag).casefold() == name.casefold():
            return _normalize_space(child.text, limit=1000)
    return ""


def _descendants(node: ET.Element, name: str) -> list[ET.Element]:
    folded = name.casefold()
    return [child for child in node.iter() if _xml_local(child.tag).casefold() == folded]


def _reject_dangerous_xml(raw: bytes) -> None:
    head = raw[:100_000].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ValueError("DTD/entity declarations are forbidden in upstream XML")


def _parse_ofac_sdn(raw: bytes, spec: SourceSpec) -> list[dict[str, Any]]:
    _reject_dangerous_xml(raw)
    root = ET.fromstring(raw)
    rows: list[dict[str, Any]] = []
    for entry in _descendants(root, "sdnEntry")[: spec.max_items]:
        first = _direct_text(entry, "firstName")
        last = _direct_text(entry, "lastName")
        primary = _normalize_space(" ".join(part for part in (first, last) if part), limit=500)
        if not primary:
            primary = _direct_text(entry, "sdnName")
        if not primary:
            continue
        aliases: list[str] = []
        for aka in _descendants(entry, "aka"):
            alias = _normalize_space(
                " ".join(
                    part
                    for part in (
                        _direct_text(aka, "firstName"),
                        _direct_text(aka, "lastName"),
                    )
                    if part
                ),
                limit=500,
            )
            if alias and alias.casefold() != primary.casefold():
                aliases.append(alias)
        programs = sorted(
            {
                _normalize_space(program.text, limit=120)
                for program in _descendants(entry, "program")
                if _normalize_space(program.text, limit=120)
            }
        )
        identifiers: list[dict[str, str]] = []
        for identifier in _descendants(entry, "id"):
            kind = _direct_text(identifier, "idType")
            number = _direct_text(identifier, "idNumber")
            kind_folded = kind.casefold()
            if number and any(
                token in kind_folded
                for token in ("vessel", "imo", "mmsi", "aircraft", "tail", "call sign")
            ):
                identifiers.append({"type": kind, "value": number})
        vessel_info = _descendants(entry, "vesselInfo")
        if vessel_info:
            vessel = vessel_info[0]
            for kind in ("callSign", "vesselType", "vesselFlag", "vesselOwner"):
                value = _direct_text(vessel, kind)
                if value:
                    identifiers.append({"type": kind, "value": value})
        rows.append(
            {
                "kind": "sanctions_designation",
                "title": primary,
                "names": [primary] + sorted(set(aliases)),
                "entry_uid": _direct_text(entry, "uid") or None,
                "entity_type": _direct_text(entry, "sdnType") or "UNAVAILABLE",
                "programs": programs,
                "identifiers": identifiers[:50],
                "summary": "Public OFAC designation record; manual compliance review required.",
                "action_authority": "NONE",
            }
        )
    return rows


def _parse_un_sanctions(raw: bytes, spec: SourceSpec) -> list[dict[str, Any]]:
    _reject_dangerous_xml(raw)
    root = ET.fromstring(raw)
    rows: list[dict[str, Any]] = []
    for node in root.iter():
        local = _xml_local(node.tag).upper()
        if local not in {"INDIVIDUAL", "ENTITY"}:
            continue
        parts = [
            _direct_text(node, key)
            for key in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")
        ]
        primary = _normalize_space(" ".join(part for part in parts if part), limit=500)
        if not primary:
            primary = _direct_text(node, "NAME_ORIGINAL_SCRIPT")
        if not primary:
            continue
        aliases: list[str] = []
        alias_tag = "INDIVIDUAL_ALIAS" if local == "INDIVIDUAL" else "ENTITY_ALIAS"
        for alias_node in _descendants(node, alias_tag):
            alias = _direct_text(alias_node, "ALIAS_NAME")
            if alias and alias.casefold() != primary.casefold():
                aliases.append(alias)
        rows.append(
            {
                "kind": "sanctions_designation",
                "title": primary,
                "names": [primary] + sorted(set(aliases)),
                "reference_number": _direct_text(node, "REFERENCE_NUMBER") or None,
                "listed_on": _direct_text(node, "LISTED_ON") or None,
                "entity_type": local,
                "list_type": _direct_text(node, "UN_LIST_TYPE") or "1718",
                "summary": "Public UN Security Council designation record; manual compliance review required.",
                "action_authority": "NONE",
            }
        )
        if len(rows) >= spec.max_items:
            break
    return rows


def _parse_ckan_metadata(raw: bytes, spec: SourceSpec) -> list[dict[str, Any]]:
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("CKAN response did not report success=true")
    result = payload.get("result")
    datasets = result.get("results") if isinstance(result, dict) else None
    if not isinstance(datasets, list):
        raise ValueError("CKAN response has no result.results array")
    rows: list[dict[str, Any]] = []
    for dataset in datasets[: spec.max_items]:
        if not isinstance(dataset, dict):
            continue
        name = _normalize_space(dataset.get("name"), limit=300)
        title = _normalize_space(dataset.get("title") or name, limit=700)
        if not name or not title:
            continue
        organization = dataset.get("organization")
        organization_title = (
            _normalize_space(organization.get("title"), limit=300)
            if isinstance(organization, dict)
            else ""
        )
        tags = sorted(
            {
                _normalize_space(tag.get("display_name") or tag.get("name"), limit=100)
                for tag in (dataset.get("tags") or [])
                if isinstance(tag, dict)
                and _normalize_space(tag.get("display_name") or tag.get("name"), limit=100)
            }
        )
        resources = dataset.get("resources") or []
        formats = sorted(
            {
                _normalize_space(resource.get("format"), limit=40).upper()
                for resource in resources
                if isinstance(resource, dict)
                and _normalize_space(resource.get("format"), limit=40)
            }
        )
        rows.append(
            {
                "kind": "open_data_catalog_metadata",
                "title": title,
                "url": f"https://data.gov.ua/dataset/{urllib.parse.quote(name, safe='-_.~')}",
                "dataset_id": _normalize_space(dataset.get("id"), limit=100) or None,
                "publisher": organization_title or None,
                "metadata_modified": _normalize_space(
                    dataset.get("metadata_modified"), limit=80
                ) or None,
                "tags": tags[:40],
                "resource_count": len(resources),
                "resource_formats": formats[:40],
                "summary": _normalize_space(dataset.get("notes"), limit=1600),
                "retrieval_scope": "CATALOG_METADATA_ONLY_NO_RESOURCE_DOWNLOAD",
                "action_authority": "NONE",
            }
        )
    return rows


_PARSER_BY_NAME.update(
    {
        "cisa-kev": _parse_cisa_kev,
        "nsa-index": _parse_html_index,
        "cia-stories": _parse_html_index,
        "ofac-sdn": _parse_ofac_sdn,
        "un-sanctions": _parse_un_sanctions,
        "cert-ua-index": _parse_html_index,
        "ckan-metadata": _parse_ckan_metadata,
        "cac-index": _parse_html_index,
    }
)


def source_index() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "state": "DECLARED",
        "source_count": len(SOURCES),
        "sources": [_public_source(SOURCES[key]) for key in sorted(SOURCES)],
        "policy": POLICY,
        "action_authority": "NONE",
    }


def _publish_sanctions_to_vessels(
    spec: SourceSpec, records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if spec.classification != "SANCTIONS_COMPLIANCE_LIST":
        return {"state": "NOT_APPLICABLE", "entries": 0}
    names = sorted(
        {
            _normalize_space(name, limit=512)
            for record in records
            for name in (record.get("names") or [])
            if _normalize_space(name, limit=512)
        }
    )
    if not names:
        return {"state": MODE_UNAVAILABLE, "entries": 0, "reason": "no names parsed"}
    try:
        import killinchu_vessels_screening as vessels  # type: ignore

        result = vessels.load_screening_list(
            f"official:{spec.source_id}",
            names,
            source=f"{spec.authority} | {spec.url}",
            truth_label="REPORTED",
        )
        return {
            "state": "LOADED",
            "entries": int(result.get("entries", len(names))),
            "list": f"official:{spec.source_id}",
        }
    except Exception as exc:  # optional downstream; source fetch remains usable
        return {
            "state": MODE_UNAVAILABLE,
            "entries": 0,
            "reason": _safe_exception(exc),
        }


def fetch_source(source_id: str, *, force: bool = False) -> dict[str, Any]:
    """Fetch one fixed source, or serve its cache, without arbitrary URL input."""
    spec = SOURCES.get(source_id)
    if spec is None:
        raise KeyError(source_id)
    lock = _SOURCE_LOCKS[source_id]
    with lock:
        cached = _read_cache(source_id)
        age = _age_seconds(cached or {})
        if (
            cached is not None
            and not force
            and age is not None
            and age <= spec.ttl_seconds
        ):
            return _cache_view(cached)
        try:
            fetched = _fetch_bytes(
                spec,
                etag=str(cached.get("etag")) if cached and cached.get("etag") else None,
                last_modified=(
                    str(cached.get("last_modified"))
                    if cached and cached.get("last_modified")
                    else None
                ),
            )
            if fetched.status == 304:
                if cached is None:
                    raise ValueError("upstream returned 304 without a local cache")
                cached = dict(cached)
                cached["fetched_epoch"] = time.time()
                cached["fetched_at"] = _utc_now()
                cached["etag"] = fetched.etag
                cached["last_modified"] = fetched.last_modified
                _write_cache(source_id, cached)
                return _cache_view(cached)

            parser = _PARSER_BY_NAME.get(spec.parser)
            if parser is None:
                raise RuntimeError(f"no parser registered for {spec.parser}")
            parsed = parser(fetched.body, spec)
            records, excluded = _finalize_records(parsed, spec)
            payload: dict[str, Any] = {
                "schema": SCHEMA,
                "version": VERSION,
                "source_id": source_id,
                "source": _public_source(spec),
                "mode": MODE_LIVE,
                "truth_label": "PUBLIC_OFFICIAL_CLAIM",
                "fetched_epoch": time.time(),
                "fetched_at": _utc_now(),
                "served_at": _utc_now(),
                "http_status": fetched.status,
                "content_type": fetched.content_type,
                "final_url": fetched.final_url,
                "etag": fetched.etag,
                "last_modified": fetched.last_modified,
                "content_sha256": _sha256(fetched.body),
                "item_count": len(records),
                "excluded_item_count": len(excluded),
                "excluded_reason_classes": sorted(set(excluded))[:50],
                "items": records,
                "policy": POLICY,
                "action_authority": "NONE",
            }
            if spec.classification == "SANCTIONS_COMPLIANCE_LIST":
                payload["downstream_screening"] = _publish_sanctions_to_vessels(
                    spec, records
                )
            _write_cache(source_id, payload)
            return payload
        except Exception as exc:
            if cached is not None:
                return _cache_view(cached, error=_safe_exception(exc))
            return _unavailable(spec, exc)


def cached_health() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for source_id in sorted(SOURCES):
        spec = SOURCES[source_id]
        cached = _read_cache(source_id)
        age = _age_seconds(cached or {})
        if cached is None:
            mode = MODE_UNTESTED
            count = None
            fetched_at = None
            digest = None
        else:
            mode = MODE_CACHED
            count = cached.get("item_count")
            fetched_at = cached.get("fetched_at")
            digest = cached.get("content_sha256")
        rows.append(
            {
                "source_id": source_id,
                "name": spec.name,
                "mode": mode,
                "cache_age_seconds": age,
                "ttl_seconds": spec.ttl_seconds,
                "item_count": count,
                "fetched_at": fetched_at,
                "content_sha256": digest,
            }
        )
    tested = [row for row in rows if row["mode"] != MODE_UNTESTED]
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "state": MODE_CACHED if tested else MODE_UNTESTED,
        "tested_sources": len(tested),
        "total_sources": len(rows),
        "sources": rows,
        "policy": POLICY,
        "action_authority": "NONE",
    }


def screen_sanctions(name: str) -> dict[str, Any]:
    """Exact-fold public-list screen. It never returns a definitive CLEAR."""
    query = _normalize_space(name, limit=256)
    normalized = _normalize_name(query)
    if len(normalized) < 2:
        return {
            "query": query,
            "verdict": "BLOCKED_PENDING",
            "coverage": "NONE",
            "reason": "name must contain at least two normalized characters",
            "matches": [],
            "truth_label": "MEASURED_LIST_MATCH",
            "action_authority": "NONE",
            "manual_review_required": True,
        }
    source_results = [fetch_source("ofac-sdn"), fetch_source("un-dprk-1718")]
    matches: list[dict[str, Any]] = []
    available = 0
    source_hashes: dict[str, str | None] = {}
    for result in source_results:
        source_id = str(result.get("source_id"))
        source_hashes[source_id] = result.get("content_sha256")
        if result.get("mode") in {MODE_LIVE, MODE_CACHED}:
            available += 1
        for record in result.get("items") or []:
            names = record.get("names") or []
            matched_names = [
                candidate
                for candidate in names
                if _normalize_name(str(candidate)) == normalized
            ]
            if matched_names:
                matches.append(
                    {
                        "source_id": source_id,
                        "record_sha256": record.get("record_sha256"),
                        "reference": record.get("reference_number")
                        or record.get("entry_uid"),
                        "entity_type": record.get("entity_type"),
                        "programs": record.get("programs") or [],
                        "matched_names": matched_names,
                    }
                )
    coverage = "FULL" if available == 2 else "PARTIAL" if available else "NONE"
    if matches:
        verdict = "POSSIBLE_MATCH"
    elif available:
        verdict = "NO_EXACT_MATCH"
    else:
        verdict = "BLOCKED_PENDING"
    receipt_body = {
        "query_normalized": normalized,
        "coverage": coverage,
        "verdict": verdict,
        "source_hashes": source_hashes,
        "matches": matches,
    }
    return {
        "query": query,
        "verdict": verdict,
        "coverage": coverage,
        "sources_available": available,
        "sources_expected": 2,
        "matches": matches,
        "receipt_sha256": _sha256(_canonical_json(receipt_body)),
        "truth_label": "MEASURED_LIST_MATCH",
        "action_authority": "NONE",
        "manual_review_required": True,
        "caveat": (
            "Exact normalization is not definitive sanctions clearance. Review aliases, "
            "identifiers, ownership, jurisdiction, and current official guidance."
        ),
    }


def _warm_loop() -> None:
    # Delay startup so the application can become healthy before egress begins.
    time.sleep(5)
    while True:
        for source_id in sorted(SOURCES):
            try:
                fetch_source(source_id)
            except Exception:
                pass
            time.sleep(1)
        time.sleep(WARM_INTERVAL_SECONDS)


def start_warmer() -> bool:
    """Start one low-frequency daemon warmer; return False when disabled/running."""
    enabled = os.environ.get("KILLINCHU_PUBLIC_SOURCE_WARM", "1").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return False
    global _WARM_THREAD
    with _WARM_LOCK:
        if _WARM_THREAD is not None and _WARM_THREAD.is_alive():
            return False
        _WARM_THREAD = threading.Thread(
            target=_warm_loop,
            name="killinchu-public-source-warmer",
            daemon=True,
        )
        _WARM_THREAD.start()
        return True


def register(app: Any, ns: str = "killinchu") -> list[str]:
    """Register read-only FastAPI routes before Killinchu's SPA catch-all."""
    try:
        from fastapi import HTTPException, Query
        from fastapi.responses import JSONResponse
    except Exception as exc:  # pragma: no cover - runtime dependency contract
        raise RuntimeError("FastAPI is required to register public-source routes") from exc

    base = f"/api/{ns}/v1/osint/public"

    def response(payload: Any, status_code: int = 200) -> JSONResponse:
        return JSONResponse(
            payload,
            status_code=status_code,
            headers={"Cache-Control": "no-store"},
        )

    async def policy_route() -> JSONResponse:
        return response(
            {
                "schema": SCHEMA,
                "version": VERSION,
                "state": "DECLARED",
                "policy": POLICY,
                "action_authority": "NONE",
            }
        )

    async def sources_route() -> JSONResponse:
        return response(source_index())

    async def health_route() -> JSONResponse:
        return response(cached_health())

    async def source_route(
        source_id: str,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> JSONResponse:
        if source_id not in SOURCES:
            raise HTTPException(status_code=404, detail="unknown public source id")
        payload = await asyncio.to_thread(fetch_source, source_id)
        view = dict(payload)
        items = list(payload.get("items") or [])
        view["items"] = items[:limit]
        view["returned_item_count"] = len(view["items"])
        status = 503 if payload.get("mode") == MODE_UNAVAILABLE else 200
        return response(view, status_code=status)

    async def sanctions_screen_route(
        name: str = Query(min_length=2, max_length=256),
    ) -> JSONResponse:
        payload = await asyncio.to_thread(screen_sanctions, name)
        status = 503 if payload.get("verdict") == "BLOCKED_PENDING" else 200
        return response(payload, status_code=status)

    routes = [
        (f"{base}/policy", policy_route),
        (f"{base}/sources", sources_route),
        (f"{base}/health", health_route),
        (f"{base}/source/{{source_id}}", source_route),
        (f"{base}/sanctions/screen", sanctions_screen_route),
    ]
    existing = {getattr(route, "path", None) for route in getattr(app, "routes", [])}
    installed: list[str] = []
    for path, endpoint in routes:
        if path in existing:
            continue
        app.add_api_route(path, endpoint, methods=["GET"])
        installed.append(path)
    return installed


__all__ = [
    "CACHE_ROOT",
    "POLICY",
    "SCHEMA",
    "SOURCES",
    "SourceSpec",
    "VERSION",
    "cached_health",
    "fetch_source",
    "register",
    "screen_sanctions",
    "source_index",
    "start_warmer",
]
