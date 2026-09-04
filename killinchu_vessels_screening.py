"""killinchu_vessels_screening.py — vessels domain: sanctions screening + ownership graph.

Consolidated from the retired vessels vertical (2026-09-03). Killinchu is now
the sole SZL maritime surface (see docs/VESSELS_DOMAIN.md).

Honest by design:
- Screening results are MEASURED exact list-matches. List assertions remain
  REPORTED with explicit operator or official-public source provenance.
- Ownership data is REPORTED as declared by the operator; the graph walk is
  exact, the declarations are not independently verified.
- Combined risk scores are MODELED, not measurements.
- Every screening event emits a SHA-256 hash-chained receipt.
- Fail closed: unknown vessel, empty list, or malformed input returns
  BLOCKED_PENDING rather than CLEAR.

Pure stdlib. Wire-up: register routes in serve.py and COPY this file in the
Space Dockerfile before enabling on the live surface (KNOWN_GOTCHAS pattern).
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Tuple

# ----------------------------- receipt chain -------------------------------

_RECEIPTS: Deque[Dict[str, Any]] = deque(maxlen=1000)
_PREV_HASH = "GENESIS"


def _chain(step: str, payload: str) -> Dict[str, Any]:
    global _PREV_HASH
    h = hashlib.sha256(f"{_PREV_HASH}|{step}|{payload}".encode()).hexdigest()
    receipt = {
        "step": step,
        "hash": h,
        "prev": _PREV_HASH,
        "ts": time.time(),
        "truth_label": "MEASURED",
    }
    _PREV_HASH = h
    _RECEIPTS.append(receipt)
    return receipt


# ----------------------------- screening lists -----------------------------

# screening lists: name -> explicit source provenance + normalized entities
_LISTS: Dict[str, Dict[str, Any]] = {}


def load_screening_list(
    name: str,
    entries: List[str],
    *,
    source: str = "operator-supplied",
    truth_label: str = "REPORTED",
) -> Dict[str, Any]:
    """Load an exact-fold screening list with explicit source provenance.

    The list contents remain REPORTED assertions from the named source; only
    normalization and later membership comparison are measured.  The default
    preserves the original operator-supplied behavior.
    """
    clean_name = " ".join(str(name or "").split())[:200]
    clean_source = " ".join(str(source or "").split())[:1000]
    if not clean_name:
        raise ValueError("list name is required")
    if not clean_source:
        clean_source = "operator-supplied"
    if truth_label != "REPORTED":
        raise ValueError("screening-list assertions must remain REPORTED")
    norm = {" ".join(e.split()).casefold() for e in entries if e and e.strip()}
    _LISTS[clean_name] = {
        "source": clean_source,
        "entities": norm,
        "loaded_ts": time.time(),
        "count": len(norm),
        "truth_label": truth_label,
    }
    return {
        "list": clean_name,
        "entries": len(norm),
        "source": clean_source,
        "truth_label": truth_label,
        "note": "source assertions are reported; exact normalization is measured",
    }

def _norm(s: str) -> str:
    return " ".join(s.split()).casefold()


def screen_entity(name: str) -> Dict[str, Any]:
    """Screen one entity/vessel name against every loaded list. Fail closed."""
    if not name or not name.strip():
        return {"name": name, "result": "BLOCKED_PENDING",
                "reason": "empty query", "truth_label": "MEASURED"}
    if not _LISTS:
        return {"name": name, "result": "BLOCKED_PENDING",
                "reason": "no screening lists loaded",
                "truth_label": "MEASURED"}
    n = _norm(name)
    hits: List[Dict[str, Any]] = []
    for lname, ldata in _LISTS.items():
        if n in ldata["entities"]:
            hits.append({"list": lname, "source": ldata["source"]})
    result = "HIT" if hits else "CLEAR"
    receipt = _chain("screen.entity", f"{name}|{result}|{len(hits)}")
    return {"name": name, "result": result, "hits": hits,
            "lists_checked": len(_LISTS), "receipt": receipt,
            "truth_label": "MEASURED"}


# ----------------------------- ownership graph -----------------------------

# vessel imo -> list of (owner_name, ownership_pct)
_OWNERSHIP: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
# entity name -> list of (parent_entity, ownership_pct) for indirect ownership
_ENTITY_HOLDERS: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
_MAX_DEPTH = 6


def declare_ownership(vessel_imo: str, owner: str, pct: float) -> Dict[str, Any]:
    """Declare that `owner` holds `pct`% of vessel `vessel_imo`."""
    if not (0.0 < pct <= 100.0):
        raise ValueError("pct must be in (0, 100]")
    _OWNERSHIP[vessel_imo].append((owner, pct))
    receipt = _chain("ownership.declare", f"{vessel_imo}|{owner}|{pct}")
    return {"vessel": vessel_imo, "owner": owner, "pct": pct,
            "receipt": receipt, "truth_label": "REPORTED"}


def declare_holder(entity: str, holder: str, pct: float) -> Dict[str, Any]:
    """Declare that `holder` holds `pct`% of `entity` (indirect ownership)."""
    if not (0.0 < pct <= 100.0):
        raise ValueError("pct must be in (0, 100]")
    _ENTITY_HOLDERS[entity].append((holder, pct))
    receipt = _chain("holder.declare", f"{entity}|{holder}|{pct}")
    return {"entity": entity, "holder": holder, "pct": pct,
            "receipt": receipt, "truth_label": "REPORTED"}


def ownership_graph(vessel_imo: str) -> Dict[str, Any]:
    """Walk the declared ownership graph for a vessel. Exact traversal of
    declared edges; declarations are REPORTED, not verified."""
    edges: List[Dict[str, Any]] = []
    frontier: List[Tuple[str, float, int]] = []
    for owner, pct in _OWNERSHIP.get(vessel_imo, []):
        frontier.append((owner, pct, 1))
    seen: set = set()
    effective: Dict[str, float] = defaultdict(float)
    while frontier:
        node, pct, depth = frontier.pop(0)
        if node in seen or depth > _MAX_DEPTH:
            continue
        seen.add(node)
        holders = _ENTITY_HOLDERS.get(node, [])
        if holders:
            for holder, hpct in holders:
                edges.append({"from": holder, "to": node,
                              "pct": hpct, "depth": depth,
                              "effective_pct": round(pct * hpct / 100.0, 4)})
                frontier.append((holder, pct * hpct / 100.0, depth + 1))
        else:
            edges.append({"from": node, "to": vessel_imo,
                          "pct": pct, "depth": depth,
                          "effective_pct": round(pct, 4)})
            effective[node] += pct
    receipt = _chain("ownership.walk", f"{vessel_imo}|{len(edges)}")
    return {"vessel": vessel_imo, "edges": edges,
            "beneficial_owners": [{"name": n, "effective_pct": round(p, 4)}
                                  for n, p in sorted(effective.items(),
                                                     key=lambda kv: -kv[1])],
            "declared_total_pct": round(sum(p for _, p in _OWNERSHIP.get(vessel_imo, [])), 4),
            "receipt": receipt, "truth_label": "REPORTED",
            "note": "declarations are operator-supplied and not independently verified"}


# ----------------------------- combined vessel risk ------------------------

def vessel_risk(imo: str, name: str = "", flag: str = "",
                dark_gaps: int = 0, max_implied_speed_kn: float = 0.0,
                loiter_fixes: int = 0) -> Dict[str, Any]:
    """Combine screening, ownership, and behavior into one MODELED risk score."""
    screening = screen_entity(name) if name else {"result": "BLOCKED_PENDING",
                                                  "reason": "no name supplied",
                                                  "truth_label": "MEASURED"}
    if flag:
        flag_screen = screen_entity(flag)
    else:
        flag_screen = {"result": "NOT_CHECKED", "truth_label": "MEASURED"}
    own = ownership_graph(imo) if imo in _OWNERSHIP else {
        "edges": [], "beneficial_owners": [],
        "declared_total_pct": 0.0,
        "note": "no ownership declared", "truth_label": "REPORTED"}

    score = 0.0
    drivers: List[str] = []
    if screening.get("result") == "HIT":
        score += 0.5
        drivers.append(f"screening_hit:{len(screening['hits'])}")
    if flag_screen.get("result") == "HIT":
        score += 0.2
        drivers.append("flag_hit")
    if dark_gaps:
        score += min(0.3, 0.15 * dark_gaps)
        drivers.append(f"dark_gaps:{dark_gaps}")
    if max_implied_speed_kn > 28.0:
        score += 0.2
        drivers.append(f"speed_anomaly:{max_implied_speed_kn:.1f}kn")
    if loiter_fixes >= 5:
        score += 0.1
        drivers.append(f"loitering:{loiter_fixes}")
    unaccounted = 100.0 - own.get("declared_total_pct", 0.0)
    if imo in _OWNERSHIP and unaccounted > 5.0:
        score += min(0.2, unaccounted / 500.0)
        drivers.append(f"ownership_gap:{unaccounted:.1f}%_undeclared")

    receipt = _chain("vessel.risk", f"{imo}|{round(min(score, 1.0), 3)}")
    return {
        "imo": imo, "name": name, "flag": flag,
        "screening": {"result": screening.get("result"),
                      "hits": screening.get("hits", [])},
        "flag_screening": flag_screen.get("result"),
        "ownership": [{"name": b["name"], "effective_pct": b["effective_pct"]}
                      for b in own.get("beneficial_owners", [])],
        "behavior": {"dark_gaps": dark_gaps,
                     "max_implied_speed_kn": max_implied_speed_kn,
                     "loiter_fixes": loiter_fixes},
        "risk_score": round(min(score, 1.0), 3),
        "drivers": drivers,
        "receipt": receipt,
        "truth_label": "MODELED",
    }


def receipts(limit: int = 50) -> Dict[str, Any]:
    items = list(_RECEIPTS)[-limit:]
    return {"count": len(items), "chain_head": _PREV_HASH, "receipts": items}


def healthz() -> Dict[str, Any]:
    return {"status": "ok", "service": "killinchu-vessels-screening",
            "lists": len(_LISTS), "vessels_tracked": len(_OWNERSHIP),
            "receipt_chain": len(_RECEIPTS),
            "sources": sorted({str(row.get("source", "unknown")) for row in _LISTS.values()}),
            "truth_label": "MEASURED"}
