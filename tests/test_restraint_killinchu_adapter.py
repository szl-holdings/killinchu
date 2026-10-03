#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Synthetic route proof for killinchu's shared restraint DSSE adapter.

The Killinchu namespace inherits the shared A11OY_CODE_ADMIN_KEY handler gate.
Tests configure only a synthetic credential and disposable ECDSA keys, execute
the restraint registration block alone, and do not boot the full production app.
Production credential configuration and live route readiness remain unverified.
"""

import ast
import base64
import json
import os
import secrets
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import szl_dsse as dsse  # noqa: E402
import szl_operator_auth as auth  # noqa: E402
import szl_restraint as restraint  # noqa: E402


PATH = "/api/killinchu/v1/restraint/evaluate"
OPERATOR = secrets.token_urlsafe(32)
HEADERS = {"Authorization": f"Bearer {OPERATOR}"}


def _adapter_callbacks():
    """Compile only the actual serve.py callbacks; never boot its full app."""
    source = ast.parse((ROOT / "serve.py").read_text(encoding="utf-8"))
    names = {"_kc_restraint_sign", "_kc_restraint_verify", "_kc_restraint_identity"}
    found = {node.name: node for node in ast.walk(source)
             if isinstance(node, ast.FunctionDef) and node.name in names}
    if set(found) != names:
        raise AssertionError("killinchu restraint adapter callbacks missing")
    namespace = {"_szl_dsse": dsse}
    for name in sorted(names):
        module = ast.fix_missing_locations(ast.Module(body=[found[name]], type_ignores=[]))
        exec(compile(module, str(ROOT / "serve.py"), "exec"), namespace)
    return (namespace["_kc_restraint_sign"], namespace["_kc_restraint_verify"],
            namespace["_kc_restraint_identity"])


def _registration_block():
    """Select the real restraint registration block without booting other routes."""
    source = ast.parse((ROOT / "serve.py").read_text(encoding="utf-8"))
    blocks = [node for node in source.body if isinstance(node, ast.Try)
              and any(isinstance(child, ast.Assign)
                      and any(isinstance(target, ast.Name)
                              and target.id == "_kc_restraint_status"
                              for target in child.targets)
                      for child in ast.walk(node))]
    if len(blocks) != 1:
        raise AssertionError("expected one actual restraint registration block")
    return ast.fix_missing_locations(ast.Module(body=blocks, type_ignores=[]))


def _private_pem():
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


class KillinchuRestraintAdapter(unittest.TestCase):
    def setUp(self):
        empty_secrets = {name: "" for name in dsse.PRIVATE_KEY_ENV_VARS}
        self.env = patch.dict(os.environ, {
            **empty_secrets,
            auth.OPERATOR_KEY_ENV: OPERATOR,
            "A11OY_CODE_AUTH_MODE": "lenient",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.sign, self.verify, self.identity = _adapter_callbacks()

    def _app(self, *, sign=None, verify=None, identity_reader=True):
        app = FastAPI()
        restraint.register(app, ns="killinchu", sign_fn=sign or self.sign,
                           verify_fn=verify or self.verify,
                           identity_fn=self.identity if identity_reader else None)
        return app, TestClient(app)

    def test_operator_gate_precedes_signing_even_in_lenient_mode(self):
        app, client = self._app()
        os.environ["SZL_COSIGN_PRIVATE_KEY_PEM"] = _private_pem()
        with patch.object(dsse, "sign_payload", wraps=dsse.sign_payload) as signer:
            for headers in ({}, {"Authorization": "Bearer wrong"}):
                response = client.post(PATH, headers=headers, json={"task": "add a cache"})
                self.assertEqual(response.status_code, 401, response.text)
                self.assertEqual(response.json()["status"], "BLOCKED")
            self.assertEqual(signer.call_count, 0)
        with patch.dict(os.environ, {auth.OPERATOR_KEY_ENV: ""}):
            self.assertEqual(client.post(PATH, headers=HEADERS,
                                         json={"task": "add a cache"}).status_code, 401)
        self.assertFalse(client.get("/api/killinchu/v1/restraint/info").json()
                         ["receipt_verification"]["cryptographically_verified"])

    def test_real_dsse_roundtrip_and_get_never_signs(self):
        os.environ["SZL_COSIGN_PRIVATE_KEY_PEM"] = _private_pem()
        app, client = self._app()
        before = client.get("/api/killinchu/v1/restraint/info").json()
        self.assertFalse(before["signer_health"]["ready"])
        response = client.post(PATH, headers=HEADERS, json={"task": "add a cache"})
        self.assertEqual(response.status_code, 200, response.text)
        envelope = response.json()["signed_receipt"]
        payload = json.loads(base64.b64decode(envelope["payload"], validate=True))
        keyid = envelope["signatures"][0]["keyid"]
        self.assertEqual(payload["_signing_identity"]["keyid"], keyid)
        self.assertTrue(dsse.verify_envelope(envelope)["verified"])
        self.assertEqual(self.verify(envelope),
                         {"signature_valid": True, "keyid_verified": keyid})
        with patch.object(dsse, "sign_payload", wraps=dsse.sign_payload) as signer:
            info = client.get("/api/killinchu/v1/restraint/info").json()
            self.assertEqual(signer.call_count, 0)
        self.assertTrue(info["receipt_verification"]["cryptographically_verified"])
        self.assertEqual(info["signer_health"]["identity"], keyid)
        new_app, new_client = self._app()
        self.assertFalse(new_client.get("/api/killinchu/v1/restraint/info").json()
                         ["receipt_verification"]["cryptographically_verified"])

    def test_unsigned_tampered_and_substituted_receipts_fail_closed(self):
        app, client = self._app()
        self.assertEqual(client.post(PATH, headers=HEADERS,
                                     json={"task": "add a cache"}).status_code, 503)
        os.environ["SZL_COSIGN_PRIVATE_KEY_PEM"] = _private_pem()

        def bad_signature(payload):
            envelope = self.sign(payload)
            envelope["signatures"][0]["sig"] = base64.b64encode(b"bad").decode("ascii")
            return envelope

        app.state.szl_restraint_signer_override = bad_signature
        self.assertEqual(client.post(PATH, headers=HEADERS,
                                     json={"task": "add a cache"}).status_code, 503)

        app.state.szl_restraint_signer_override = lambda payload: self.sign(
            {**payload, "task_digest": "substituted"}
        )
        self.assertEqual(client.post(PATH, headers=HEADERS,
                                     json={"task": "add a cache"}).status_code, 503)
        self.assertFalse(client.get("/api/killinchu/v1/restraint/info").json()
                         ["receipt_verification"]["cryptographically_verified"])

        with patch.object(dsse, "verify_envelope", return_value={"verified": True}):
            self.assertEqual(self.verify(self.sign({"task_digest": "x"})),
                             {"signature_valid": False})

    def test_rotation_between_identity_and_signing_blocks(self):
        first_pem = _private_pem()
        second_pem = _private_pem()
        os.environ["SZL_COSIGN_PRIVATE_KEY_PEM"] = second_pem
        app, client = self._app()
        with patch.object(dsse, "active_public_key_pem") as public_key:
            # Supply the first key's public half while the signer uses the second.
            first = serialization.load_pem_private_key(first_pem.encode("ascii"), None)
            public_key.return_value = first.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("ascii")
            self.assertEqual(client.post(PATH, headers=HEADERS,
                                         json={"task": "add a cache"}).status_code, 503)
        self.assertFalse(client.get("/api/killinchu/v1/restraint/info").json()
                         ["receipt_verification"]["cryptographically_verified"])

    def test_verifier_requires_a_verified_row_with_matching_identity(self):
        os.environ["SZL_COSIGN_PRIVATE_KEY_PEM"] = _private_pem()
        envelope = self.sign({"task_digest": "synthetic"})
        keyid = envelope["signatures"][0]["keyid"]
        for row in (
            {"keyid": keyid, "verified": False, "verified_by_keyid": keyid},
            {"keyid": keyid, "verified": True, "verified_by_keyid": "different"},
            {"keyid": keyid, "verified": True},
        ):
            with self.subTest(row=row), patch.object(dsse, "verify_envelope", return_value={
                "verified": True, "signatures": [row],
            }):
                self.assertEqual(self.verify(envelope), {"signature_valid": False})

    def test_non_object_body_is_rejected_before_signing(self):
        os.environ["SZL_COSIGN_PRIVATE_KEY_PEM"] = _private_pem()
        app, client = self._app()
        with patch.object(dsse, "sign_payload", wraps=dsse.sign_payload) as signer:
            response = client.post(PATH, headers=HEADERS,
                                   json=[{"task": "add a cache"}])
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json(), {"error": "provide a JSON object"})
        self.assertEqual(signer.call_count, 0)
        self.assertFalse(client.get("/api/killinchu/v1/restraint/info").json()
                         ["receipt_verification"]["cryptographically_verified"])

    def test_current_private_identity_is_required_for_ready(self):
        first_pem = _private_pem()
        os.environ["SZL_COSIGN_PRIVATE_KEY_PEM"] = first_pem
        app, client = self._app()
        self.assertEqual(client.post(PATH, headers=HEADERS,
                                     json={"task": "add a cache"}).status_code, 200)
        self.assertTrue(client.get("/api/killinchu/v1/restraint/info").json()
                        ["signer_health"]["ready"])
        os.environ["SZL_COSIGN_PRIVATE_KEY_PEM"] = ""
        with patch.object(dsse, "sign_payload", wraps=dsse.sign_payload) as signer:
            removed = client.get("/api/killinchu/v1/restraint/info").json()
            self.assertEqual(signer.call_count, 0)
        self.assertFalse(removed["signer_health"]["ready"])
        self.assertFalse(removed["signer_health"]["identity_checked"])
        # A prior verified receipt remains historical evidence, not current readiness.
        self.assertTrue(removed["receipt_verification"]["cryptographically_verified"])

        os.environ["SZL_COSIGN_PRIVATE_KEY_PEM"] = _private_pem()
        rotated = client.get("/api/killinchu/v1/restraint/info").json()
        self.assertFalse(rotated["signer_health"]["ready"])
        self.assertEqual(client.post(PATH, headers=HEADERS,
                                     json={"task": "add a cache"}).status_code, 200)
        self.assertTrue(client.get("/api/killinchu/v1/restraint/info").json()
                        ["signer_health"]["ready"])

    def test_missing_identity_reader_never_reports_ready(self):
        os.environ["SZL_COSIGN_PRIVATE_KEY_PEM"] = _private_pem()
        app, client = self._app(identity_reader=False)
        self.assertEqual(client.post(PATH, headers=HEADERS,
                                     json={"task": "add a cache"}).status_code, 200)
        missing = client.get("/api/killinchu/v1/restraint/info").json()
        self.assertFalse(missing["signer_health"]["ready"])
        self.assertFalse(missing["signer_health"]["identity_checked"])
        self.assertTrue(missing["receipt_verification"]["cryptographically_verified"])

    def test_actual_registration_uses_reviewed_local_module(self):
        def stale_register(*args, **kwargs):
            raise AssertionError("older substrate route gate was selected")

        stale_package = types.ModuleType("szl_substrate")
        stale_module = types.ModuleType("szl_substrate.szl_restraint")
        stale_module.register = stale_register
        stale_package.szl_restraint = stale_module
        app = FastAPI()
        namespace = {"app": app, "_szl_dsse": dsse, "sys": sys}
        with patch.dict(sys.modules, {"szl_substrate": stale_package,
                                      "szl_substrate.szl_restraint": stale_module}):
            exec(compile(_registration_block(), str(ROOT / "serve.py"), "exec"),
                 namespace)
        self.assertIs(namespace["_szl_restraint"], restraint)
        self.assertIs(app.state.szl_restraint_identity_override,
                      namespace["_kc_restraint_identity"])
        with TestClient(app) as client, patch.object(dsse, "sign_payload",
                                                    wraps=dsse.sign_payload) as signer:
            response = client.post(PATH, json={"task": "add a cache"})
            self.assertEqual(response.status_code, 401, response.text)
            self.assertEqual(signer.call_count, 0)


if __name__ == "__main__":
    unittest.main()
