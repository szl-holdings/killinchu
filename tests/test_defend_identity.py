# SPDX-License-Identifier: Apache-2.0
"""Generated signing keys exercise the offline identity seam; no live provider."""
from __future__ import annotations

import dataclasses
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest

jwt = pytest.importorskip("jwt", reason="install requirements-defend-identity.txt for offline identity tests")
pytest.importorskip("cryptography", reason="install requirements-defend-identity.txt for asymmetric verification")
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from app.defend import identity

NOW = 1792094400
ISSUER = "https://identity.example.test/tenant"
AUDIENCE = "defend-test-client"


@pytest.fixture(scope="module")
def keys():
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ec_key = ec.generate_private_key(ec.SECP256R1())
    rsa_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(rsa_key.public_key(), as_dict=True)
    ec_jwk = jwt.algorithms.ECAlgorithm.to_jwk(ec_key.public_key(), as_dict=True)
    rsa_jwk.update(kid="rsa-key", alg="RS256", use="sig")
    ec_jwk.update(kid="ec-key", alg="ES256", use="sig")
    return rsa_key, ec_key, {"keys": [rsa_jwk, ec_jwk]}


@pytest.fixture
def verifier(keys, monkeypatch):
    monkeypatch.setattr(identity, "_wall_time", lambda: NOW)
    monkeypatch.setattr(identity, "_monotonic", lambda: 1000)
    return make_verifier(keys[2])


def make_verifier(jwks_document, **updates):
    config = dict(issuer=ISSUER, audience=AUDIENCE, tenant_claim="tid",
                  tenant_mapping={"provider-tenant": "defend-tenant"}, jwks=json.dumps(jwks_document))
    config.update(updates)
    return identity.PinnedOIDCVerifier(**config)


def claims(**updates):
    values = dict(iss=ISSUER, aud=AUDIENCE, sub="immutable-subject", jti="test-jti-canary",
                  tid="provider-tenant", roles=["analyst"], iat=NOW - 60, nbf=NOW - 60, exp=NOW + 300)
    values.update(updates)
    return values


def sign(keys, values=None, *, algorithm="RS256", headers=None):
    key = keys[0] if algorithm == "RS256" else keys[1]
    return jwt.encode(values or claims(), key, algorithm=algorithm,
                      headers=headers or {"kid": "rsa-key" if algorithm == "RS256" else "ec-key"})


@pytest.mark.parametrize("algorithm", ["RS256", "ES256"])
def test_accepts_signed_claims_with_pinned_key(verifier, keys, algorithm):
    token = sign(keys, algorithm=algorithm)
    actual = verifier.verify(token)
    assert UUID(actual.principal_id).version == 5
    assert actual.tenant_id == "defend-tenant"
    assert actual.roles == frozenset({"analyst"})
    assert actual.capabilities == frozenset({"cases:read", "receipts:read", "analyses:submit"})
    assert len(actual.jti_sha256) == 64
    assert "test-jti-canary" not in repr(actual)
    assert token not in repr(actual)
    assert actual.expires_at == NOW + 300
    with pytest.raises(dataclasses.FrozenInstanceError):
        actual.tenant_id = "other"


def test_display_changes_preserve_principal_and_subject_change_does_not(verifier, keys):
    first = verifier.verify(sign(keys, claims(name="Display One", email="one@example.test")))
    second = verifier.verify(sign(keys, claims(name="Display Two", email="two@example.test", jti="new-jti")))
    other = verifier.verify(sign(keys, claims(sub="different-subject")))
    assert first.principal_id == second.principal_id
    assert first.jti_sha256 != second.jti_sha256
    assert first.principal_id != other.principal_id
    assert "email" not in dataclasses.asdict(first)


def test_issuer_is_part_of_principal_identity(verifier, keys):
    first = verifier.verify(sign(keys))
    other_issuer = "https://other-identity.example.test/tenant"
    other = make_verifier(keys[2], issuer=other_issuer).verify(sign(keys, claims(iss=other_issuer)))
    assert first.principal_id != other.principal_id


@pytest.mark.parametrize("updates", [
    {"iss": "https://untrusted.example.test"}, {"aud": "other-client"},
    {"aud": [AUDIENCE, "another-client"]}, {"aud": [AUDIENCE, AUDIENCE]},
    {"exp": NOW}, {"exp": NOW - 1}, {"nbf": NOW + 1}, {"iat": NOW + 1},
    {"iat": True}, {"nbf": str(NOW - 60)}, {"exp": float(NOW + 300)},
    {"exp": 253402300800}, {"iat": -1}, {"exp": None}, {"sub": ""},
    {"sub": ["subject"]}, {"jti": ""}, {"jti": " space "}, {"tid": "other-tenant"},
    {"tid": ["provider-tenant"]}, {"roles": []}, {"roles": "analyst"},
    {"roles": ["administrator"]}, {"roles": ["analyst", "operator"]},
    {"roles": ["analyst", "analyst"]}, {"roles": [{}]},
])
def test_rejects_wrong_or_malformed_signed_claims(verifier, keys, updates):
    with pytest.raises(identity.IdentityRejected):
        verifier.verify(sign(keys, claims(**updates)))


@pytest.mark.parametrize("name", ["iss", "aud", "exp", "nbf", "iat", "sub", "jti", "tid", "roles"])
def test_requires_every_identity_claim(verifier, keys, name):
    values = claims()
    del values[name]
    with pytest.raises(identity.IdentityRejected):
        verifier.verify(sign(keys, values))


def test_accepts_only_registered_single_audience_list(verifier, keys):
    assert verifier.verify(sign(keys, claims(aud=[AUDIENCE]))).tenant_id == "defend-tenant"


@pytest.mark.parametrize("role", sorted(identity.ROLE_CAPABILITIES))
def test_each_reviewed_single_role_has_only_its_declared_capabilities(verifier, keys, role):
    actual = verifier.verify(sign(keys, claims(roles=[role])))
    assert actual.capabilities == identity.ROLE_CAPABILITIES[role]
    if role == "operator":
        assert "approvals:decide" not in actual.capabilities
        assert "cases:read" not in actual.capabilities
    if role == "auditor":
        assert actual.capabilities == frozenset({"evidence:read"})


def test_signature_unknown_key_and_algorithm_confusion_fail_closed(verifier, keys):
    rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(claims(), rogue_key, algorithm="RS256", headers={"kid": "rsa-key"})
    unknown = sign(keys, headers={"kid": "retired-key"})
    none = jwt.encode(claims(), None, algorithm="none", headers={"kid": "rsa-key"})
    symmetric = jwt.encode(claims(), b"test-symmetric-secret-long-enough", algorithm="HS256", headers={"kid": "rsa-key"})
    confused = sign(keys, algorithm="ES256", headers={"kid": "rsa-key"})
    for token in (forged, unknown, none, symmetric, confused):
        with pytest.raises(identity.IdentityRejected):
            verifier.verify(token)


@pytest.mark.parametrize("header", [{"jku": "https://attacker.test/jwks"}, {"jwk": {}},
                                     {"x5u": "https://attacker.test/cert"}, {"crit": []}])
def test_token_cannot_choose_key_source_or_critical_extensions(verifier, keys, header):
    with pytest.raises(identity.IdentityRejected, match="TOKEN_HEADER_INVALID"):
        verifier.verify(sign(keys, headers={"kid": "rsa-key", **header}))


def test_duplicate_claims_rejected_even_when_signature_valid(verifier, keys):
    payload = json.dumps(claims())[:-1] + ', "tid": "different-tenant"}'
    token = jwt.api_jws.encode(payload.encode(), keys[0], algorithm="RS256", headers={"kid": "rsa-key"})
    with pytest.raises(identity.IdentityRejected, match="TOKEN_INVALID"):
        verifier.verify(token)


@pytest.mark.parametrize("token", [None, b"bytes", "", "not.a.token", "a" * (identity.MAX_TOKEN_BYTES + 1), "é.a.b"])
def test_bounds_and_malformed_input(verifier, token):
    with pytest.raises(identity.IdentityRejected):
        verifier.verify(token)


def test_errors_and_traceback_do_not_include_token_or_provider_canary(verifier, keys):
    token = sign(keys, claims(iss="https://secret-provider-canary.example.test"))
    try:
        verifier.verify(token)
    except identity.IdentityRejected as exc:
        rendered = "".join(traceback.format_exception(exc))
        assert token not in rendered
        assert "secret-provider-canary" not in rendered
        assert "test-jti-canary" not in rendered
        assert str(exc) == exc.reason == "TOKEN_INVALID"
    else:
        pytest.fail("invalid token accepted")


@pytest.mark.parametrize("updates", [
    {"issuer": "http://identity.example.test"}, {"issuer": "https://user:secret@identity.example.test"},
    {"issuer": "https://identity.example.test?q=secret"}, {"audience": ""},
    {"tenant_claim": "caller_chosen_claim"}, {"tenant_mapping": {}},
    {"tenant_mapping": {"one": "same", "two": "same"}},
    {"jwks": "x" * (identity.MAX_JWKS_BYTES + 1)}, {"jwks": '{"keys":[],"keys":[]}'},
])
def test_rejects_ambiguous_or_unsafe_configuration(keys, updates):
    with pytest.raises(identity.IdentityRejected, match="IDENTITY_CONFIGURATION_INVALID"):
        make_verifier(keys[2], **updates)


def test_rejects_duplicate_key_id_private_key_and_wrong_key_usage(keys):
    public = keys[2]["keys"][0]
    private = jwt.algorithms.RSAAlgorithm.to_jwk(keys[0], as_dict=True)
    private.update(kid="rsa-key", alg="RS256")
    for jwks in ({"keys": [public, public]}, {"keys": [private]},
                 {"keys": [{**public, "use": "enc"}]},
                 {"keys": [{**public, "key_ops": ["sign", "verify"]}]},
                 {"keys": [{**public, "alg": "HS256"}]}):
        with pytest.raises(identity.IdentityRejected, match="IDENTITY_CONFIGURATION_INVALID"):
            make_verifier(jwks)


def test_operator_mapping_is_copied_at_construction(keys):
    mapping = {"provider-tenant": "original"}
    checker = make_verifier(keys[2], tenant_mapping=mapping)
    mapping["provider-tenant"] = "modified"
    assert checker._tenants["provider-tenant"] == "original"


def test_clock_rollback_does_not_extend_expiry(verifier, keys, monkeypatch):
    token = sign(keys, claims(exp=NOW + 1))
    monkeypatch.setattr(identity, "_wall_time", lambda: NOW - 1)
    monkeypatch.setattr(identity, "_monotonic", lambda: 1002)
    with pytest.raises(identity.IdentityRejected, match="TOKEN_TIME_INVALID"):
        verifier.verify(token)


def test_expired_token_stays_expired_after_wall_clock_rollback(verifier, keys, monkeypatch):
    token = sign(keys, claims(exp=NOW + 3))
    monkeypatch.setattr(identity, "_wall_time", lambda: NOW + 4)
    with pytest.raises(identity.IdentityRejected, match="TOKEN_TIME_INVALID"):
        verifier.verify(token)
    monkeypatch.setattr(identity, "_wall_time", lambda: NOW)
    monkeypatch.setattr(identity, "_monotonic", lambda: 1001)
    with pytest.raises(identity.IdentityRejected, match="TOKEN_TIME_INVALID"):
        verifier.verify(token)


def test_concurrent_requests_share_the_observed_time_floor(verifier, keys, monkeypatch):
    token = sign(keys, claims(exp=NOW + 3))
    monkeypatch.setattr(identity, "_wall_time", lambda: NOW + 4)
    with pytest.raises(identity.IdentityRejected, match="TOKEN_TIME_INVALID"):
        verifier.verify(token)
    monkeypatch.setattr(identity, "_wall_time", lambda: NOW)
    monkeypatch.setattr(identity, "_monotonic", lambda: 1001)

    def attempt(_):
        try:
            verifier.verify(token)
        except identity.IdentityRejected as exc:
            return exc.reason
        return "ACCEPTED"

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(attempt, range(16))) == ["TOKEN_TIME_INVALID"] * 16


@pytest.mark.parametrize("wall,monotonic", [(NOW + 10, 1000), (NOW - 10, 1000), (NOW, 999), (float("nan"), 1000)])
def test_unreliable_clock_fails_closed(verifier, keys, monkeypatch, wall, monotonic):
    monkeypatch.setattr(identity, "_wall_time", lambda: wall)
    monkeypatch.setattr(identity, "_monotonic", lambda: monotonic)
    with pytest.raises(identity.IdentityRejected, match="IDENTITY_CLOCK_UNAVAILABLE"):
        verifier.verify(sign(keys))


def test_verified_local_token_cannot_promote_production_readiness(verifier, keys):
    verifier.verify(sign(keys))
    assert verifier.qualification_status() == {
        "state": "BLOCKED", "production_ready": False,
        "production_oidc": "NOT_VERIFIED", "reason": "LIVE_IDENTITY_QUALIFICATION_INCOMPLETE",
    }
