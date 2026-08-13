from __future__ import annotations

import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "killinchu_elite_console.py"
CANONICAL = "https://szlholdings-killinchu.hf.space/elite"
SOCIAL_IMAGE = "https://szlholdings-killinchu.hf.space/og-card.png"


def _console_html() -> str:
    module = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    for statement in module.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "_CONSOLE_HTML" for target in statement.targets):
            continue
        value = ast.literal_eval(statement.value)
        if isinstance(value, str):
            return value
    raise AssertionError("_CONSOLE_HTML must remain a static string literal")


def test_console_metadata_uses_the_reachable_canonical_origin() -> None:
    html = _console_html()

    assert f'<link rel="canonical" href="{CANONICAL}" />' in html
    assert f'<meta property="og:url" content="{CANONICAL}" />' in html
    assert f'<meta property="og:image" content="{SOCIAL_IMAGE}" />' in html
    assert f'<meta property="og:image:secure_url" content="{SOCIAL_IMAGE}" />' in html
    assert f'<meta name="twitter:image" content="{SOCIAL_IMAGE}" />' in html
    assert "killinchu.a-11-oy.com" not in html
    assert "killinchu.a11oy.net" not in html


def test_shared_three_core_precedes_every_dependent_console_bundle() -> None:
    html = _console_html()
    core = '<script src="/vendor/three.min.js"></script>'
    timer_shim = "THREE.Timer=Timer;"
    dependents = (
        '<script defer src="/vendor/3d-force-graph.min.js"></script>',
        '<script defer src="/vendor/globe.gl.min.js"></script>',
        '<script defer src="/vendor/anvaka/ngraph.three.min.js"></script>',
    )

    assert html.count(core) == 1
    assert html.count(timer_shim) == 1
    core_position = html.index(core)
    shim_position = html.index(timer_shim)
    globe_position = html.index(dependents[1])
    assert core_position < shim_position < globe_position
    assert "DOMContentLoaded" not in html[core_position:globe_position]
    for dependent in dependents:
        assert core_position < html.index(dependent)
