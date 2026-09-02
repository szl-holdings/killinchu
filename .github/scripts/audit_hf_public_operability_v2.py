#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Authoritative-host operability audit for SZLHOLDINGS Hugging Face Spaces.

The Hub exposes a stable `host`/`subdomain` for each Space. This audit uses that
provider metadata instead of synthesizing a hostname from the current repo id,
which would falsely label moved or renamed Spaces as 404. It is read-only and
records no source contents, response bodies, cookies, or secrets.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from typing import Any
from urllib.parse import quote, urlparse

import requests
import yaml
from huggingface_hub import HfApi

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


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def scalar(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    rendered = str(value).strip()
    return rendered or None


def normalized_stage(value: Any) -> str:
    rendered = scalar(value)
    return (rendered or "UNKNOWN").upper().replace("-", "_").replace(" ", "_")


def scrub(exc: BaseException, token: str | None = None) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if token:
        text = text.replace(token, "***")
    return re.sub(r"hf_[A-Za-z0-9]{20,}", "***", text)[:600]


def fallback_subdomain(repo_id: str) -> str:
    owner, name = repo_id.split("/", 1)
    slug = lambda value: re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return f"{slug(owner)}-{slug(name)}"


def normalize_origin(
    repo_id: str,
    info: Any,
    detail: dict[str, Any],
) -> tuple[str, str, str]:
    host = scalar(detail.get("host") or getattr(info, "host", None))
    subdomain = scalar(detail.get("subdomain") or getattr(info, "subdomain", None))
    source = "provider"

    if host:
        if host.startswith("http://") or host.startswith("https://"):
            return host.rstrip("/") + "/", subdomain or urlparse(host).hostname or "", source
        return f"https://{host.strip('/')}/", subdomain or host.split(".", 1)[0], source

    if subdomain:
        if subdomain.startswith("http://") or subdomain.startswith("https://"):
            return subdomain.rstrip("/") + "/", urlparse(subdomain).hostname or "", source
        if "." in subdomain:
            return f"https://{subdomain.strip('/')}/", subdomain.split(".", 1)[0], source
        return f"https://{subdomain}.hf.space/", subdomain, source

    guessed = fallback_subdomain(repo_id)
    return f"https://{guessed}.hf.space/", guessed, "fallback"


def http_probe(url: str, token: str | None = None) -> dict[str, Any]:
    headers = {
        "User-Agent": "szl-hf-public-operability-audit/2",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.1",
        "Cache-Control": "no-cache",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=15,
            allow_redirects=True,
            stream=True,
        )
        status = int(response.status_code)
        final_host = urlparse(response.url).hostname
        content_type = (response.headers.get("content-type") or "").split(";", 1)[0]
        response.close()
        return {
            "status": status,
            "good": status in GOOD_HTTP,
            "final_host": final_host,
            "content_type": content_type or None,
            "error": None,
        }
    except requests.RequestException as exc:
        return {
            "status": None,
            "good": False,
            "final_host": None,
            "content_type": None,
            "error": scrub(exc, token),
        }


def get_json(
    session: requests.Session,
    token: str,
    path: str,
) -> tuple[int, Any]:
    response = session.get(
        f"https://huggingface.co{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "szl-hf-public-operability-audit/2",
        },
        timeout=30,
    )
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None
    finally:
        response.close()


def get_raw(
    session: requests.Session,
    token: str,
    repo_id: str,
    path: str,
) -> tuple[int, str | None]:
    response = session.get(
        "https://huggingface.co/spaces/"
        f"{repo_id}/raw/main/{quote(path, safe='/')}",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "szl-hf-public-operability-audit/2",
        },
        timeout=30,
        allow_redirects=True,
    )
    try:
        return (
            (response.status_code, response.text[:262144])
            if response.status_code == 200
            else (response.status_code, None)
        )
    finally:
        response.close()


def frontmatter(text: str | None) -> dict[str, Any]:
    if not text or not text.startswith("---"):
        return {}
    match = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", text, re.S)
    if not match:
        return {}
    try:
        value = yaml.safe_load(match.group(1)) or {}
        return value if isinstance(value, dict) else {}
    except yaml.YAMLError:
        return {"_parse_error": True}


def tree_root(
    session: requests.Session,
    token: str,
    repo_id: str,
) -> dict[str, Any]:
    status, body = get_json(
        session,
        token,
        f"/api/spaces/{repo_id}/tree/main?recursive=false&expand=false",
    )
    paths = sorted(
        str(row["path"])
        for row in (body if isinstance(body, list) else [])
        if isinstance(row, dict) and row.get("path")
    )
    return {"status": status, "root_paths": paths, "root_path_count": len(paths)}


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
            "stage": normalized_stage(getattr(value, "stage", None)),
            "hardware": scalar(getattr(value, "hardware", None)),
            "requested_hardware": scalar(
                getattr(value, "requested_hardware", None)
            ),
            "error": None,
        }
    except Exception as exc:
        return {
            "stage": "RUNTIME_LOOKUP_ERROR",
            "hardware": None,
            "requested_hardware": None,
            "error": scrub(exc, token),
        }


def visibility(
    detail: dict[str, Any],
    info: Any,
    public_probe: dict[str, Any],
) -> str:
    explicit = scalar(detail.get("visibility"))
    if explicit:
        return explicit.lower()
    private = bool(detail.get("private", getattr(info, "private", False)))
    if not private:
        return "public"
    # HF's `private` flag covers both private and protected in some API shapes.
    # Protected apps remain reachable anonymously; fully private apps return 404.
    if public_probe["good"]:
        return "protected"
    if public_probe["status"] == 404:
        return "private"
    return "nonpublic"


def verdict(row: dict[str, Any]) -> tuple[bool, str]:
    tags = {tag.lower() for tag in row["tags"]}
    if row["archived"] or row["disabled"] or tags.intersection(INACTIVE_TAGS):
        return True, "INTENTIONALLY_INACTIVE"

    sdk = row["sdk"]
    runtime_stage = row["runtime"]["stage"]
    public_probe = row["public_probe"]
    auth_probe = row["authenticated_probe"]
    vis = row["visibility"]

    if runtime_stage in ERROR_STAGES or runtime_stage == "RUNTIME_LOOKUP_ERROR":
        return False, f"RUNTIME_ERROR:{runtime_stage}"
    if runtime_stage in TRANSITION_STAGES:
        return False, f"RUNTIME_TRANSITION:{runtime_stage}"
    if runtime_stage == "PAUSED":
        return False, "RUNTIME_PAUSED"

    if sdk == "static":
        if not row["entrypoint"]["present"]:
            return False, f"STATIC_ENTRYPOINT_MISSING:{row['entrypoint']['app_file']}"
        if vis in {"public", "protected"} and not public_probe["good"]:
            return False, f"EXTERNAL_STATIC_ROOT_HTTP:{public_probe['status']}"
        if vis == "private":
            # Private embed roots are expected to be hidden; source + entrypoint
            # existence is the appropriate static deployment contract.
            return True, "PRIVATE_STATIC_SOURCE_READY"
        return True, "STATIC_OPERATIONAL"

    if runtime_stage not in {"RUNNING", "SLEEPING", "STOPPED"}:
        return False, f"RUNTIME_UNKNOWN:{runtime_stage}"

    if vis in {"public", "protected"}:
        if public_probe["good"]:
            return True, "EXTERNAL_OPERATIONAL"
        if public_probe["status"] in {401, 403} and auth_probe["good"]:
            return False, f"EXTERNAL_ROOT_AUTH_GATED:{public_probe['status']}"
        return False, f"EXTERNAL_ROOT_HTTP:{public_probe['status']}"

    if vis == "private":
        if runtime_stage in {"RUNNING", "SLEEPING", "STOPPED"}:
            return True, "PRIVATE_RUNTIME_HEALTHY"
    if auth_probe["good"]:
        return True, "NONPUBLIC_OPERATIONAL_AUTHENTICATED"
    return False, "NONPUBLIC_UNREACHABLE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", default="SZLHOLDINGS")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    configured = [
        value
        for value in (
            os.environ.get("HF_ORG_TOKEN"),
            os.environ.get("HF_TOKEN"),
        )
        if value
    ]
    if not configured:
        raise SystemExit("no Hugging Face token configured")

    session = requests.Session()
    token = None
    identity: dict[str, Any] = {}
    for candidate in configured:
        status, value = get_json(session, candidate, "/api/whoami-v2")
        if status == 200 and isinstance(value, dict):
            token = candidate
            identity = value
            break
    if not token:
        raise SystemExit("no configured token authenticated")

    role = next(
        (
            org.get("roleInOrg")
            for org in identity.get("orgs", []) or []
            if str(org.get("name", "")).lower() == args.org.lower()
        ),
        None,
    )
    api = HfApi(token=token)
    spaces = list(api.list_spaces(author=args.org, full=True, limit=1000))
    records: list[dict[str, Any]] = []

    for item in sorted(spaces, key=lambda value: str(getattr(value, "id", ""))):
        repo_id = str(getattr(item, "id", "") or getattr(item, "repo_id", ""))
        detail_status, raw_detail = get_json(session, token, f"/api/spaces/{repo_id}")
        detail = raw_detail if isinstance(raw_detail, dict) else {}

        # space_info can expose authoritative subdomain/host even if list_spaces
        # omitted it. Failure falls back to the already authenticated list row.
        try:
            expanded = api.space_info(
                repo_id=repo_id,
                expand=[
                    "subdomain",
                    "sdk",
                    "runtime",
                    "private",
                    "cardData",
                    "disabled",
                    "tags",
                    "sha",
                    "lastModified",
                ],
            )
        except Exception:
            expanded = item

        sdk = str(
            detail.get("sdk")
            or getattr(expanded, "sdk", None)
            or getattr(item, "sdk", "unknown")
        ).lower()
        tags = sorted(
            {
                str(tag)
                for tag in (
                    detail.get("tags")
                    or getattr(expanded, "tags", None)
                    or getattr(item, "tags", [])
                    or []
                )
            }
        )
        archived = bool(detail.get("archived", getattr(item, "archived", False)))
        disabled = bool(
            detail.get(
                "disabled",
                getattr(expanded, "disabled", getattr(item, "disabled", False)),
            )
        )
        tree = tree_root(session, token, repo_id)
        readme_status, readme = get_raw(session, token, repo_id, "README.md")
        config = frontmatter(readme)
        configured_sdk = str(config.get("sdk") or sdk).lower()
        app_file = (
            str(config.get("app_file") or "index.html") if sdk == "static" else None
        )
        entrypoint_present = (
            bool(app_file and app_file in set(tree["root_paths"]))
            if sdk == "static"
            else True
        )

        resolved_origin, subdomain, origin_source = normalize_origin(
            repo_id,
            expanded,
            detail,
        )
        public_probe = http_probe(resolved_origin)
        auth_probe = http_probe(resolved_origin, token)
        vis = visibility(detail, expanded, public_probe)

        record = {
            "repo_id": repo_id,
            "sha": scalar(detail.get("sha") or getattr(expanded, "sha", None)),
            "sdk": sdk,
            "configured_sdk": configured_sdk,
            "visibility": vis,
            "private_flag": bool(
                detail.get("private", getattr(expanded, "private", False))
            ),
            "gated": scalar(detail.get("gated", getattr(expanded, "gated", None))),
            "archived": archived,
            "disabled": disabled,
            "tags": tags,
            "last_modified": scalar(
                detail.get("lastModified")
                or getattr(expanded, "last_modified", None)
            ),
            "detail_api_status": detail_status,
            "origin": resolved_origin,
            "origin_source": origin_source,
            "subdomain": subdomain,
            "readme_status": readme_status,
            "frontmatter": {
                "present": bool(config),
                "parse_error": bool(config.get("_parse_error")),
                "sdk": scalar(config.get("sdk")),
                "app_file": scalar(config.get("app_file")),
                "app_build_command_present": bool(config.get("app_build_command")),
                "base_path": scalar(config.get("base_path")),
                "pinned": config.get("pinned") if "pinned" in config else None,
            },
            "tree": tree,
            "entrypoint": {"app_file": app_file, "present": entrypoint_present},
            "runtime": runtime(api, repo_id, sdk, token),
            "public_probe": public_probe,
            "authenticated_probe": auth_probe,
        }
        operational, state = verdict(record)
        record["operational"] = operational
        record["verdict"] = state
        records.append(record)

    residual = [row for row in records if not row["operational"]]
    report = {
        "schema": "szl.hf.public_operability_audit.v2",
        "generated_at": utcnow(),
        "organization": args.org,
        "authentication": {
            "identity": identity.get("name"),
            "type": identity.get("type"),
            "organization_role": role,
        },
        "policy": {
            "read_only": True,
            "authoritative_provider_origins": True,
            "fallback_origins": sum(row["origin_source"] == "fallback" for row in records),
            "source_contents_recorded": False,
            "response_bodies_recorded": False,
            "secrets_recorded": False,
        },
        "counts": {
            "spaces": len(records),
            "public": sum(row["visibility"] == "public" for row in records),
            "protected": sum(row["visibility"] == "protected" for row in records),
            "private": sum(row["visibility"] == "private" for row in records),
            "static": sum(row["sdk"] == "static" for row in records),
            "operational_or_intentionally_inactive": len(records) - len(residual),
            "residual": len(residual),
        },
        "residual_ids": [row["repo_id"] for row in residual],
        "spaces": records,
    }
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, sort_keys=True, indent=2)
        handle.write("\n")

    print(json.dumps(report["counts"], sort_keys=True))
    for row in residual:
        print(
            f"RESIDUAL {row['repo_id']} {row['verdict']} "
            f"origin_source={row['origin_source']} host={urlparse(row['origin']).hostname}"
        )
    return 0 if not residual else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"fatal: {scrub(exc)}", file=sys.stderr)
        raise
