"""Killinchu Research & Sources plus the public-intelligence source mesh.

The legacy ``/research`` contract remains a curated catalogue with optional
reachability probes. The additive ``/public-intel`` contract reads only a fixed
allowlist of official, publicly accessible HTTPS sources. It does not accept an
arbitrary URL, credentials, cookies, form submissions, active scans, or access-
controlled resources.

Every runtime read is bounded by source-specific host, redirect, size, content-
type, timeout, and cache contracts. Results carry source identity, fetch time,
HTTP metadata, SHA-256 evidence, and an honest ``MEASURED`` or ``UNAVAILABLE``
state. Content is reported as source claims, not attested truth.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import html.parser as _html_parser
import ipaddress as _ipaddress
import json as _json
import socket as _socket
import threading as _threading
import time as _time
import urllib.error as _urlerr
import urllib.parse as _urlparse
import urllib.request as _urlreq
import xml.etree.ElementTree as _etree
from typing import Any as _Any

_HONEST = (
    "Curated upstream sources. Static lists never claim reachability; /live "
    "reports live/unreachable with HTTP status and checked_at. Public-intel "
    "uses a fixed official HTTPS allowlist and fails closed. No fabricated "
    "sources, arbitrary URL fetches, credentials, scans, or protected content."
)
_UA = "killinchu-public-intel/1.0 (+https://github.com/szl-holdings/killinchu)"


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Curated source catalogue used by the existing Research & Sources panels.
# ---------------------------------------------------------------------------
# kind: repo | docs | standard | feed | knowledge | arxiv | official-index
_SRC = {
    "uds_core": ("UDS Core", "https://github.com/defenseunicorns/uds-core", "repo", "Secure runtime platform."),
    "uds_cli": ("UDS CLI", "https://github.com/defenseunicorns/uds-cli", "repo", "Bundle/deploy CLI."),
    "uds_common": ("UDS Common", "https://github.com/defenseunicorns/uds-common", "repo", "Shared UDS tasks and actions."),
    "pepr": ("Pepr", "https://github.com/defenseunicorns/pepr", "repo", "Kubernetes policy engine."),
    "zarf": ("Zarf", "https://github.com/zarf-dev/zarf", "repo", "Air-gapped package delivery."),
    "uds_docs": ("UDS Core documentation", "https://docs.defenseunicorns.com/core", "docs", "Runtime and platform docs."),
    "du_home": ("Defense Unicorns", "https://www.defenseunicorns.com", "docs", "Mission-software context."),
    "pepr_docs": ("Pepr docs", "https://pepr.dev", "docs", "Policy-as-code docs."),
    "zarf_docs": ("Zarf docs", "https://docs.zarf.dev/", "docs", "Air-gap delivery docs."),
    "cosign": ("Sigstore Cosign", "https://github.com/sigstore/cosign", "repo", "Signing and attestation."),
    "in_toto": ("in-toto Attestation framework", "https://github.com/in-toto/attestation", "repo", "Attestation predicates."),
    "in_toto_io": ("in-toto project", "https://in-toto.io", "docs", "Supply-chain integrity framework."),
    "slsa_fw": ("SLSA framework", "https://github.com/slsa-framework/slsa", "repo", "Supply-chain levels."),
    "slsa_dev": ("SLSA specification", "https://slsa.dev", "standard", "Supply-chain provenance standard."),
    "kev_mirror": ("CISA KEV official GitHub mirror", "https://raw.githubusercontent.com/cisagov/kev-data/main/known_exploited_vulnerabilities.json", "feed", "Known Exploited Vulnerabilities JSON catalogue."),
    "nvd": ("NVD CVE API 2.0", "https://services.nvd.nist.gov/rest/json/cves/2.0", "feed", "NIST vulnerability data API."),
    "epss": ("FIRST EPSS API", "https://api.first.org/data/v1/epss", "feed", "Exploit-probability scores."),
    "mitre_attack": ("MITRE ATT&CK Enterprise STIX", "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json", "feed", "Official ATT&CK STIX bundle."),
    "mitre_site": ("MITRE ATT&CK", "https://attack.mitre.org/", "knowledge", "Adversary tactics and techniques."),
    "nist_800207": ("NIST SP 800-207", "https://csrc.nist.gov/pubs/sp/800/207/final", "standard", "Zero Trust Architecture."),
    "adsb_mil": ("adsb.lol military ADS-B", "https://api.adsb.lol/v2/mil", "feed", "Public ADS-B observation claims."),
    "fed_reg": ("US Federal Register API", "https://www.federalregister.gov/api/v1/documents.json", "feed", "Rules, notices, and executive actions."),
    "usgs_quake": ("USGS earthquake feed", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson", "feed", "Public seismic GeoJSON feed."),
    "lean": ("Lean community", "https://leanprover-community.github.io/", "knowledge", "Formal proof references."),
    "zenodo": ("Zenodo", "https://zenodo.org/", "knowledge", "Research records and DOIs."),
    "asf_mag": ("Air & Space Forces Magazine", "https://www.airandspaceforces.com/", "knowledge", "Public defense reporting."),
    "arx_cuas1": ("C-UAS state of the art", "https://arxiv.org/abs/2008.12461", "arxiv", "Counter-UAS survey."),
    "arx_cuas2": ("Objective-driven counter-UAS testing", "https://arxiv.org/abs/2405.04477", "arxiv", "Counter-UAS evaluation."),
    "arx_cuas3": ("Counter-UAS integration into UTM", "https://arxiv.org/abs/2111.07291", "arxiv", "Counter-UAS and UTM."),
    "arx_cuas4": ("Multi-physics HPM counter-UAS", "https://arxiv.org/abs/2602.08477", "arxiv", "Counter-UAS research."),
    "arx_swarm1": ("Drone swarm security governance", "https://arxiv.org/abs/2112.15454", "arxiv", "Swarm security."),
    "arx_swarm2": ("TriSweep four-drone swarm", "https://arxiv.org/abs/2605.22709", "arxiv", "Swarm framework."),
    "arx_mar1": ("Vessel behavior anomaly detection", "https://arxiv.org/abs/2004.03722", "arxiv", "Maritime anomaly survey."),
    "arx_mar2": ("Context-aware maritime anomaly detection", "https://arxiv.org/abs/2602.00124", "arxiv", "Maritime surveillance research."),
    "arx_sc1": ("Software supply-chain security SoK", "https://arxiv.org/abs/2406.10109", "arxiv", "Supply-chain security."),
    "arx_sc2": ("GoSurf supply-chain vectors", "https://arxiv.org/abs/2407.04442", "arxiv", "Supply-chain research."),
    "arx_sc3": ("Maven-Hijack", "https://arxiv.org/abs/2407.18760", "arxiv", "Packaging-order supply-chain research."),
    "arx_bft1": ("Byzantine fault-tolerant distributed ML", "https://arxiv.org/abs/2008.04699", "arxiv", "BFT research."),
    "arx_bft2": ("BFT under minimal redundancy", "https://arxiv.org/abs/2009.14763", "arxiv", "BFT research."),
    "arx_pqc1": ("PQC signature placement", "https://arxiv.org/abs/2604.06100", "arxiv", "Post-quantum signatures."),
    "arx_pqc2": ("Post-quantum blockchain review", "https://arxiv.org/abs/2402.00922", "arxiv", "Post-quantum review."),
    "arx_zt1": ("Enterprise Zero Trust Architecture", "https://arxiv.org/abs/2410.18291", "arxiv", "Zero-trust research."),
    "arx_zt2": ("Intent-aware authorization for CI/CD", "https://arxiv.org/abs/2504.14777", "arxiv", "Zero-trust CI/CD."),
    "arx_zt3": ("SecureBank Zero Trust Architecture", "https://arxiv.org/abs/2512.23124", "arxiv", "Zero-trust research."),
    "arx_lean1": ("Ramanujan-Nagell in Lean 4", "https://arxiv.org/abs/2604.09808", "arxiv", "Lean formalization."),
    "arx_lean2": ("Nagata factoriality in Lean 4", "https://arxiv.org/abs/2604.05238", "arxiv", "Lean formalization."),
    "arx_lean3": ("Chemical physics in Lean", "https://arxiv.org/abs/2210.12150", "arxiv", "Lean formalization."),
    "arx_epss": ("Exploit Prediction Scoring System", "https://arxiv.org/abs/1908.04856", "arxiv", "Vulnerability prioritization."),
    "arx_k8s": ("Kubernetes security SoK", "https://arxiv.org/abs/2006.15275", "arxiv", "Kubernetes security."),
    "ofac_sdn": ("OFAC Sanctions List Service", "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML", "feed", "Official public SDN XML."),
    "un_dprk": ("UN Security Council consolidated list — DPRK 1718", "https://scsanctions.un.org/resources/xml/en/name/consolidated.xml", "feed", "Official list filtered to KPi/KPe references."),
    "cia_world_leaders": ("CIA World Leaders directory", "https://www.cia.gov/resources/world-leaders/foreign-governments/", "official-index", "Public directory of foreign governments and cabinet members."),
    "nsa_advisories": ("NSA public cybersecurity advisories", "https://www.nsa.gov/Cybersecurity/Cybersecurity-Advisories-Guidance/", "official-index", "Public advisories only; access-controlled resources excluded."),
    "cert_ua": ("CERT-UA public recommendations", "https://cert.gov.ua/recommendations", "official-index", "Public cyber recommendations and notices."),
    "ukraine_open_data": ("Ukraine open-data CKAN API", "https://data.gov.ua/api/3/action/recently_changed_packages_activity_list?limit=50", "feed", "Public metadata for recently changed datasets."),
    "china_mfa": ("PRC Ministry of Foreign Affairs press conferences", "https://www.mfa.gov.cn/mfa_eng/xw/fyrbt/lxjzh/index.html", "official-index", "Public English-language official statements."),
    "china_state_council": ("PRC State Council policy releases", "https://english.www.gov.cn/policies/latestreleases/", "official-index", "Public English-language policy releases."),
}

_TAB = {
    "hero_interdiction": ["adsb_mil", "arx_mar1", "arx_cuas1", "arx_mar2"],
    "u_maritime": ["adsb_mil", "arx_mar1", "arx_mar2"],
    "maritime": ["adsb_mil", "arx_mar1", "arx_mar2"],
    "u_fleet": ["adsb_mil", "uds_core", "du_home", "asf_mag"],
    "fleet": ["adsb_mil", "uds_core", "du_home"],
    "fleet_c2": ["uds_core", "pepr", "arx_bft1", "adsb_mil"],
    "u_space": ["lean", "asf_mag"],
    "u_swarm": ["arx_swarm1", "arx_swarm2", "arx_cuas1"],
    "swarm": ["arx_swarm1", "arx_swarm2", "arx_cuas1"],
    "swarmres": ["arx_swarm1", "arx_bft1", "uds_core"],
    "swarm_intent": ["arx_swarm1", "arx_swarm2", "arx_cuas3"],
    "u_minedops": ["arx_cuas1", "arx_cuas4", "arx_k8s"],
    "u_melt": ["uds_core", "arx_bft1", "slsa_dev"],
    "melt": ["uds_core", "arx_bft1"],
    "osint_naval": ["adsb_mil", "arx_mar1", "arx_mar2", "ofac_sdn", "un_dprk"],
    "osint_counter_uas": ["arx_cuas1", "arx_cuas2", "arx_cuas3", "arx_cuas4"],
    "osint_advisories": ["kev_mirror", "nvd", "epss", "nsa_advisories", "cert_ua"],
    "osint_procurement": ["fed_reg", "ukraine_open_data", "china_state_council"],
    "osint_geopolitical": ["cia_world_leaders", "china_mfa", "china_state_council", "ukraine_open_data", "un_dprk"],
    "amaru_naval": ["adsb_mil", "arx_mar1", "arx_mar2", "ofac_sdn", "un_dprk"],
    "amaru_counter_uas": ["arx_cuas1", "arx_cuas2", "arx_cuas3", "arx_cuas4"],
    "amaru_advisories": ["kev_mirror", "nvd", "epss", "nsa_advisories", "cert_ua"],
    "amaru_procurement": ["fed_reg", "ukraine_open_data"],
    "amaru_geopolitical": ["cia_world_leaders", "china_mfa", "ukraine_open_data", "un_dprk"],
    "operator_watch": ["adsb_mil", "arx_mar1", "ofac_sdn", "un_dprk"],
    "operator_correlate": ["adsb_mil", "arx_sc1", "arx_mar1", "kev_mirror"],
    "operator_entities": ["adsb_mil", "arx_sc1", "cia_world_leaders"],
    "operator_routing": ["adsb_mil", "uds_core"],
    "operator_digest": ["adsb_mil", "kev_mirror", "nsa_advisories", "cert_ua"],
    "rosie_watch": ["adsb_mil", "arx_mar1", "ofac_sdn", "un_dprk"],
    "rosie_correlate": ["adsb_mil", "arx_sc1", "arx_mar1", "kev_mirror"],
    "rosie_entities": ["adsb_mil", "arx_sc1", "cia_world_leaders"],
    "rosie_routing": ["adsb_mil", "uds_core"],
    "rosie_digest": ["adsb_mil", "kev_mirror", "nsa_advisories", "cert_ua"],
    "u_intel": ["adsb_mil", "kev_mirror", "nvd", "epss", "mitre_attack", "nsa_advisories", "cert_ua", "ofac_sdn", "un_dprk"],
    "u_darkgraph": ["adsb_mil", "kev_mirror", "mitre_attack", "arx_sc1", "arx_mar1", "ofac_sdn"],
    "darkgraph": ["adsb_mil", "kev_mirror", "mitre_attack", "arx_sc1", "arx_mar1", "ofac_sdn"],
    "darkhunt": ["adsb_mil", "kev_mirror", "nsa_advisories", "cert_ua", "arx_mar1"],
    "u_fusion": ["adsb_mil", "kev_mirror", "arx_sc1", "arx_mar1", "ofac_sdn", "un_dprk"],
    "fusion": ["adsb_mil", "kev_mirror", "arx_sc1", "ofac_sdn"],
    "u_posture": ["uds_core", "pepr", "arx_zt1", "arx_k8s", "nsa_advisories"],
    "posture_drift": ["uds_core", "pepr", "arx_zt1", "nist_800207"],
    "topology_health": ["uds_core", "arx_k8s", "arx_zt1"],
    "attack_surface": ["arx_k8s", "arx_zt1", "kev_mirror", "mitre_attack", "nsa_advisories"],
    "zerotrust_mesh": ["arx_zt1", "arx_zt2", "arx_zt3", "pepr", "nist_800207"],
    "u_warhacker": ["cosign", "in_toto", "slsa_dev", "arx_sc1"],
    "warhacker": ["cosign", "in_toto", "slsa_dev"],
    "warboard": ["cosign", "slsa_dev", "in_toto"],
    "uds_package": ["zarf", "uds_core", "uds_cli", "slsa_dev"],
    "u_consensus": ["arx_bft1", "arx_bft2", "uds_core"],
    "bft": ["arx_bft1", "arx_bft2"],
    "u_receipts": ["cosign", "in_toto", "slsa_dev"],
    "u_proofs": ["lean", "arx_lean1", "arx_lean2", "zenodo"],
    "u_about": ["uds_core", "slsa_dev", "lean", "zenodo"],
    "u_engage": ["du_home", "uds_core", "slsa_dev"],
    "engage": ["du_home", "uds_core"],
    "determinism_demo": ["lean", "cosign", "in_toto"],
    "tamper_demo": ["cosign", "in_toto", "slsa_dev"],
    "lambda": ["lean", "zenodo", "arx_lean1"],
    "putnam": ["lean", "arx_lean1", "arx_lean2", "arx_lean3"],
    "readiness": ["uds_core", "slsa_dev", "pepr"],
    "tracks": ["adsb_mil", "arx_mar1"],
    "livepic": ["adsb_mil", "arx_mar1"],
    "living_anatomy": ["lean", "zenodo", "arx_lean3"],
    "organism": ["lean", "zenodo", "arx_lean3"],
    "cross": ["adsb_mil", "kev_mirror", "arx_sc1", "ofac_sdn", "un_dprk"],
    "operate": ["uds_core", "pepr", "adsb_mil"],
    "pqc": ["arx_pqc1", "arx_pqc2", "cosign", "slsa_dev"],
    "kev": ["kev_mirror", "nvd", "epss", "arx_epss"],
    "cve": ["kev_mirror", "nvd", "epss"],
    "cve_watch": ["nvd", "kev_mirror", "epss", "arx_epss"],
    "cve_gate_impact": ["nvd", "kev_mirror", "epss", "slsa_dev"],
    "attack": ["mitre_attack", "mitre_site", "kev_mirror", "nsa_advisories", "arx_sc1"],
    "adversary_techniques": ["mitre_attack", "mitre_site", "kev_mirror", "nsa_advisories", "arx_sc1"],
    "signed_incidents": ["cosign", "in_toto", "slsa_dev", "kev_mirror", "cert_ua"],
    "threat_intelligence": ["kev_mirror", "nvd", "epss", "mitre_attack", "nsa_advisories", "cert_ua", "arx_sc1"],
    "feed_liveness": ["kev_mirror", "nvd", "epss", "mitre_attack", "adsb_mil", "usgs_quake", "ofac_sdn", "un_dprk"],
    "threats": ["kev_mirror", "nvd", "mitre_attack", "nsa_advisories", "cert_ua", "arx_sc1"],
    "threatrank": ["epss", "kev_mirror", "arx_epss"],
    "sanctions": ["ofac_sdn", "un_dprk", "fed_reg"],
    "roe": ["fed_reg", "asf_mag"],
    "legal": ["fed_reg"],
    "contracting": ["fed_reg", "ukraine_open_data"],
    "geofence": ["arx_cuas3", "adsb_mil"],
    "decoders": ["arx_cuas1", "arx_swarm2"],
    "pulse": ["usgs_quake"],
    "geoint": ["adsb_mil", "cia_world_leaders", "ukraine_open_data", "china_mfa"],
    "constellations": ["asf_mag", "lean"],
    "audit": ["cosign", "in_toto", "slsa_dev"],
    "chain": ["cosign", "in_toto", "slsa_dev"],
    "research": ["lean", "zenodo", "arx_sc1", "arx_lean1"],
    "honest": ["slsa_dev", "lean", "zenodo"],
    "deploy": ["zarf", "uds_core", "uds_cli"],
    "beyond": ["lean", "zenodo", "arx_lean1"],
    "scicompute": ["lean", "arx_lean3", "zenodo"],
    "healthtwin": ["arx_k8s", "uds_core"],
    "edgeest": ["arx_k8s", "arx_cuas4"],
    "telemem": ["arx_k8s", "adsb_mil"],
    "adaptsample": ["arx_cuas2", "adsb_mil"],
    "tacroute": ["arx_cuas3", "adsb_mil"],
    "prioritize": ["epss", "kev_mirror", "adsb_mil", "ofac_sdn"],
    "w910stl": ["uds_core", "arx_bft1"],
    "w910ci": ["arx_zt2", "cosign", "slsa_dev"],
    "w910gg": ["arx_swarm1", "arx_bft1"],
    "w910mesh": ["arx_zt1", "pepr", "uds_core"],
    "w910audit": ["cosign", "in_toto", "slsa_dev"],
    "w910quorum": ["arx_bft1", "arx_bft2"],
    "evidence": ["lean", "zenodo", "arx_sc1", "kev_mirror"],
    "live_intel": ["adsb_mil", "kev_mirror", "fed_reg", "nsa_advisories", "cert_ua", "ofac_sdn", "un_dprk", "china_mfa", "ukraine_open_data"],
}

_KW = [
    (("maritim", "naval", "vessel", "voyage", "ais", "fleet", "track"), ["adsb_mil", "arx_mar1", "arx_mar2", "ofac_sdn"]),
    (("uas", "drone", "swarm", "interdict", "counter", "geofenc", "decoder"), ["arx_cuas1", "arx_swarm1", "adsb_mil"]),
    (("kev", "cve", "advisor", "threat", "vuln", "exploit", "epss"), ["kev_mirror", "nvd", "epss", "mitre_attack", "nsa_advisories", "cert_ua"]),
    (("sanction", "dprk", "north_korea", "north-korea"), ["ofac_sdn", "un_dprk", "fed_reg"]),
    (("attack", "adversar", "mitre", "technique", "tactic", "ttp"), ["mitre_attack", "mitre_site", "kev_mirror", "nsa_advisories", "arx_sc1"]),
    (("receipt", "consensus", "bft", "quorum", "dsse", "chain", "khipu", "ledger"), ["cosign", "in_toto", "slsa_dev", "arx_bft1"]),
    (("proof", "putnam", "lambda", "anatomy", "organism", "formula", "determin", "tamper"), ["lean", "arx_lean1", "zenodo"]),
    (("uds", "package", "posture", "topology", "zerotrust", "mesh", "airgap", "deploy"), ["uds_core", "pepr", "zarf", "arx_zt1", "arx_k8s"]),
    (("pqc", "quantum"), ["arx_pqc1", "arx_pqc2", "cosign"]),
    (("space", "constellation", "orbit", "leo"), ["asf_mag", "lean"]),
    (("china", "prc", "beijing"), ["china_mfa", "china_state_council", "cia_world_leaders"]),
    (("ukraine", "kyiv", "cert-ua"), ["cert_ua", "ukraine_open_data", "cia_world_leaders"]),
    (("intel", "fusion", "darkgraph", "geopolit", "cross", "geoint"), ["cia_world_leaders", "china_mfa", "ukraine_open_data", "adsb_mil", "kev_mirror", "ofac_sdn", "un_dprk"]),
    (("legal", "roe", "contract", "procure", "audit", "compliance"), ["fed_reg", "ofac_sdn", "cosign", "slsa_dev"]),
]
_DEFAULT = ["uds_core", "slsa_dev", "lean", "adsb_mil"]


def _ids_for_tab(tab: str) -> list[str]:
    if tab in _TAB:
        return _TAB[tab]
    low = (tab or "").lower()
    for keys, ids in _KW:
        if any(key in low for key in keys):
            return ids
    return _DEFAULT


def _src_record(source_id: str) -> dict[str, _Any]:
    value = _SRC.get(source_id)
    if not value:
        return {"id": source_id, "title": source_id, "url": "", "kind": "unknown", "note": ""}
    title, url, kind, note = value
    return {"id": source_id, "title": title, "url": url, "kind": kind, "note": note}


def sources_for(tab: str) -> list[dict[str, _Any]]:
    return [_src_record(source_id) for source_id in _ids_for_tab(tab)]


_PROBE_CACHE: dict[str, tuple[float, dict[str, _Any]]] = {}
_PROBE_TTL = 600.0
_PROBE_TIMEOUT = 6.0
_PROBE_LOCK = _threading.Lock()


def _probe(url: str) -> dict[str, _Any]:
    if not url:
        return {"reachable": False, "http_status": 0, "checked_at": _now_iso(), "note": "no url"}
    now = _time.time()
    with _PROBE_LOCK:
        hit = _PROBE_CACHE.get(url)
        if hit and now - hit[0] < _PROBE_TTL:
            return hit[1]

    def _attempt(method: str) -> dict[str, _Any]:
        request = _urlreq.Request(
            url,
            method=method,
            headers={"User-Agent": _UA, "Accept": "*/*", "Range": "bytes=0-0"},
        )
        with _urlreq.urlopen(request, timeout=_PROBE_TIMEOUT) as response:
            code = int(getattr(response, "status", 0) or response.getcode() or 0)
            return {"reachable": 200 <= code < 400, "http_status": code, "checked_at": _now_iso()}

    result: dict[str, _Any] | None = None
    for method in ("HEAD", "GET"):
        try:
            result = _attempt(method)
            if result["reachable"]:
                break
        except _urlerr.HTTPError as error:
            code = int(getattr(error, "code", 0) or 0)
            result = {"reachable": 200 <= code < 400, "http_status": code, "checked_at": _now_iso()}
            if method == "GET":
                break
        except Exception as error:  # noqa: BLE001
            result = {"reachable": False, "http_status": 0, "checked_at": _now_iso(), "note": type(error).__name__}
    if result is None:
        result = {"reachable": False, "http_status": 0, "checked_at": _now_iso(), "note": "UNAVAILABLE"}
    with _PROBE_LOCK:
        _PROBE_CACHE[url] = (now, result)
    return result


def _summary(records: list[dict[str, _Any]], probed: bool) -> dict[str, _Any]:
    output: dict[str, _Any] = {"total": len(records)}
    if probed:
        live = sum(1 for record in records if record.get("reachable"))
        output["live"] = live
        output["unreachable"] = len(records) - live
    by_kind: dict[str, int] = {}
    for record in records:
        kind = str(record.get("kind") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
    output["by_kind"] = by_kind
    return output


_PUBLIC_POLICY = {
    "access": "PUBLIC_HTTPS_GET_ONLY",
    "classification": "PUBLIC",
    "authentication": "NONE",
    "arbitrary_url_input": False,
    "active_scanning": False,
    "form_submission": False,
    "protected_resources": False,
    "claim_boundary": "REPORTED source claims; MEASURED transport and payload evidence",
}

_PUBLIC_FEEDS: dict[str, dict[str, _Any]] = {
    "cisa-kev": {
        "title": "CISA Known Exploited Vulnerabilities",
        "url": "https://raw.githubusercontent.com/cisagov/kev-data/main/known_exploited_vulnerabilities.json",
        "hosts": ("raw.githubusercontent.com",),
        "jurisdiction": "us",
        "category": "cyber-advisory",
        "format": "json",
        "parser": "cisa-kev",
        "ttl": 1800,
        "max_bytes": 8_000_000,
        "path_prefix": None,
    },
    "nvd-recent": {
        "title": "NIST NVD CVE API 2.0",
        "url": "https://services.nvd.nist.gov/rest/json/cves/2.0?resultsPerPage=50",
        "hosts": ("services.nvd.nist.gov",),
        "jurisdiction": "us",
        "category": "vulnerability",
        "format": "json",
        "parser": "nvd",
        "ttl": 1800,
        "max_bytes": 10_000_000,
        "path_prefix": None,
    },
    "ofac-sdn": {
        "title": "US Treasury OFAC SDN list",
        "url": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
        "hosts": (
            "sanctionslistservice.ofac.treas.gov",
            "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com",
        ),
        "jurisdiction": "global",
        "category": "sanctions",
        "format": "xml",
        "parser": "ofac",
        "ttl": 21600,
        "max_bytes": 30_000_000,
        "path_prefix": None,
    },
    "un-dprk-1718": {
        "title": "UN Security Council DPRK 1718 sanctions",
        "url": "https://scsanctions.un.org/resources/xml/en/name/consolidated.xml",
        "hosts": ("scsanctions.un.org", "unsolprodfiles.blob.core.windows.net"),
        "jurisdiction": "dprk-related",
        "category": "sanctions",
        "format": "xml",
        "parser": "un-dprk",
        "ttl": 21600,
        "max_bytes": 30_000_000,
        "path_prefix": None,
    },
    "cia-world-leaders": {
        "title": "CIA World Leaders — foreign governments",
        "url": "https://www.cia.gov/resources/world-leaders/foreign-governments/",
        "hosts": ("www.cia.gov",),
        "jurisdiction": "global",
        "category": "government-directory",
        "format": "html",
        "parser": "html-index",
        "ttl": 21600,
        "max_bytes": 4_000_000,
        "path_prefix": "/resources/world-leaders/foreign-governments/",
    },
    "nsa-advisories": {
        "title": "NSA public cybersecurity advisories",
        "url": "https://www.nsa.gov/Cybersecurity/Cybersecurity-Advisories-Guidance/",
        "hosts": ("www.nsa.gov",),
        "jurisdiction": "us",
        "category": "cyber-advisory",
        "format": "html",
        "parser": "html-index",
        "ttl": 1800,
        "max_bytes": 6_000_000,
        "path_prefix": "/Cybersecurity/Cybersecurity-Advisories-Guidance/",
    },
    "cert-ua": {
        "title": "CERT-UA public recommendations",
        "url": "https://cert.gov.ua/recommendations",
        "hosts": ("cert.gov.ua",),
        "jurisdiction": "ukraine",
        "category": "cyber-advisory",
        "format": "html",
        "parser": "html-index",
        "ttl": 1800,
        "max_bytes": 5_000_000,
        "path_prefix": "/recommend",
    },
    "ukraine-open-data": {
        "title": "Ukraine open-data CKAN activity",
        "url": "https://data.gov.ua/api/3/action/recently_changed_packages_activity_list?limit=50",
        "hosts": ("data.gov.ua",),
        "jurisdiction": "ukraine",
        "category": "open-data-metadata",
        "format": "json",
        "parser": "ukraine-ckan",
        "ttl": 1800,
        "max_bytes": 8_000_000,
        "path_prefix": None,
    },
    "china-mfa": {
        "title": "PRC Ministry of Foreign Affairs press conferences",
        "url": "https://www.mfa.gov.cn/mfa_eng/xw/fyrbt/lxjzh/index.html",
        "hosts": ("www.mfa.gov.cn",),
        "jurisdiction": "china",
        "category": "official-statement",
        "format": "html",
        "parser": "html-index",
        "ttl": 1800,
        "max_bytes": 6_000_000,
        "path_prefix": "/mfa_eng/xw/fyrbt/",
    },
    "china-state-council": {
        "title": "PRC State Council policy releases",
        "url": "https://english.www.gov.cn/policies/latestreleases/",
        "hosts": ("english.www.gov.cn",),
        "jurisdiction": "china",
        "category": "official-policy",
        "format": "html",
        "parser": "html-index",
        "ttl": 1800,
        "max_bytes": 6_000_000,
        "path_prefix": "/policies/latestreleases/",
    },
}
_PUBLIC_CACHE: dict[str, tuple[float, dict[str, _Any]]] = {}
_PUBLIC_CACHE_LOCK = _threading.Lock()
_PUBLIC_FETCH_LOCKS = {source_id: _threading.Lock() for source_id in _PUBLIC_FEEDS}
_ALLOWED_CONTENT_TYPES = (
    "application/json",
    "application/xml",
    "text/xml",
    "text/html",
    "text/plain",
    "application/octet-stream",
)


def _is_public_ip(address: str) -> bool:
    ip = _ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_target(url: str, allowed_hosts: tuple[str, ...]) -> str:
    parsed = _urlparse.urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("HTTPS_REQUIRED")
    if parsed.username or parsed.password:
        raise ValueError("USERINFO_FORBIDDEN")
    if parsed.port not in (None, 443):
        raise ValueError("PORT_FORBIDDEN")
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in allowed_hosts:
        raise ValueError("HOST_NOT_ALLOWLISTED")
    addresses = {
        item[4][0]
        for item in _socket.getaddrinfo(host, 443, type=_socket.SOCK_STREAM)
    }
    if not addresses or not all(_is_public_ip(address) for address in addresses):
        raise ValueError("NON_PUBLIC_ADDRESS")
    return host


class _BoundRedirect(_urlreq.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: tuple[str, ...]):
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        _validate_target(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_bytes(source: dict[str, _Any]) -> tuple[bytes, dict[str, _Any]]:
    url = str(source["url"])
    hosts = tuple(source["hosts"])
    _validate_target(url, hosts)
    request = _urlreq.Request(
        url,
        method="GET",
        headers={
            "User-Agent": _UA,
            "Accept": "application/json, application/xml, text/xml, text/html;q=0.9, text/plain;q=0.8",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache",
        },
    )
    opener = _urlreq.build_opener(_urlreq.ProxyHandler({}), _BoundRedirect(hosts))
    max_bytes = int(source["max_bytes"])
    with opener.open(request, timeout=12) as response:
        final_url = response.geturl()
        _validate_target(final_url, hosts)
        status = int(getattr(response, "status", 0) or response.getcode() or 0)
        if status != 200:
            raise RuntimeError("HTTP_%d" % status)
        content_type = (response.headers.get_content_type() or "").lower()
        if not any(content_type.startswith(allowed) for allowed in _ALLOWED_CONTENT_TYPES):
            raise ValueError("CONTENT_TYPE_NOT_ALLOWED")
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > max_bytes:
            raise ValueError("PAYLOAD_TOO_LARGE")
        payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError("PAYLOAD_TOO_LARGE")
        metadata = {
            "http_status": status,
            "final_url": final_url,
            "content_type": content_type,
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        }
    return payload, metadata


def _text(node: _etree.Element | None, name: str) -> str:
    if node is None:
        return ""
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1] == name:
            return " ".join("".join(child.itertext()).split())
    return ""


def _record(
    source_id: str,
    title: str,
    *,
    item_id: str = "",
    summary: str = "",
    published: str = "",
    url: str = "",
    extra: dict[str, _Any] | None = None,
) -> dict[str, _Any]:
    source = _PUBLIC_FEEDS[source_id]
    canonical = _json.dumps(
        {
            "source_id": source_id,
            "id": item_id,
            "title": title,
            "summary": summary,
            "published": published,
            "url": url,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    output: dict[str, _Any] = {
        "id": item_id or _hashlib.sha256(canonical).hexdigest()[:24],
        "title": title or "UNAVAILABLE",
        "summary": summary,
        "published": published or None,
        "url": url or source["url"],
        "source_id": source_id,
        "source_title": source["title"],
        "jurisdiction": source["jurisdiction"],
        "category": source["category"],
        "claim_state": "REPORTED",
        "evidence_state": "MEASURED",
        "content_sha256": _hashlib.sha256(canonical).hexdigest(),
    }
    if extra:
        output["attributes"] = extra
    return output


def _parse_cisa(source_id: str, payload: bytes) -> list[dict[str, _Any]]:
    document = _json.loads(payload.decode("utf-8"))
    output = []
    for row in document.get("vulnerabilities", [])[:500]:
        cve = str(row.get("cveID") or "")
        output.append(
            _record(
                source_id,
                str(row.get("vulnerabilityName") or cve or "UNAVAILABLE"),
                item_id=cve,
                summary=str(row.get("shortDescription") or ""),
                published=str(row.get("dateAdded") or ""),
                url="https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                extra={
                    "vendor_project": row.get("vendorProject"),
                    "product": row.get("product"),
                    "required_action": row.get("requiredAction"),
                    "due_date": row.get("dueDate"),
                    "known_ransomware_use": row.get("knownRansomwareCampaignUse"),
                },
            )
        )
    return output


def _parse_nvd(source_id: str, payload: bytes) -> list[dict[str, _Any]]:
    document = _json.loads(payload.decode("utf-8"))
    output = []
    for wrapper in document.get("vulnerabilities", [])[:200]:
        cve = wrapper.get("cve") or {}
        descriptions = cve.get("descriptions") or []
        description = next(
            (str(row.get("value") or "") for row in descriptions if row.get("lang") == "en"),
            "",
        )
        cve_id = str(cve.get("id") or "")
        output.append(
            _record(
                source_id,
                cve_id or "NVD vulnerability record",
                item_id=cve_id,
                summary=description,
                published=str(cve.get("published") or ""),
                url="https://nvd.nist.gov/vuln/detail/%s" % cve_id if cve_id else source_id,
                extra={"last_modified": cve.get("lastModified"), "source_identifier": cve.get("sourceIdentifier")},
            )
        )
    return output


def _parse_ofac(source_id: str, payload: bytes) -> list[dict[str, _Any]]:
    root = _etree.fromstring(payload)
    output = []
    for entry in [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "sdnEntry"][:5000]:
        uid = _text(entry, "uid")
        first = _text(entry, "firstName")
        last = _text(entry, "lastName")
        programs = [
            " ".join("".join(node.itertext()).split())
            for node in entry.iter()
            if node.tag.rsplit("}", 1)[-1] == "program" and "".join(node.itertext()).strip()
        ]
        name = " ".join(part for part in (first, last) if part).strip() or uid or "UNAVAILABLE"
        output.append(
            _record(
                source_id,
                name,
                item_id=uid,
                summary=_text(entry, "remarks"),
                url="https://sanctionssearch.ofac.treas.gov/Details.aspx?id=%s" % uid if uid else source_id,
                extra={"sdn_type": _text(entry, "sdnType"), "programs": sorted(set(programs))},
            )
        )
    return output


def _parse_un_dprk(source_id: str, payload: bytes) -> list[dict[str, _Any]]:
    root = _etree.fromstring(payload)
    output = []
    for entry in [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] in {"INDIVIDUAL", "ENTITY"}]:
        reference = _text(entry, "REFERENCE_NUMBER")
        if not reference.startswith(("KPi.", "KPe.")):
            continue
        names = [_text(entry, key) for key in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")]
        name = " ".join(value for value in names if value).strip() or _text(entry, "NAME_ORIGINAL_SCRIPT") or reference
        output.append(
            _record(
                source_id,
                name,
                item_id=reference,
                summary=_text(entry, "COMMENTS1"),
                published=_text(entry, "LISTED_ON"),
                url="https://main.un.org/securitycouncil/en/sanctions/1718/materials",
                extra={"record_type": entry.tag.rsplit("}", 1)[-1]},
            )
        )
    return output


def _parse_ukraine_ckan(source_id: str, payload: bytes) -> list[dict[str, _Any]]:
    document = _json.loads(payload.decode("utf-8"))
    rows = document.get("result") if document.get("success") is True else []
    if not isinstance(rows, list):
        return []
    output = []
    for row in rows[:200]:
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        package = data.get("package") if isinstance(data.get("package"), dict) else data
        name = str(package.get("name") or package.get("id") or row.get("object_id") or "")
        title = str(package.get("title") or data.get("title") or name or row.get("activity_type") or "Dataset activity")
        output.append(
            _record(
                source_id,
                title,
                item_id=str(row.get("id") or name),
                summary=str(row.get("activity_type") or "dataset metadata activity"),
                published=str(row.get("timestamp") or row.get("last_updated") or ""),
                url="https://data.gov.ua/dataset/%s" % _urlparse.quote(name) if name else source_id,
                extra={"activity_type": row.get("activity_type"), "dataset_name": name},
            )
        )
    return output


class _LinkIndex(_html_parser.HTMLParser):
    def __init__(self, base_url: str, allowed_hosts: tuple[str, ...], path_prefix: str | None):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.allowed_hosts = allowed_hosts
        self.path_prefix = path_prefix
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.rows: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.current_href = str(href)
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self.current_href is None:
            return
        title = " ".join(" ".join(self.current_text).split())
        absolute = _urlparse.urljoin(self.base_url, self.current_href)
        parsed = _urlparse.urlsplit(absolute)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            title
            and len(title) >= 8
            and parsed.scheme == "https"
            and host in self.allowed_hosts
            and (not self.path_prefix or parsed.path.startswith(self.path_prefix))
            and absolute.rstrip("/") != self.base_url.rstrip("/")
        ):
            self.rows.append((title, absolute))
        self.current_href = None
        self.current_text = []


def _parse_html_index(source_id: str, payload: bytes) -> list[dict[str, _Any]]:
    source = _PUBLIC_FEEDS[source_id]
    parser = _LinkIndex(source["url"], tuple(source["hosts"]), source.get("path_prefix"))
    parser.feed(payload.decode("utf-8", "replace"))
    seen: set[tuple[str, str]] = set()
    output = []
    for title, url in parser.rows:
        key = (title.casefold(), url)
        if key in seen:
            continue
        seen.add(key)
        output.append(_record(source_id, title, url=url))
        if len(output) >= 100:
            break
    return output


_PARSERS = {
    "cisa-kev": _parse_cisa,
    "nvd": _parse_nvd,
    "ofac": _parse_ofac,
    "un-dprk": _parse_un_dprk,
    "ukraine-ckan": _parse_ukraine_ckan,
    "html-index": _parse_html_index,
}


def _public_result(source_id: str) -> dict[str, _Any]:
    source = _PUBLIC_FEEDS.get(source_id)
    if source is None:
        return {"state": "UNAVAILABLE", "reason": "UNKNOWN_SOURCE", "source_id": source_id, "items": []}
    now = _time.time()
    with _PUBLIC_CACHE_LOCK:
        hit = _PUBLIC_CACHE.get(source_id)
        if hit and now - hit[0] < int(source["ttl"]):
            cached = dict(hit[1])
            cached["cache"] = "HIT"
            return cached
    with _PUBLIC_FETCH_LOCKS[source_id]:
        with _PUBLIC_CACHE_LOCK:
            hit = _PUBLIC_CACHE.get(source_id)
            if hit and _time.time() - hit[0] < int(source["ttl"]):
                cached = dict(hit[1])
                cached["cache"] = "HIT"
                return cached
        fetched_at = _now_iso()
        try:
            payload, metadata = _fetch_bytes(source)
            parser = _PARSERS[str(source["parser"])]
            items = parser(source_id, payload)
            result = {
                "state": "MEASURED",
                "source_id": source_id,
                "source": {
                    "title": source["title"],
                    "url": source["url"],
                    "jurisdiction": source["jurisdiction"],
                    "category": source["category"],
                    "classification": "PUBLIC",
                    "access_mode": "PUBLIC_HTTPS_GET_ONLY",
                },
                "fetched_at": fetched_at,
                "cache": "MISS",
                "transport": metadata,
                "payload_sha256": _hashlib.sha256(payload).hexdigest(),
                "payload_bytes": len(payload),
                "item_count": len(items),
                "items": items,
                "claim_boundary": _PUBLIC_POLICY["claim_boundary"],
            }
        except Exception as error:  # noqa: BLE001
            result = {
                "state": "UNAVAILABLE",
                "source_id": source_id,
                "source": {
                    "title": source["title"],
                    "url": source["url"],
                    "jurisdiction": source["jurisdiction"],
                    "category": source["category"],
                    "classification": "PUBLIC",
                    "access_mode": "PUBLIC_HTTPS_GET_ONLY",
                },
                "fetched_at": fetched_at,
                "cache": "MISS",
                "reason": type(error).__name__,
                "item_count": None,
                "items": [],
                "claim_boundary": _PUBLIC_POLICY["claim_boundary"],
            }
        with _PUBLIC_CACHE_LOCK:
            _PUBLIC_CACHE[source_id] = (_time.time(), result)
        return dict(result)


def _public_source_rows() -> list[dict[str, _Any]]:
    rows = []
    for source_id, source in sorted(_PUBLIC_FEEDS.items()):
        rows.append(
            {
                "id": source_id,
                "title": source["title"],
                "url": source["url"],
                "jurisdiction": source["jurisdiction"],
                "category": source["category"],
                "format": source["format"],
                "classification": "PUBLIC",
                "access_mode": "PUBLIC_HTTPS_GET_ONLY",
                "ttl_seconds": source["ttl"],
                "max_bytes": source["max_bytes"],
                "allowed_hosts": list(source["hosts"]),
            }
        )
    return rows


def register(app, ns: str = "killinchu") -> None:
    """Attach legacy research routes and the additive public-intel mesh."""
    try:
        from fastapi.responses import JSONResponse
    except Exception:  # pragma: no cover
        return

    research_base = "/api/%s/v1/research" % ns
    intel_base = "/api/%s/v1/public-intel" % ns

    @app.get(intel_base + "/sources")
    async def _public_sources():  # noqa: ANN202
        return JSONResponse({
            "layer": "%s public-intelligence source mesh" % ns,
            "state": "DECLARED",
            "policy": _PUBLIC_POLICY,
            "source_count": len(_PUBLIC_FEEDS),
            "sources": _public_source_rows(),
            "checked_at": _now_iso(),
        })

    @app.get(intel_base + "/status")
    async def _public_status():  # noqa: ANN202
        with _PUBLIC_CACHE_LOCK:
            cache = {
                source_id: {
                    "state": value[1].get("state", "UNAVAILABLE"),
                    "fetched_at": value[1].get("fetched_at"),
                    "age_seconds": max(0, round(_time.time() - value[0], 1)),
                    "item_count": value[1].get("item_count"),
                }
                for source_id, value in sorted(_PUBLIC_CACHE.items())
            }
        return JSONResponse({
            "layer": "%s public-intelligence source mesh" % ns,
            "state": "MEASURED",
            "policy": _PUBLIC_POLICY,
            "registered_sources": len(_PUBLIC_FEEDS),
            "cached_sources": len(cache),
            "cache": cache,
            "checked_at": _now_iso(),
        })

    @app.get(intel_base + "/digest")
    async def _public_digest(jurisdiction: str = "all", limit: int = 50):  # noqa: ANN202
        import asyncio

        limit = max(1, min(int(limit), 100))
        allowed = {"all"} | {str(source["jurisdiction"]) for source in _PUBLIC_FEEDS.values()}
        if jurisdiction not in allowed:
            return JSONResponse(
                {"state": "UNAVAILABLE", "reason": "UNKNOWN_JURISDICTION", "allowed": sorted(allowed), "items": []},
                status_code=400,
            )
        selected = [
            source_id
            for source_id, source in sorted(_PUBLIC_FEEDS.items())
            if jurisdiction == "all" or source["jurisdiction"] == jurisdiction
        ]
        semaphore = asyncio.Semaphore(3)

        async def _one(source_id: str) -> dict[str, _Any]:
            async with semaphore:
                return await asyncio.to_thread(_public_result, source_id)

        results = list(await asyncio.gather(*[_one(source_id) for source_id in selected]))
        items = []
        for result in results:
            items.extend(result.get("items") or [])
        items.sort(key=lambda row: str(row.get("published") or ""), reverse=True)
        measured = sum(1 for result in results if result.get("state") == "MEASURED")
        return JSONResponse({
            "layer": "%s public-intelligence digest" % ns,
            "state": "MEASURED" if measured else "UNAVAILABLE",
            "jurisdiction": jurisdiction,
            "policy": _PUBLIC_POLICY,
            "sources_requested": len(selected),
            "sources_measured": measured,
            "sources_unavailable": len(selected) - measured,
            "source_states": {result["source_id"]: result.get("state", "UNAVAILABLE") for result in results},
            "item_count": min(len(items), limit),
            "items": items[:limit],
            "checked_at": _now_iso(),
        })

    @app.get(intel_base + "/{source_id}")
    async def _public_source(source_id: str, limit: int = 50):  # noqa: ANN202
        if source_id not in _PUBLIC_FEEDS:
            return JSONResponse(
                {"state": "UNAVAILABLE", "reason": "UNKNOWN_SOURCE", "source_id": source_id, "items": []},
                status_code=404,
            )
        limit = max(1, min(int(limit), 100))
        result = await __import__("asyncio").to_thread(_public_result, source_id)
        result = dict(result)
        result["items"] = list(result.get("items") or [])[:limit]
        result["returned_items"] = len(result["items"])
        return JSONResponse(result, status_code=200 if result.get("state") == "MEASURED" else 503)

    @app.get(research_base)
    async def _research_index():  # noqa: ANN202
        return JSONResponse({
            "layer": "%s research & sources" % ns,
            "honest": _HONEST,
            "tabs_with_overrides": sorted(_TAB.keys()),
            "source_pool": len(_SRC),
            "public_intel": intel_base + "/sources",
            "checked_at": _now_iso(),
        })

    @app.get(research_base + "/{tab}")
    async def _research_tab(tab: str):  # noqa: ANN202
        records = sources_for(tab)
        return JSONResponse({
            "layer": "%s research sources" % ns,
            "honest": _HONEST,
            "tab": tab,
            "explicit": tab in _TAB,
            "summary": _summary(records, probed=False),
            "sources": records,
            "checked_at": _now_iso(),
        })

    @app.get(research_base + "/{tab}/live")
    async def _research_tab_live(tab: str):  # noqa: ANN202
        import asyncio

        records = sources_for(tab)

        async def _one(record: dict[str, _Any]) -> dict[str, _Any]:
            result = await asyncio.to_thread(_probe, record["url"])
            merged = dict(record)
            merged.update(result)
            return merged

        probed = list(await asyncio.gather(*[_one(record) for record in records]))
        return JSONResponse({
            "layer": "%s research sources (live probe)" % ns,
            "honest": _HONEST,
            "tab": tab,
            "explicit": tab in _TAB,
            "summary": _summary(probed, probed=True),
            "sources": probed,
            "checked_at": _now_iso(),
        })
