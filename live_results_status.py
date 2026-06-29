"""Read/verify/write live result polling status without changing race data."""
from __future__ import annotations

import json
import os
import sqlite3
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from race_scope import normalize_country
from results_coverage import build_results_coverage


def verified_status(connection: sqlite3.Connection, target_date: str, country: str = "ALL",
                    metadata: dict[str, Any] | None = None,
                    now: datetime | None = None) -> dict[str, Any]:
    country = normalize_country(country)
    coverage = build_results_coverage(connection, target_date, country)
    tracks = []
    for track in coverage["tracks"]:
        races = [row for row in coverage["races"] if row["track"] == track["track"]]
        missing = sorted(row["race_no"] for row in races if not row["result_fetched"] and row["race_no"] is not None)
        tracks.append({
            "track": track["track"], "program_races": int(track["program_races"]),
            "result_races": int(track["result_races"]),
            "completed": int(track["result_races"]) == int(track["program_races"]),
            "missing_races": missing,
        })
    base = dict(metadata or {})
    interval = 300
    server_now = now or datetime.now(timezone.utc)
    raw_last = base.get("ended_at") or base.get("last_run_at")
    try:
        last_run = datetime.fromisoformat(str(raw_last).replace("Z", "+00:00")) if raw_last else None
        if last_run and last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)
    except ValueError:
        last_run = None
    next_run = (last_run + timedelta(seconds=interval)) if last_run else (server_now + timedelta(seconds=interval))
    seconds_remaining = max(0, math.ceil((next_run - server_now).total_seconds()))
    base.update({
        "date": target_date, "country": country,
        "last_run_at": last_run.isoformat() if last_run else None,
        "next_run_at": next_run.isoformat(), "server_now": server_now.isoformat(),
        "interval_seconds": interval, "seconds_remaining": seconds_remaining,
        "next_check_seconds": interval,
        "completed_tracks": sum(row["completed"] for row in tracks),
        "total_tracks": len(tracks), "tracks": tracks,
    })
    base.setdefault("status", "SUCCESS")
    base.setdefault("started_at", None); base.setdefault("ended_at", None)
    base.setdefault("duration_seconds", 0); base.setdefault("warnings", []); base.setdefault("errors", [])
    return base


def read_status_file(path: str | Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_live_status(db_path: str | Path, path: str | Path, target_date: str, country: str,
                      metadata: dict[str, Any]) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        payload = verified_status(connection, target_date, country, metadata)
    finally:
        connection.close()
    output = Path(path); output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    return payload
