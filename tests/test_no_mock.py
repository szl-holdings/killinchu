# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
#
# NO-MOCK guard (doctrine: "HONESTY OVER CHECKLIST — no synthetic data, no
# fabricated signatures").  This meta-test statically scans the shipped
# killinchu source tree and FAILS the build if any forbidden mock/stub/fake/
# placeholder construct leaks into non-test code paths.  It also asserts that
# the runtime crypto + Λ are REAL (executed), not stubbed.
import ast
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC = os.path.join(REPO, "src", "killinchu")

# Forbidden substrings in PRODUCTION (non-test) source. Case-insensitive.
# We allow these tokens to APPEAR inside string literals/comments only when they
# are part of an explicit honesty disclaimer (e.g. "NO MOCK", "not a mock"),
# which we detect and exclude below.
FORBIDDEN = ("mock", "fake", "stub", "dummy", "placeholder", "todo", "fixme",
             "hard-coded signature", "return 0.42", "random.random")

# Phrases that legitimately contain a forbidden token as part of a *negation*
# / honesty statement — these are allowed.
ALLOW_NEGATIONS = (
    "no mock", "no mocks", "not a mock", "never a placeholder", "no placeholder",
    "no fabricat", "never fake", "no synthetic", "not random", "never random",
    "no shortcuts", "not stubbed", "never emit a placeholder/fake",
    "placeholder/fake signature", "never mock", "not mock",
)


def _production_py_files():
    files = []
    for root, _dirs, names in os.walk(SRC):
        for n in names:
            if n.endswith(".py"):
                files.append(os.path.join(root, n))
    return files


def _strip_allowed(line_lower: str) -> str:
    for ok in ALLOW_NEGATIONS:
        line_lower = line_lower.replace(ok, " ")
    return line_lower


def test_no_forbidden_tokens_in_production_source():
    offenders = []
    for path in _production_py_files():
        with open(path, encoding="utf-8") as f:
            for lineno, raw in enumerate(f, 1):
                low = _strip_allowed(raw.lower())
                for tok in FORBIDDEN:
                    if tok in low:
                        offenders.append(f"{os.path.relpath(path, REPO)}:{lineno}: "
                                         f"forbidden '{tok}' -> {raw.strip()}")
    assert not offenders, "MOCK/STUB leakage in production code:\n" + "\n".join(offenders)


def test_production_files_exist():
    expected = ["__init__.py", "lambda_calc.py", "dsse.py", "khipu.py", "edge.py"]
    for name in expected:
        assert os.path.exists(os.path.join(SRC, name)), f"missing {name}"


def test_no_unittest_mock_imports_in_production():
    bad = []
    for path in _production_py_files():
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if "mock" in a.name.lower():
                        bad.append(f"{path}: import {a.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").lower()
                if "mock" in mod or mod == "unittest.mock":
                    bad.append(f"{path}: from {node.module} import ...")
    assert not bad, "unittest.mock imported in production:\n" + "\n".join(bad)


def test_signature_is_real_not_constant():
    """Two different verdicts must produce two DIFFERENT real signatures, and a
    tampered payload must FAIL verification — proving the signer is real ECDSA,
    not a constant/mock."""
    import base64
    from src.killinchu.dsse import sign_verdict, verify_envelope, public_key_pem

    env_a = sign_verdict({"track": "A", "lambda_value": 0.91})
    env_b = sign_verdict({"track": "B", "lambda_value": 0.42})
    sig_a = env_a["signatures"][0]["sig"]
    sig_b = env_b["signatures"][0]["sig"]
    assert sig_a != sig_b, "signatures identical across distinct payloads => not real"

    pub = public_key_pem()
    assert verify_envelope(env_a, pub_pem=pub)["verified"] is True

    # Tamper the payload -> verification MUST fail (real crypto binds payload).
    tampered = dict(env_a)
    tampered["payload"] = base64.b64encode(b'{"track":"A","lambda_value":1.0}').decode()
    assert verify_envelope(tampered, pub_pem=pub)["verified"] is False


def test_lambda_is_computed_not_hardcoded():
    """Λ must respond to inputs: a clean axis vector and a degraded one must
    yield different Λ values (proves the aggregator runs)."""
    from src.killinchu.lambda_calc import compute_lambda
    clean = {k: 0.97 for k in (
        "soundness", "calibration", "robustness", "provenance", "consent",
        "reversibility", "transparency", "fairness", "containment", "attestation",
        "freshness", "authority", "auditability")}
    degraded = dict(clean)
    degraded["containment"] = 0.10
    v_clean = compute_lambda(clean, n_observations=64)
    v_deg = compute_lambda(degraded, n_observations=64)
    assert v_clean.lambda_value != v_deg.lambda_value
    assert v_deg.lambda_value < v_clean.lambda_value
