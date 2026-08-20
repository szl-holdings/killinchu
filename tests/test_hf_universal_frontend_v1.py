from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_hf_universal_frontend_v1.py"
SPEC = importlib.util.spec_from_file_location("hf_universal_frontend_v1", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _bind_root(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(MODULE, "ROOT", root)
    monkeypatch.setattr(MODULE, "README", root / "README.md")
    monkeypatch.setattr(MODULE, "MANIFEST", root / "docs" / "hf-universal-frontend-v1.json")


def _readme(sdk: str, app_file: str, short: str = "Old description") -> str:
    return (
        "---\n"
        "title: Example\n"
        f"sdk: {sdk}\n"
        f"app_file: {app_file}\n"
        f"short_description: {short}\n"
        "---\n"
        "# Example\n"
    )


def test_front_matter_parser_rejects_absent_metadata() -> None:
    with pytest.raises(MODULE.AdapterError):
        MODULE.parse_front_matter("# Missing front matter\n")


def test_static_adapter_injects_viewport_and_css(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _bind_root(monkeypatch, tmp_path)
    (tmp_path / "README.md").write_text(_readme("static", "index.html"), encoding="utf-8")
    (tmp_path / "index.html").write_text("<html><head><title>x</title></head><body><a class='btn'>Run</a></body></html>", encoding="utf-8")

    result = MODULE.apply()
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert result["framework"] == "static"
    assert 'name="viewport"' in html
    assert MODULE.HTML_MARKER in html
    assert "short_description: Governed autonomous-systems command surface" in readme
    assert "fullWidth: true" in readme
    assert "header: mini" in readme
    assert MODULE.validate()["framework"] == "static"


def test_docker_static_adapter_uses_canonical_static_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _bind_root(monkeypatch, tmp_path)
    (tmp_path / "README.md").write_text(
        "---\ntitle: Example\nsdk: docker\nshort_description: Old description\n---\n# Example\n",
        encoding="utf-8",
    )
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    nested = static / "jackin"
    nested.mkdir()
    (nested / "index.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")

    result = MODULE.apply()

    assert result["sdk"] == "docker"
    assert result["framework"] == "static"
    assert result["app_file"] == "static/index.html"
    assert result["css_file"] == "static/szl-universal-frontend.css"
    assert MODULE.HTML_MARKER in (static / "index.html").read_text(encoding="utf-8")
    assert MODULE.HTML_MARKER not in (nested / "index.html").read_text(encoding="utf-8")


def test_gradio_adapter_binds_new_css_keyword(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _bind_root(monkeypatch, tmp_path)
    (tmp_path / "README.md").write_text(_readme("gradio", "app.py"), encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "import gradio as gr\n\nwith gr.Blocks(title='Example') as demo:\n    gr.Markdown('# Example')\n",
        encoding="utf-8",
    )

    result = MODULE.apply()
    source = (tmp_path / "app.py").read_text(encoding="utf-8")
    compile(source, "app.py", "exec")
    assert result["framework"] == "gradio"
    assert MODULE.PYTHON_MARKER in source
    assert "gr.Blocks(css=_SZL_UNIVERSAL_CSS, title='Example')" in source
    assert MODULE.validate()["framework"] == "gradio"


def test_gradio_adapter_preserves_existing_css(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _bind_root(monkeypatch, tmp_path)
    (tmp_path / "README.md").write_text(_readme("gradio", "app.py"), encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "import gradio as gr\nCUSTOM = 'body{}'\nwith gr.Blocks(css=CUSTOM) as demo:\n    pass\n",
        encoding="utf-8",
    )

    MODULE.apply()
    source = (tmp_path / "app.py").read_text(encoding="utf-8")
    compile(source, "app.py", "exec")
    assert "css=(_SZL_UNIVERSAL_CSS + '\\n' + str(CUSTOM))" in source


def test_streamlit_adapter_runs_after_page_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _bind_root(monkeypatch, tmp_path)
    (tmp_path / "README.md").write_text(_readme("streamlit", "app.py"), encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "import streamlit as st\n\nst.set_page_config(page_title='Example')\nst.title('Example')\n",
        encoding="utf-8",
    )

    result = MODULE.apply()
    source = (tmp_path / "app.py").read_text(encoding="utf-8")
    compile(source, "app.py", "exec")
    assert result["framework"] == "streamlit"
    assert source.index("st.set_page_config") < source.index(MODULE.PYTHON_MARKER)
    assert "unsafe_allow_html=True" in source


def test_react_adapter_injects_one_import(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _bind_root(monkeypatch, tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text(_readme("docker", "src/main.tsx"), encoding="utf-8")
    (tmp_path / "package.json").write_text('{"scripts":{"build":"vite build"}}', encoding="utf-8")
    (tmp_path / "src" / "main.tsx").write_text(
        "import React from 'react';\nimport './index.css';\nconsole.log(React);\n",
        encoding="utf-8",
    )

    result = MODULE.apply()
    source = (tmp_path / "src" / "main.tsx").read_text(encoding="utf-8")
    assert result["framework"] == "react"
    assert source.count(MODULE.REACT_MARKER) == 1
    MODULE.apply()
    source = (tmp_path / "src" / "main.tsx").read_text(encoding="utf-8")
    assert source.count(MODULE.REACT_MARKER) == 1


def test_validate_rejects_css_hash_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _bind_root(monkeypatch, tmp_path)
    (tmp_path / "README.md").write_text(_readme("static", "index.html"), encoding="utf-8")
    (tmp_path / "index.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    result = MODULE.apply()
    css = tmp_path / result["css_file"]
    css.write_text(css.read_text(encoding="utf-8") + "\n/* drift */\n", encoding="utf-8")
    with pytest.raises(MODULE.AdapterError, match="hash mismatch"):
        MODULE.validate()


def test_manifest_is_machine_readable_and_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _bind_root(monkeypatch, tmp_path)
    (tmp_path / "README.md").write_text(_readme("static", "index.html", "x" * 80), encoding="utf-8")
    (tmp_path / "index.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    result = MODULE.apply()
    payload = json.loads((tmp_path / "docs" / "hf-universal-frontend-v1.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "szl.hf-universal-frontend/v1"
    assert payload["remote_mutation"] is False
    assert len(payload["short_description"]) <= 60
    assert result["contract"]["minimum_touch_target_px"] == 44
