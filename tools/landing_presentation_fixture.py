# SPDX-License-Identifier: Apache-2.0
"""Compose the source landing through its real HTML middleware, without operations.

The local Starlette app has one HTML route and no operational routes, storage,
signer, credentials or startup handlers. The two classes embedded in serve.py
are selected as AST declarations; the operational module is never imported.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from killinchu_defend_plane import PlaneTabsMiddleware
from killinchu_nav_wireup import _make_injector


def _widget_middleware() -> tuple[type, type]:
    """Use the actual two HTML-only class bodies and their literal tag bytes."""
    tree = ast.parse((ROOT / "serve.py").read_bytes(), filename="serve.py")
    names = ("_OperatorWidgetInjectorKC", "_RestraintChaskiInjector")
    literal_names = ("_OPW_KC_TAG", "_OPW_KC_MARK", "_RST_KC_TAG", "_RST_KC_MARK")
    declarations = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name in names]
    if len(declarations) != len(names):
        raise ValueError("source HTML middleware declarations changed")
    for declaration in declarations:
        if declaration.decorator_list or any(
            not isinstance(node, ast.AsyncFunctionDef) or node.name != "dispatch" or node.decorator_list
            for node in declaration.body
        ):
            raise ValueError("source HTML middleware declaration shape changed")
    namespace = {
        "_OPW_KC_Base": BaseHTTPMiddleware,
        "_RST_KC_Base": BaseHTTPMiddleware,
        "_OPW_KC_SResp": Response,
        "_RST_KC_SResp": Response,
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in literal_names:
                value = ast.literal_eval(node.value)
                if not isinstance(value, bytes) or name in namespace:
                    raise ValueError("source HTML middleware tags must be unique bytes")
                namespace[name] = value
    if not all(name in namespace for name in literal_names):
        raise ValueError("source HTML middleware tags are missing")
    # Only these already-reviewed class declarations are compiled. No import,
    # route registration, module statement or runtime startup from serve.py runs.
    exec(compile(ast.Module(body=declarations, type_ignores=[]), "serve.py", "exec"), namespace)
    return tuple(namespace[name] for name in names)


def rendered_landing() -> bytes:
    async def landing(_request):
        return Response((ROOT / "static/landing.html").read_bytes(), media_type="text/html")

    app = Starlette(routes=[Route("/", landing, methods=["GET"])])
    # Response composition order follows serve.py: capability rail, brand
    # navigation, operator script, then the restraint annotation script.
    app.add_middleware(PlaneTabsMiddleware)
    app.add_middleware(_make_injector())
    for middleware in _widget_middleware():
        app.add_middleware(middleware)
    with TestClient(app) as client:
        response = client.get("/")
    if response.status_code != 200 or not response.headers.get("content-type", "").startswith("text/html"):
        raise ValueError("local source HTML composition failed")
    return response.content
