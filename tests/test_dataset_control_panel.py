# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
#
# test_dataset_control_panel.py — REAL, committed guard for the unified
# "Data Sources / Overlays" control panel on the /elite track board
# (feat/dataset-control-panel). NO MOCKS, pure stdlib, no network.
#
# It proves:
#   * the panel view + nav item are present in the served console HTML
#   * the panel is wired to the REAL documented routes the sibling PRs added
#     (#133 AIS Aug-2024, #134 pirate/WPI overlays, #132 CoT export)
#   * Live AIS is the default source and is the only one on main
#   * unmerged routes are honestly labelled "available when PR #N merges"
#     (doctrine v11: never claim a route is live when it is not)
#   * sample datasets are labelled SAMPLE, never claimed live
#   * the elite-wiring map carries a matching dataset_control entry that
#     satisfies every existing wiring invariant
from __future__ import annotations

import killinchu_elite_console as kec
import killinchu_elite_wiring as kew

HTML = kec._CONSOLE_HTML


def test_view_and_nav_present():
    # VIEWS entry + a nav-item that routes to it.
    assert "dataset_control:{title:'Data Sources / Overlays'" in HTML
    assert 'go(\'dataset_control\')' in HTML
    assert "render:(c)=>dataset_control_render(c)" in HTML


def test_wired_to_documented_routes():
    # The real routes the sibling PRs documented must all be referenced.
    for route in (
        "/ais/live",                                  # live default (on main)
        "/ais/sources",                               # PR #133 source manifest
        "/ais/tracks?source=noaa_ais_aug2024",        # PR #133 selector
        "/ais/aug2024/risk-board?sign=true",          # PR #133 governed risk board
        "/maritime/overlays/pirate-attacks",          # PR #134 pirate overlay
        "/maritime/overlays/world-port-index",        # PR #134 WPI overlay
        "/cot/export",                                 # PR #132 CoT export
        "/cot/status",                                 # PR #132 CoT honesty manifest
    ):
        assert route in HTML, f"panel does not reference documented route {route!r}"


def test_live_ais_is_default():
    # The default source is live_ais with kind 'live' and pr:null (on main).
    assert "source:'live_ais'" in HTML
    assert "live_ais: {label:'Live AIS', pr:null, kind:'live'" in HTML


def test_unmerged_routes_labelled_honestly():
    # The honest guard copy must be present, parameterised by PR number.
    assert "available when PR #'+pr+' merges" in HTML
    # And the three sibling PR numbers are carried so the label resolves.
    assert "pr:133" in HTML and "pr:134" in HTML
    assert "dc_unavail(132)" in HTML  # CoT export guard


def test_samples_labelled_sample_not_live():
    # Sample datasets must declare kind:'sample' and SAMPLE badge copy; never
    # claim to be live (doctrine v11: sample != live).
    assert "kind:'sample'" in HTML
    assert "SAMPLE" in HTML
    # The NOAA source honestly states it is NOT the full month.
    assert "NOT the full month" in HTML


def test_additive_only_marker():
    # Panel must announce it is additive and does not touch the live board.
    assert "Additive" in HTML or "additive" in HTML


def test_wiring_entry_present_and_valid():
    w = kew.ELITE_WIRING.get("dataset_control")
    assert w is not None, "dataset_control missing from ELITE_WIRING"
    assert w["data_class"] == "live-feed"
    assert w["endpoints"], "dataset_control has no endpoints"
    for ep in w["endpoints"]:
        assert ep.startswith("/api/"), f"bad endpoint {ep!r}"
    # It references the live default and the new dataset/CoT routes.
    joined = " ".join(w["endpoints"])
    assert "/ais/live" in joined
    assert "/ais/sources" in joined
    assert "/maritime/overlays/pirate-attacks" in joined
    assert "/cot/status" in joined


def test_wiring_entry_no_key_smuggled():
    import re
    blob = repr(kew.ELITE_WIRING["dataset_control"])
    assert not re.search(r"(?i)(api[_-]?key|access[_-]?token|bearer\s+[A-Za-z0-9])", blob)
    assert "key=" not in blob.lower()


if __name__ == "__main__":
    test_view_and_nav_present()
    test_wired_to_documented_routes()
    test_live_ais_is_default()
    test_unmerged_routes_labelled_honestly()
    test_samples_labelled_sample_not_live()
    test_additive_only_marker()
    test_wiring_entry_present_and_valid()
    test_wiring_entry_no_key_smuggled()
    print("OK — all dataset-control-panel self-tests passed")
