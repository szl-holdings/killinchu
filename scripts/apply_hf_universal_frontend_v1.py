#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MANIFEST = ROOT / "docs" / "hf-universal-frontend-v1.json"
SHORT_DESCRIPTION = "Governed autonomous-systems command surface"
PYTHON_MARKER = "# SZL_HF_UNIVERSAL_FRONTEND_V1"
HTML_MARKER = 'data-szl-universal-frontend="v1"'
REACT_MARKER = "// SZL_HF_UNIVERSAL_FRONTEND_V1"

UNIVERSAL_CSS = r"""/* SZL Hugging Face Universal Frontend v1
 * Mobile-first, framework-neutral accessibility and overflow contract.
 */
:root {
  --szl-touch-target: 44px;
  --szl-gutter: clamp(14px, 3vw, 28px);
  --szl-content-max: 1440px;
}

*, *::before, *::after { box-sizing: border-box; }
html { max-width: 100%; overflow-x: clip; text-size-adjust: 100%; }
body, #root, .gradio-container, .stApp, [data-testid="stAppViewContainer"] {
  max-width: 100%;
  min-width: 0;
}
body { margin: 0; overflow-x: clip; }

main, section, article, header, footer, nav, form,
.row, .column, .grid, .container, .wrap, .panel, .card,
.gr-row, .gr-column, .gr-group, .gr-box, .gradio-container > div {
  min-width: 0;
}

img, video, svg, iframe { max-width: 100%; height: auto; }
canvas { max-width: 100%; }
pre, code, samp, kbd, .mono,
[class*="hash"], [class*="digest"], [class*="revision"],
[class*="receipt"], [data-evidence-id] {
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-word;
}
pre { overflow-x: auto; white-space: pre-wrap; }
table { max-width: 100%; }
.table-wrap, [class*="table-container"], [data-testid="stDataFrame"] {
  max-width: 100%;
  overflow-x: auto;
  overscroll-behavior-inline: contain;
}

button,
[role="button"],
input[type="button"],
input[type="submit"],
input[type="reset"],
a.btn,
a.button,
a[class*="button"],
.gr-button,
.gr-button-primary,
[data-testid*="submit"] {
  min-height: var(--szl-touch-target);
  min-width: var(--szl-touch-target);
  max-width: 100%;
}

input, select, textarea { max-width: 100%; min-height: var(--szl-touch-target); }
:focus-visible { outline: 3px solid currentColor; outline-offset: 3px; }

.gradio-container,
.stApp > header + div,
[data-testid="stAppViewContainer"] > .main {
  width: min(100%, var(--szl-content-max));
  margin-inline: auto;
}
.gradio-container { padding-inline: var(--szl-gutter) !important; }
[data-testid="stAppViewContainer"] .block-container {
  max-width: var(--szl-content-max);
  padding-inline: var(--szl-gutter);
}

@media (max-width: 768px) {
  .gr-row, .row, [class*="columns"], [class*="grid"] {
    min-width: 0;
  }
  .gradio-container,
  [data-testid="stAppViewContainer"] .block-container {
    padding-inline: var(--szl-gutter) !important;
  }
}

@media (max-width: 560px) {
  :root { --szl-gutter: 14px; }
  .cta-row, .actions, .button-row, [class*="action-row"] {
    display: grid !important;
    grid-template-columns: minmax(0, 1fr) !important;
    width: 100%;
  }
  .cta-row > *, .actions > *, .button-row > *, [class*="action-row"] > * {
    width: 100%;
    max-width: 100%;
  }
  dialog, [role="dialog"], .modal, [class*="modal"] {
    max-width: calc(100vw - 28px);
    max-height: calc(100dvh - 28px);
    overflow: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
"""


class AdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class FrontMatter:
    start: int
    end: int
    lines: list[str]
    values: dict[str, str]


@dataclass(frozen=True)
class Detection:
    sdk: str
    framework: str
    app_file: Path
    css_file: Path
    entry_file: Path | None = None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_scalar(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
    return text.strip()


def parse_front_matter(text: str) -> FrontMatter:
    if not text.startswith("---\n"):
        raise AdapterError("README.md must begin with Hugging Face YAML front matter")
    marker = "\n---\n"
    end = text.find(marker, 4)
    if end < 0:
        raise AdapterError("README.md front matter is not terminated")
    raw = text[4:end]
    lines = raw.splitlines()
    values: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$", line)
        if match:
            values[match.group(1)] = _parse_scalar(match.group(2))
    return FrontMatter(start=4, end=end, lines=lines, values=values)


def _set_front_matter_value(lines: list[str], key: str, value: str) -> list[str]:
    rendered = f"{key}: {value}"
    pattern = re.compile(rf"^{re.escape(key)}\s*:")
    matches = [index for index, line in enumerate(lines) if pattern.match(line)]
    if len(matches) > 1:
        raise AdapterError(f"README.md contains duplicate {key!r} front-matter keys")
    updated = list(lines)
    if matches:
        updated[matches[0]] = rendered
    else:
        updated.append(rendered)
    return updated


def update_readme() -> dict[str, Any]:
    text = README.read_text(encoding="utf-8")
    front = parse_front_matter(text)
    lines = _set_front_matter_value(front.lines, "short_description", SHORT_DESCRIPTION)
    lines = _set_front_matter_value(lines, "fullWidth", "true")
    lines = _set_front_matter_value(lines, "header", "mini")
    replacement = "---\n" + "\n".join(lines) + "\n---\n"
    updated = replacement + text[front.end + len("\n---\n") :]
    README.write_text(updated, encoding="utf-8")
    refreshed = parse_front_matter(updated)
    short = refreshed.values.get("short_description")
    if not short or len(short) > 60:
        raise AdapterError("short_description is absent or exceeds 60 characters")
    return refreshed.values


def _candidate_python_files() -> list[Path]:
    preferred = [
        ROOT / "app.py",
        ROOT / "main.py",
        ROOT / "src" / "app.py",
        ROOT / "src" / "main.py",
    ]
    found = [path for path in preferred if path.is_file()]
    if found:
        return found
    return sorted(
        path
        for path in ROOT.rglob("*.py")
        if ".git" not in path.parts
        and "tests" not in path.parts
        and "scripts" not in path.parts
        and "site-packages" not in path.parts
    )


def _python_framework(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    if "gradio" in lowered and (".blocks(" in lowered or ".interface(" in lowered):
        return "gradio"
    if "streamlit" in lowered and re.search(r"\bst\.", text):
        return "streamlit"
    return None


def _react_entry() -> Path | None:
    candidates = [
        ROOT / "src" / "main.tsx",
        ROOT / "src" / "main.jsx",
        ROOT / "src" / "index.tsx",
        ROOT / "src" / "index.jsx",
        ROOT / "src" / "App.tsx",
        ROOT / "src" / "App.jsx",
    ]
    return next((path for path in candidates if path.is_file()), None)


def detect(front: FrontMatter) -> Detection:
    sdk = (front.values.get("sdk") or "").strip().lower()
    declared = front.values.get("app_file") or front.values.get("appFile")
    app = (ROOT / declared).resolve() if declared else None
    if app and not app.is_file():
        raise AdapterError(f"declared app_file does not exist: {declared}")

    if app and app.suffix.lower() in {".html", ".htm"}:
        return Detection(sdk=sdk or "static", framework="static", app_file=app, css_file=app.parent / "szl-universal-frontend.css")

    python_files = [app] if app and app.suffix.lower() == ".py" else _candidate_python_files()
    for path in python_files:
        if path is None:
            continue
        framework = _python_framework(path)
        if framework:
            return Detection(sdk=sdk or framework, framework=framework, app_file=path, css_file=path.parent / "szl-universal-frontend.css")

    if sdk == "static":
        html = app or ROOT / "index.html"
        if html.is_file():
            return Detection(sdk=sdk, framework="static", app_file=html, css_file=html.parent / "szl-universal-frontend.css")

    # Docker Spaces commonly serve a pre-built static application from a
    # repository-local static/ directory. Keep this deterministic and bounded
    # to the canonical root document rather than an arbitrary nested HTML file.
    docker_static = ROOT / "static" / "index.html"
    if sdk == "docker" and docker_static.is_file():
        return Detection(
            sdk=sdk,
            framework="static",
            app_file=docker_static,
            css_file=docker_static.parent / "szl-universal-frontend.css",
        )

    entry = _react_entry()
    if entry and (ROOT / "package.json").is_file():
        return Detection(sdk=sdk or "docker", framework="react", app_file=entry, css_file=entry.parent / "szl-universal-frontend.css", entry_file=entry)

    raise AdapterError("no supported Static, Gradio, Streamlit, or React entry point was found")


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for match in re.finditer("\n", text):
        offsets.append(match.end())
    return offsets


def _absolute_offset(offsets: list[int], lineno: int, col: int) -> int:
    return offsets[lineno - 1] + col


def _insert_after_imports(text: str, block: str) -> str:
    tree = ast.parse(text)
    insertion_line = 0
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        insertion_line = body[0].end_lineno or body[0].lineno
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            insertion_line = max(insertion_line, node.end_lineno or node.lineno)
    lines = text.splitlines(keepends=True)
    insertion = block if block.endswith("\n") else block + "\n"
    lines.insert(insertion_line, insertion)
    return "".join(lines)


def _patch_gradio(path: Path, css_file: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if PYTHON_MARKER not in text:
        helper = (
            f"\n{PYTHON_MARKER}\n"
            "import pathlib as _szl_frontend_pathlib\n"
            f"_SZL_UNIVERSAL_CSS = (_szl_frontend_pathlib.Path(__file__).resolve().parent / {css_file.name!r}).read_text(encoding='utf-8')\n"
        )
        text = _insert_after_imports(text, helper)

    tree = ast.parse(text)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {"Blocks", "Interface"}:
            calls.append(node)
    if not calls:
        raise AdapterError(f"no Gradio Blocks or Interface call found in {path}")
    call = sorted(calls, key=lambda node: (node.lineno, node.col_offset))[0]
    css_keyword = next((keyword for keyword in call.keywords if keyword.arg == "css"), None)
    offsets = _line_offsets(text)
    if css_keyword:
        segment = ast.get_source_segment(text, css_keyword.value)
        if not segment:
            raise AdapterError("could not recover the existing Gradio css expression")
        if "_SZL_UNIVERSAL_CSS" not in segment:
            start = _absolute_offset(offsets, css_keyword.value.lineno, css_keyword.value.col_offset)
            end = _absolute_offset(offsets, css_keyword.value.end_lineno or css_keyword.value.lineno, css_keyword.value.end_col_offset or css_keyword.value.col_offset)
            replacement = f"(_SZL_UNIVERSAL_CSS + '\\n' + str({segment}))"
            text = text[:start] + replacement + text[end:]
    else:
        func = call.func
        end = _absolute_offset(offsets, func.end_lineno or func.lineno, func.end_col_offset or func.col_offset)
        if text[end : end + 1] != "(":
            raise AdapterError("could not locate the Gradio call opening parenthesis")
        text = text[: end + 1] + "css=_SZL_UNIVERSAL_CSS, " + text[end + 1 :]

    ast.parse(text)
    path.write_text(text, encoding="utf-8")


def _patch_streamlit(path: Path, css_file: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if PYTHON_MARKER in text:
        return
    tree = ast.parse(text)
    insertion_line = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            insertion_line = max(insertion_line, node.end_lineno or node.lineno)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "st" and func.attr == "set_page_config":
                insertion_line = max(insertion_line, node.end_lineno or node.lineno)
    block = (
        f"\n{PYTHON_MARKER}\n"
        "import pathlib as _szl_frontend_pathlib\n"
        f"_SZL_UNIVERSAL_CSS = (_szl_frontend_pathlib.Path(__file__).resolve().parent / {css_file.name!r}).read_text(encoding='utf-8')\n"
        "st.markdown(f'<style>{_SZL_UNIVERSAL_CSS}</style>', unsafe_allow_html=True)\n"
    )
    lines = text.splitlines(keepends=True)
    lines.insert(insertion_line, block)
    updated = "".join(lines)
    ast.parse(updated)
    path.write_text(updated, encoding="utf-8")


def _patch_static(path: Path, css_file: Path) -> None:
    text = path.read_text(encoding="utf-8")
    updated = text
    if not re.search(r"<meta\s+[^>]*name=[\"']viewport[\"']", updated, re.IGNORECASE):
        match = re.search(r"<head[^>]*>", updated, re.IGNORECASE)
        if not match:
            raise AdapterError(f"{path} contains no <head> element")
        viewport = '\n<meta name="viewport" content="width=device-width, initial-scale=1">'
        updated = updated[: match.end()] + viewport + updated[match.end() :]
    if HTML_MARKER not in updated:
        closing = re.search(r"</head\s*>", updated, re.IGNORECASE)
        if not closing:
            raise AdapterError(f"{path} contains no </head> element")
        href = css_file.name
        link = f'\n<link rel="stylesheet" href="./{href}" {HTML_MARKER}>'
        updated = updated[: closing.start()] + link + "\n" + updated[closing.start() :]
    path.write_text(updated, encoding="utf-8")


def _patch_react(entry: Path, css_file: Path) -> None:
    text = entry.read_text(encoding="utf-8")
    if REACT_MARKER in text:
        return
    relative = "./" + css_file.name
    import_line = f"import {relative!r}; {REACT_MARKER}\n"
    lines = text.splitlines(keepends=True)
    insertion = 0
    for index, line in enumerate(lines):
        if line.lstrip().startswith("import "):
            insertion = index + 1
    lines.insert(insertion, import_line)
    entry.write_text("".join(lines), encoding="utf-8")


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")


def apply() -> dict[str, Any]:
    readme_values = update_readme()
    front = parse_front_matter(README.read_text(encoding="utf-8"))
    detection = detect(front)
    detection.css_file.write_text(UNIVERSAL_CSS, encoding="utf-8")

    if detection.framework == "gradio":
        _patch_gradio(detection.app_file, detection.css_file)
    elif detection.framework == "streamlit":
        _patch_streamlit(detection.app_file, detection.css_file)
    elif detection.framework == "static":
        _patch_static(detection.app_file, detection.css_file)
    elif detection.framework == "react":
        _patch_react(detection.entry_file or detection.app_file, detection.css_file)
    else:  # pragma: no cover - protected by detect()
        raise AdapterError(f"unsupported framework: {detection.framework}")

    manifest = {
        "schema": "szl.hf-universal-frontend/v1",
        "remote_mutation": False,
        "sdk": detection.sdk,
        "framework": detection.framework,
        "app_file": _relative(detection.app_file),
        "css_file": _relative(detection.css_file),
        "entry_file": _relative(detection.entry_file) if detection.entry_file else None,
        "short_description": readme_values.get("short_description"),
        "contract": {
            "viewport_classes": [360, 390, 768, 1024, 1440],
            "minimum_touch_target_px": 44,
            "horizontal_overflow_allowed": False,
            "reduced_motion_required": True,
            "technical_identifier_wrapping_required": True,
        },
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate(manifest)
    manifest["file_sha256"] = {
        "README.md": _sha256(README),
        manifest["app_file"]: _sha256(ROOT / manifest["app_file"]),
        manifest["css_file"]: _sha256(ROOT / manifest["css_file"]),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate(manifest)
    return manifest


def validate(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    if manifest is None:
        if not MANIFEST.is_file():
            raise AdapterError("universal frontend manifest is absent")
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema") != "szl.hf-universal-frontend/v1":
        raise AdapterError("unexpected universal frontend manifest schema")
    front = parse_front_matter(README.read_text(encoding="utf-8"))
    short = front.values.get("short_description")
    if not short or len(short) > 60:
        raise AdapterError("README short_description is absent or too long")
    if front.values.get("fullWidth", "").lower() != "true":
        raise AdapterError("README fullWidth must be true")
    if front.values.get("header") != "mini":
        raise AdapterError("README header must be mini")

    app = ROOT / str(manifest["app_file"])
    css = ROOT / str(manifest["css_file"])
    if not app.is_file() or not css.is_file():
        raise AdapterError("declared app or universal CSS file is absent")
    css_text = css.read_text(encoding="utf-8")
    required_css = (
        "--szl-touch-target: 44px",
        "overflow-wrap: anywhere",
        "@media (max-width: 560px)",
        "@media (prefers-reduced-motion: reduce)",
        "overflow-x: clip",
    )
    missing = [token for token in required_css if token not in css_text]
    if missing:
        raise AdapterError("universal CSS is missing: " + ", ".join(missing))

    framework = manifest.get("framework")
    app_text = app.read_text(encoding="utf-8")
    if framework in {"gradio", "streamlit"} and PYTHON_MARKER not in app_text:
        raise AdapterError("Python frontend marker is absent")
    if framework == "gradio" and "_SZL_UNIVERSAL_CSS" not in app_text:
        raise AdapterError("Gradio CSS binding is absent")
    if framework == "streamlit" and "unsafe_allow_html=True" not in app_text:
        raise AdapterError("Streamlit CSS binding is absent")
    if framework == "static" and HTML_MARKER not in app_text:
        raise AdapterError("Static CSS link marker is absent")
    if framework == "static" and not re.search(r"name=[\"']viewport[\"']", app_text, re.IGNORECASE):
        raise AdapterError("Static viewport metadata is absent")
    if framework == "react" and REACT_MARKER not in app_text:
        raise AdapterError("React CSS import marker is absent")

    hashes = manifest.get("file_sha256")
    if isinstance(hashes, dict):
        for relative, expected in hashes.items():
            path = ROOT / relative
            if not path.is_file() or _sha256(path) != expected:
                raise AdapterError(f"file hash mismatch: {relative}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        result = apply() if args.apply else validate()
    except (AdapterError, OSError, SyntaxError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, indent=2, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "mode": "apply" if args.apply else "check",
                "framework": result.get("framework"),
                "app_file": result.get("app_file"),
                "css_file": result.get("css_file"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
