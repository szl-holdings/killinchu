# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "killinchu_elite_console.py"


def _literal(name: str) -> str:
    module = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    for statement in module.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        ):
            continue
        value = ast.literal_eval(statement.value)
        if isinstance(value, str):
            return value
    raise AssertionError(f"{name} must remain a static string literal")


def test_data_view_navigation_is_keyboard_operable_and_exposes_current_view() -> None:
    console = _literal("_CONSOLE_HTML")

    for contract in (
        "document.querySelectorAll('.nav-item[data-view]')",
        "item.setAttribute('role','button')",
        "item.setAttribute('tabindex','0')",
        "item.addEventListener('keydown'",
        "e.key==='Enter'||e.key===' '",
        "item.click()",
        "item.setAttribute('aria-current','page')",
        "item.removeAttribute('aria-current')",
        "window.__szlSyncNavA11y(_surf)",
        "window.__szlSyncNavA11y(view)",
        "new MutationObserver",
    ):
        assert contract in console


def test_investor_dialog_traps_focus_and_isolates_background() -> None:
    overlay = _literal("_CEO_OVERLAY_HTML")

    for contract in (
        'id="szl-ceo" role="dialog" aria-modal="true"',
        'aria-hidden="true" tabindex="-1"',
        "function focusableNodes()",
        'e.key==="Tab"',
        "e.shiftKey",
        "panel.contains(active)",
        'node.setAttribute("inert","")',
        'node.setAttribute("aria-hidden","true")',
        "setBackgroundIsolation(true)",
        "setBackgroundIsolation(false)",
        'panel.setAttribute("aria-hidden","false")',
        'panel.setAttribute("aria-hidden","true")',
        "returnFocus=document.activeElement",
        'e.key==="Escape"',
    ):
        assert contract in overlay

    restore_background = overlay.index("setBackgroundIsolation(false)")
    disarm_focus_trap = overlay.index('panel.classList.remove("on")', restore_background)
    restore_focus = overlay.index("focusTarget.focus()", disarm_focus_trap)
    assert restore_background < disarm_focus_trap < restore_focus
