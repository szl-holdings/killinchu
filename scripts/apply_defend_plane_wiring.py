#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Wire the consolidated Killinchu Defend plane into every active build path.

This transaction is deliberately idempotent and fails closed when an expected
anchor moves.  It edits only the explicit runtime assembly, Docker manifests,
focused CI, deployment proof and the superseded redirect contract.  Running it
twice must produce no second diff.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        raise RuntimeError(f"required file is missing: {path}")
    return target.read_text(encoding="utf-8")


def write(path: str, value: str) -> bool:
    target = ROOT / path
    current = target.read_text(encoding="utf-8")
    if current == value:
        return False
    target.write_text(value, encoding="utf-8")
    print(f"UPDATED {path}")
    return True


def insert_after(path: str, *, anchor: str, payload: str, marker: str) -> bool:
    text = read(path)
    if marker in text:
        return False
    if text.count(anchor) != 1:
        raise RuntimeError(
            f"{path}: expected exactly one insertion anchor, observed {text.count(anchor)}"
        )
    return write(path, text.replace(anchor, anchor + payload, 1))


def insert_before(path: str, *, anchor: str, payload: str, marker: str) -> bool:
    text = read(path)
    if marker in text:
        return False
    if text.count(anchor) != 1:
        raise RuntimeError(
            f"{path}: expected exactly one insertion anchor, observed {text.count(anchor)}"
        )
    return write(path, text.replace(anchor, payload + anchor, 1))


SERVE_ANCHOR = (
    'app = FastAPI(title="Killinchu — Andean Drone Intelligence", version="1.0.0")\n'
)
SERVE_MARKER = "KILLINCHU_DEFEND_PLANE_V1"
SERVE_BLOCK = r'''

# KILLINCHU_DEFEND_PLANE_V1 — same-origin Aegis/Sentra consolidation.
# The module ports the bounded defensive-control contract from the exact source
# revision named by /api/defend/source.  It is registered before the SPA
# catch-all so /defend and /api/defend/* are real routes, not presentation-only
# links.  Failure is visible through deployment smoke probes; no silent fallback
# can satisfy those probes.
try:
    import killinchu_defend_plane as _killinchu_defend_plane

    _killinchu_defend_status = _killinchu_defend_plane.register(
        app,
        ns="killinchu",
    )
    print(
        f"[killinchu] Defend plane wired ({_killinchu_defend_status})",
        file=sys.stderr,
    )
except Exception as _killinchu_defend_error:
    _killinchu_defend_status = (
        f"defend-plane-not-wired:{_killinchu_defend_error!r}"
    )
    print(
        f"[killinchu] Defend plane NOT mounted "
        f"({_killinchu_defend_error!r})",
        file=sys.stderr,
    )
'''

DOCKER_ANCHOR = "# Shared Spaces modules (Dev2+3) — canonical handoffs + isolated-origin tiles.\n"
DOCKER_MARKER = "COPY killinchu_defend_plane.py ./killinchu_defend_plane.py"
DOCKER_BLOCK = (
    "# Consolidated Aegis/Sentra capability plane — real same-origin UI, API, "
    "state and receipts.\n"
    "COPY killinchu_defend_plane.py ./killinchu_defend_plane.py\n"
)

PREPARE_JOB = r'''  prepare-defend-secret:
    name: Preserve or create the write-only Defend receipt signer
    runs-on: ubuntu-latest
    timeout-minutes: 8
    env:
      HF_TOKEN: ${{ secrets.HF_ORG_TOKEN || secrets.HF_TOKEN }}
    steps:
      - name: Harden runner
        uses: step-security/harden-runner@05e31511f85b41b11d1cf0ef85d0992719546e2c # v2.21.0
        with:
          egress-policy: audit

      - name: Set up Python
        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.12.10"

      - name: Install pinned Hugging Face secret-metadata client
        run: python -m pip install --disable-pip-version-check --no-cache-dir "huggingface_hub==1.23.0"

      - name: Preserve the signer or create it exactly once
        shell: bash
        run: |
          set -euo pipefail
          test -n "${HF_TOKEN:-}" || { echo "::error::Hugging Face writer credential is unavailable"; exit 2; }
          echo "::add-mask::$HF_TOKEN"
          python - <<'PY'
          import os
          import secrets
          from typing import Any

          from huggingface_hub import HfApi

          SPACE = "SZLHOLDINGS/killinchu"
          KEY = "KILLINCHU_DEFEND_SIGNING_KEY"
          api = HfApi(token=os.environ["HF_TOKEN"])
          api.auth_check(repo_id=SPACE, repo_type="space", write=True)
          metadata: Any = api.get_space_secrets(SPACE)
          if isinstance(metadata, dict):
              names = set(metadata)
          elif isinstance(metadata, list):
              names = {
                  str(
                      item.get("key")
                      if isinstance(item, dict)
                      else getattr(item, "key", item)
                  )
                  for item in metadata
              }
          else:
              raise SystemExit("Space secret metadata response has an unexpected shape")
          if KEY in names:
              print(f"{KEY} exists; preserving its write-only value.")
          else:
              api.add_space_secret(
                  repo_id=SPACE,
                  key=KEY,
                  value=secrets.token_hex(32),
                  description=(
                      "Persistent HMAC key for Killinchu Defend receipt chains; "
                      "generated once by governed CI and never printed."
                  ),
              )
              print(f"{KEY} created; its value was never printed or written to disk.")
          PY

'''

CI_JOB = r'''  defend-plane:
    name: Consolidated Defend plane contract
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Harden runner
        uses: step-security/harden-runner@05e31511f85b41b11d1cf0ef85d0992719546e2c # v2.21.0
        with:
          egress-policy: audit

      - name: Checkout exact source
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: ${{ github.sha }}
          persist-credentials: false

      - name: Set up Python
        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.12.10"

      - name: Install the exact focused test closure
        run: |
          python -m pip install --disable-pip-version-check --no-cache-dir \
            "fastapi==0.137.2" "starlette==1.3.1" "httpx==0.28.1" \
            -r requirements-test.txt
          python -m pip check

      - name: Compile and prove the bounded workflow
        run: |
          python -m py_compile killinchu_defend_plane.py
          python -m pytest -q \
            tests/test_killinchu_defend_plane.py \
            tests/test_resilience_route_convergence.py

      - name: Prove explicit image and runtime assembly
        shell: bash
        run: |
          set -euo pipefail
          grep -Fq 'COPY killinchu_defend_plane.py ./killinchu_defend_plane.py' Dockerfile
          grep -Fq 'KILLINCHU_DEFEND_PLANE_V1' serve.py
          grep -Fq '/api/defend/status' .github/workflows/hf-sync.yml

'''

ROUTE_TEST = '''"""Contract tests for Killinchu's single cyber-resilience public surface."""
from __future__ import annotations

import killinchu_nav_wireup as routes


EXPECTED_REDIRECTS = {
    "/vessels": "/elite/maritime",
    "/maritime": "/elite/maritime",
    "/airspace": "/elite#cuas_lab",
}


def test_retired_mission_pack_names_resolve_same_origin_inside_killinchu() -> None:
    for source, target in EXPECTED_REDIRECTS.items():
        assert routes._BARE_SURFACE_REDIRECTS[source] == target
        assert source.startswith("/")
        assert target.startswith("/")
        assert "://" not in target


def test_defend_and_resilience_are_real_routes_not_presentation_redirects() -> None:
    assert "/resilience" not in routes._BARE_SURFACE_REDIRECTS
    assert "/defend" not in routes._BARE_SURFACE_REDIRECTS
    assert "/immune" not in routes._BARE_SURFACE_REDIRECTS


def test_legacy_space_origins_are_not_runtime_dependencies() -> None:
    source = open(routes.__file__, encoding="utf-8").read()
    for legacy_origin in (
        "szlholdings-vessels.hf.space",
        "szlholdings-sentra.hf.space",
        "szlholdings-immune.hf.space",
        "szlholdings-aegis-assurance.hf.space",
    ):
        assert legacy_origin not in source
'''


def patch_runtime_assembly() -> int:
    changed = 0
    for path in ("serve.py", "deploy/space/serve.py"):
        changed += insert_after(
            path,
            anchor=SERVE_ANCHOR,
            payload=SERVE_BLOCK,
            marker=SERVE_MARKER,
        )
    for path in ("Dockerfile", "deploy/space/Dockerfile"):
        changed += insert_before(
            path,
            anchor=DOCKER_ANCHOR,
            payload=DOCKER_BLOCK,
            marker=DOCKER_MARKER,
        )
    return changed


def patch_redirect_contract() -> int:
    changed = 0
    path = "killinchu_nav_wireup.py"
    text = read(path)
    obsolete = '    "/resilience": "/elite",\n'
    if obsolete in text:
        text = text.replace(obsolete, "", 1)
        changed += write(path, text)
    elif '"/resilience"' in text.split("_BARE_SURFACE_REDIRECTS", 1)[1].split("}", 1)[0]:
        raise RuntimeError("resilience redirect changed shape; refusing an ambiguous edit")
    changed += write("tests/test_resilience_route_convergence.py", ROUTE_TEST)
    return changed


def patch_deployment() -> int:
    path = ".github/workflows/hf-sync.yml"
    text = read(path)
    if "  prepare-defend-secret:\n" not in text:
        anchor = "jobs:\n  deploy:\n"
        if text.count(anchor) != 1:
            raise RuntimeError("hf-sync deploy-job anchor moved")
        text = text.replace(anchor, "jobs:\n" + PREPARE_JOB + "  deploy:\n", 1)
    if "    needs: prepare-defend-secret\n" not in text:
        anchor = "  deploy:\n    name: Deploy, source-bind, and attest exact surface\n"
        if text.count(anchor) != 1:
            raise RuntimeError("hf-sync deploy-name anchor moved")
        text = text.replace(
            anchor,
            anchor + "    needs: prepare-defend-secret\n",
            1,
        )
    if '"/api/defend/status"' not in text:
        old = (
            "      smoke-paths: '[\"/\",\"/api/killinchu/healthz\","
            "\"/api/build-info\",\"/console\","
            "\"/api/killinchu/v1/code/capabilities\","
            "\"/static/analyst.html\","
            "\"/api/killinchu/v1/defensive-intake/tools\"]'\n"
        )
        new = (
            "      smoke-paths: '[\"/\",\"/api/killinchu/healthz\","
            "\"/api/build-info\",\"/console\",\"/defend\","
            "\"/resilience\",\"/api/defend/status\","
            "\"/api/defend/source\","
            "\"/api/killinchu/v1/code/capabilities\","
            "\"/static/analyst.html\","
            "\"/api/killinchu/v1/defensive-intake/tools\"]'\n"
        )
        if old not in text:
            raise RuntimeError("hf-sync smoke-path contract moved")
        text = text.replace(old, new, 1)
    return int(write(path, text))


def patch_ci() -> int:
    path = ".github/workflows/ci.yml"
    text = read(path)
    if "  defend-plane:\n" in text:
        return 0
    anchor = "jobs:\n  docs:\n"
    if text.count(anchor) != 1:
        raise RuntimeError("CI jobs anchor moved")
    return int(write(path, text.replace(anchor, "jobs:\n" + CI_JOB + "  docs:\n", 1)))


def main() -> int:
    changed = 0
    changed += patch_runtime_assembly()
    changed += patch_redirect_contract()
    changed += patch_deployment()
    changed += patch_ci()

    # Post-conditions are stronger than merely observing a diff.
    requirements = {
        "serve.py": (SERVE_MARKER,),
        "deploy/space/serve.py": (SERVE_MARKER,),
        "Dockerfile": (DOCKER_MARKER,),
        "deploy/space/Dockerfile": (DOCKER_MARKER,),
        ".github/workflows/hf-sync.yml": (
            "prepare-defend-secret:",
            "needs: prepare-defend-secret",
            "/api/defend/status",
        ),
        ".github/workflows/ci.yml": ("defend-plane:",),
    }
    for path, markers in requirements.items():
        text = read(path)
        for marker in markers:
            if marker not in text:
                raise RuntimeError(f"post-condition missing in {path}: {marker}")
    if '"/resilience": "/elite"' in read("killinchu_nav_wireup.py"):
        raise RuntimeError("obsolete resilience redirect survived the transaction")

    print(f"DEFEND WIRING COMPLETE changed_files={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
