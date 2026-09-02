#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recover stalled SZLHOLDINGS Hugging Face Spaces without changing hardware.

The controller is deliberately bounded:
- authenticated inventory of every Space in the organization;
- static, archived, disabled, and explicitly deprecated assets are never restarted;
- sleeping/stopped Spaces are first given a normal visitor wake-up;
- only paused, terminal-error, persistently transitional, or unreachable dynamic
  Spaces are restarted;
- a cache-preserving restart is attempted first;
- one factory reboot is allowed only for a residual broken target;
- hardware, storage, visibility, secrets, variables, and repository files are
  never changed;
- no token, response body, or Space log is written to evidence.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Iterable

import requests
from huggingface_hub import HfApi

ORG_DEFAULT = "SZLHOLDINGS"
STATIC_SDKS = {"static"}
TERMINAL_ERROR_STAGES = {
    "BUILD_ERROR",
    "RUNTIME_ERROR",
    "CONFIG_ERROR",
    "NO_APP_FILE",
    "ERROR",
    "FAILED",
    "CRASHED",
}
PAUSED_STAGES = {"PAUSED"}
WAKEABLE_STAGES = {"SLEEPING", "STOPPED"}
INTERMEDIATE_STAGES = {
    "BUILDING",
    "RUNNING_BUILDING",
    "APP_STARTING",
    "RUNNING_APP_STARTING",
    "STARTING",
    "RESTARTING",
}
RUNNING_STAGES = {"RUNNING"}
DEPRECATED_TAGS = {"deprecated", "superseded", "archived", "historical"}
HTTP_REACHABLE_MAX = 499


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_scalar(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    rendered = str(value).strip()
    return rendered or None


def normalize_stage(value: Any) -> str:
    rendered = normalize_scalar(value)
    if not rendered:
        return "UNKNOWN"
    return rendered.upper().replace("-", "_").replace(" ", "_")


def clean_error(exc: BaseException, token: str | None = None) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if token:
        text = text.replace(token, "***")
    text = re.sub(r"hf_[A-Za-z0-9]{20,}", "***", text)
    return text[:700]


def iso_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def hf_origin(repo_id: str) -> str:
    owner, name = repo_id.split("/", 1)

    def slug(part: str) -> str:
        value = re.sub(r"[^a-z0-9]+", "-", part.lower()).strip("-")
        return value

    return f"https://{slug(owner)}-{slug(name)}.hf.space/"


def probe_origin(origin: str, attempts: int = 2, timeout: float = 7.0) -> dict[str, Any]:
    result: dict[str, Any] = {
        "origin": origin,
        "attempted": True,
        "reachable": False,
        "status": None,
        "error_class": None,
    }
    headers = {
        "User-Agent": "szl-hf-stalled-recovery/1",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.1",
    }
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                origin,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
            )
            status = int(response.status_code)
            response.close()
            result.update(
                {
                    "attempt": attempt,
                    "status": status,
                    # 401/403/404/429 still prove that an application edge answered.
                    "reachable": status <= HTTP_REACHABLE_MAX,
                    "error_class": None if status <= HTTP_REACHABLE_MAX else "HTTPServerError",
                }
            )
            if result["reachable"]:
                return result
        except requests.RequestException as exc:
            result.update(
                {
                    "attempt": attempt,
                    "error_class": type(exc).__name__,
                    "status": None,
                }
            )
        if attempt < attempts:
            time.sleep(2)
    return result


def get_tags(info: Any) -> list[str]:
    raw = getattr(info, "tags", None) or []
    return sorted({str(tag) for tag in raw})


def is_deprecated(tags: Iterable[str], repo_id: str, archived: bool, disabled: bool) -> bool:
    normalized = {str(tag).strip().lower() for tag in tags}
    return bool(
        archived
        or disabled
        or normalized.intersection(DEPRECATED_TAGS)
        or repo_id.lower().endswith("/experiments")
    )


def runtime_snapshot(api: HfApi, repo_id: str, sdk: str, token: str) -> dict[str, Any]:
    if sdk.lower() in STATIC_SDKS:
        return {
            "stage": "RUNNING_STATIC",
            "hardware": None,
            "requested_hardware": None,
            "sleep_time": None,
            "error": None,
        }
    try:
        runtime = api.get_space_runtime(repo_id=repo_id)
        return {
            "stage": normalize_stage(getattr(runtime, "stage", None)),
            "hardware": normalize_scalar(getattr(runtime, "hardware", None)),
            "requested_hardware": normalize_scalar(
                getattr(runtime, "requested_hardware", None)
            ),
            "sleep_time": getattr(runtime, "sleep_time", None),
            "error": None,
        }
    except Exception as exc:
        return {
            "stage": "RUNTIME_LOOKUP_ERROR",
            "hardware": None,
            "requested_hardware": None,
            "sleep_time": None,
            "error": clean_error(exc, token),
        }


def info_snapshot(api: HfApi, info: Any, token: str) -> dict[str, Any]:
    repo_id = str(getattr(info, "id", "") or getattr(info, "repo_id", ""))
    sdk = str(getattr(info, "sdk", "") or "unknown").lower()
    tags = get_tags(info)
    archived = bool(getattr(info, "archived", False))
    disabled = bool(getattr(info, "disabled", False))
    private = bool(getattr(info, "private", False))
    gated = normalize_scalar(getattr(info, "gated", None))
    visibility = normalize_scalar(getattr(info, "visibility", None))
    runtime = runtime_snapshot(api, repo_id, sdk, token)
    return {
        "repo_id": repo_id,
        "sdk": sdk,
        "tags": tags,
        "archived": archived,
        "disabled": disabled,
        "private": private,
        "gated": gated,
        "visibility": visibility,
        "last_modified": iso_value(getattr(info, "last_modified", None)),
        "origin": hf_origin(repo_id),
        "runtime": runtime,
    }


def list_full_spaces(api: HfApi, org: str) -> list[Any]:
    try:
        return list(api.list_spaces(author=org, full=True, limit=1000))
    except TypeError:
        return list(api.list_spaces(author=org, full=True))


def list_asset_count(callable_obj: Any, org: str) -> dict[str, Any]:
    try:
        values = list(callable_obj(author=org, full=True, limit=1000))
        disabled = sum(bool(getattr(item, "disabled", False)) for item in values)
        return {"count": len(values), "disabled": disabled, "error": None}
    except TypeError:
        try:
            values = list(callable_obj(author=org, full=True))
            disabled = sum(bool(getattr(item, "disabled", False)) for item in values)
            return {"count": len(values), "disabled": disabled, "error": None}
        except Exception as exc:
            return {"count": None, "disabled": None, "error": clean_error(exc)}
    except Exception as exc:
        return {"count": None, "disabled": None, "error": clean_error(exc)}


def classify(row: dict[str, Any]) -> str:
    sdk = row["sdk"]
    stage = row["runtime"]["stage"]
    probe = row.get("probe_before") or {}
    if is_deprecated(
        row["tags"], row["repo_id"], row["archived"], row["disabled"]
    ):
        return "INTENTIONALLY_INACTIVE"
    if sdk in STATIC_SDKS:
        return "STATIC_HEALTHY" if probe.get("reachable") else "STATIC_UNREACHABLE"
    if stage in PAUSED_STAGES:
        return "RESTART_REQUIRED_PAUSED"
    if stage in TERMINAL_ERROR_STAGES or stage == "RUNTIME_LOOKUP_ERROR":
        return "RESTART_REQUIRED_ERROR"
    if stage in WAKEABLE_STAGES:
        return "VISITOR_WAKE"
    if stage in INTERMEDIATE_STAGES:
        return "OBSERVE_TRANSITION"
    if stage in RUNNING_STAGES:
        return "HEALTHY" if probe.get("reachable") else "RESTART_REQUIRED_UNREACHABLE"
    if probe.get("reachable"):
        return "HEALTHY_UNKNOWN_STAGE"
    return "RESTART_REQUIRED_UNKNOWN"


def refresh_runtime(api: HfApi, row: dict[str, Any], token: str) -> dict[str, Any]:
    return runtime_snapshot(api, row["repo_id"], row["sdk"], token)


def restart(
    api: HfApi,
    row: dict[str, Any],
    token: str,
    *,
    factory_reboot: bool,
) -> dict[str, Any]:
    started = utcnow()
    try:
        runtime = api.restart_space(
            repo_id=row["repo_id"], factory_reboot=factory_reboot
        )
        return {
            "kind": "factory_reboot" if factory_reboot else "restart",
            "started_at": started,
            "accepted": True,
            "response_stage": normalize_stage(getattr(runtime, "stage", None)),
            "error": None,
        }
    except Exception as exc:
        return {
            "kind": "factory_reboot" if factory_reboot else "restart",
            "started_at": started,
            "accepted": False,
            "response_stage": None,
            "error": clean_error(exc, token),
        }


def settle_candidates(
    api: HfApi,
    rows: list[dict[str, Any]],
    token: str,
    settle_seconds: int,
) -> None:
    candidates = [
        row
        for row in rows
        if row["classification_before"] in {"VISITOR_WAKE", "OBSERVE_TRANSITION"}
    ]
    if not candidates:
        return
    time.sleep(settle_seconds)
    for row in candidates:
        previous_stage = row["runtime"]["stage"]
        current = refresh_runtime(api, row, token)
        row["runtime_after_settle"] = current
        if row["sdk"] not in STATIC_SDKS:
            row["probe_after_settle"] = probe_origin(row["origin"], attempts=1)
        else:
            row["probe_after_settle"] = row.get("probe_before")
        current_stage = current["stage"]
        reachable = bool((row.get("probe_after_settle") or {}).get("reachable"))
        progressed = current_stage != previous_stage
        row["settle_progressed"] = progressed
        if current_stage == "RUNNING" and reachable:
            row["classification_after_settle"] = "RECOVERED_BY_WAKE_OR_PROGRESS"
        elif current_stage in INTERMEDIATE_STAGES and progressed:
            row["classification_after_settle"] = "PROGRESSING"
        elif current_stage in TERMINAL_ERROR_STAGES | PAUSED_STAGES:
            row["classification_after_settle"] = "RESTART_REQUIRED_ERROR"
        elif current_stage in WAKEABLE_STAGES:
            row["classification_after_settle"] = "RESTART_REQUIRED_SLEEP_STUCK"
        elif current_stage in INTERMEDIATE_STAGES:
            row["classification_after_settle"] = "RESTART_REQUIRED_TRANSITION_STUCK"
        elif reachable:
            row["classification_after_settle"] = "HEALTHY_UNKNOWN_STAGE"
        else:
            row["classification_after_settle"] = "RESTART_REQUIRED_UNKNOWN"


def should_restart(row: dict[str, Any]) -> bool:
    final_class = row.get("classification_after_settle") or row["classification_before"]
    return final_class.startswith("RESTART_REQUIRED_")


def poll_targets(
    api: HfApi,
    targets: list[dict[str, Any]],
    token: str,
    *,
    timeout_seconds: int,
    poll_seconds: int,
    phase: str,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    pending = {row["repo_id"]: row for row in targets}
    while pending and time.monotonic() < deadline:
        for repo_id, row in list(pending.items()):
            runtime = refresh_runtime(api, row, token)
            observation = {
                "observed_at": utcnow(),
                "phase": phase,
                "stage": runtime["stage"],
                "error": runtime.get("error"),
            }
            row.setdefault("observations", []).append(observation)
            stage = runtime["stage"]
            if stage == "RUNNING":
                probe = probe_origin(row["origin"], attempts=1)
                observation["probe"] = probe
                if probe.get("reachable"):
                    row["after"] = {"runtime": runtime, "probe": probe}
                    row["result"] = "RECOVERED"
                    pending.pop(repo_id, None)
            elif stage in TERMINAL_ERROR_STAGES | PAUSED_STAGES:
                row["after"] = {"runtime": runtime, "probe": None}
                row["result"] = "TERMINAL_ERROR"
                pending.pop(repo_id, None)
        if pending:
            time.sleep(poll_seconds)

    for repo_id, row in pending.items():
        runtime = refresh_runtime(api, row, token)
        probe = probe_origin(row["origin"], attempts=1)
        row["after"] = {"runtime": runtime, "probe": probe}
        row["result"] = "TIMEOUT"


def final_assessment(row: dict[str, Any]) -> tuple[bool, str]:
    if row["classification_before"] == "INTENTIONALLY_INACTIVE":
        return True, "INTENTIONALLY_INACTIVE"
    if row["sdk"] in STATIC_SDKS:
        reachable = bool((row.get("probe_before") or {}).get("reachable"))
        return reachable, "STATIC_HEALTHY" if reachable else "STATIC_UNREACHABLE"

    after = row.get("after")
    if after:
        stage = after["runtime"]["stage"]
        reachable = bool((after.get("probe") or {}).get("reachable"))
    else:
        stage = (
            row.get("runtime_after_settle", row["runtime"])
            .get("stage", "UNKNOWN")
        )
        probe = row.get("probe_after_settle") or row.get("probe_before") or {}
        reachable = bool(probe.get("reachable"))

    if stage == "RUNNING" and reachable:
        return True, "RUNNING_REACHABLE"
    if stage in WAKEABLE_STAGES and reachable:
        return True, "WAKEABLE_EDGE_REACHABLE"
    if stage in INTERMEDIATE_STAGES:
        return False, f"TRANSITION_NOT_TERMINAL:{stage}"
    if stage in TERMINAL_ERROR_STAGES | PAUSED_STAGES:
        return False, stage
    if reachable:
        return True, f"REACHABLE_STAGE:{stage}"
    return False, f"UNREACHABLE_STAGE:{stage}"


def write_summary(report: dict[str, Any]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    counts = report["counts"]
    lines = [
        "# SZLHOLDINGS stalled-Space recovery",
        "",
        f"- Observed Spaces: **{counts['spaces']}**",
        f"- Restart targets: **{counts['restart_targets']}**",
        f"- Normal restarts accepted: **{counts['normal_restarts_accepted']}**",
        f"- Factory reboots accepted: **{counts['factory_reboots_accepted']}**",
        f"- Recovered targets: **{counts['recovered_targets']}**",
        f"- Residual operational blockers: **{counts['residual']}**",
        f"- Intentionally inactive/deprecated: **{counts['intentionally_inactive']}**",
        "",
        "| Space | Before | Action | After | Result |",
        "|---|---|---|---|---|",
    ]
    for row in report["spaces"]:
        actions = ", ".join(
            action["kind"] + (" accepted" if action["accepted"] else " rejected")
            for action in row.get("actions", [])
        ) or "none"
        after_stage = (
            ((row.get("after") or {}).get("runtime") or {}).get("stage")
            or (row.get("runtime_after_settle") or {}).get("stage")
            or row["runtime"]["stage"]
        )
        lines.append(
            f"| `{row['repo_id']}` | `{row['runtime']['stage']}` | "
            f"{actions} | `{after_stage}` | `{row.get('final_state', 'UNKNOWN')}` |"
        )
    if report["residual"]:
        lines.extend(["", "## Residual blockers"])
        for residual in report["residual"]:
            lines.append(
                f"- `{residual['repo_id']}` — `{residual['state']}`"
            )
    path = Path(summary_path)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(existing + "\n".join(lines) + "\n", encoding="utf-8")


def self_test() -> None:
    base = {
        "repo_id": "SZLHOLDINGS/demo",
        "sdk": "docker",
        "tags": [],
        "archived": False,
        "disabled": False,
        "runtime": {"stage": "RUNNING"},
        "probe_before": {"reachable": True},
    }
    assert classify(dict(base)) == "HEALTHY"
    paused = dict(base)
    paused["runtime"] = {"stage": "PAUSED"}
    assert classify(paused) == "RESTART_REQUIRED_PAUSED"
    static = dict(base)
    static["sdk"] = "static"
    assert classify(static) == "STATIC_HEALTHY"
    deprecated = dict(base)
    deprecated["tags"] = ["deprecated"]
    assert classify(deprecated) == "INTENTIONALLY_INACTIVE"
    assert hf_origin("SZLHOLDINGS/llm_router.live") == (
        "https://szlholdings-llm-router-live.hf.space/"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", default=ORG_DEFAULT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settle-seconds", type=int, default=75)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--normal-timeout-seconds", type=int, default=600)
    parser.add_argument("--factory-timeout-seconds", type=int, default=900)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("self-test: PASS")
        return 0

    token = os.environ.get("HF_ORG_TOKEN") or os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_ORG_TOKEN/HF_TOKEN is not configured")

    report: dict[str, Any] = {
        "schema": "szl.hf-stalled-recovery/v1",
        "started_at": utcnow(),
        "organization": args.org,
        "policy": {
            "hardware_changed": False,
            "storage_changed": False,
            "visibility_changed": False,
            "secrets_changed": False,
            "space_files_changed": False,
            "static_spaces_restarted": False,
            "normal_restart_first": True,
            "factory_reboot_limit_per_target": 1,
        },
        "authentication": {},
        "asset_inventory": {},
        "spaces": [],
        "residual": [],
        "fatal_error": None,
    }

    try:
        api = HfApi(token=token)
        who = api.whoami(token=token)
        orgs = who.get("orgs", []) if isinstance(who, dict) else []
        org_row = next(
            (
                item
                for item in orgs
                if str(item.get("name", "")).lower() == args.org.lower()
            ),
            None,
        )
        report["authentication"] = {
            "identity": who.get("name") or who.get("fullname") or who.get("type"),
            "type": who.get("type"),
            "organization_visible": org_row is not None,
            "organization_role": (org_row or {}).get("roleInOrg"),
        }

        infos = list_full_spaces(api, args.org)
        infos = sorted(
            (
                info
                for info in infos
                if str(getattr(info, "id", "")).lower().startswith(
                    args.org.lower() + "/"
                )
            ),
            key=lambda info: str(getattr(info, "id", "")).lower(),
        )
        report["asset_inventory"] = {
            "models": list_asset_count(api.list_models, args.org),
            "datasets": list_asset_count(api.list_datasets, args.org),
        }

        rows = [info_snapshot(api, info, token) for info in infos]

        # Probe every public application edge in parallel. No bearer token is sent
        # to a Space origin.
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(probe_origin, row["origin"]): row for row in rows
            }
            for future in concurrent.futures.as_completed(futures):
                row = futures[future]
                try:
                    row["probe_before"] = future.result()
                except Exception as exc:
                    row["probe_before"] = {
                        "origin": row["origin"],
                        "attempted": True,
                        "reachable": False,
                        "status": None,
                        "error_class": type(exc).__name__,
                    }

        for row in rows:
            row["actions"] = []
            row["classification_before"] = classify(row)

        settle_candidates(api, rows, token, args.settle_seconds)

        targets = [row for row in rows if should_restart(row)]
        for row in targets:
            action = restart(api, row, token, factory_reboot=False)
            row["actions"].append(action)

        accepted_normal = [
            row
            for row in targets
            if row["actions"] and row["actions"][-1]["accepted"]
        ]
        poll_targets(
            api,
            accepted_normal,
            token,
            timeout_seconds=args.normal_timeout_seconds,
            poll_seconds=args.poll_seconds,
            phase="normal_restart",
        )

        # A single cacheless rebuild is allowed only for still-broken dynamic
        # targets. It does not alter source, settings, or hardware.
        factory_targets = []
        for row in targets:
            ok, _ = final_assessment(row)
            if not ok:
                action = restart(api, row, token, factory_reboot=True)
                row["actions"].append(action)
                if action["accepted"]:
                    factory_targets.append(row)

        poll_targets(
            api,
            factory_targets,
            token,
            timeout_seconds=args.factory_timeout_seconds,
            poll_seconds=args.poll_seconds,
            phase="factory_reboot",
        )

        residual = []
        for row in rows:
            ok, state = final_assessment(row)
            row["final_ok"] = ok
            row["final_state"] = state
            if not ok:
                residual.append(
                    {
                        "repo_id": row["repo_id"],
                        "state": state,
                        "sdk": row["sdk"],
                        "before_stage": row["runtime"]["stage"],
                        "actions": [
                            {
                                "kind": action["kind"],
                                "accepted": action["accepted"],
                                "response_stage": action["response_stage"],
                                "error": action["error"],
                            }
                            for action in row.get("actions", [])
                        ],
                        "after": row.get("after"),
                    }
                )

        report["spaces"] = rows
        report["residual"] = residual
        report["counts"] = {
            "spaces": len(rows),
            "restart_targets": len(targets),
            "normal_restarts_accepted": sum(
                bool(row["actions"] and row["actions"][0]["accepted"])
                for row in targets
            ),
            "factory_reboots_accepted": len(factory_targets),
            "recovered_targets": sum(
                row.get("final_ok", False) for row in targets
            ),
            "residual": len(residual),
            "intentionally_inactive": sum(
                row["classification_before"] == "INTENTIONALLY_INACTIVE"
                for row in rows
            ),
            "static": sum(row["sdk"] in STATIC_SDKS for row in rows),
        }
        report["completed_at"] = utcnow()
        report["terminal_green"] = not residual
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_summary(report)

        print(
            json.dumps(
                {
                    "organization": args.org,
                    "counts": report["counts"],
                    "terminal_green": report["terminal_green"],
                    "residual": [
                        {"repo_id": row["repo_id"], "state": row["state"]}
                        for row in residual
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if not residual else 2
    except Exception as exc:
        report["fatal_error"] = clean_error(exc, token)
        report["completed_at"] = utcnow()
        report["terminal_green"] = False
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(report["fatal_error"], file=sys.stderr)
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
