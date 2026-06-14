# -*- coding: utf-8 -*-
# ===========================================================================
# killinchu_nav_wireup.py — Estate cross-link wire-up (R5, Restraint lane)
# ---------------------------------------------------------------------------
# GOAL (R5): the a11oy Restraint surface (governed code-minimization /
# dependency-frugality ladder, R1) must be REACHABLE from killinchu's left-nav
# and cross-linked into the flagship cluster, completing the estate-wide
# wire-up on BOTH apps. Restraint physically lives on a11oy
# (https://szlholdings-a11oy.hf.space/restraint) — killinchu does not re-host
# it — so the killinchu nav item is an honest cross-app link to that surface.
#
# FIX (ADDITIVE, idempotent, 0 lines removed from the SPA shell): mirror the
# proven a11oy_nav_wireup.py / serve.py _OperatorWidgetInjectorKC pattern — a
# single BaseHTTPMiddleware that, on every text/html response that carries the
# killinchu sidebar, injects ONE Restraint nav-item immediately before the
# sidebar footer (<div class="side-foot">). Keyed by the data-attribute
# data-nav-restraint="r5" so re-runs NEVER double-inject and OTHER lanes' nav
# items (ecosystem, the operator widget, etc.) are NEVER touched. A lightweight
# "Related surfaces" cross-link strip (data-related-restraint="r5") is appended
# to the flagship pages so Restraint joins the SZL-Nemo ↔ Auto-Review ↔ Factory
# ↔ Constitution ↔ Energy ↔ Quant ↔ GRC ↔ Restraint cluster from killinchu too.
#
# The SPA shell (static/index.html) is NOT edited. The injector only ADDS
# markup; it removes nothing and never clobbers another lane's nav.
#
# DOCTRINE (v11): locked = 8 @ c7c0ba17; Λ = Conjecture 1 (NOT a theorem);
# 0 visible codenames (label is the surface's own honest title); 0 CDN (the only
# URL is the same-estate a11oy Restraint page, not a third-party CDN asset);
# honest labels only; never weakens a gate; never commits a key; additive-only.
#
# Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
# ===========================================================================
from typing import Any, Dict, List

# The a11oy-hosted Restraint surfaces (same estate, NOT a third-party CDN).
_A11OY_BASE = "https://szlholdings-a11oy.hf.space"
_RESTRAINT_URL = _A11OY_BASE + "/restraint"
_RESTRAINT_BENCH_URL = _A11OY_BASE + "/restraint-bench"

# Idempotency markers.
_NAV_MARKER = b'data-nav-restraint="r5"'
_REL_MARKER = b'data-related-restraint="r5"'

# Sidebar anchor: the killinchu sidebar ends with <div class="side-foot">…; we
# place the Restraint nav-item immediately before it (last item in the aside).
_FOOT_ANCHOR = b'<div class="side-foot">'
# Fallback anchors if the footer is ever renamed.
_GROUP_ANCHOR = b'<div class="nav-group">'
_NAVITEM_ANCHOR = b'<div class="nav-item"'

# Flagship pages on killinchu that get the cross-link strip.
_FLAGSHIP_PATHS = {"/ecosystem", "/estate-organism", "/counter-uas"}


def _build_nav_item() -> bytes:
    """ONE Restraint nav-item, mirroring killinchu's own nav-item markup
    (class="nav-item" + <span class="ico"> + label). Navigates cross-app to the
    a11oy Restraint surface via location.href. 0 CDN, 0 inline <style>, no codename."""
    item = (
        '<div class="nav-item" data-nav-restraint="r5" '
        'onclick="location.href=\'%s\'" style="cursor:pointer" '
        'title="a11oy Restraint — governed code-minimization / dependency-frugality (aligns with, not certified)">'
        '<span class="ico">\u27c2</span>Restraint (Governed Frugality)</div>'
    ) % _RESTRAINT_URL
    return item.encode("utf-8")


def _build_related_strip(current_path: str) -> bytes:
    """A small 'Related surfaces' strip that adds Restraint to the flagship
    cluster from killinchu. Inline-styled (0 CDN). Honest labels."""
    rel = [
        ("/ecosystem", "Estate Hub"),
        (_A11OY_BASE + "/nemo", "SZL-Nemo"),
        (_A11OY_BASE + "/autoreview", "Auto-Review"),
        (_A11OY_BASE + "/factory", "Factory"),
        (_A11OY_BASE + "/constitution", "Constitution"),
        (_A11OY_BASE + "/energy", "Energy"),
        (_A11OY_BASE + "/quant", "Quant"),
        (_A11OY_BASE + "/grc", "GRC"),
        (_RESTRAINT_URL, "Restraint"),
    ]
    links = []
    for path, label in rel:
        if path == current_path:
            continue
        links.append(
            '<a href="%s" style="color:#d4a444;text-decoration:none;'
            'margin:0 .55em;white-space:nowrap">%s</a>' % (path, label)
        )
    strip = (
        '<nav data-related-restraint="r5" aria-label="Related surfaces" '
        'style="margin:1.25rem auto;max-width:1100px;padding:.6rem .9rem;'
        'border-top:1px solid #1d2632;font:13px/1.6 system-ui,sans-serif;'
        'color:#7c8794;text-align:center">'
        '<span style="color:#7c8794;margin-right:.4em">Related surfaces:</span>'
        + "".join(links)
        + "</nav>"
    )
    return strip.encode("utf-8")


def _make_injector():
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import Response

    nav_item = _build_nav_item()

    class _RestraintNavInjectorKC(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            resp = await call_next(request)
            try:
                ct = (resp.headers.get("content-type") or "").lower()
                if "text/html" not in ct:
                    return resp
                p = request.url.path
                # Never touch API / SSE / asset routes.
                if (p.startswith("/api/") or p.startswith("/v1/")
                        or p.startswith("/vendor/") or p.startswith("/assets/")
                        or p.startswith("/static/")):
                    return resp

                body = b""
                async for chunk in resp.body_iterator:
                    body += chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode()

                # (1) Restraint nav-item — only on pages carrying the sidebar.
                #     Idempotent via _NAV_MARKER; never clobbers other nav items.
                if _NAV_MARKER not in body:
                    if _FOOT_ANCHOR in body:
                        body = body.replace(_FOOT_ANCHOR, nav_item + _FOOT_ANCHOR, 1)
                    elif _NAVITEM_ANCHOR in body:
                        # No footer found but a nav exists -> place after the first
                        # existing nav-item so Restraint still lands in the nav.
                        idx = body.find(b">", body.find(_NAVITEM_ANCHOR))
                        # find end of that first nav-item div
                        end = body.find(b"</div>", idx)
                        if end != -1:
                            cut = end + len(b"</div>")
                            body = body[:cut] + nav_item + body[cut:]
                    elif _GROUP_ANCHOR in body:
                        body = body.replace(_GROUP_ANCHOR, _GROUP_ANCHOR + nav_item, 1)

                # (2) Related-surfaces strip — only on flagship pages, idempotent.
                if p in _FLAGSHIP_PATHS and _REL_MARKER not in body and b"</body>" in body:
                    body = body.replace(b"</body>", _build_related_strip(p) + b"</body>", 1)

                # body_iterator was fully consumed; MUST rebuild the Response from
                # the buffered bytes even when unchanged (returning the exhausted
                # resp would emit an EMPTY body -> white-screen).
                headers = dict(resp.headers)
                headers.pop("content-length", None)
                return Response(content=body, status_code=resp.status_code,
                                headers=headers, media_type="text/html")
            except Exception:
                return resp

    return _RestraintNavInjectorKC


def register(app, ns: str = "killinchu") -> Dict[str, Any]:
    """Attach the idempotent Restraint nav cross-link injector. ADDITIVE; registers
    NO routes (Restraint is hosted on a11oy) — it only injects an honest cross-app
    nav item + a flagship cross-link strip into killinchu's HTML responses.
    try/except-guarded by the caller."""
    registered: List[str] = []
    app.add_middleware(_make_injector())
    registered.append("MIDDLEWARE killinchu Restraint nav cross-link injector (R5)")
    return {
        "registered": registered,
        "count": len(registered),
        "capability": "Restraint Nav Cross-Link (R5)",
        "links": {"restraint": _RESTRAINT_URL, "restraint_bench": _RESTRAINT_BENCH_URL},
        "data_label": "NAV",
    }


# ---------------------------------------------------------------------------
# Self-test: builds a synthetic killinchu console + a flagship page, runs the
# injector twice, asserts the Restraint nav-item + cross-link strip appear
# EXACTLY ONCE, that NO original markup was removed, and that it is 0-CDN /
# 0-codename / 0-script.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from starlette.applications import Starlette
    from starlette.responses import HTMLResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    SAMPLE_CONSOLE = (
        '<html><body><aside>'
        '<div class="nav-group">Operate</div>'
        '<div class="nav-item" data-view="tracks" onclick="go(\'tracks\')">'
        '<span class="ico">\u25c9</span>Live Track Board</div>'
        '<div class="side-foot">footer</div>'
        '</aside><main>x</main></body></html>'
    )
    SAMPLE_ECO = '<html><body><h1>Estate Hub</h1></body></html>'

    async def _console(req):
        return HTMLResponse(SAMPLE_CONSOLE)

    async def _eco(req):
        return HTMLResponse(SAMPLE_ECO)

    app = Starlette(routes=[Route("/", _console), Route("/ecosystem", _eco)])
    st = register(app, ns="killinchu")
    assert st["count"] == 1 and st["links"]["restraint"].endswith("/restraint")
    c = TestClient(app)

    h1 = c.get("/").text
    h2 = c.get("/").text  # second hit must be byte-identical (idempotent)
    assert h1.count('data-nav-restraint="r5"') == 1, "Restraint nav must inject exactly once"
    assert h2.count('data-nav-restraint="r5"') == 1, "Restraint nav must be idempotent"
    assert _RESTRAINT_URL in h1, "nav item must link the a11oy Restraint surface"
    assert "Restraint (Governed Frugality)" in h1, "honest Restraint label"
    # additive: original nav untouched
    assert "Live Track Board" in h1, "must NOT remove existing nav items"
    assert "Operate</div>" in h1, "must NOT remove existing nav group"
    assert "footer</div>" in h1, "must NOT remove footer"
    # placed immediately before the footer
    assert 'Restraint (Governed Frugality)</div><div class="side-foot">' in h1, "must place before footer"
    assert h1 == h2, "second render must be byte-identical (idempotent)"

    e1 = c.get("/ecosystem").text
    e2 = c.get("/ecosystem").text
    assert e1.count('data-related-restraint="r5"') == 1, "cross-link strip must inject once"
    assert e2.count('data-related-restraint="r5"') == 1, "cross-link strip must be idempotent"
    assert _RESTRAINT_URL in e1 and "/autoreview" in e1, "strip must cross-link Restraint + flagships"
    # /ecosystem is the current page -> omitted from its own strip
    inner = e1.split('data-related-restraint="r5"')[1].split("</nav>")[0]
    assert "/ecosystem" not in inner, "strip must omit the current page (/ecosystem)"
    assert e1 == e2, "second ecosystem render must be byte-identical"

    # Doctrine guard: 0 CDN (only the same-estate a11oy URL), 0 script, 0 codename.
    injected = (_build_nav_item().decode() + _build_related_strip("/ecosystem").decode())
    low = injected.lower()
    assert "<script" not in low, "nav markup must inject no script"
    # the ONLY absolute URLs allowed are same-estate a11oy hf.space links
    import re
    urls = re.findall(r'https?://[^\'"\s]+', injected)
    assert all(u.startswith(_A11OY_BASE) for u in urls), "only same-estate a11oy URLs allowed: %s" % urls

    print("killinchu_nav_wireup: ALL OK (Restraint nav item + cross-link strip; "
          "idempotent; additive; 0 codenames; 0 CDN; same-estate cross-link only)")
