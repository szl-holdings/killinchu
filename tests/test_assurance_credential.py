# SPDX-License-Identifier: Apache-2.0
"""The assurance credential must verify the active runtime's attestations.

Only ephemeral test keys are used. No organization signer is needed or read.
"""

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import szl_be_hardening
import szl_dsse


@pytest.mark.parametrize("key_source", ["absent", "inline", "public-only"])
def test_credential_key_matches_fingerprint_and_attestation(
    monkeypatch, tmp_path, key_source
):
    for name in szl_dsse.PRIVATE_KEY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(szl_dsse.TRUSTED_PUBLIC_PEMS_ENV, raising=False)
    monkeypatch.setattr(szl_dsse, "_RUNTIME_PUBLIC_KEYS", {})
    monkeypatch.setattr(szl_dsse, "_ACTIVE_RUNTIME_KEYID", None)

    expected_pem = szl_dsse.COSIGN_PUBLIC_PEM.strip()
    if key_source != "absent":
        private_key = ec.generate_private_key(ec.SECP256R1())
        expected_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii").strip()
        if key_source == "inline":
            private_pem = private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode("ascii")
            monkeypatch.setenv("SZL_COSIGN_PRIVATE_KEY_PEM", private_pem)
        else:
            szl_dsse.configure_runtime_public_key(expected_pem)

    app = FastAPI()
    report = szl_be_hardening.harden(
        app, organ="killinchu", khipu_path=str(tmp_path / "khipu.sqlite3")
    )
    assert report["ok"] is True
    with TestClient(app) as client:
        response = client.get("/api/killinchu/v1/assurance/credential")
        assert response.status_code == 200
        credential = response.json()
        assert credential["data_kind"] == "live"
        assert credential["public_key_pem"] == expected_pem
        assert szl_dsse.keyid_for_public_pem(credential["public_key_pem"]) == (
            credential["public_key_fingerprint_sha256"]
        )

        response = client.get("/api/killinchu/v1/assurance/attest")
        assert response.status_code == 200
        envelope = response.json()["dsse"]
        assert credential["signing_available"] is (key_source == "inline")
        if key_source == "inline":
            signature = envelope["signatures"][0]
            assert signature["keyid"] == credential["public_key_fingerprint_sha256"]
            public_key = serialization.load_pem_public_key(
                credential["public_key_pem"].encode("ascii")
            )
            public_key.verify(
                base64.b64decode(signature["sig"]),
                szl_dsse.pae(
                    envelope["payloadType"], base64.b64decode(envelope["payload"])
                ),
                ec.ECDSA(hashes.SHA256()),
            )
        else:
            assert envelope["signed"] is False
            assert envelope["signatures"] == []
