"""Focused contracts for the responsive control dock and COP route successor."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
WIDGET_PATH = ROOT / "static-vendor" / "a11oy-operator-widget.js"
ALLOWLIST_PATH = ROOT / ".github" / "shared-file-drift-allow.txt"
EXPECTED_WIDGET_BYTES = 39_419
EXPECTED_WIDGET_SHA256 = "0c4ad9e285bfcf8783b84c0dec13360f2159aba5f56904bf9454998d2371ec3b"


class ControlDockCopRouteContractTests(unittest.TestCase):
    def test_cop_link_is_accessible_relative_and_safe_area_aware(self) -> None:
        source = (ROOT / "serve.py").read_text(encoding="utf-8")
        for console_url in (
            "https://killinchu.example/elite",
            "https://killinchu.example/killinchu/elite",
        ):
            self.assertEqual(
                urljoin(console_url, "/elite/cop"),
                "https://killinchu.example/elite/cop",
            )
        for token in (
            'href="/elite/cop"',
            'data-szl-dock-control="cop"',
            'aria-label="Open the operational Common Operating Picture"',
            'bottom:calc(env(safe-area-inset-bottom,0px) + 16px)',
            'min-height:44px',
            '_COP_MARK = b\'data-szl-dock-control="cop"\'',
        ):
            self.assertIn(token, source)

    def test_open_notifications_use_the_visible_live_log(self) -> None:
        source = WIDGET_PATH.read_text(encoding="utf-8")
        self.assertIn(
            '.aow-root[data-open="true"] .aow-toasts{display:none;}',
            source,
        )
        self.assertIn("pushMsg('op'", source)
        self.assertIn(
            "max-height:calc(100vh - 120px - env(safe-area-inset-bottom,0px))",
            source,
        )
        self.assertIn(
            "max-height:calc(100vh - 168px - env(safe-area-inset-bottom,0px))",
            source,
        )

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
            "new window.MutationObserver(syncDockPosition)",
            "{ childList: true, subtree: true }",
            "document.querySelector('[data-szl-dock-control=\"investor\"]')",
            'data-dock-has-investor="true"',
            'bottom:calc(env(safe-area-inset-bottom,0px) + 200px)',
            'max-height:calc(100vh - 228px - env(safe-area-inset-bottom,0px))',
            '.aow-root[data-dock-has-investor="true"] .aow-toasts{bottom:calc(env(safe-area-inset-bottom,0px) + 200px);}',
            '@media (max-height:480px) and (min-width:600px)',
            'top:calc(env(safe-area-inset-top,0px) + 8px)',
            'right:calc(env(safe-area-inset-right,0px) + 176px)',
            'max-width:calc(100vw - 192px)',
            '@media (max-height:480px) and (max-width:599px)',
            'bottom:calc(env(safe-area-inset-bottom,0px) + 72px)',
            'left:calc(env(safe-area-inset-left,0px) + 8px)',
            'html[data-aow-panel-open="true"] [data-szl-dock-control="cop"]',
            'html[data-aow-panel-open="true"] [data-szl-dock-control="investor"]',
            "document.documentElement.removeAttribute('data-aow-panel-open')",
        ):
            self.assertIn(token, source)

    def test_operator_widget_immutable_url_is_content_addressed(self) -> None:
        source = (ROOT / "serve.py").read_text(encoding="utf-8")
        versioned_url = (
            "/vendor/a11oy-operator-widget.js?v=" + EXPECTED_WIDGET_SHA256
        )
        self.assertIn(f'src="{versioned_url}"', source)
        self.assertIn(
            'headers={"Cache-Control": "public, max-age=31536000, immutable"}',
            source,
        )

    def test_widget_remains_under_shared_drift_enforcement(self) -> None:
        lines = ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines()
        widget_lines = [
            line
            for line in lines
            if line.split("#", 1)[0].strip()
            == "static-vendor/a11oy-operator-widget.js"
        ]
        self.assertEqual(widget_lines, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
