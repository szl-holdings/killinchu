# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""Alert-webhook failures must never echo the relay's response body.

Three workflows page the team through the shared ``SLACK_WEBHOOK_URL`` relay:
hf-drift-check, killinchu-api-health and knowledge-corpus-autosync. On a
non-2xx answer they used to print the raw response body. An edge error page
(a Cloudflare managed challenge, for example) reflects the request path, and
the relay path carries the secret token, so the failure message published that
token in a public Actions log. GitHub only masks the exact secret value, not a
substring of it.

This drives the REAL ``run:`` script of each alert step, extracted from the
workflow YAML, under bash. ``curl`` is shadowed by a fake on PATH that answers
like an edge challenge page: its body echoes the request path and it writes
the response headers to the ``-D`` file. ``jq`` is the real one. Per workflow:

* every non-2xx answer still fails the step (delivery failure stays loud);
* neither the body nor any part of the webhook path reaches stdout/stderr;
* a Cloudflare challenge (``cf-mitigated: challenge``) and an HTTP 402 are
  named as edge causes, and any other code says the body was withheld;
* a 2xx answer still reports delivery.

Only the HTTP POST is intercepted. The classification is the workflow's own.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path

import pytest

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - CI installs pyyaml
    pytest.skip("pyyaml not installed", allow_module_level=True)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# (workflow file, job id, step name, extra env the step's `env:` block sets,
#  the line it prints on delivery)
ALERT_STEPS = {
    "hf-drift-check": (
        "hf-drift-check.yml",
        "drift-check",
        "Alert the team on README drift (or fetch failure)",
        {"STATUS": "drift", "SPACE_ID": "SZLHOLDINGS/killinchu",
         "RAW_URL": "https://huggingface.co/spaces/SZLHOLDINGS/killinchu/raw/main/README.md",
         "HTTP_CODE": "200", "GH_BYTES": "100", "HF_BYTES": "101"},
        "Direct alert delivered.",
    ),
    "killinchu-api-health": (
        "killinchu-api-health.yml",
        "health",
        "Alert the team on sustained API failure",
        {"CHECKED": "5", "PASSED": "4", "FAILED": "1"},
        "Direct alert delivered.",
    ),
    "knowledge-corpus-autosync": (
        "knowledge-corpus-autosync.yml",
        "auto-sync",
        "Notify the team of the auto-sync outcome",
        {"GATE_OUTCOME": "success", "PR_RESULT": "pr_opened",
         "PR_URL": "https://github.com/szl-holdings/killinchu/pull/1",
         "COMPARE_URL": ""},
        "Outcome delivered.",
    ),
}

# A fake `curl`: writes a challenge-style body that echoes the request path to
# the -o file, the canned headers to the -D file, records the --data payload,
# and prints the HTTP code like `curl -w '%{http_code}'`.
FAKE_CURL = r"""#!/usr/bin/env bash
outfile=""; headfile=""; data=""; prev=""; url=""
for arg in "$@"; do
  case "$prev" in
    -o) outfile="$arg" ;;
    -D) headfile="$arg" ;;
    --data) data="$arg" ;;
  esac
  prev="$arg"; url="$arg"
done
path="/${url#*://*/}"
[ -n "$outfile" ] && printf '<title>Just a moment...</title><script>fa:"%s?__cf_chl_f_tk=x"</script>' "$path" > "$outfile"
[ -n "$headfile" ] && printf '%b' "${FAKE_CURL_HEADERS:-}" > "$headfile"
[ -n "${CURL_CAPTURE:-}" ] && printf '%s' "$data" > "$CURL_CAPTURE"
printf '%s' "${FAKE_CURL_CODE:-200}"
"""

CF_CHALLENGE = "HTTP/2 403\r\nserver: cloudflare\r\ncf-mitigated: challenge\r\n\r\n"
X402 = "HTTP/2 402\r\nserver: cloudflare\r\npayment-required: x402\r\n\r\n"
PLAIN = "HTTP/1.1 405 Method Not Allowed\r\nserver: nginx\r\n\r\n"


def _alert_script(key: str) -> str:
    workflow, job, step_name, _env, _ok = ALERT_STEPS[key]
    data = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    for step in data["jobs"][job]["steps"]:
        if step.get("name") == step_name:
            return step["run"]
    raise AssertionError(f"{workflow}: step {step_name!r} not found in job {job!r}")


def _run(key: str, code: str, headers: str):
    _workflow, _job, _step, extra_env, _ok = ALERT_STEPS[key]
    token = secrets.token_hex(24)
    webhook = f"https://relay.invalid/relay/ntfy/{token}"
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        bindir = tdp / "bin"
        bindir.mkdir()
        curl = bindir / "curl"
        curl.write_text(FAKE_CURL)
        curl.chmod(0o755)
        capture = tdp / "capture.json"
        script = tdp / "alert.sh"
        script.write_text(_alert_script(key))
        env = {
            "PATH": f"{bindir}:{os.environ.get('PATH', '')}",
            "CURL_CAPTURE": str(capture),
            "FAKE_CURL_CODE": code,
            "FAKE_CURL_HEADERS": headers,
            "SLACK_WEBHOOK_URL": webhook,
            "RUN_URL": "https://github.com/szl-holdings/killinchu/actions/runs/1",
            "REPO": "szl-holdings/killinchu",
            **extra_env,
        }
        proc = subprocess.run(["bash", str(script)], env=env, capture_output=True,
                              text=True, cwd=td, timeout=60)
        payload = json.loads(capture.read_text()) if capture.exists() else None
    return proc, payload, token


@pytest.mark.parametrize("key", sorted(ALERT_STEPS))
@pytest.mark.parametrize(
    ("code", "headers", "expected"),
    [
        ("403", CF_CHALLENGE, "Cloudflare managed challenge"),
        ("402", X402, "x402 paywall"),
        ("405", PLAIN, "response body withheld"),
    ],
    ids=["cloudflare-challenge", "x402", "other"],
)
def test_failed_delivery_fails_loud_without_echoing_body_or_path(key, code, headers, expected):
    proc, payload, token = _run(key, code, headers)
    output = proc.stdout + proc.stderr
    assert payload is not None and payload.get("text"), "the POST must still be attempted"
    assert proc.returncode != 0, f"{key}: HTTP {code} must fail the step"
    assert f"(HTTP {code})" in output and expected in output, output
    assert token not in output, f"{key}: the webhook token leaked into the log"
    assert "/relay/ntfy/" not in output, f"{key}: the webhook path leaked into the log"
    assert "Just a moment" not in output, f"{key}: the response body leaked into the log"


@pytest.mark.parametrize("key", sorted(ALERT_STEPS))
def test_2xx_delivery_still_succeeds(key):
    proc, payload, token = _run(key, "200", "HTTP/2 200\r\n\r\n")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert payload is not None and payload.get("text")
    assert ALERT_STEPS[key][4] in proc.stdout
    assert token not in proc.stdout + proc.stderr


def test_no_workflow_prints_a_webhook_response_body():
    """Static guard for the next copy of this snippet."""
    offenders = [
        path.name
        for path in sorted(WORKFLOWS.glob("*.y*ml"))
        if "$(cat /tmp/resp" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"workflows still print a raw webhook response: {offenders}"
