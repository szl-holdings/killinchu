#!/usr/bin/env python3
"""Apply the bounded shared integrations Flow Shell source-boundary repair."""
from __future__ import annotations

from pathlib import Path


MODULE = Path("szl_connectors_serve.py")
TEST = Path("tests/test_integrations_flow_boundary.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def patch_module() -> None:
    text = MODULE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    from fastapi.responses import JSONResponse, FileResponse\n",
        "    from fastapi.responses import JSONResponse, FileResponse, HTMLResponse\n",
        "FastAPI response import",
    )
    text = replace_once(
        text,
        "    Request = object  # type: ignore\n\nimport szl_connectors as sc\n",
        "    Request = object  # type: ignore\n    HTMLResponse = object  # type: ignore\n\nimport szl_connectors as sc\n",
        "import guard",
    )
    helper = '''_INDEX_HTML = Path("/app/static/index.html")
_FLOW_STYLE = '<link rel="stylesheet" href="/assets/szl-flow.css" data-szl-flow-asset="style" />'
_FLOW_SCRIPT = '<script src="/assets/szl-flow.js" defer data-szl-flow-asset="script"></script>'


def _with_a11oy_flow_shell(text: str) -> str:
    """Bind the product-only Flow Shell without mutating shared source bytes."""
    style_count = text.count('data-szl-flow-asset="style"')
    script_count = text.count('data-szl-flow-asset="script"')
    if style_count > 1 or script_count > 1:
        raise ValueError("duplicate Flow Shell marker")
    if style_count == 0:
        index = text.lower().rfind("</head>")
        if index < 0:
            raise ValueError("integrations document has no closing head")
        text = text[:index] + "  " + _FLOW_STYLE + "\\n" + text[index:]
    if script_count == 0:
        index = text.lower().rfind("</body>")
        if index < 0:
            raise ValueError("integrations document has no closing body")
        text = text[:index] + "  " + _FLOW_SCRIPT + "\\n" + text[index:]
    return text
'''
    text = replace_once(
        text,
        '_INDEX_HTML = Path("/app/static/index.html")\n',
        helper,
        "page roots",
    )
    old_route = '''        if f.is_file():
            return FileResponse(f, media_type="text/html")
        if _INDEX_HTML.is_file():
'''
    new_route = '''        if f.is_file():
            if ns == "a11oy":
                try:
                    page = _with_a11oy_flow_shell(f.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, ValueError) as error:
                    return JSONResponse(
                        {"error": "integrations page unavailable", "detail": type(error).__name__},
                        status_code=500,
                    )
                return HTMLResponse(page, media_type="text/html")
            return FileResponse(f, media_type="text/html")
        if _INDEX_HTML.is_file():
'''
    text = replace_once(text, old_route, new_route, "integrations route")
    MODULE.write_text(text, encoding="utf-8", newline="\n")


def write_test() -> None:
    TEST.write_text('''#!/usr/bin/env python3
"""Regression contract for the shared integrations source boundary."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "szl_connectors_serve.py"
PAGE = ROOT / "pages" / "integrations.html"
STYLE_MARKER = 'data-szl-flow-asset="style"'
SCRIPT_MARKER = 'data-szl-flow-asset="script"'


class IntegrationsFlowBoundaryContract(unittest.TestCase):
    def _helper(self):
        source = MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        wanted = []
        for node in tree.body:
            if isinstance(node, ast.Assign):
                names = {target.id for target in node.targets if isinstance(target, ast.Name)}
                if names & {"_FLOW_STYLE", "_FLOW_SCRIPT"}:
                    wanted.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name == "_with_a11oy_flow_shell":
                wanted.append(node)
        namespace = {}
        selected = ast.Module(body=wanted, type_ignores=[])
        ast.fix_missing_locations(selected)
        exec(compile(selected, str(MODULE), "exec"), namespace)
        return namespace["_with_a11oy_flow_shell"]

    def test_helper_is_idempotent_and_exact(self) -> None:
        bind = self._helper()
        original = "<html><head><title>x</title></head><body>y</body></html>"
        bound = bind(original)
        self.assertEqual(bound.count(STYLE_MARKER), 1)
        self.assertEqual(bound.count(SCRIPT_MARKER), 1)
        self.assertEqual(bind(bound), bound)

    def test_shared_page_remains_product_asset_free(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        self.assertNotIn(STYLE_MARKER, page)
        self.assertNotIn(SCRIPT_MARKER, page)

    def test_route_binds_only_the_a11oy_namespace(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn('if ns == "a11oy":', source)
        self.assertIn('return HTMLResponse(page, media_type="text/html")', source)
        self.assertIn('return FileResponse(f, media_type="text/html")', source)


if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8", newline="\n")


def main() -> int:
    patch_module()
    write_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
