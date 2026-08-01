"""Focused contracts for the responsive control dock and COP route successor."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
WIDGET_PATH = ROOT / "static-vendor" / "a11oy-operator-widget.js"
ALLOWLIST_PATH = ROOT / ".github" / "shared-file-drift-allow.txt"
EXPECTED_WIDGET_BYTES = 40_737
EXPECTED_WIDGET_SHA256 = "50fbf93caba2439d06a5cb340a66166cdf401f91f2ec36104e22364462a09681"


def _extract_braced_function(source: str, name: str) -> str:
    marker = f"  function {name}("
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated JavaScript function: {name}")


def _extract_investor_click_listener(source: str) -> str:
    marker = "  document.addEventListener('click', function (e) {"
    start = source.index(marker)
    terminator = "  }, true);"
    end = source.index(terminator, start) + len(terminator)
    return source[start:end]


def _extract_ceo_overlay_script(source: str) -> str:
    overlay = source.index('_CEO_OVERLAY_HTML = r"""')
    start = source.index("<script>", overlay) + len("<script>")
    end = source.index("</script>", start)
    return source[start:end]


def _run_node(script: str) -> None:
    node = os.environ.get("SZL_NODE_BINARY") or shutil.which("node")
    if not node:
        if os.environ.get("CI", "").lower() == "true":
            raise AssertionError(
                "Node.js must be provisioned for the CI behavioral focus contract"
            )
        raise unittest.SkipTest(
            "Node.js unavailable; set SZL_NODE_BINARY to run the focus contract"
        )
    result = subprocess.run(
        [node, "-"],
        input=script,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode:
        raise AssertionError(
            f"JavaScript behavioral contract failed ({result.returncode}):\n"
            f"{result.stdout}{result.stderr}"
        )


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
            "data-szl-initial-focus",
            'initialFocus.focus==="function"',
            'fab.focus==="function"',
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
            "target.closest('[data-szl-dock-control=\"investor\"]')",
            "close(false)",
            "focusControlledDialog(investorControl)",
            "control.getAttribute('aria-expanded') !== 'true'",
            "dialog.getAttribute('aria-modal') !== 'true'",
        ):
            self.assertIn(token, source)

    def test_investor_handoff_focuses_modal_and_returns_to_launcher(self) -> None:
        widget_source = WIDGET_PATH.read_text(encoding="utf-8")
        focus_function = _extract_braced_function(
            widget_source, "focusControlledDialog"
        )
        click_listener = _extract_investor_click_listener(widget_source)
        console_source = (ROOT / "killinchu_elite_console.py").read_text(
            encoding="utf-8"
        )
        overlay_script = _extract_ceo_overlay_script(console_source)
        script = r"""
const timers = [];
const documentListeners = {};
let document;

class FakeClassList {
  constructor() { this.values = new Set(); }
  add(value) { this.values.add(value); }
  remove(value) { this.values.delete(value); }
  contains(value) { return this.values.has(value); }
}

class FakeElement {
  constructor(id) {
    this.id = id;
    this.attrs = {};
    this.listeners = {};
    this.classList = new FakeClassList();
    this.style = {};
  }
  addEventListener(type, listener) {
    (this.listeners[type] ||= []).push(listener);
  }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null; }
  hasAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name); }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  focus() { document.activeElement = this; }
}

const fab = new FakeElement("szl-ceo-fab");
fab.setAttribute("aria-controls", "szl-ceo");
fab.setAttribute("aria-expanded", "false");
fab.closest = function(selector) {
  return selector === '[data-szl-dock-control="investor"]' ? this : null;
};
const panel = new FakeElement("szl-ceo");
panel.setAttribute("aria-modal", "true");
const initialFocus = new FakeElement("szl-ceo-close");
initialFocus.closest = function(selector) {
  return selector === "[data-szl-ceo-close]" ? this : null;
};
panel.querySelector = function(selector) {
  if (selector === "details") return null;
  if (selector.includes("[data-szl-initial-focus]")) return initialFocus;
  return null;
};

document = {
  activeElement: fab,
  documentElement: { style: {} },
  head: { appendChild() {} },
  getElementById(id) {
    if (id === "szl-ceo-fab") return fab;
    if (id === "szl-ceo") return panel;
    return null;
  },
  createElement(id) { return new FakeElement(id); },
  addEventListener(type, listener, capture) {
    (documentListeners[type] ||= []).push({ listener, capture: capture === true });
  },
};
const windowListeners = {};
const window = {
  SZLLabels: { badgeHTML() { return ""; }, ensureStyle() {} },
  addEventListener(type, listener) { (windowListeners[type] ||= []).push(listener); },
};
const location = { hash: "" };
function setTimeout(callback) { timers.push(callback); }
function fetch() { throw new Error("unexpected network call"); }
""" + overlay_script + r"""
let isOpen = true;
let operatorClosedWith = "not-called";
function close(restoreFocus) { operatorClosedWith = restoreFocus; isOpen = false; }
""" + focus_function + "\n" + click_listener + r"""
function dispatchInvestorClick() {
  const event = { target: fab, preventDefault() { this.defaultPrevented = true; } };
  (documentListeners.click || []).filter(item => item.capture).forEach(item => item.listener(event));
  (fab.listeners.click || []).forEach(listener => listener(event));
  (documentListeners.click || []).filter(item => !item.capture).forEach(item => item.listener(event));
  while (timers.length) timers.shift()();
}

fab.focus();
dispatchInvestorClick();
if (operatorClosedWith !== false) throw new Error("operator handoff did not use close(false)");
if (!panel.classList.contains("on")) throw new Error("investor modal did not open");
if (fab.getAttribute("aria-expanded") !== "true") throw new Error("launcher did not expose open state");
if (document.activeElement !== initialFocus) throw new Error("focus did not enter investor modal");

const closeEvent = { target: initialFocus, preventDefault() { this.defaultPrevented = true; } };
(panel.listeners.click || []).forEach(listener => listener(closeEvent));
if (panel.classList.contains("on")) throw new Error("investor modal did not close");
if (document.activeElement !== fab) throw new Error("focus did not return to investor launcher");

dispatchInvestorClick();
if (document.activeElement !== initialFocus) throw new Error("focus did not re-enter investor modal");
const escapeEvent = { key: "Escape" };
(documentListeners.keydown || []).forEach(item => item.listener(escapeEvent));
if (panel.classList.contains("on")) throw new Error("Escape did not close investor modal");
if (document.activeElement !== fab) throw new Error("Escape did not restore launcher focus");
"""
        _run_node(script)

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
