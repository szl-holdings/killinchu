# SPDX-License-Identifier: Apache-2.0
"""Dependency contract for the shipped killinchu image (stdlib only).

The image is ``Dockerfile``: per-file COPY of the runtime modules plus pinned
``RUN pip install`` lines, started with ``python serve.py``. requirements.txt is
deliberately partial (see its header), so the Dockerfile is the runtime
manifest here and every COPY'd module's import graph is checked against it:

1. serve.py's eager import closure (module level, unguarded) needs only the
   stdlib, shipped local modules and hard-pinned or transitive packages.
2. Every third-party name imported by shipped code is declared: a Dockerfile
   pin, a transitive of a hard pin, a named OPTIONAL package, or a module that
   lives in another szl-holdings repository (CROSS_REPO).
3. Every local module that shipped code imports, guarded or not, is shipped,
   unless EXCLUDED_FROM_IMAGE records why it is deliberately left out. A guarded
   import of an unshipped file degrades silently in the image (the
   "merged-but-not-live" failure). .github/scripts/copy_completeness.py checks
   root-level modules only; this check also covers package submodules and
   sys.path-vendored packages.
4. The registries below stay truthful, so they cannot hide a new gap.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = "Dockerfile"
ENTRYPOINT = "serve.py"
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist"}

# Import name -> distribution pinned in the Dockerfile (hard or `|| true`).
# Import names were measured with importlib.metadata.packages_distributions()
# in a venv built from the Dockerfile RUN lines (Python 3.14.7).
DOCKER_IMPORTS = {
    "cryptography": "cryptography", "defusedxml": "defusedxml", "dilithium_py": "dilithium-py",
    "fastapi": "fastapi", "httpx": "httpx", "huggingface_hub": "huggingface-hub", "lmdb": "lmdb",
    "networkx": "networkx", "numpy": "numpy", "psycopg": "psycopg", "pyModeS": "pymodes",
    "pymavlink": "pymavlink", "scipy": "scipy", "sgp4": "sgp4", "slowapi": "slowapi",
    "sqlite_vss": "sqlite-vss", "starlette": "starlette", "uvicorn": "uvicorn",
    "websocket": "websocket-client", "yaml": "pyyaml",
}
# Installed in the image only as dependencies of these hard pins.
TRANSITIVE = {"anyio": ("starlette", "httpx"), "pydantic": ("fastapi",)}
# Not installed in the image. Each use must degrade: a guarded import, or a
# module that is reached only through a guarded import.
OPTIONAL = {
    "faiss": "faiss-cpu; vector recall, guarded",
    "llama_cpp": "llama-cpp-python; local GGUF inference, guarded",
    "opentelemetry": "opentelemetry-api; tracing, guarded (vendored vsp_otel is used)",
    "oqs": "liboqs-python (NOT the unrelated PyPI project 'oqs'); dilithium-py is the pinned ML-DSA fallback",
    "sentence_transformers": "sentence-transformers; embeddings, guarded",
    "sigstore": "sigstore; szl_formulas.verify_dsse_real raises when absent (fail-closed)",
    "sklearn": "scikit-learn; szl_mosaic_core only, killinchu_mosaic falls back to its numpy bank",
    "szl_receipt": "szl-receipt (git pin in requirements.txt); the image uses the vendored copy",
    "torch": "torch; szl_mosaic_core autoencoder, numpy fallback",
    "z3": "z3-solver; szl_qhawaq reports the cross-check as ROADMAP when absent",
}
# Shipped modules that cannot import in the image (they hard-import an OPTIONAL name).
UNIMPORTABLE_IN_IMAGE = {"szl_mosaic_core.py": "sklearn"}
# Modules provided by other szl-holdings repositories or the host; absent from this tree.
CROSS_REPO = frozenset(["a11oy_active_flux_router", "a11oy_code_orchestrator", "a11oy_signing_key", "a11oy_state_store", "a11oy_vertical_feeds", "ayllu", "gdw_durable_source", "killinchu_drone_3d_health", "second_brain", "szl3d_holographic", "szl_backend_hardening", "szl_brain_api", "szl_corpus_publish", "szl_demo", "szl_energy_live", "szl_energy_operator", "szl_energy_provenance", "szl_jack", "szl_khipu", "szl_ltc_dynamics", "szl_model_harness", "szl_pnt_mesh", "szl_router", "szl_router_client", "szl_sgh_scheduler", "szl_sidebar", "szl_substrate", "szl_thesis_about", "szl_uds_pages", "szl_wire"])
# Repository modules that shipped code imports (guarded) but that are deliberately
# kept out of the image. Each entry must exist in the repo, stay un-COPY'd and still
# be imported by shipped code, so an exclusion cannot go stale silently.
EXCLUDED_FROM_IMAGE = {
    "szl_connectors/data_sources/maritime_overlays.py": (
        "owner decision 2026-11-03: its pirate-attack hot zones are SAMPLE-labelled and "
        "shipping it would change live pirate_zone risk scores; killinchu_maritime_risk "
        "falls back to no hot zones (pirate_zone risk 0.0)"
    ),
}
# Top-level directories that shipped code puts on sys.path before importing from
# them (serve.py: ./src for the killinchu edge package; killinchu_flow_compartments:
# ./vendor_yarqa for the vendored yarqa engine).
SYS_PATH_DIRS = ("src", "vendor_yarqa")
IMPORT_EXC = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}
EXTRA_STDLIB = {"annotationlib", "compression", "tomllib"}


def _stdlib() -> set[str]:
    return set(getattr(sys, "stdlib_module_names", ())) | EXTRA_STDLIB | {"__future__"}


def _logical(text: str):
    buf = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#") or (not buf and not stripped):
            continue
        if raw.rstrip().endswith("\\"):
            buf += raw.rstrip()[:-1] + " "
            continue
        yield (buf + raw).strip()
        buf = ""
    if buf.strip():
        yield buf.strip()


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def dockerfile_pins(text: str) -> tuple[dict[str, str], dict[str, str]]:
    hard: dict[str, str] = {}
    soft: dict[str, str] = {}
    for ins in _logical(text):
        if not ins.upper().startswith("RUN ") or "pip install" not in ins:
            continue
        bucket = soft if re.search(r"\|\|\s*true\b", ins) else hard
        for spec in re.findall(r'"([^"]+)"', ins.split("||")[0]):
            m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", spec)
            if m:
                bucket[_norm(m.group(0))] = spec
    return hard, soft


def copy_ops(text: str) -> list[tuple[list[str], str]]:
    ops = []
    for ins in _logical(text):
        if not ins.upper().startswith("COPY "):
            continue
        body = ins[5:].strip()
        flags = []
        while body.startswith("--"):
            flag, _, body = body.partition(" ")
            flags.append(flag)
            body = body.strip()
        if any(f.startswith("--from") for f in flags):
            continue
        parts = json.loads(body) if body.startswith("[") else body.split()
        ops.append((parts[:-1], parts[-1]))
    return ops


def shipped_files(text: str, root: Path) -> tuple[set[str], list[str]]:
    """Repo-relative .py files the COPY instructions put in the image, plus any renames."""
    shipped: set[str] = set()
    renamed: list[str] = []
    for srcs, dst in copy_ops(text):
        d = dst.removeprefix("./")
        dnorm = d.rstrip("/")
        for src in srcs:
            s = src.rstrip("/")
            path = root / s
            if path.is_dir():
                if dnorm != s:
                    renamed.append(f"{src} -> {dst}")
                shipped.update(p.relative_to(root).as_posix() for p in path.rglob("*.py"))
            elif path.is_file() and s.endswith(".py"):
                if dnorm in ("", "."):
                    target = Path(s).name
                elif d.endswith("/"):
                    target = dnorm + "/" + Path(s).name
                else:
                    target = dnorm
                if target != s:
                    renamed.append(f"{src} -> {dst}")
                shipped.add(s)
    return shipped, renamed


class ImportScan:
    """Module imports with an edge class: hard, guarded, lazy, conditional, main, type_checking."""

    def __init__(self, tree: ast.Module):
        self.sites: list[tuple[int, str, int, tuple[str, ...], str]] = []
        self.literals: set[str] = set()
        self.syspath = False
        self._body(tree.body, "module", None, None)

    @staticmethod
    def _catches_import(handler: ast.ExceptHandler) -> bool:
        if handler.type is None:
            return True
        elts = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        names = {e.id if isinstance(e, ast.Name) else getattr(e, "attr", None) for e in elts}
        return bool(names & IMPORT_EXC)

    def _edge(self, scope, guard, cond) -> str:
        if cond in ("type_checking", "main"):
            return cond
        if guard:
            return "guarded"
        if scope == "function":
            return "lazy"
        return "conditional" if cond else "hard"

    def _body(self, stmts, scope, guard, cond):
        for s in stmts:
            self._stmt(s, scope, guard, cond)

    def _stmt(self, s, scope, guard, cond):
        edge = self._edge(scope, guard, cond)
        if isinstance(s, ast.Import):
            for a in s.names:
                self.sites.append((s.lineno, a.name, 0, (), edge))
        elif isinstance(s, ast.ImportFrom):
            if s.module != "__future__":
                self.sites.append((s.lineno, s.module or "", s.level or 0, tuple(a.name for a in s.names), edge))
        elif isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._exprs(s.decorator_list + s.args.defaults, scope, guard, cond)
            self._body(s.body, "function", None, cond)
        elif isinstance(s, ast.ClassDef):
            self._exprs(s.decorator_list + s.bases, scope, guard, cond)
            self._body(s.body, scope, guard, cond)
        elif isinstance(s, ast.Try) or type(s).__name__ == "TryStar":
            g = "try" if any(self._catches_import(h) for h in s.handlers) else guard
            self._body(s.body, scope, g, cond)
            for h in s.handlers:
                self._body(h.body, scope, guard, cond)
            self._body(s.orelse, scope, guard, cond)
            self._body(s.finalbody, scope, guard, cond)
        elif isinstance(s, (ast.With, ast.AsyncWith)):
            g = guard
            for item in s.items:
                e = item.context_expr
                if (isinstance(e, ast.Call) and getattr(e.func, "id", getattr(e.func, "attr", None)) == "suppress"
                        and any(getattr(a, "id", getattr(a, "attr", None)) in IMPORT_EXC for a in e.args)):
                    g = "suppress"
                self._exprs([e], scope, guard, cond)
            self._body(s.body, scope, g, cond)
        elif isinstance(s, ast.If):
            self._exprs([s.test], scope, guard, cond)
            t = s.test
            if (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or getattr(t, "attr", None) == "TYPE_CHECKING":
                self._body(s.body, scope, guard, "type_checking")
            elif (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == "__name__"
                  and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in t.comparators)):
                self._body(s.body, scope, guard, "type_checking" if cond == "type_checking" else "main")
            else:
                self._body(s.body, scope, guard, cond or "if")
            self._body(s.orelse, scope, guard, cond or "if")
        elif isinstance(s, (ast.For, ast.AsyncFor, ast.While)):
            self._exprs([getattr(s, "iter", None) or getattr(s, "test", None)], scope, guard, cond)
            self._body(s.body + s.orelse, scope, guard, cond or "loop")
        elif type(s).__name__ == "Match":
            for case in s.cases:
                self._body(case.body, scope, guard, cond or "if")
        else:
            self._exprs([s], scope, guard, cond)

    def _exprs(self, nodes, scope, guard, cond):
        for n in nodes:
            if n is None:
                continue
            for sub in ast.walk(n):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    self.literals.add(sub.value)
                if isinstance(sub, ast.Attribute) and sub.attr in ("insert", "append") and \
                        isinstance(sub.value, ast.Attribute) and sub.value.attr == "path":
                    self.syspath = True
                if not isinstance(sub, ast.Call) or not sub.args:
                    continue
                fn = getattr(sub.func, "id", getattr(sub.func, "attr", None))
                a0 = sub.args[0]
                if fn in ("import_module", "__import__") and isinstance(a0, ast.Constant) \
                        and isinstance(a0.value, str) and not a0.value.startswith("."):
                    lam = any(isinstance(x, ast.Lambda) for x in ast.walk(n))
                    self.sites.append((sub.lineno, a0.value, 0, (),
                                       self._edge("function" if lam else scope, guard, cond)))


def _repo_py(root: Path) -> list[str]:
    out = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root)
        if not (set(rel.parts) & SKIP_DIRS):
            out.append(rel.as_posix())
    return sorted(out)


def _modname(path: str) -> str:
    parts = path[:-3].split("/")
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


class Contract:
    def __init__(self, root: Path = ROOT):
        self.root = root
        text = (root / DOCKERFILE).read_text(encoding="utf-8")
        self.hard, self.soft = dockerfile_pins(text)
        self.shipped, self.renamed = shipped_files(text, root)
        self.files = _repo_py(root)
        self.fileset = set(self.files)
        self.index = {}
        for p in self.files:
            self.index.setdefault(_modname(p), p)
        self.dirs = {".".join(p.split("/")[:i]) for p in self.files for i in range(1, p.count("/") + 1)}
        self.local_tops = {m.split(".")[0] for m in self.index} | {d.split(".")[0] for d in self.dirs}
        self.vendor = {}
        for vp in SYS_PATH_DIRS:
            for p in self.files:
                if p.startswith(vp + "/"):
                    self.vendor.setdefault(p[len(vp) + 1:].split("/")[0].removesuffix(".py"), vp)
        self.stdlib = _stdlib()
        self.scans = {p: ImportScan(ast.parse((root / p).read_bytes(), filename=p))
                      for p in sorted(self.shipped) if (root / p).is_file()}

    def resolve(self, path: str, mod: str, level: int, names: tuple[str, ...], vendor_ok: bool):
        """Return (kind, top, [local target files]); kind is local | stdlib | external."""
        if level:
            base = _modname(path).split(".")
            if not path.endswith("__init__.py"):
                base = base[:-1]
            base = base[:len(base) - (level - 1)] if level > 1 else base
            mod = ".".join(base + ([mod] if mod else []))
            prefix = ""
        else:
            top = mod.split(".")[0]
            if top in self.local_tops:
                prefix = ""
            elif vendor_ok and top in self.vendor:
                prefix = self.vendor[top] + "/"
            elif top in self.stdlib:
                return "stdlib", top, []
            else:
                return "external", top, []
        parts = mod.split(".") if mod else []
        targets = []
        for i in range(1, len(parts) + 1):
            dotted = ".".join(parts[:i])
            for cand in (prefix + dotted.replace(".", "/") + ".py", prefix + dotted.replace(".", "/") + "/__init__.py"):
                if cand in self.fileset:
                    targets.append(cand)
        for n in names:
            dotted = (mod + "." + n) if mod else n
            for cand in (prefix + dotted.replace(".", "/") + ".py", prefix + dotted.replace(".", "/") + "/__init__.py"):
                if cand in self.fileset:
                    targets.append(cand)
        return "local", (parts[0] if parts else ""), sorted(set(targets))

    def edges(self, path: str):
        scan = self.scans[path]
        vendor_ok = scan.syspath and any(v in scan.literals for v in SYS_PATH_DIRS)
        for line, mod, level, names, edge in scan.sites:
            if edge in ("type_checking",) or (edge == "main" and path != ENTRYPOINT):
                continue
            kind, top, targets = self.resolve(path, mod, level, names, vendor_ok)
            yield line, mod, edge, kind, top, targets

    def eager_closure(self) -> set[str]:
        seen, todo = {ENTRYPOINT}, [ENTRYPOINT]
        while todo:
            f = todo.pop()
            if f not in self.scans:
                continue
            for _, _, edge, kind, _, targets in self.edges(f):
                if edge == "hard" and kind == "local":
                    for t in targets:
                        if t not in seen:
                            seen.add(t)
                            todo.append(t)
        return seen


_CONTRACT = None


def contract() -> Contract:
    global _CONTRACT
    if _CONTRACT is None:
        _CONTRACT = Contract()
    return _CONTRACT


def test_classifier_negative_controls():
    src = ("import os\nimport requests\ntry:\n    import yaml\nexcept ImportError:\n    yaml = None\n"
           "try:\n    def f():\n        import networkx\nexcept ImportError:\n    pass\n"
           "try:\n    import numpy\nexcept RuntimeError:\n    pass\nif TYPE_CHECKING:\n    import pandas\n"
           "if __name__ == '__main__':\n    import click\n")
    got = {mod: edge for _, mod, _, _, edge in ImportScan(ast.parse(src)).sites}
    assert got == {"os": "hard", "requests": "hard", "yaml": "guarded", "networkx": "lazy",
                   "numpy": "hard", "pandas": "type_checking", "click": "main"}, got


def test_image_layout_matches_repo_layout():
    c = contract()
    assert ENTRYPOINT in c.shipped, "serve.py is not COPY'd"
    assert not c.renamed, f"COPY renames Python sources, so repo imports != image imports: {c.renamed}"


def test_entrypoint_eager_closure_is_installed():
    c = contract()
    problems = []
    for f in sorted(c.eager_closure()):
        if f not in c.shipped:
            problems.append(f"{f}: imported unguarded at module level by the serve.py closure but not COPY'd")
            continue
        for line, mod, edge, kind, top, _ in c.edges(f):
            if kind != "external" or edge not in ("hard", "main"):
                continue
            dist = DOCKER_IMPORTS.get(top)
            if dist in c.hard or any(p in c.hard for p in TRANSITIVE.get(top, ())):
                continue
            problems.append(f"{f}:{line} import {mod!r} needs a hard (no '|| true') Dockerfile pin")
    assert not problems, "\n".join(problems)


def test_every_third_party_import_in_shipped_code_is_declared():
    c = contract()
    declared = set(DOCKER_IMPORTS) | set(TRANSITIVE) | set(OPTIONAL) | CROSS_REPO
    problems = [f"{f}:{line} import {mod!r} ({edge}) is not declared: add a Dockerfile pin, "
                f"or register it in OPTIONAL / CROSS_REPO with a reason"
                for f in sorted(c.scans) for line, mod, edge, kind, top, _ in c.edges(f)
                if kind == "external" and top not in declared]
    assert not problems, "\n".join(problems)


def test_every_local_import_in_shipped_code_is_shipped():
    c = contract()
    problems = []
    for f in sorted(c.scans):
        for line, mod, edge, kind, top, targets in c.edges(f):
            for t in targets:
                if kind == "local" and t not in c.shipped and t not in EXCLUDED_FROM_IMAGE:
                    problems.append(f"{f}:{line} imports {mod or '.'!r} ({edge}) -> {t} exists in the repo "
                                    f"but is not COPY'd, so the image silently takes the fallback path")
    assert not problems, "\n".join(sorted(set(problems)))


def test_unimportable_shipped_modules_are_registered():
    c = contract()
    found = {}
    for f in sorted(c.scans):
        for line, mod, edge, kind, top, _ in c.edges(f):
            if kind == "external" and edge == "hard" and (top in OPTIONAL or top in CROSS_REPO):
                found.setdefault(f, top)
    assert found == UNIMPORTABLE_IN_IMAGE, f"measured {found} != registered {UNIMPORTABLE_IN_IMAGE}"
    assert not set(found) & c.eager_closure(), "serve.py would crash: an unimportable module is in its eager closure"


def test_registries_are_truthful():
    c = contract()
    pinned = set(c.hard) | set(c.soft)
    problems = [f"DOCKER_IMPORTS[{k!r}] = {v!r} is not pinned in {DOCKERFILE}"
                for k, v in DOCKER_IMPORTS.items() if v not in pinned]
    problems += [f"TRANSITIVE[{k!r}] parent {p!r} is not a hard pin"
                 for k, ps in TRANSITIVE.items() for p in ps if p not in c.hard]
    used = {top for f in c.scans for _, _, _, kind, top, _ in c.edges(f) if kind == "external"}
    problems += [f"OPTIONAL/CROSS_REPO entry {n!r} is no longer imported by shipped code; remove it"
                 for n in sorted((set(OPTIONAL) | CROSS_REPO) - used)]
    problems += [f"CROSS_REPO entry {n!r} now exists in this repository; ship it or drop the entry"
                 for n in sorted(CROSS_REPO & c.local_tops)]
    problems += [f"top-level vendor directory {d!r} is not listed in SYS_PATH_DIRS"
                 for d in sorted({p.split("/")[0] for p in c.files if p.startswith("vendor")} - set(SYS_PATH_DIRS))]
    problems += [f"SYS_PATH_DIRS entry {d!r} is not a directory of this repository"
                 for d in SYS_PATH_DIRS if not (c.root / d).is_dir()]
    imported_locals = {t for f in c.scans for _, _, _, kind, _, targets in c.edges(f)
                       if kind == "local" for t in targets}
    for path in sorted(EXCLUDED_FROM_IMAGE):
        if path not in c.fileset:
            problems.append(f"EXCLUDED_FROM_IMAGE entry {path!r} no longer exists in the repository")
        elif path in c.shipped:
            problems.append(f"EXCLUDED_FROM_IMAGE entry {path!r} is now COPY'd; remove the exclusion "
                            "(and its reason) deliberately")
        elif path not in imported_locals:
            problems.append(f"EXCLUDED_FROM_IMAGE entry {path!r} is no longer imported by shipped code; remove it")
    assert not problems, "\n".join(problems)
