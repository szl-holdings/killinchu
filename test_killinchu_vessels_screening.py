"""Tests for killinchu_vessels_screening — the vessels-domain close-out module.

Pure stdlib. Asserts fail-closed screening, exact ownership math, and
truth-label honesty. Run: python -m pytest test_killinchu_vessels_screening.py -q
"""
import killinchu_vessels_screening as vs


def test_list_load_and_hit():
    r = vs.load_screening_list("op-list", ["Shadow Fleet Co", "  bad   actor  "])
    assert r["entries"] == 2
    assert r["truth_label"] == "REPORTED"
    s = vs.screen_entity("SHADOW   FLEET CO")
    assert s["result"] == "HIT"
    assert s["hits"][0]["list"] == "op-list"
    assert s["truth_label"] == "MEASURED"


def test_clear_and_fail_closed():
    assert vs.screen_entity("Innocent Maritime Ltd")["result"] == "CLEAR"
    assert vs.screen_entity("")["result"] == "BLOCKED_PENDING"


def test_fail_closed_without_lists():
    saved = vs._LISTS.copy()
    vs._LISTS.clear()
    try:
        assert vs.screen_entity("Anything")["result"] == "BLOCKED_PENDING"
    finally:
        vs._LISTS.clear()
        vs._LISTS.update(saved)


def test_ownership_effective_pct():
    vs.declare_ownership("IMO-T", "HoldCo", 60.0)
    vs.declare_ownership("IMO-T", "DirectCo", 40.0)
    vs.declare_holder("HoldCo", "UltimateParent", 100.0)
    g = vs.ownership_graph("IMO-T")
    bos = {b["name"]: b["effective_pct"] for b in g["beneficial_owners"]}
    assert abs(bos["UltimateParent"] - 60.0) < 1e-6
    assert abs(bos["DirectCo"] - 40.0) < 1e-6
    assert g["declared_total_pct"] == 100.0


def test_combined_risk_drivers():
    vs.load_screening_list("op-list2", ["Named Target"])
    vr = vs.vessel_risk("IMO-R", name="Named Target", flag="Named Target",
                        dark_gaps=1, max_implied_speed_kn=30.0, loiter_fixes=6)
    assert vr["truth_label"] == "MODELED"
    assert vr["risk_score"] > 0.9
    assert any(d.startswith("screening_hit") for d in vr["drivers"])
    assert any(d.startswith("dark_gaps") for d in vr["drivers"])
    assert any(d.startswith("speed_anomaly") for d in vr["drivers"])


def test_receipt_chain_grows_and_links():
    before = vs.healthz()["receipt_chain"]
    vs.screen_entity("Chain Probe")
    after = vs.healthz()["receipt_chain"]
    assert after == before + 1
    recs = vs.receipts(limit=2)["receipts"]
    assert recs[-1]["prev"] != "GENESIS"
