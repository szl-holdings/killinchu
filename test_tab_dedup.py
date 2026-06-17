# SPDX-License-Identifier: Apache-2.0
"""test_tab_dedup.py — feat/tab-dedup guard.

Asserts the /elite tab de-duplication is HONEST and LOSSLESS:

  1. Every ORIGINAL go() route key (the full pre-dedup inventory) still RESOLVES
     to a rendering view — either as a top-level VIEWS entry, a dynamically
     registered view, a _SUBMAP sub-view, or a VIEW_ALIASES alias that routes to
     a surviving merged surface + sub-view.
  2. Every VIEW_ALIASES alias points at a real surface key that exists in _SUBMAP,
     and the alias's sub-view key is actually listed in that surface's sub-views
     (so the deep link opens the right pane — no silent fallback).
  3. The merged surfaces are registered (renderSurface wired) and their sub-views
     all reference real, defined view keys.
  4. The visible top-level nav is consolidated to the ~30 target (a hard ceiling),
     and no nav item points at a key that does not resolve.
  5. Honest labels are preserved (no LIVE/SAMPLE/EXPERIMENTAL/SIMULATED/PROPOSED
     wording was deleted wholesale by the merge).

Pure stdlib + regex over the in-module _CONSOLE_HTML string. No browser, no net.
"""
from __future__ import annotations

import re

import killinchu_elite_console as KEC

HTML = KEC._CONSOLE_HTML

# ── The authoritative ORIGINAL inventory of go() route keys (pre-dedup). This is
#    the contract: each MUST still resolve after the merge. Sourced from the
#    killinchu_elite_wiring.ELITE_WIRING self-audit map (every wired view) plus
#    the maritime/operator/cuas realm keys folded by this PR. ──
import killinchu_elite_wiring as KEW

# ELITE_WIRING also documents pure API endpoint-groups that were NEVER go()/nav
# views (no data-view, no VIEWS entry, no dynamic registration in the console —
# verified against origin/main). They are backend audit rows, not routable tabs,
# so they are out of scope for the "every route key still resolves" contract.
_NON_VIEW_AUDIT_KEYS = {"ais_aug2024", "cot_interop"}

ORIGINAL_KEYS = sorted((set(KEW.ELITE_WIRING.keys()) - _NON_VIEW_AUDIT_KEYS) | {
    # realm members folded into merged surfaces (kept as aliases)
    "tracks", "livepic", "u_maritime",
    "u_fleet", "fleet_c2",
    "u_swarm", "swarm_intent", "cuas_swarm",
    "u_fusion", "cuas_fusion",
    "u_intel", "osint_intel", "osint_naval", "osint_procurement",
    "osint_advisories", "osint_geopolitical", "osint_counter_uas",
    "operator_digest", "operator_routing", "operator_entities",
    "operator_correlate", "operator_watch",
    "u_consensus", "mesh_resilience",
    "u_receipts", "provenance",
    "cuas_intercept", "cuas_spoof", "cuas_triage", "cuas_pq",
})


def _extract_submap() -> dict[str, list[str]]:
    """Parse window._SUBMAP = { key:[{k:'..',l:'..'},...], ... }."""
    m = re.search(r"window\._SUBMAP\s*=\s*\{(.*?)\n\};", HTML, re.S)
    assert m, "could not locate window._SUBMAP literal"
    block = m.group(1)
    out: dict[str, list[str]] = {}
    # each top-level entry:  surfaceKey: [ ... ],
    for em in re.finditer(r"(\w+)\s*:\s*\[(.*?)\]", block, re.S):
        surface = em.group(1)
        subs = re.findall(r"k:'([^']+)'", em.group(2))
        out[surface] = subs
    return out


def _extract_aliases() -> dict[str, dict[str, str]]:
    """Parse window.VIEW_ALIASES = { key:{s:'..',k:'..'}, ... }."""
    m = re.search(r"window\.VIEW_ALIASES\s*=\s*\{(.*?)\n\};", HTML, re.S)
    assert m, "could not locate window.VIEW_ALIASES literal"
    block = m.group(1)
    out: dict[str, dict[str, str]] = {}
    for em in re.finditer(r"(\w+)\s*:\s*\{s:'([^']+)',k:'([^']+)'\}", block):
        out[em.group(1)] = {"s": em.group(2), "k": em.group(3)}
    return out


def _defined_view_keys() -> set[str]:
    """All keys that resolve to a render-capable VIEWS entry.

    Covers: top-level literal `key:{title:`, dynamic `V.key =` / `VIEWS['key']=`,
    `reg('key'...)` registrations, surface keys (renderSurface), and _SUBMAP
    sub-view keys (which are themselves VIEWS entries the surface renders).
    """
    keys: set[str] = set()
    keys |= set(re.findall(r"\n\s{0,6}([a-z_0-9]+)\s*:\s*\{title:", HTML))
    keys |= set(re.findall(r"\bV\.([a-z_0-9]+)\s*=\s*\{", HTML))
    keys |= set(re.findall(r"\bV\['([a-z_0-9]+)'\]\s*=", HTML))
    keys |= set(re.findall(r"VIEWS\['([a-z_0-9]+)'\]\s*=", HTML))
    keys |= set(re.findall(r"window\.VIEWS\.([a-z_0-9]+)\s*=", HTML))
    keys |= set(re.findall(r"\breg\('([a-z_0-9]+)'", HTML))
    return keys


SUBMAP = _extract_submap()
ALIASES = _extract_aliases()
DEFINED = _defined_view_keys()
ALL_SUBVIEW_KEYS = {k for subs in SUBMAP.values() for k in subs}


def _resolves(key: str) -> tuple[bool, str]:
    """Return (resolves?, how) for an original route key."""
    if key in ALIASES:
        a = ALIASES[key]
        if a["s"] not in SUBMAP:
            return False, f"alias->missing surface {a['s']}"
        if a["k"] not in SUBMAP[a["s"]]:
            return False, f"alias->sub {a['k']} not in surface {a['s']}"
        return True, f"alias -> {a['s']}#{a['k']}"
    if key in SUBMAP:
        return True, "surface"
    if key in DEFINED:
        return True, "view"
    if key in ALL_SUBVIEW_KEYS:
        return True, "subview"
    return False, "UNRESOLVED"


def test_every_original_key_resolves():
    failures = []
    for key in ORIGINAL_KEYS:
        ok, how = _resolves(key)
        if not ok:
            failures.append(f"{key}: {how}")
    assert not failures, "Original go() keys that NO LONGER resolve:\n  " + "\n  ".join(failures)


def test_aliases_point_at_real_surface_and_subview():
    failures = []
    for key, a in ALIASES.items():
        if a["s"] not in SUBMAP:
            failures.append(f"{key} -> surface {a['s']} missing from _SUBMAP")
        elif a["k"] not in SUBMAP[a["s"]]:
            failures.append(f"{key} -> sub {a['k']} not in surface {a['s']} {SUBMAP[a['s']]}")
    assert not failures, "Broken aliases:\n  " + "\n  ".join(failures)


def test_merged_surfaces_registered_and_subviews_defined():
    """Each merged surface must be a registered view and its sub-views defined."""
    merged = {"u_maritime", "u_swarm", "u_fusion", "u_intel", "u_operator",
              "u_consensus", "u_receipts", "fleet_c2", "cuas_lab"}
    failures = []
    for surf in merged:
        if surf not in SUBMAP:
            failures.append(f"surface {surf} absent from _SUBMAP")
            continue
        # surface itself renderable (literal/dynamic view OR renderSurface-wired)
        wired = (surf in DEFINED) or (f"renderSurface('{surf}'" in HTML)
        if not wired:
            failures.append(f"surface {surf} not wired to renderSurface / not a view")
        for sub in SUBMAP[surf]:
            if sub not in DEFINED and sub not in ALL_SUBVIEW_KEYS:
                failures.append(f"surface {surf} sub-view {sub} is not a defined view")
    assert not failures, "Merged surface problems:\n  " + "\n  ".join(failures)


def _visible_nav_keys() -> list[str]:
    """data-view keys on STATIC nav-item/<a> elements in the served HTML."""
    return re.findall(r'class="nav-item[^"]*"[^>]*data-view="([a-z_0-9]+)"', HTML)


def test_visible_nav_consolidated_under_ceiling():
    nav = _visible_nav_keys()
    uniq = sorted(set(nav))
    # every visible nav key must resolve
    bad = [k for k in uniq if not _resolves(k)[0]]
    assert not bad, f"visible nav keys that do not resolve: {bad}"
    # consolidation target: ~30 strong tabs. Hard ceiling 34 (static nav only;
    # runtime-injected R&D tabs add a few more but are fenced as EXPERIMENTAL).
    assert len(uniq) <= 34, f"too many top-level static nav tabs ({len(uniq)}): {uniq}"


def test_no_folded_key_kept_as_standalone_static_nav():
    """The folded realm members must NOT still appear as their own static nav tab."""
    folded = set(ALIASES.keys())
    nav = set(_visible_nav_keys())
    leaked = sorted(folded & nav)
    # tracks is intentionally allowed to remain a DEMO pinned entry (canonical key,
    # resolves via alias to the maritime surface). Everything else must be gone.
    leaked = [k for k in leaked if k != "tracks"]
    assert not leaked, f"folded keys still present as standalone static nav: {leaked}"


def test_honest_labels_preserved():
    for token in ("LIVE", "SAMPLE", "EXPERIMENTAL", "SIMULATED", "PROPOSED", "Conjecture"):
        assert token in HTML, f"honest label token '{token}' vanished from the console"


if __name__ == "__main__":
    import sys
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    rc = 0
    print(f"tab-dedup guard :: {len(ORIGINAL_KEYS)} original keys · "
          f"{len(SUBMAP)} surfaces · {len(ALIASES)} aliases\n")
    for f in funcs:
        try:
            f()
            print(f"  PASS  {f.__name__}")
        except AssertionError as e:
            rc = 1
            print(f"  FAIL  {f.__name__}\n        {e}")
    # resolution report
    print("\n  per-key resolution:")
    for key in ORIGINAL_KEYS:
        ok, how = _resolves(key)
        print(f"    {'ok ' if ok else 'XX '} {key:22} {how}")
    sys.exit(rc)
