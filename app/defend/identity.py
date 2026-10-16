# SPDX-License-Identifier: Apache-2.0
"""Offline OIDC verification source seam; production identity remains BLOCKED.

Keys and issuer/tenant configuration are operator-pinned at construction. This
module never fetches provider documents and does not wire public routes or grant
effector authority. Rotation, revocation, sessions, nonce/state, distributed
limits, audit receipts, and live qualification still require implementation.
"""
from __future__ import annotations

import hashlib
import json
import math
from threading import Lock
from time import monotonic as _monotonic, time as _wall_time
from dataclasses import dataclass
from types import MappingProxyType
from urllib.parse import urlsplit
from uuid import UUID, uuid5

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa

MAX_TOKEN_BYTES = 16384
MAX_JWKS_BYTES = 65536
MAX_KEYS = 16
MAX_CLOCK_DRIFT_SECONDS = 5
PRINCIPAL_NAMESPACE = UUID("d81d4517-8918-5cc5-a7e7-e45e3d08c571")
TENANT_CLAIMS = frozenset({"tid", "tenant_id", "org_id"})
ROLE_CAPABILITIES = MappingProxyType({
    "analyst": frozenset({"cases:read", "receipts:read", "analyses:submit"}),
    "requester": frozenset({"cases:create", "approvals:request"}),
    "approver": frozenset({"approvals:decide"}),
    "auditor": frozenset({"evidence:read"}),
    "operator": frozenset({"migrations:run", "deployments:run", "backups:run", "incidents:control"}),
})


class IdentityRejected(ValueError):
    """Typed reason only: no token, provider response, or crypto exception text."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class VerifiedIdentity:
    """Verified local claims only; does not establish live session authority."""

    principal_id: str
    tenant_id: str
    roles: frozenset[str]
    capabilities: frozenset[str]
    jti_sha256: str
    issued_at: int
    not_before: int
    expires_at: int


def _text(value: object, maximum: int = 256) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= maximum
            and value == value.strip() and all(ord(c) >= 32 for c in value))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError("nonfinite number")


def _json(value):
    return json.loads(value, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


class PinnedOIDCVerifier:
    """Validate against a fixed issuer, audience, tenant mapping, and public JWKS.

    Only a single reviewed role is accepted. Capabilities describe the role
    matrix; service authorization must additionally enforce tenant context,
    approval separation, current revocation/session state, and effect policy.
    """

    def __init__(self, *, issuer: str, audience: str, tenant_claim: str,
                 tenant_mapping: dict[str, str], jwks: str):
        try:
            parsed = urlsplit(issuer)
            if (not _text(issuer, 2048) or parsed.scheme != "https" or not parsed.hostname
                    or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or not _text(audience, 256) or tenant_claim not in TENANT_CLAIMS):
                raise ValueError("invalid issuer or claims configuration")
            if (not isinstance(tenant_mapping, dict) or not 1 <= len(tenant_mapping) <= 64
                    or any(not _text(k) or not _text(v) for k, v in tenant_mapping.items())
                    or len(set(tenant_mapping.values())) != len(tenant_mapping)):
                raise ValueError("ambiguous tenant mapping")
            if not isinstance(jwks, str) or len(jwks) > MAX_JWKS_BYTES or len(jwks.encode()) > MAX_JWKS_BYTES:
                raise ValueError("oversized JWKS")
            document = _json(jwks)
            keys = document["keys"]
            if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_KEYS:
                raise ValueError("invalid key count")
            pinned = {}
            for key in keys:
                kid, algorithm = key.get("kid"), key.get("alg")
                if (not _text(kid) or kid in pinned or algorithm not in {"RS256", "ES256"}
                        or key.get("use", "sig") != "sig"
                        or key.get("key_ops", ["verify"]) != ["verify"]
                        or any(field in key for field in ("d", "p", "q", "dp", "dq", "qi", "oth", "k"))):
                    raise ValueError("invalid public key")
                public = jwt.PyJWK.from_dict(key, algorithm=algorithm).key
                if algorithm == "RS256":
                    if not isinstance(public, rsa.RSAPublicKey) or not 2048 <= public.key_size <= 8192:
                        raise ValueError("invalid RSA key")
                elif not isinstance(public, ec.EllipticCurvePublicKey) or not isinstance(public.curve, ec.SECP256R1):
                    raise ValueError("invalid EC key")
                pinned[kid] = (algorithm, public)
            self._issuer = issuer
            self._audience = audience
            self._tenant_claim = tenant_claim
            self._tenants = MappingProxyType(dict(tenant_mapping))
            self._keys = MappingProxyType(pinned)
            self._wall_anchor = _wall_time()
            self._monotonic_anchor = _monotonic()
            if not math.isfinite(self._wall_anchor) or not math.isfinite(self._monotonic_anchor):
                raise ValueError("invalid clock")
            self._clock_floor = self._wall_anchor
            self._clock_lock = Lock()
        except Exception:
            raise IdentityRejected("IDENTITY_CONFIGURATION_INVALID") from None

    @staticmethod
    def qualification_status() -> dict:
        return {"state": "BLOCKED", "production_ready": False,
                "production_oidc": "NOT_VERIFIED",
                "reason": "LIVE_IDENTITY_QUALIFICATION_INCOMPLETE"}

    def _now(self) -> float:
        # Serialize reads and the observed-time floor: a later request must not
        # revive an expired token after wall time rolls back within tolerance.
        with self._clock_lock:
            wall, monotonic = _wall_time(), _monotonic()
            elapsed = monotonic - self._monotonic_anchor
            anchored = self._wall_anchor + elapsed
            if (not math.isfinite(wall) or not math.isfinite(monotonic) or elapsed < 0
                    or abs(wall - anchored) > MAX_CLOCK_DRIFT_SECONDS):
                raise IdentityRejected("IDENTITY_CLOCK_UNAVAILABLE")
            self._clock_floor = max(self._clock_floor, wall, anchored)
            return self._clock_floor

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            return self._verify(token)
        except IdentityRejected:
            raise
        except Exception:
            raise IdentityRejected("TOKEN_INVALID") from None

    def _verify(self, token: str) -> VerifiedIdentity:
        if (not isinstance(token, str) or not 1 <= len(token) <= MAX_TOKEN_BYTES
                or not token.isascii() or token.count(".") != 2):
            raise IdentityRejected("TOKEN_INVALID")
        segments = token.split(".")
        # Reject ambiguous JSON, including duplicate claims, before verification.
        # These decoded values never supply authoritative identity information.
        header = _json(jwt.utils.base64url_decode(segments[0]))
        if not isinstance(_json(jwt.utils.base64url_decode(segments[1])), dict):
            raise IdentityRejected("TOKEN_INVALID")
        if (not isinstance(header, dict) or header.get("alg") not in {"RS256", "ES256"}
                or any(name in header for name in ("crit", "b64", "jku", "jwk", "x5u", "x5c"))):
            raise IdentityRejected("TOKEN_HEADER_INVALID")
        kid = header.get("kid")
        if not _text(kid) or kid not in self._keys:
            raise IdentityRejected("TOKEN_KEY_UNKNOWN")
        algorithm, key = self._keys[kid]
        if header["alg"] != algorithm:
            raise IdentityRejected("TOKEN_HEADER_INVALID")
        claims = jwt.decode(
            token, key, algorithms=[algorithm], issuer=self._issuer, audience=self._audience,
            leeway=0, options={
                "require": ["iss", "aud", "exp", "nbf", "iat", "sub", "jti", self._tenant_claim, "roles"],
                # NumericDate types and time checks use the bounded monotonic clock below.
                "verify_exp": False, "verify_nbf": False, "verify_iat": False,
            },
        )
        if claims["aud"] != self._audience and claims["aud"] != [self._audience]:
            raise IdentityRejected("TOKEN_AUDIENCE_INVALID")
        if any(type(claims[name]) is not int or not 0 <= claims[name] <= 253402300799
               for name in ("exp", "nbf", "iat")):
            raise IdentityRejected("TOKEN_DATES_INVALID")
        now = self._now()
        if (claims["exp"] <= now or claims["iat"] > now or claims["nbf"] > now
                or claims["exp"] <= claims["iat"] or claims["exp"] <= claims["nbf"]):
            raise IdentityRejected("TOKEN_TIME_INVALID")
        if not _text(claims["sub"]) or not _text(claims["jti"]):
            raise IdentityRejected("TOKEN_CLAIMS_INVALID")
        provider_tenant = claims[self._tenant_claim]
        if not _text(provider_tenant) or provider_tenant not in self._tenants:
            raise IdentityRejected("TOKEN_TENANT_DENIED")
        roles = claims["roles"]
        if (not isinstance(roles, list) or len(roles) != 1
                or not isinstance(roles[0], str) or roles[0] not in ROLE_CAPABILITIES):
            raise IdentityRejected("TOKEN_ROLE_DENIED")
        principal = uuid5(PRINCIPAL_NAMESPACE, json.dumps(
            [self._issuer, claims["sub"]], ensure_ascii=True, separators=(",", ":")))
        return VerifiedIdentity(
            principal_id=str(principal), tenant_id=self._tenants[provider_tenant],
            roles=frozenset(roles), capabilities=ROLE_CAPABILITIES[roles[0]],
            jti_sha256=hashlib.sha256(claims["jti"].encode("utf-8")).hexdigest(),
            issued_at=claims["iat"], not_before=claims["nbf"], expires_at=claims["exp"],
        )
