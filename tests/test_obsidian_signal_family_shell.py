#!/usr/bin/env python3
"""Offline contract for Killinchu's SZL Obsidian Signal field shell."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "szl-obsidian-signal.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "truth-cop.js").read_text(encoding="utf-8")


class KillinchuObsidianSignalContract(unittest.TestCase):
    def test_family_shell_and_unique_field_identity_are_both_present(self) -> None:
        for token in (
            "SZL Obsidian Signal",
            "--szl-field-bg:#030708",
            "--szl-field-accent:#68e8d8",
            "--szl-field-signal:#d9955b",
            ".szl-family-rail",
            ".szl-family-track",
            "field-vector",
        ):
            self.assertIn(token, CSS + JS)
        self.assertNotIn("#ff74d4", CSS)
        self.assertNotIn("magenta", CSS.lower())

    def test_family_navigation_points_to_canonical_surfaces(self) -> None:
        for label, href in (
            ("A11oy", "https://a-11-oy.com/"),
            ("Killinchu", "/"),
            ("Hatun", "https://a-11-oy.com/wires"),
            ("Living Anatomy", "https://a-11-oy.com/living-anatomy"),
            ("Understand", "/elite"),
            ("Build", "https://github.com/szl-holdings/killinchu"),
            ("Verify", "/api/killinchu/v1/receipt/ledger/readiness"),
        ):
            self.assertIn(f'familyLink("{label}", "{href}"', JS)
        self.assertNotIn("szlholdings-hatun-mcp.hf.space", JS)

    def test_truth_contract_stays_fail_closed(self) -> None:
        self.assertIn('var ENDPOINT = "/api/killinchu/v1/threats/active"', JS)
        self.assertIn('["LIVE", "CACHED", "TRAINING", "UNAVAILABLE"]', JS)
        self.assertIn("no tracks fabricated", JS)
        self.assertIn("not confirmed threats", JS)
        self.assertNotIn("SIMULATED", JS)
        self.assertIn('cache: "no-store"', JS)
        self.assertIn("AbortController", JS)
        self.assertNotIn("setInterval", JS)

    def test_all_screen_and_accessibility_contract_is_explicit(self) -> None:
        for token in (
            "safe-area-inset",
            "min-height:44px",
            "touch-action:pan-x",
            "-webkit-overflow-scrolling:touch",
            "prefers-reduced-motion",
            "prefers-contrast",
            "forced-colors",
            "focus-visible",
            "@media(max-width:360px)",
        ):
            self.assertIn(token, CSS)
        self.assertIn('brand.style.minWidth = "44px"', JS)
        self.assertIn('brand.style.minHeight = "44px"', JS)

    def test_assets_are_local_small_and_structurally_balanced(self) -> None:
        self.assertIn('link.href = "/static/szl-obsidian-signal.css"', JS)
        self.assertNotRegex(CSS, r"url\(\s*['\"]?https?://")
        self.assertLess(len(CSS.encode("utf-8")), 40_000)
        self.assertLess(len(JS.encode("utf-8")), 30_000)
        stripped = re.sub(r"/\*.*?\*/", "", CSS, flags=re.DOTALL)
        self.assertEqual(stripped.count("{"), stripped.count("}"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
