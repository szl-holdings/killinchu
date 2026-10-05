"""Actual route reads must not mint receipts or update platform-fix history."""
from copy import deepcopy
import hashlib
import importlib
import json
import threading
from types import SimpleNamespace
import urllib.request

from fastapi.testclient import TestClient
import pytest

from killinchu_ledger import DURABLE_EXTERNAL, EPHEMERAL, LedgerRuntime
import killinchu_ledger_sqlite as storage


AIR = {"hex": "LOCAL", "lat": 59.3, "lon": 22.1, "gs": 18.0, "track": 90.0,
       "true_heading": 90.0, "nic": 9}
AIS = {"mmsi": "LOCAL", "lat": 59.3, "lon": 22.1, "sog": 18.0, "cog": 90.0,
       "heading": 90.0, "raim": True, "posAcc": True, "navStat": 0}
SITES = ["borrowed", "geoint", "integrity", "twin", "posture"]


def _digest(receipt, parents):
    digest = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode())
    for parent in parents:
        digest.update(parent.encode())
    return digest.hexdigest()


@pytest.fixture
def host(monkeypatch, request):
    network = []

    def forbid_network(*args, **kwargs):
        network.append(True)
        raise OSError("offline route test has no provider access")

    monkeypatch.setattr(urllib.request, "urlopen", forbid_network)
    # Host registration also starts an unrelated readiness snapshot builder.
    # Keep that background provider-probe lane out of this offline route suite.
    monkeypatch.setenv("SZL_READINESS_WARM", "0")
    readiness = importlib.import_module("szl_readiness")
    monkeypatch.setattr(readiness, "_kick_background_build", lambda ns: None)
    module = importlib.import_module("serve")
    twin = importlib.import_module("killinchu_health_twin")
    posture = importlib.import_module("killinchu_posture_topology")
    feeds = importlib.import_module("killinchu_live_feeds")
    monkeypatch.setattr(twin, "_lf", SimpleNamespace(
        _fetch_air=lambda *a: {"aircraft": [deepcopy(AIR)]},
        _fetch_ais=lambda *a: {"vessels": [deepcopy(AIS)]}))
    # Threat-feed unavailability is explicit. The actual health/trust math runs.
    unavailable = {"available": False, "hits": [], "hit": False, "note": "LOCAL_TEST"}
    for name in ("_kev_uas_hits", "_nvd_uas_hits", "_ofac_sdn_screen"):
        monkeypatch.setattr(twin, name, lambda *a: deepcopy(unavailable))
    monkeypatch.setattr(feeds, "get_feed", lambda *a: {
        "data": posture._reference_snapshot(), "mode": "SAMPLE"})
    address = "observational-" + hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:12]
    network.clear()
    return module, TestClient(module.app, client=(address, 50000)), twin, network


def _path(host, site):
    prefix = "/api/killinchu/v1"
    return {
        "borrowed": prefix + "/borrowed-powers",
        "geoint": prefix + "/geoint?lat=59.3&lon=22.1&radius_km=25",
        "integrity": prefix + "/drones/" + str(host[0]._DRONES[0]["id"]) + "/integrity",
        "twin": prefix + "/twin/state?platform=ADSB-LOCAL",
        "posture": prefix + "/posture/drift",
    }[site]


def _runtime(tmp_path, host, monkeypatch, mode, *, started=True):
    adapter = None
    path = None
    if mode == DURABLE_EXTERNAL:
        path = tmp_path / "canonical.sqlite3"
        adapter = storage.SQLiteLedgerAdapter(path, storage.provision(path), timeout_s=0.02)
    runtime = LedgerRuntime([], threading.RLock(), _digest, mode=mode, adapter=adapter,
                            recovery_interval_s=0)
    if started:
        assert runtime.startup()["ready"] is True
        receipt = {"kind": "LOCAL_TEST", "synthetic": True}
        runtime.append({"index": 0, "parents": [], "receipt": receipt,
                        "digest": _digest(receipt, []), "dsse": {"signatures": []}})
    monkeypatch.setattr(host[0], "_LEDGER_RUNTIME", runtime)
    monkeypatch.setattr(host[0], "_KHIPU_DAG", runtime._dag)
    return runtime, adapter, path


def _observe(monkeypatch, host, runtime, adapter):
    calls = {"startup": 0, "append": 0, "readiness": 0, "adapter": 0, "sign": 0}
    for name in ("startup", "append", "readiness"):
        original = getattr(runtime, name)

        def counted(*args, _name=name, _original=original, **kwargs):
            calls[_name] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(runtime, name, counted)
    if adapter:
        for name in ("startup", "append", "readiness", "replay", "verify_integrity"):
            original = getattr(adapter, name)

            def counted_adapter(*args, _original=original, **kwargs):
                calls["adapter"] += 1
                return _original(*args, **kwargs)

            monkeypatch.setattr(adapter, name, counted_adapter)

    def forbidden_sign(*args, **kwargs):
        calls["sign"] += 1
        raise AssertionError("a read must not sign")

    monkeypatch.setattr(host[0], "_receipt_signatures", forbidden_sign)
    import szl_dsse
    monkeypatch.setattr(szl_dsse, "sign_payload", forbidden_sign)
    for name in ("signing_available", "_load_private_key", "public_key_fingerprint"):
        monkeypatch.setattr(szl_dsse, name, forbidden_sign)
    # The shared key helper is optional in this host. A trap also catches a
    # future dynamic import instead of assuming the module is already present.
    import sys
    monkeypatch.setitem(sys.modules, "a11oy_signing_key",
                        SimpleNamespace(load_signing_key=forbidden_sign))
    monkeypatch.setattr(storage, "provision", lambda *a, **k: pytest.fail("read provisioned storage"))
    return calls


@pytest.mark.parametrize("mode", [EPHEMERAL, DURABLE_EXTERNAL])
@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("method", ["get", "head"])
def test_served_observation_does_not_mint_or_change_store(
        tmp_path, monkeypatch, host, mode, site, method):
    runtime, adapter, database = _runtime(tmp_path, host, monkeypatch, mode)
    twin = host[2]
    monkeypatch.setattr(twin, "_LAST_FIX", {"LOCAL": {"lat": 59.0, "lon": 22.0, "ts": 1.0}})
    monkeypatch.setattr(twin, "_LAST_FIX_AIR", {
        "LOCAL": {"lat": 59.0, "lon": 22.0, "ts": 1.0, "track": 85.0}})
    before = runtime.snapshot()
    before_database = database.read_bytes() if database else None
    history = deepcopy((twin._LAST_FIX, twin._LAST_FIX_AIR, twin._THREAT_CACHE))
    calls = _observe(monkeypatch, host, runtime, adapter)
    response = getattr(host[1], method)(_path(host, site))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert host[3] == []
    if method == "head":
        assert response.content == b""
    else:
        body = response.json()
        receipt = body["query_receipt"] if site == "borrowed" else body["receipt"]
        assert receipt["index"] is receipt["digest"] is None
        assert receipt["signed"] is False
        assert receipt["state"] == "UNSIGNED_READ_ONLY"
        assert body["receipt_minted"] is False
        assert body["export_read_only"] is True
        if site == "geoint":
            assert body["observation_count"] == len(body["observations"]) > 0
            assert "planning estimate" in body["honesty"]
        if site == "borrowed":
            assert body["signing"]["dsse_signing_available"] is None
            assert body["signing"]["state"] == "UNKNOWN"
            assert body["signing"]["fingerprint"] is None
        if site == "integrity":
            assert body["tripwires_evaluated"] == len(body["tripwires"]) > 0
        if site == "twin":
            assert body["subsystems"]
            assert body["conformal"]["method"].startswith("split-conformal")
            assert "Conjecture 1" in body["lambda_meaning"]
        if site == "posture":
            assert body["verdict"] in {"STABLE", "DRIFT DETECTED"}
            assert len(body["features"]) == 3
    assert runtime.snapshot() == before
    assert (twin._LAST_FIX, twin._LAST_FIX_AIR, twin._THREAT_CACHE) == history
    if database:
        assert database.read_bytes() == before_database
    assert calls == {name: 0 for name in calls}
    # Confirm the first matching served route precedes the host SPA fallback.
    from starlette.routing import Match
    scope = {"type": "http", "path": _path(host, site).split("?")[0],
             "method": method.upper(), "root_path": ""}
    first = next(route for route in host[0].app.router.routes
                 if route.matches(scope)[0] is Match.FULL)
    assert first.endpoint.__module__ in {
        "killinchu_elite_console", "killinchu_expansion",
        "killinchu_health_twin", "killinchu_posture_topology"}


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("failure", ["unstarted", "missing"])
def test_unsigned_preview_does_not_recover_or_claim_ledger_readiness(
        tmp_path, monkeypatch, host, site, failure):
    runtime, adapter, database = _runtime(
        tmp_path, host, monkeypatch, DURABLE_EXTERNAL, started=failure != "unstarted")
    if failure == "missing":
        database.rename(tmp_path / "preserved.sqlite3")
        assert runtime.readiness(recover=False)["ready"] is False
    before = runtime.snapshot()
    calls = _observe(monkeypatch, host, runtime, adapter)
    response = host[1].get(_path(host, site))
    assert response.status_code == 200
    assert host[3] == []
    body = response.json()
    assert body["receipt_minted"] is False
    assert body["export_read_only"] is True
    assert "ledger" not in body and "production_ready" not in body
    assert runtime.snapshot() == before
    assert runtime._ready is False
    assert calls == {name: 0 for name in calls}
    if failure == "missing":
        assert not database.exists()


@pytest.mark.parametrize("kind", ["air", "ais"])
@pytest.mark.parametrize("method", ["get", "head"])
def test_twin_fix_observation_preserves_previous_history_and_trust(
        tmp_path, monkeypatch, host, kind, method):
    runtime, adapter, database = _runtime(tmp_path, host, monkeypatch, EPHEMERAL)
    twin = host[2]
    history_name = "_LAST_FIX_AIR" if kind == "air" else "_LAST_FIX"
    history = {"LOCAL": {"lat": 59.0, "lon": 22.0, "ts": 1.0, "track": 85.0}}
    monkeypatch.setattr(twin, history_name, deepcopy(history))
    data = AIR if kind == "air" else AIS
    mapper = twin._signals_from_air if kind == "air" else twin._signals_from_ais
    platform = "ADSB-LOCAL" if kind == "air" else "AIS-LOCAL"
    expected = twin._platform_state(platform, mapper(data, read_only=True))
    response = getattr(host[1], method)("/api/killinchu/v1/twin/state?platform=" + platform)
    assert response.status_code == 200
    assert getattr(twin, history_name) == history
    if method == "get":
        body = response.json()
        assert body["lambda"] == expected["lambda"]
        assert body["yuyay_gate"] == expected["yuyay_gate"]
        assert body["subsystems"] == expected["subsystems"]
    # The existing explicit writer mapping retains its history recording.
    mapper(data)
    assert getattr(twin, history_name)["LOCAL"]["lat"] == data["lat"]
    assert getattr(twin, history_name) != history


@pytest.mark.parametrize("site", ["geoint", "integrity"])
def test_existing_expansion_post_still_writes_receipt(tmp_path, monkeypatch, host, site):
    runtime, adapter, database = _runtime(tmp_path, host, monkeypatch, DURABLE_EXTERNAL, started=False)
    monkeypatch.setattr(host[0], "_receipt_signatures", lambda receipt: ([], False))
    body = {"lat": 59.3, "lon": 22.1, "radius_km": 25} if site == "geoint" else {
        "force_fire": ["T11"]}
    response = host[1].post(_path(host, site).split("?")[0], json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["receipt"]["index"] == 0
    assert payload["receipt_minted"] is True
    assert payload["export_read_only"] is False
    node = runtime.snapshot()[0]
    assert node["receipt"]["kind"] == ("geoint_aggregation" if site == "geoint" else "integrity_scan")
    assert node["digest"] == payload["receipt"]["digest"]
    assert adapter.replay() == [node]
    assert runtime.readiness(recover=False)["production_ready"] is False
    if site == "integrity":
        assert "T11" in payload["fired"]


@pytest.mark.parametrize("site", ["geoint", "integrity"])
def test_existing_expansion_post_fails_closed_on_missing_store(tmp_path, monkeypatch, host, site):
    runtime, adapter, database = _runtime(tmp_path, host, monkeypatch, DURABLE_EXTERNAL, started=False)
    database.rename(tmp_path / "preserved.sqlite3")
    monkeypatch.setattr(host[0], "_receipt_signatures", lambda receipt: ([], False))
    response = host[1].post(_path(host, site).split("?")[0], json={})
    assert response.status_code == 503
    assert runtime.snapshot() == []
    assert not database.exists()


def test_explicit_twin_remediation_keeps_simulated_writer_contract(tmp_path, monkeypatch, host):
    runtime, adapter, database = _runtime(tmp_path, host, monkeypatch, DURABLE_EXTERNAL, started=False)
    monkeypatch.setattr(host[0], "_receipt_signatures", lambda receipt: ([], False))
    response = host[1].post("/api/killinchu/v1/twin/remediate",
                           json={"platform": "ADSB-LOCAL", "action": "recall"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] in {"AUTHORIZED", "DENIED"}
    assert "SIMULATED" in body["governance"]["effector"]
    assert body["receipt"]["index"] == 0
    assert host[2]._LAST_FIX_AIR["LOCAL"]["lat"] == AIR["lat"]
    assert runtime.snapshot()[0]["receipt"]["kind"] == "twin_remediate"
    assert adapter.replay() == runtime.snapshot()


def test_missing_drone_does_not_mint(tmp_path, monkeypatch, host):
    runtime, adapter, database = _runtime(tmp_path, host, monkeypatch, EPHEMERAL)
    calls = _observe(monkeypatch, host, runtime, adapter)
    response = host[1].get("/api/killinchu/v1/drones/ABSENT/integrity")
    assert response.status_code == 404
    assert calls == {name: 0 for name in calls}


@pytest.mark.parametrize("values", [[1.0], [1.0, 1.0], [10.0, 0.98], [0.97, 0.97], [10**1000], [-10**1000]])
def test_health_trust_aggregate_cannot_exceed_ceiling(host, values):
    assert 0.0 <= host[2]._geo_mean(values) <= 0.97


@pytest.mark.parametrize("values", [[float("nan")], [float("inf")], [float("-inf")], [True], ["0.95"]])
def test_invalid_health_trust_aggregate_fails_closed(host, values):
    assert host[2]._geo_mean(values) == 0.0


@pytest.mark.parametrize("failure", ["absent", "throws"])
def test_health_preview_denies_without_canonical_gate(monkeypatch, host, failure):
    twin = host[2]
    if failure == "absent":
        monkeypatch.setattr(twin, "_yuyay_score", None)
    else:
        def unavailable(proposal):
            raise RuntimeError("SYNTHETIC-GATE-UNAVAILABLE")
        monkeypatch.setattr(twin, "_yuyay_score", unavailable)
    # High local scores must not substitute for the unavailable canonical gate.
    monkeypatch.setattr(twin, "_subsystem", lambda platform_id, axis, signals: {
        "subsystem": axis, "status": "nominal", "nonconformity": 0.0,
        "trust": 1.0, "action": "advisory",
    })
    response = host[1].get("/api/killinchu/v1/twin/state?platform=ADSB-LOCAL")
    assert response.status_code == 200
    body = response.json()
    assert body["lambda"] == 0.97
    assert body["conformal"]["band"][1] <= 0.97
    assert body["yuyay_gate"]["authorized"] is False
    assert body["yuyay_gate"]["first_fail"]["axis"] == "UNKNOWN"
    assert "SYNTHETIC-GATE-UNAVAILABLE" not in response.text


def test_subsystem_nominal_trust_retains_ceiling(host):
    twin = host[2]
    state = twin._platform_state("SYNTHETIC-TRUST", twin._signals_from_air(AIR, read_only=True))
    assert all(0.0 <= subsystem["trust"] <= 0.97 for subsystem in state["subsystems"])
    assert state["lambda"] <= 0.97
    assert state["conformal"]["band"][1] <= 0.97


@pytest.mark.parametrize("gate", [None, [], True, {}, {"pass": "false"}, {"pass": 1}, {"pass": None},
    {"pass": True}, {"pass": True, "score_vector": [], "first_fail": {"axis": "A01"}}])
def test_malformed_canonical_gate_cannot_authorize(monkeypatch, host, gate):
    monkeypatch.setattr(host[2], "_yuyay_score", lambda proposal: gate)
    response = host[1].get("/api/killinchu/v1/twin/state?platform=ADSB-LOCAL")
    assert response.status_code == 200
    assert response.json()["yuyay_gate"]["authorized"] is False
    assert response.json()["yuyay_gate"]["first_fail"]["axis"] == "UNKNOWN"


def _canonical_gate(host):
    import killinchu_anatomy
    return killinchu_anatomy.yuyay_score({"confidence": 0.97, "track_id": "SYNTHETIC",
        "source_label": "SAMPLE", "reversible": True, "severity": "low"})


@pytest.mark.parametrize("corruption", ["short", "duplicate", "floor", "nonfinite", "row_pass",
    "string_pass", "first_fail", "no_first_fail", "aggregate", "rule"])
def test_inconsistent_full_gate_denies(monkeypatch, host, corruption):
    gate = _canonical_gate(host)
    assert gate["pass"] is True
    if corruption == "short":
        gate["score_vector"].pop()
    elif corruption == "duplicate":
        gate["score_vector"][1] = deepcopy(gate["score_vector"][0])
    elif corruption == "floor":
        gate["score_vector"][0]["floor"] = 0.0
    elif corruption == "nonfinite":
        gate["score_vector"][0]["score"] = float("nan")
    elif corruption == "row_pass":
        gate["score_vector"][0]["pass"] = False
    elif corruption == "string_pass":
        gate["score_vector"][0]["pass"] = "true"
    elif corruption == "first_fail":
        gate["first_fail"] = {"axis": "A01", "reason": "SYNTHETIC-FAILURE"}
    elif corruption == "no_first_fail":
        del gate["first_fail"]
    elif corruption == "aggregate":
        gate["pass"] = False
    else:
        gate["rule"] = ""
    monkeypatch.setattr(host[2], "_yuyay_score", lambda proposal: gate)
    response = host[1].get("/api/killinchu/v1/twin/state?platform=ADSB-LOCAL")
    assert response.status_code == 200
    assert response.json()["yuyay_gate"]["authorized"] is False
    assert response.json()["yuyay_gate"]["first_fail"]["axis"] == "UNKNOWN"


@pytest.mark.parametrize("deny", [False, True])
def test_complete_canonical_gate_preserves_result(monkeypatch, host, deny):
    import killinchu_anatomy
    proposal = {"confidence": 0.97, "track_id": "SYNTHETIC", "source_label": "SAMPLE",
                "reversible": True, "severity": "low", "stop": deny}
    gate = killinchu_anatomy.yuyay_score(proposal)
    monkeypatch.setattr(host[2], "_yuyay_score", lambda proposal: gate)
    response = host[1].get("/api/killinchu/v1/twin/state?platform=ADSB-LOCAL")
    assert response.status_code == 200
    body = response.json()["yuyay_gate"]
    assert body["authorized"] is (not deny)
    assert body["first_fail"] == gate["first_fail"]
