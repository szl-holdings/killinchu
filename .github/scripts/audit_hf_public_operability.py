#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Strict, secret-free operability audit for the SZLHOLDINGS Hugging Face estate.

Runtime stage alone is not enough to call a Space operational. This audit checks
all authenticated Space metadata and, for every externally accessible Space,
verifies the configured entrypoint and the public embed origin independently.
It is read-only and records no source contents, tokens, cookies, or response
bodies.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from typing import Any
from urllib.parse import quote

import requests
import yaml
from huggingface_hub import HfApi

ORG_DEFAULT = "SZLHOLDINGS"
GOOD_HTTP = set(range(200, 400))
TRANSITION_STAGES = {
    "BUILDING",
    "RUNNING_BUILDING",
    "APP_STARTING",
    "RUNNING_APP_STARTING",
    "STARTING",
    "RESTARTING",
}
ERROR_STAGES = {
    "BUILD_ERROR",
    "RUNTIME_ERROR",
    "CONFIG_ERROR",
    "NO_APP_FILE",
    "ERROR",
    "FAILED",
    "CRASHED",
}
INACTIVE_TAGS = {"deprecated", "superseded", "archived", "historical"}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def clean(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    rendered = str(value).strip()
    return rendered or None


def stage(value: Any) -> str:
    rendered = clean(value)
    return (rendered or "UNKNOWN").upper().replace("-", "_").replace(" ", "_")


def redact_error(exc: BaseException, token: str | None = None) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if token:
        text = text.replace(token, "***")
    text = re.sub(r"hf_[A-Za-z0-9]{20,}", "***", text)
    return text[:600]


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def origin(repo_id: str) -> str:
    owner, name = repo_id.split("/", 1)
    return f"https://{slug(owner)}-{slug(name)}.hf.space/"


def request_status(
    url: str,
    *,
    token: str | None = None,
    timeout: float = 12.0,
) -> dict[str, Any]:
    headers = {
        "User-Agent": "szl-hf-public-operability-audit/1",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.1",
        "Cache-Control": "no-cache",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
            stream=True,
        )
        status_code = int(response.status_code)
        content_type = (response.headers.get("content-type") or "").split(";", 1)[0]
        final_url = response.url
        response.close()
        return {
            "status": status_code,
            "good": status_code in GOOD_HTTP,
            "content_type": content_type or None,
            "final_host": requests.utils.urlparse(final_url).hostname,
            "error": None,
        }
    except requests.RequestException as exc:
        return {
            "status": None,
            "good": False,
            "content_type": None,
            "final_host": None,
            "error": redact_error(exc, token),
        }


def api_json(
    session: requests.Session,
    token: str,
    path: str,
) -> tuple[int, Any]:
    url = f"https://huggingface.co{path}"
    response = session.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "szl-hf-public-operability-audit/1",
        },
        timeout=30,
    )
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None
    finally:
        response.close()


def raw_text(
    session: requests.Session,
    token: str,
    repo_id: str,
    path: str,
) -> tuple[int, str | None]:
    url = (
        "https://huggingface.co/spaces/"
        f"{repo_id}/raw/main/{quote(path, safe='/')}"
    )
    response = session.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "szl-hf-public-operability-audit/1",
        },
        timeout=30,
        allow_redirects=True,
    )
    try:
        if response.status_code != 200:
            return response.status_code, None
        # README/frontmatter is bounded; source contents never enter the report.
        return response.status_code, response.text[:262144]
    finally:
        response.close()


def parse_frontmatter(text: str | None) -> dict[str, Any]:
    if not text or not text.startswith("---"):
        return {}
    match = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", text, flags=re.S)
    if not match:
        return {}
    try:
        parsed = yaml.safe_load(match.group(1)) or {}
        return parsed if isinstance(parsed, dict) else {}
    except yaml.YAMLError:
        return {"_parse_error": True}


def root_tree(
    session: requests.Session,
    token: str,
    repo_id: str,
) -> dict[str, Any]:
    status_code, body = api_json(
        session,
        token,
        f"/api/spaces/{repo_id}/tree/main?recursive=false&expand=false",
    )
    names: list[str] = []
    if status_code == 200 and isinstance(body, list):
        for row in body:
            if isinstance(row, dict) and row.get("path"):
                names.append(str(row["path"]))
    return {
        "status": status_code,
        "root_paths": sorted(names),
        "root_path_count": len(names),
    }


def runtime(api: HfApi, repo_id: str, sdk: str, token: str) -> dict[str, Any]:
    if sdk == "static":
        return {
            "stage": "RUNNING_STATIC",
            "hardware": None,
            "requested_hardware": None,
            "error": None,
        }
    try:
        value = api.get_space_runtime(repo_id=repo_id)
        return {
            "stage": stage(getattr(value, "stage", None)),
            "hardware": clean(getattr(value, "hardware", None)),
            "requested_hardware": clean(
                getattr(value, "requested_hardware", None)
            ),
            "error": None,
        }
    except Exception as exc:
        return {
            "stage": "RUNTIME_LOOKUP_ERROR",
            "hardware": None,
            "requested_hardware": None,
            "error": redact_error(exc, token),
        }


def infer_visibility(info: Any, detail: dict[str, Any]) -> str:
    explicit = clean(detail.get("visibility"))
    if explicit:
        return explicit.lower()
    if bool(detail.get("private", getattr(info, "private", False))):
        # The public API does not always distinguish protected from private.
        return "nonpublic"
    return "public"


def classify(row: dict[str, Any]) -> tuple[bool, str]:
    tags = {str(tag).lower() for tag in row["tags"]}
    if row["archived"] or row["disabled"] or tags.intersection(INACTIVE_TAGS):
        return True, "INTENTIONALLY_INACTIVE"

    runtime_stage = row["runtime"]["stage"]
    public_probe = row["public_probe"]
    authenticated_probe = row["authenticated_probe"]
    visibility = row["visibility"]
    sdk = row["sdk"]

    if runtime_stage in ERROR_STAGES or runtime_stage == "RUNTIME_LOOKUP_ERROR":
        return False, f"RUNTIME_ERROR:{runtime_stage}"
    if runtime_stage in TRANSITION_STAGES:
        return False, f"RUNTIME_TRANSITION:{runtime_stage}"
    if runtime_stage == "PAUSED":
        return False, "RUNTIME_PAUSED"

    if sdk == "static":
        app_file = row["entrypoint"]["app_file"]
        if not row["entrypoint"]["present"]:
            return False, f"STATIC_ENTRYPOINT_MISSING:{app_file}"
        if visibility == "public" and not public_probe["good"]:
            return False, f"PUBLIC_STATIC_ROOT_HTTP:{public_probe['status']}"
        if visibility != "public" and not authenticated_probe["good"]:
            return False, f"NONPUBLIC_STATIC_ROOT_HTTP:{authenticated_probe['status']}"
        return True, "STATIC_OPERATIONAL"

    if runtime_stage not in {"RUNNING", "SLEEPING", "STOPPED"}:
        return False, f"RUNTIME_UNKNOWN:{runtime_stage}"

    if visibility == "public":
        if public_probe["good"]:
            return True, "PUBLIC_OPERATIONAL"
        if public_probe["status"] in {401, 403} and authenticated_probe["good"]:
            return False, f"PUBLIC_ROOT_AUTH_GATED:{public_probe['status']}"
        return False, f"PUBLIC_ROOT_HTTP:{public_probe['status']}"

    # Protected/private Spaces are not declared public. A successful authenticated
    # origin request proves the app; otherwise a RUNNING runtime plus an edge
    # response still proves provider execution without claiming public access.
    if authenticated_probe["good"]:
        return True, "NONPUBLIC_OPERATIONAL_AUTHENTICATED"
    if runtime_stage in {"RUNNING", "SLEEPING", "STOPPED"} and (
        public_probe["status"] is not None
    ):
        return True, "NONPUBLIC_RUNTIME_EDGE_PRESENT"
    return False, "NONPUBLIC_UNREACHABLE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", default=ORG_DEFAULT)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    tokens = [
        value
        for value in (
            os.environ.get("HF_ORG_TOKEN"),
            os.environ.get("HF_TOKEN"),
        )
        if value
    ]
    if not tokens:
        raise SystemExit("no Hugging Face token configured")

    token = None
    whoami: dict[str, Any] = {}
    session = requests.Session()
    for candidate in tokens:
        status_code, body = api_json(session, candidate, "/api/whoami-v2")
        if status_code == 200 and isinstance(body, dict):
            token = candidate
            whoami = body
            break
    if not token:
        raise SystemExit("no configured token authenticated")

    org_role = None
    for org in whoami.get("orgs", []) or []:
        if str(org.get("name", "")).lower() == args.org.lower():
            org_role = org.get("roleInOrg")
            break

    api = HfApi(token=token)
    spaces = list(api.list_spaces(author=args.org, full=True, limit=1000))
    records: list[dict[str, Any]] = []

    for info in sorted(spaces, key=lambda item: str(getattr(item, "id", ""))):
        repo_id = str(getattr(info, "id", "") or getattr(info, "repo_id", ""))
        status_code, detail = api_json(session, token, f"/api/spaces/{repo_id}")
        detail = detail if isinstance(detail, dict) else {}
        sdk = str(detail.get("sdk") or getattr(info, "sdk", "unknown")).lower()
        tags = sorted({str(tag) for tag in (detail.get("tags") or getattr(info, "tags", []) or [])})
        archived = bool(detail.get("archived", getattr(info, "archived", False)))
        disabled = bool(detail.get("disabled", getattr(info, "disabled", False)))
        visibility = infer_visibility(info, detail)
        tree = root_tree(session, token, repo_id)
        readme_status, readme_text = raw_text(session, token, repo_id, "README.md")
        config = parse_frontmatter(readme_text)
        configured_sdk = str(config.get("sdk") or sdk).lower()
        app_file = str(config.get("app_file") or "index.html") if sdk == "static" else None
        paths = set(tree["root_paths"])
        entrypoint_present = bool(app_file and app_file in paths) if sdk == "static" else True
        public_probe = request_status(origin(repo_id))
        authenticated_probe = request_status(origin(repo_id), token=token)

        record = {
            "repo_id": repo_id,
            "sdk": sdk,
            "configured_sdk": configured_sdk,
            "visibility": visibility,
            "private_flag": bool(detail.get("private", getattr(info, "private", False))),
            "gated": clean(detail.get("gated", getattr(info, "gated", None))),
            "archived": archived,
            "disabled": disabled,
            "tags": tags,
            "last_modified": clean(detail.get("lastModified") or getattr(info, "last_modified", None)),
            "detail_api_status": status_code,
            "readme_status": readme_status,
            "frontmatter_present": bool(config),
            "frontmatter_parse_error": bool(config.get("_parse_error")),
            "tree": tree,
            "entrypoint": {
                "app_file": app_file,
                "present": entrypoint_present,
            },
            "runtime": runtime(api, repo_id, sdk, token),
            "public_probe": public_probe,
            "authenticated_probe": authenticated_probe,
        }
        ok, verdict = classify(record)
        record["operational"] = ok
        record["verdict"] = verdict
        records.append(record)

    residual = [record for record in records if not record["operational"]]
    report = {
        "schema": "szl.hf.public_operability_audit.v1",
        "generated_at": now(),
        "organization": args.org,
        "authentication": {
            "identity": whoami.get("name"),
            "type": whoami.get("type"),
            "organization_role": org_role,
        },
        "policy": {
            "read_only": True,
            "source_contents_recorded": False,
            "response_bodies_recorded": False,
            "secrets_recorded": False,
            "runtime_running_is_not_public_operability": True,
        },
        "counts": {
            "spaces": len(records),
            "operational_or_intentionally_inactive": len(records) - len(residual),
            "residual": len(residual),
            "public": sum(record["visibility"] == "public" for record in records),
            "nonpublic": sum(record["visibility"] != "public" for record in records),
            "static": sum(record["sdk"] == "static" for record in records),
        },
        "residual_ids": [record["repo_id"] for record in residual],
        "spaces": records,
    }
    output = json.dumps(report, sort_keys=True, indent=2) + "\n"
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(output)
    print(json.dumps(report["counts"], sort_keys=True))
    for record in residual:
        print(f"RESIDUAL {record['repo_id']} {record['verdict']}")
    return 0 if not residual else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # receipt still must not leak token values
        print(f"fatal: {redact_error(exc)}", file=sys.stderr)
        raise
