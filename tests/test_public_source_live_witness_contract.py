#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Network-free contract tests for the public-source live witness."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "public_source_live_witness.py"
WORKFLOW = ROOT / ".github" / "workflows" / "public-source-live-witness.yml"

spec = importlib.util.spec_from_file_location("public_source_live_witness", SCRIPT)
assert spec and spec.loader
witness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(witness)


class PublicSourceLiveWitnessContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_operator_has_fixed_origins_and_exact_source_inventory(self) -> None:
        self.assertEqual(
            witness.BASE,
            "https://szlholdings-killinchu.hf.space",
        )
        self.assertEqual(
            witness.SOURCE_IDS,
            {
                "cisa-kev",
                "nsa-advisories",
                "cia-public-stories",
                "ofac-sdn",
                "un-dprk-1718",
                "cert-ua-advisories",
                "ukraine-open-data-metadata",
                "china-cac-notices",
            },
        )
        with self.assertRaises(ValueError):
            witness.request_json("https://evil.example/anything", timeout=1)

    def test_every_explicit_urllib_request_is_get_only(self) -> None:
        methods = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            if not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "Request"
            ):
                continue
            for keyword in node.keywords:
                if keyword.arg == "method":
                    self.assertIsInstance(keyword.value, ast.Constant)
                    methods.append(keyword.value.value)
        self.assertEqual(methods, ["GET"])
        for forbidden in (
            "subprocess",
            "os.system",
            "paramiko",
            "ftplib",
            "socket.create_connection",
            'method="POST"',
            'method="PUT"',
            'method="PATCH"',
            'method="DELETE"',
        ):
            self.assertNotIn(forbidden, self.source)

    def test_policy_validator_requires_the_non_intrusion_boundary(self) -> None:
        payload = {
            "schema": witness.SCHEMA,
            "state": "DECLARED",
            "action_authority": "NONE",
            "policy": {
                "network": {
                    "method": "GET_ONLY",
                    "arbitrary_url_input": False,
                    "authentication_bypass": False,
                    "credential_use": False,
                    "protected_resources": False,
                },
                "content": {
                    key: "PROHIBITED"
                    for key in witness.PROHIBITED_CONTENT_KEYS
                },
                "authority": {
                    "action_authority": "NONE",
                    "automated_targeting": False,
                    "automated_enforcement": False,
                    "human_review_required": True,
                },
            },
        }
        witness._require_policy(payload)
        payload["policy"]["network"]["authentication_bypass"] = True
        with self.assertRaises(AssertionError):
            witness._require_policy(payload)

    def test_source_validator_accepts_metadata_rows_without_invented_authority(self) -> None:
        payload = {
            "schema": witness.SCHEMA,
            "source_count": len(witness.SOURCE_IDS),
            "action_authority": "NONE",
            "sources": [
                {
                    "source_id": source_id,
                    "url": f"https://official.example/{source_id}",
                    "classification": "PUBLIC_OFFICIAL_METADATA",
                }
                for source_id in sorted(witness.SOURCE_IDS)
            ],
        }
        self.assertEqual(witness._require_sources(payload), witness.SOURCE_IDS)

    def test_sanctions_validator_never_accepts_clear_or_action_authority(self) -> None:
        witness._require_sanctions(
            503,
            {
                "verdict": "BLOCKED_PENDING",
                "action_authority": "NONE",
                "manual_review_required": True,
            },
        )
        for payload in (
            {
                "verdict": "CLEAR",
                "action_authority": "NONE",
                "manual_review_required": True,
            },
            {
                "verdict": "NO_EXACT_MATCH",
                "action_authority": "EXECUTE",
                "manual_review_required": True,
            },
        ):
            with self.assertRaises(AssertionError):
                witness._require_sanctions(200, payload)

    def test_workflow_runs_after_deploy_and_on_protected_main_changes(self) -> None:
        for marker in (
            "name: Public Source Fabric Live Witness",
            "workflow_run:",
            "- Sync to HuggingFace Space",
            "branches: [main]",
            "scripts/public_source_live_witness.py",
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.head_branch == 'main'",
            "permissions:\n  contents: read",
            "persist-credentials: false",
            "--retry-seconds 420",
        ):
            self.assertIn(marker, self.workflow)
        for forbidden in (
            "HF_TOKEN",
            "HF_ORG_TOKEN",
            "HF_WRITE_TOKEN",
            "contents: write",
            "secrets: inherit",
            "workflow_dispatch:\n    inputs:",
        ):
            self.assertNotIn(forbidden, self.workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
