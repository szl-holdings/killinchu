#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the presentation extension without granting it the host's data access.

The existing product host is admitted by exact bytes, not a blanket networking
exception. Only the separately delimited presentation extension is subject to the
no-network/no-storage contract. Both remain in one existing script, so no second
navigation, product-state owner, or client runtime is installed.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST_SHA256 = "f6d13c4719079750c61f2eb77405aed28a668cf4bc4962c7751845a62f097d6b"
BOUNDARY = b"\n/*\n * SZL Public Experience v3.1\n"
FORBIDDEN_JS = ("fetch(", "XMLHttpRequest", "sendBeacon", "localStorage", "sessionStorage", "document.cookie")
REQUIRED_JS = ("__SZL_PUBLIC_EXPERIENCE_V3__", "szlPublicExperienceV3", "szlViewportTier", "visualViewport", "requestAnimationFrame")
REQUIRED_CSS = ("SZL Public Experience v3", "--szl-touch-target", "100dvh", "safe-area-inset", "overflow-x: clip", "max-width: 479px", "min-width: 768px", "min-width: 1440px", "min-width: 1920px", "min-width: 2560px", "prefers-reduced-motion", "prefers-contrast", "forced-colors", "@media print")


class ContractError(ValueError):
    """A candidate changes the admitted host or breaks the presentation contract."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def split_host(data: bytes) -> tuple[bytes, bytes]:
    if data.count(BOUNDARY) != 1:
        raise ContractError("one unambiguous presentation boundary is required")
    host, extension = data.split(BOUNDARY, 1)
    if sha256(host) != HOST_SHA256:
        raise ContractError("product host changed; review its authority separately")
    extension = BOUNDARY[1:] + extension
    text = extension.decode("utf-8")
    if any(value in text for value in FORBIDDEN_JS):
        raise ContractError("presentation extension contains prohibited client behavior")
    if any(value not in text for value in REQUIRED_JS):
        raise ContractError("presentation extension is missing a required contract")
    return host, extension


def validate_css(text: str) -> None:
    if any(value not in text for value in REQUIRED_CSS):
        raise ContractError("responsive stylesheet is missing a required contract")
    if any(value in text for value in ("@import", "cdn.", "unpkg.", "jsdelivr.")):
        raise ContractError("responsive stylesheet contains an external runtime asset")
    if text.count("{") != text.count("}"):
        raise ContractError("responsive stylesheet has unbalanced braces")


def main() -> int:
    script = ROOT / "static/truth-cop.js"
    css = ROOT / "static/szl-universal-frontend.css"
    source = ROOT / "design/szl-public-experience-v3.css"
    for path in (script, css, source):
        if path.is_symlink() or not path.is_file():
            raise ContractError("a regular source or managed asset is missing")
    host, extension = split_host(script.read_bytes())
    validate_css(css.read_text(encoding="utf-8"))
    subprocess.run(["node", "--check", str(script)], check=True, timeout=20)

    # Reuse the canonical generator and manifest validation, not a second writer.
    spec = importlib.util.spec_from_file_location("szl_host_frontend_generator", ROOT / "scripts/apply_hf_universal_frontend_v1.py")
    assert spec and spec.loader
    generator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = generator
    spec.loader.exec_module(generator)
    generator.validate()
    if css.read_bytes() != generator.UNIVERSAL_CSS.encode("utf-8"):
        raise ContractError("managed CSS differs from its canonical source composition")
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    if "truth-cop.js" not in html or 'data-szl-universal-frontend="v1"' not in html:
        raise ContractError("product entrypoint is not bound to both existing asset hosts")
    print(json.dumps({
        "schema": "szl.public-experience-host-contract/v1",
        "status": "PASS",
        "scope": "SOURCE_CONTRACT_ONLY",
        "host_sha256": sha256(host),
        "presentation_sha256": sha256(extension),
        "css_source_sha256": sha256(source.read_bytes()),
        "managed_css_sha256": sha256(css.read_bytes()),
        "production_acceptance": False,
        "provider_writes": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
