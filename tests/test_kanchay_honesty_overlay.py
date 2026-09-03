# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
#
# Overlay contract (ATELIER / AYNI): KANCHAY tokens, uniform SIMULATED chip,
# Waman is the detector, KILLINCHU-EYE is an alias. No weights, no frames,
# no inference-lab wiring, no Brand Orchestration Layer chrome.
from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("KILLINCHU_ROOT", str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("KILLINCHU_LEDGER_MODE", "EPHEMERAL")

# This suite drives the real app through TestClient. The osint/archive suites
# install a tuple-route fastapi STUB in sys.modules for their own isolation;
# if one of them was collected first, the stub is resident and the real
# package import below would explode at collection time. Detect the stub (a
# plain module, never a package) and evict it plus everything bound to it.
import sys as _sys
import importlib as _importlib

_resident = _sys.modules.get("fastapi")
if _resident is not None and not hasattr(_resident, "__path__"):
    for _name in [m for m in list(_sys.modules) if m == "fastapi" or m.startswith("fastapi.")]:
        del _sys.modules[_name]
    _sys.modules.pop("killinchu_osint", None)
    _sys.modules.pop("serve", None)
    _importlib.import_module("fastapi")

from fastapi.testclient import TestClient

from serve import app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OVERLAY_CSS = ROOT / "static" / "szl-kanchay-overlay.css"
LANDING = ROOT / "static" / "landing.html"
ELITE = ROOT / "killinchu_elite_console.py"

HOUSE = ("#080c14", "#3af4c8", "#5b8dee", "#d7b96b")
RETIRED = ("#0a0a0a", "#c9b787", "#5fb3a3")
LOCKED_LABELS = (
    "MEASURED",
    "REPORTED",
    "ROADMAP",
    "UNKNOWN",
    "SIMULATED",
    "UNAVAILABLE",
)
FORBIDDEN_OVERLAY = (
    "from_pretrained",
    "trained weights",
    "safetensors",
    ".pth",
    "Try-Chaski",
    "tok/s",
    "szl-model-inference-lab",
    "command demonstration",
    "Brand Orchestration",
)


class KanchayHonestyOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.css = OVERLAY_CSS.read_text(encoding="utf-8")
        cls.landing = LANDING.read_text(encoding="utf-8")
        cls.elite = ELITE.read_text(encoding="utf-8")

    def test_overlay_css_is_kanchay_house_and_not_retired_pair(self):
        self.assertTrue(OVERLAY_CSS.is_file())
        for token in HOUSE:
            self.assertIn(token, self.css)
        for token in RETIRED:
            self.assertNotIn(token, self.css)
        self.assertIn("Space Grotesk", self.css)
        self.assertIn("JetBrains Mono", self.css)
        self.assertIn("szl-chip-simulated", self.css)
        self.assertIn("szl-chip-roadmap", self.css)
        self.assertIn("szl-chip-unknown", self.css)
        self.assertIn('nav[data-related-restraint]', self.css)
        self.assertIn("/pricing", self.css)
        self.assertIn("api-keys", self.css)
        self.assertIn("/sdk", self.css)

    def test_overlay_files_do_not_claim_weights_or_lab_wiring(self):
        blob = self.css + self.landing
        for needle in FORBIDDEN_OVERLAY:
            self.assertNotIn(needle, blob)
        self.assertNotIn("huggingface.co/SZLHOLDINGS/waman/resolve", blob)
        self.assertNotIn("artifact_class: WEIGHTS", blob)

    def test_landing_front_door_is_waman_alias_and_simulated(self):
        self.assertIn('data-szl-overlay="atelier-ayni"', self.landing)
        self.assertIn("Waman", self.landing)
        self.assertIn("KILLINCHU-EYE is an alias, not a second detector", self.landing)
        self.assertIn("SIMULATED", self.landing)
        self.assertIn('<span class="szl-chip szl-chip-simulated">SIMULATED</span>', self.landing)
        self.assertIn("no tensors", self.landing)
        self.assertIn("frames SKIP", self.landing)
        self.assertIn("Conjecture 1, never a theorem", self.landing)
        self.assertIn("#080c14", self.landing)
        self.assertIn("#3af4c8", self.landing)
        self.assertIn("#d7b96b", self.landing)
        self.assertNotIn("command demonstration", self.landing)
        self.assertNotIn("from_pretrained", self.landing)

    def test_elite_source_uses_uniform_simulated_and_waman_alias(self):
        self.assertIn("Waman is the detector. KILLINCHU-EYE is an alias.", self.elite)
        self.assertIn("not a second detector", self.elite)
        self.assertIn("szl-chip-simulated", self.elite)
        self.assertNotIn("command demonstration", self.elite.lower())
        self.assertNotIn("from_pretrained", self.elite)
        self.assertNotIn("szl-model-inference-lab", self.elite)
        self.assertIn("Conjecture 1", self.elite)
        self.assertIn("never a theorem", self.elite)

    def test_elite_and_home_html_carry_overlay(self):
        home = self.client.get("/")
        elite = self.client.get("/elite")
        self.assertEqual(home.status_code, 200)
        self.assertEqual(elite.status_code, 200)
        chip = '<span class="szl-chip szl-chip-simulated">SIMULATED</span>'
        for response, name in ((home, "/"), (elite, "/elite")):
            body = response.text
            self.assertIn("text/html", response.headers.get("content-type", ""), name)
            self.assertIn("szl-kanchay-overlay.css", body, name)
            self.assertIn('data-szl-overlay="atelier-ayni"', body, name)
            self.assertIn(chip, body, name)
            self.assertGreaterEqual(body.count(chip), 1, name)
            self.assertIn("Waman", body, name)
            self.assertIn("KILLINCHU-EYE", body, name)
            self.assertIn("not a second detector", body, name)
            self.assertIn("no tensors", body, name)
            self.assertIn("frames SKIP", body, name)
            self.assertIn("SIMULATED", body, name)
            self.assertIn("Conjecture 1", body, name)
            self.assertNotIn("from_pretrained", body, name)
            self.assertNotIn("szl-model-inference-lab", body, name)
            self.assertNotIn("Try-Chaski", body, name)
            self.assertNotIn("command demonstration", body.lower(), name)
            self.assertNotIn("Brand Orchestration", body, name)
            self.assertLessEqual(body.lower().count("huggingface.co/szlholdings/waman/resolve"), 0, name)

    def test_simulated_chip_is_not_dropped_and_waman_has_no_tensors(self):
        chip = '<span class="szl-chip szl-chip-simulated">SIMULATED</span>'
        self.assertIn(chip, self.landing)
        self.assertIn("no tensors", self.landing)
        self.assertIn("frames SKIP", self.landing)
        self.assertIn("KILLINCHU-EYE is an alias, not a second detector", self.landing)
        self.assertIn("visibility: visible !important", self.css)
        self.assertIn("#szl-kanchay-honesty .szl-chip-simulated", self.css)
        # Overlay must not hide the locked chip or stamp fake operational.
        self.assertNotIn(
            "#szl-kanchay-honesty .szl-chip-simulated { display: none",
            " ".join(self.css.split()),
        )
        ribbon = self.landing[
            self.landing.find('id="szl-kanchay-honesty"') : self.landing.find(
                'id="szl-kanchay-honesty"'
            )
            + 900
        ]
        self.assertIn(chip, ribbon)
        self.assertIn("Effector stays", ribbon)
        self.assertNotIn("fully real", ribbon.lower())
        self.assertNotIn("operational", ribbon.lower())
        self.assertNotIn("from_pretrained", ribbon)

    def test_locked_honesty_labels_are_the_only_chips_on_overlay(self):
        for label in ("ROADMAP", "UNKNOWN", "SIMULATED"):
            self.assertIn(label, self.landing)
        self.assertIn(".szl-chip-simulated", self.css)
        self.assertIn(".szl-chip-roadmap", self.css)
        self.assertIn(".szl-chip-unknown", self.css)
        # Overlay chip classes must not invent a seventh vocabulary.
        for banned in ("PROVEN", "LIVE", "SAMPLE", "EXPERIMENTAL", "MODELED"):
            self.assertNotIn(f"szl-chip-{banned.lower()}", self.css)

    def test_overlay_css_is_served(self):
        response = self.client.get("/static/szl-kanchay-overlay.css")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/css"))
        self.assertIn(b"#080c14", response.content)
        self.assertIn(b"szl-chip-simulated", response.content)


if __name__ == "__main__":
    unittest.main()
