# SPDX-License-Identifier: Apache-2.0
"""Network-free regression tests for the actual source-native presentation host."""
from __future__ import annotations
import importlib.util
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("public_experience_host", ROOT / "scripts/verify_public_experience_host.py")
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
DATA = (ROOT / "static/truth-cop.js").read_bytes()
CSS = (ROOT / "static/szl-universal-frontend.css").read_text()


def test_actual_host_and_presentation_are_separately_verified():
    host, extension = M.split_host(DATA)
    assert b'fetch(ENDPOINT,' in host
    assert b'"/api/killinchu/v1/threats/active"' in host
    assert b'UNAVAILABLE' in host and b'TRAINING MODE' in host
    assert b'window.KillinchuTruthCOP' in host
    assert M.sha256(host) == M.HOST_SHA256
    assert b'fetch(' not in extension


def test_changed_product_host_is_not_granted_a_network_exception():
    with pytest.raises(M.ContractError, match="host changed"):
        M.split_host(DATA.replace(b'/api/killinchu/v1/threats/active', b'https://other.invalid', 1))


def test_product_host_cannot_be_removed_to_make_presentation_checks_pass():
    with pytest.raises(M.ContractError, match="host changed"):
        M.split_host(M.BOUNDARY + DATA.split(M.BOUNDARY, 1)[1])


@pytest.mark.parametrize('addition', M.FORBIDDEN_JS)
def test_presentation_cannot_inherit_product_network_or_storage(addition):
    with pytest.raises(M.ContractError, match="prohibited client behavior"):
        M.split_host(DATA + ('\n' + addition).encode())


def test_duplicate_boundary_never_hides_code_from_validation():
    with pytest.raises(M.ContractError, match="unambiguous"):
        M.split_host(DATA + M.BOUNDARY)


def test_absent_boundary_is_rejected():
    with pytest.raises(M.ContractError, match="unambiguous"):
        M.split_host(DATA.replace(M.BOUNDARY, b'\n/* changed boundary\n'))


@pytest.mark.parametrize('marker', M.REQUIRED_JS)
def test_required_presentation_contracts_are_not_silently_removed(marker):
    host, extension = DATA.split(M.BOUNDARY, 1)
    with pytest.raises(M.ContractError, match="missing a required"):
        M.split_host(host + M.BOUNDARY + extension.replace(marker.encode(), b'changed_marker'))


def test_actual_stylesheet_preserves_responsive_contract():
    M.validate_css(CSS)


@pytest.mark.parametrize('token', ('@import', 'cdn.', 'unpkg.', 'jsdelivr.'))
def test_external_stylesheet_dependencies_are_rejected(token):
    with pytest.raises(M.ContractError, match="external"):
        M.validate_css(CSS + token)


def test_css_brace_damage_is_rejected():
    with pytest.raises(M.ContractError, match="unbalanced"):
        M.validate_css(CSS + '{')


def test_entire_host_including_tail_is_valid_javascript():
    subprocess.run(['node', '--check', str(ROOT / 'static/truth-cop.js')], check=True, timeout=20)


def test_native_regeneration_is_idempotent_and_keeps_v3():
    paths = [ROOT / p for p in ('README.md', 'static/index.html', 'static/szl-universal-frontend.css', 'static/truth-cop.js', 'docs/hf-universal-frontend-v1.json', 'design/szl-public-experience-v3.css')]
    before = {p: p.read_bytes() for p in paths}
    for _ in range(2):
        subprocess.run([sys.executable, str(ROOT / 'scripts/apply_hf_universal_frontend_v1.py'), '--apply'], check=True, capture_output=True, timeout=20)
        assert {p: p.read_bytes() for p in paths} == before
    subprocess.run([sys.executable, str(ROOT / 'scripts/verify_public_experience_host.py')], check=True, capture_output=True, timeout=20)
