#!/usr/bin/env python3
"""Self-test for the own-metal reachability classifier.

Offline: DNS resolution and HTTP fetch are both stubbed. Proves the classifier
separates the three situations that have different owners, which is the entire
reason the script exists:

  no DNS record        -> DNS_RECORD_MISSING   (Cloudflare DNS change)
  resolves, HTTP 530   -> TUNNEL_NOT_CONNECTED (start cloudflared on the box)
  resolves, HTTP 200   -> REACHABLE            (nothing to do)

Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import diagnose_own_metal_reachability as dg  # noqa: E402

CF_1033_PAGE = "<!doctype html>" + ("<!-- pad -->" * 400) + "\nerror code: 1033\n</html>"


class ClassifyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._resolve = dg.resolve
        self._fetch = dg.fetch

    def tearDown(self) -> None:
        dg.resolve = self._resolve
        dg.fetch = self._fetch

    def _stub(self, *, resolved, addrs=(), dns_error="", status=0, body="", http_error=""):
        dg.resolve = lambda _h: (resolved, list(addrs), dns_error)
        dg.fetch = lambda _u, _t: (status, body, http_error)

    def test_missing_dns_record_is_a_cloudflare_problem(self) -> None:
        self._stub(resolved=False, dns_error="gaierror: Name or service not known")
        r = dg.classify("killinchu.a-11-oy.com", "https://killinchu.a-11-oy.com/healthz", 5)
        self.assertEqual(r["diagnosis"], dg.DIAGNOSIS_DNS_MISSING)
        self.assertIn("Cloudflare DNS", r["owner"])
        self.assertFalse(r["dns_resolved"])

    def test_http_530_without_body_is_still_a_tunnel_problem(self) -> None:
        """Regression: a truncated or empty interstitial must not downgrade to ORIGIN_ERROR."""
        self._stub(resolved=True, addrs=["104.21.27.230"], status=530, body="")
        r = dg.classify("gdw.a-11-oy.com", "https://gdw.a-11-oy.com/healthz", 5)
        self.assertEqual(r["diagnosis"], dg.DIAGNOSIS_TUNNEL_DOWN)
        self.assertIn("cloudflared", r["owner"])

    def test_error_code_1033_deep_in_a_long_body_is_found(self) -> None:
        """Regression: the code sits well past 2 KB in Cloudflare's HTML page."""
        self.assertGreater(CF_1033_PAGE.index("error code: 1033"), 2048)
        self._stub(resolved=True, addrs=["104.21.27.230"], status=530, body=CF_1033_PAGE)
        r = dg.classify("gdw.a-11-oy.com", "https://gdw.a-11-oy.com/healthz", 5)
        self.assertEqual(r["diagnosis"], dg.DIAGNOSIS_TUNNEL_DOWN)
        self.assertEqual(r["cloudflare_error_code"], "1033")

    def test_reachable_target_blames_nobody(self) -> None:
        self._stub(resolved=True, addrs=["1.2.3.4"], status=200, body='{"status":"ok"}')
        r = dg.classify("szlholdings-killinchu.hf.space", "https://x/healthz", 5)
        self.assertEqual(r["diagnosis"], dg.DIAGNOSIS_REACHABLE)
        self.assertIn("nobody", r["owner"])

    def test_app_level_5xx_is_an_application_problem(self) -> None:
        self._stub(resolved=True, addrs=["1.2.3.4"], status=502, body="bad gateway")
        r = dg.classify("box.example.test", "https://x/healthz", 5)
        self.assertEqual(r["diagnosis"], dg.DIAGNOSIS_ORIGIN_ERROR)
        self.assertIn("application", r["owner"])

    def test_resolves_but_no_response_is_unknown_not_a_guess(self) -> None:
        self._stub(resolved=True, addrs=["1.2.3.4"], status=0, http_error="TimeoutError: timed out")
        r = dg.classify("box.example.test", "https://x/healthz", 5)
        self.assertEqual(r["diagnosis"], dg.DIAGNOSIS_UNKNOWN)
        self.assertIn("manual triage", r["owner"])

    def test_every_diagnosis_has_a_named_owner(self) -> None:
        for name in (
            dg.DIAGNOSIS_DNS_MISSING,
            dg.DIAGNOSIS_TUNNEL_DOWN,
            dg.DIAGNOSIS_ORIGIN_ERROR,
            dg.DIAGNOSIS_REACHABLE,
            dg.DIAGNOSIS_UNKNOWN,
        ):
            self.assertIn(name, dg.OWNERS)
            self.assertTrue(dg.OWNERS[name])

    def test_main_never_gates(self) -> None:
        """The script diagnoses; the blocking gate is the primary-surface check."""
        self._stub(resolved=False, dns_error="gaierror")
        self.assertEqual(dg.main(["--url", "https://killinchu.a-11-oy.com"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
