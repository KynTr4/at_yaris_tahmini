"""Fail-closed VPS healthcheck for the SQLite shadow deployment."""
from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from app_config import (
    BACKUP_DIR, DB_PATH, LOG_DIR, PROJECT_ROOT, REPORTS_DIR,
    WEB_PASSWORD, WEB_PORT, WEB_USERNAME, ensure_runtime_dirs,
)
from feature_contract import MODEL_FEATURES, validate_model_feature_contract
from shadow_monitor import load_history, snapshot_coverage_pass
from validate_feature_provenance import validate as validate_provenance


def recent_json(name: str, max_age_hours: float) -> tuple[bool, str]:
    path = LOG_DIR / f"{name}_latest.json"
    if not path.exists():
        return False, f"missing: {path.name}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        ended = datetime.fromisoformat(payload["ended_at"].replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - ended.astimezone(timezone.utc)
        status_value = str(payload.get("status") or "")
        acceptable = status_value.lower() in {
            "success", "warning", "skipped_already_running"
        }
        ok = acceptable and age <= timedelta(hours=max_age_hours)
        return ok, f"status={payload.get('status')}, age_hours={age.total_seconds()/3600:.2f}"
    except Exception as exc:
        return False, f"invalid JSON: {exc}"


def check_logs() -> tuple[bool, str]:
    cutoff = datetime.now().timestamp() - 24 * 3600
    findings = []
    for path in LOG_DIR.glob("*.err.log"):
        if path.stat().st_mtime >= cutoff and path.stat().st_size:
            text = path.read_text(encoding="utf-8", errors="replace")[-20000:]
            if re.search(r"\b(ERROR|CRITICAL|Traceback)\b", text, re.I):
                findings.append(path.name)
    return not findings, "none" if not findings else ", ".join(findings)


def check_web() -> list[tuple[str, bool, str]]:
    checks = []
    if platform.system() == "Linux" and shutil.which("systemctl"):
        process = subprocess.run(
            ["systemctl", "is-active", "at-yaris-web.service"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        service_state = process.stdout.strip() or "unknown"
        checks.append(("web_service", service_state == "active", f"state={service_state}"))
    else:
        checks.append(("web_service", False, "systemd unavailable on this host"))

    url = f"http://127.0.0.1:{WEB_PORT}/api/health"
    try:
        urllib.request.urlopen(url, timeout=5)
        unauth_status = 200
    except urllib.error.HTTPError as exc:
        unauth_status = exc.code
    except Exception as exc:
        unauth_status = 0
        unauth_error = str(exc)
    checks.append((
        "web_basic_auth", unauth_status == 401,
        f"unauthenticated_status={unauth_status}" + (f", error={unauth_error}" if unauth_status == 0 else ""),
    ))

    token = base64.b64encode(f"{WEB_USERNAME}:{WEB_PASSWORD}".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
            api_ok = response.status == 200 and "status" in body
            api_detail = f"status={response.status}, dashboard={body.get('status')}"
    except Exception as exc:
        api_ok, api_detail = False, str(exc)
    checks.append(("web_api", api_ok, api_detail))
    return checks


def run_checks() -> list[dict[str, object]]:
    ensure_runtime_dirs(); checks = []
    def add(name, ok, detail, critical=True):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "critical": critical, "detail": detail})

    try:
        connection = sqlite3.connect(str(DB_PATH), timeout=10)
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        add("database", quick == "ok", f"quick_check={quick}")
        agf_late = connection.execute(
            """SELECT COUNT(*) FROM agf_snapshots a
               JOIN program_snapshots p ON p.race_id=a.race_id AND p.horse_id=a.horse_id
               WHERE a.source_endpoint='TJK_AGFv2'
                 AND julianday(a.captured_at)>=julianday(p.race_start_at)"""
        ).fetchone()[0]
        add("agf_pre_race", agf_late == 0, f"late_tjk_agf_snapshots={agf_late}")
        latest_prediction = connection.execute("SELECT MAX(prediction_time) FROM prediction_snapshots").fetchone()[0]
        recent_program = connection.execute(
            "SELECT COUNT(*) FROM program_snapshots WHERE julianday(race_start_at)>=julianday('now','-24 hours')"
        ).fetchone()[0]
        connection.close()
        if latest_prediction:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(latest_prediction.replace("Z", "+00:00"))
            prediction_ok = age <= timedelta(hours=24)
            detail = f"age_hours={age.total_seconds()/3600:.2f}"
        else:
            prediction_ok = recent_program == 0
            detail = f"no predictions; recent_program_rows={recent_program}"
        add("prediction_recency", prediction_ok, detail)
    except Exception as exc:
        add("database", False, str(exc))

    for name, hours in (("run", 36), ("agf_update", 24), ("results_update", 24)):
        ok, detail = recent_json(name, hours)
        add(f"runner_{name}", ok, detail)

    provenance = validate_provenance(DB_PATH)
    add("leakage_gate", bool(provenance["passed"]), str(provenance["checks"]))
    try:
        validate_model_feature_contract(MODEL_FEATURES); contract_ok, contract_detail = True, "contract valid"
    except Exception as exc:
        contract_ok, contract_detail = False, str(exc)
    add("feature_contract", contract_ok, contract_detail)
    history, _ = load_history(DB_PATH)
    coverage, missed = snapshot_coverage_pass(DB_PATH, history)
    add("snapshot_coverage", coverage, f"missed_races={missed[:20]}")

    try:
        connection = sqlite3.connect(str(DB_PATH), timeout=10)
        last_monitor = connection.execute("SELECT MAX(run_at) FROM shadow_monitoring_runs").fetchone()[0]
        connection.close()
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last_monitor.replace("Z", "+00:00")) if last_monitor else timedelta.max
        add("shadow_monitor", bool(last_monitor) and age <= timedelta(hours=24), f"last_run={last_monitor}")
    except Exception as exc:
        add("shadow_monitor", False, str(exc))

    usage = shutil.disk_usage(PROJECT_ROOT)
    free_gb = usage.free / 1024**3; free_pct = usage.free / usage.total * 100
    min_gb = float(os.environ.get("HEALTH_MIN_FREE_GB", "2"))
    add("disk_space", free_gb >= min_gb and free_pct >= 10, f"free_gb={free_gb:.2f}, free_pct={free_pct:.1f}")
    ok, detail = check_logs(); add("error_logs", ok, detail)
    for name, ok, detail in check_web():
        add(name, ok, detail)
    backups = sorted(BACKUP_DIR.glob("daily/*.tar.gz"), key=lambda path: path.stat().st_mtime, reverse=True)
    backup_ok = bool(backups) and datetime.fromtimestamp(backups[0].stat().st_mtime) >= datetime.now() - timedelta(hours=36)
    add("backup_recency", backup_ok, str(backups[0]) if backups else "no backup")
    return checks


def write_report(checks: list[dict[str, object]]) -> bool:
    healthy = not any(row["status"] == "FAIL" and row["critical"] for row in checks)
    lines = [
        "# VPS Healthcheck", "", f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}", "",
        f"## Result: **{'HEALTHY' if healthy else 'CRITICAL'}**", "",
        "| Check | Status | Critical | Detail |", "| --- | --- | --- | --- |",
    ]
    for row in checks:
        detail = str(row["detail"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['check']} | {row['status']} | {row['critical']} | {detail} |")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "vps_healthcheck.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return healthy


def main() -> int:
    healthy = write_report(run_checks())
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
