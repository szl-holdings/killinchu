# SPDX-License-Identifier: Apache-2.0
"""Offline Public Experience v3 contract for the Killinchu root shell."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "static" / "truth-cop.js"
LANDING = ROOT / "static" / "landing.html"
APP_SHELL = ROOT / "static" / "index.html"


def test_public_root_controller_installs_the_v3_marker() -> None:
    script = CONTROLLER.read_text(encoding="utf-8")

    assert 'setAttribute("data-szl-public-experience-v3", "true")' in script
    assert "installPublicExperienceV3();" in script
    assert "installPublicExperienceV3: installPublicExperienceV3" in script


def test_exact_live_failing_controls_are_zoom_and_touch_safe() -> None:
    script = CONTROLLER.read_text(encoding="utf-8")

    for selector in (
        'document.querySelector(".topbar")',
        'document.querySelector(".topbar__in")',
        'document.querySelector(".topbar .brand")',
        'document.querySelector(".topbar__meta")',
    ):
        assert selector in script

    for contract in (
        'brand.style.minWidth = "44px"',
        'brand.style.minHeight = "44px"',
        'brand.style.touchAction = "manipulation"',
        'shell.style.flexWrap = "wrap"',
        'meta.style.whiteSpace = "normal"',
        'meta.style.overflowWrap = "anywhere"',
        'html.style.overflowX = "clip"',
        'document.body.style.overflowX = "clip"',
    ):
        assert contract in script


def test_existing_public_shells_load_the_same_bounded_controller() -> None:
    landing = LANDING.read_text(encoding="utf-8")
    app_shell = APP_SHELL.read_text(encoding="utf-8")

    assert 'src="/static/truth-cop.js"' in landing
    assert 'src="/static/truth-cop.js"' in app_shell


def test_truth_vocabulary_and_endpoint_remain_unchanged() -> None:
    script = CONTROLLER.read_text(encoding="utf-8")

    assert 'var ENDPOINT = "/api/killinchu/v1/threats/active"' in script
    assert '["LIVE", "CACHED", "TRAINING", "UNAVAILABLE"]' in script
    assert "no tracks fabricated" in script
    assert "not confirmed threats" in script
    assert "SIMULATED" not in script
