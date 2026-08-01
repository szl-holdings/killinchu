"""Focused contracts for the responsive control dock and COP route successor."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WIDGET_PATH = ROOT / "static-vendor" / "a11oy-operator-widget.js"
ALLOWLIST_PATH = ROOT / ".github" / "shared-file-drift-allow.txt"
EXPECTED_WIDGET_BYTES = 36_331
EXPECTED_WIDGET_SHA256 = "4fc45e43803b677af74863ecfb303202110fb99104eb0f5f614ad12a6647caf4"
REMOVAL_CONDITION = (
    "removed immediately after paired A11oy successor lands and "
    "main-to-main equality is proven"
)


class ControlDockCopRouteContractTests(unittest.TestCase):
    def test_cop_link_is_accessible_relative_and_safe_area_aware(self) -> None:
        source = (ROOT / "serve.py").read_text(encoding="utf-8")
        for token in (
            'href="elite/cop"',
            'data-szl-dock-control="cop"',
            'aria-label="Open the operational Common Operating Picture"',
            'bottom:calc(env(safe-area-inset-bottom,0px) + 16px)',
            'min-height:44px',
            '_COP_MARK = b\'data-szl-dock-control="cop"\'',
        ):
            self.assertIn(token, source)

    def test_investor_control_occupies_the_third_accessible_dock_row(self) -> None:
        source = (ROOT / "killinchu_elite_console.py").read_text(encoding="utf-8")
        for token in (
            'bottom:calc(env(safe-area-inset-bottom,0px) + 140px)',
            '#szl-ceo-fab:focus-visible',
            'data-szl-dock-control="investor"',
            'aria-label="Open the Killinchu investor view"',
        ):
            self.assertIn(token, source)

    def test_operator_widget_is_the_coordinated_payload(self) -> None:
        payload = WIDGET_PATH.read_bytes()
        self.assertEqual(len(payload), EXPECTED_WIDGET_BYTES)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), EXPECTED_WIDGET_SHA256)
        source = payload.decode("utf-8")
        for token in (
            "data-szl-dock-control': 'operator'",
            "data-dock-has-cop",
            "document.querySelector('[data-szl-dock-control=\"cop\"]')",
            "window.addEventListener('load', syncDockPosition, { once: true })",
        ):
            self.assertIn(token, source)

    def test_widget_allowlist_is_narrow_and_self_expiring(self) -> None:
        lines = ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines()
        widget_lines = [
            line
            for line in lines
            if line.split("#", 1)[0].strip()
            == "static-vendor/a11oy-operator-widget.js"
        ]
        self.assertEqual(len(widget_lines), 1)
        self.assertIn(REMOVAL_CONDITION, widget_lines[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
