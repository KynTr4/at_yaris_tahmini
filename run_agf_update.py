"""Refresh AGF snapshots with race-aware cadence and final-minute priority."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from app_config import DB_PATH, TZ_NAME
from pipeline_runner import run_step, runner_lock, write_run_log


def select_upcoming(now: pd.Timestamp | None = None, db_path=DB_PATH) -> tuple[pd.DataFrame, str]:
    now = now or pd.Timestamp.now(tz="UTC")
    connection = sqlite3.connect(str(db_path), timeout=60)
    try:
        frame = pd.read_sql_query(
            """WITH ranked AS (
                   SELECT *,ROW_NUMBER() OVER(
                       PARTITION BY race_id,horse_id ORDER BY captured_at DESC,snapshot_id DESC
                   ) rn FROM program_snapshots
               ), races AS (
                   SELECT race_id,race_start_at,race_no
                   FROM ranked WHERE rn=1
                   GROUP BY race_id,race_start_at,race_no
               ), latest_agf AS (
                   SELECT race_id,MAX(captured_at) AS last_agf_at
                   FROM agf_snapshots GROUP BY race_id
               )
               SELECT r.*,a.last_agf_at
               FROM races r LEFT JOIN latest_agf a USING(race_id)""",
            connection,
        )
    finally:
        connection.close()
    if frame.empty:
        return frame, "no_program"
    starts = pd.to_datetime(frame["race_start_at"], utc=True, errors="coerce")
    local_today = now.tz_convert(ZoneInfo(TZ_NAME)).date()
    local_dates = starts.dt.tz_convert(ZoneInfo(TZ_NAME)).dt.date
    frame = frame[starts.gt(now) & local_dates.eq(local_today)].copy()
    if frame.empty:
        return frame, "no_future_races"
    starts = pd.to_datetime(frame["race_start_at"], utc=True)
    frame["minutes_to_start"] = (starts - now).dt.total_seconds() / 60
    frame["cadence_minutes"] = 15.0
    frame.loc[frame["minutes_to_start"].le(60), "cadence_minutes"] = 5.0
    frame.loc[frame["minutes_to_start"].le(30), "cadence_minutes"] = 2.0
    # The systemd timer runs once per minute, the allowed upper bound of the
    # requested 30–60 second final cadence.
    frame.loc[frame["minutes_to_start"].le(10), "cadence_minutes"] = 1.0

    last_capture = pd.to_datetime(frame["last_agf_at"], utc=True, errors="coerce")
    valid_last = last_capture.le(now) & last_capture.lt(starts)
    elapsed_minutes = (now - last_capture).dt.total_seconds() / 60
    frame["is_due"] = ~valid_last | elapsed_minutes.ge(frame["cadence_minutes"])

    urgent = frame[frame["minutes_to_start"].le(10)]
    if not urgent.empty:
        nearest_start = pd.to_datetime(urgent["race_start_at"], utc=True).min()
        nearest = urgent[pd.to_datetime(urgent["race_start_at"], utc=True).eq(nearest_start)]
        due = nearest[nearest["is_due"]].copy()
        return due, "urgent_10m_60s" if not due.empty else "urgent_10m_not_due"

    due = frame[frame["is_due"]].copy()
    return due, "tiered_due" if not due.empty else "tiered_not_due"


def main() -> int:
    selected, mode = select_upcoming()
    payload = {
        "runner": "agf_update", "started_at": datetime.now(timezone.utc).isoformat(),
        "selection_mode": mode, "selected_races": selected["race_id"].tolist() if len(selected) else [],
        "steps": [],
    }
    with runner_lock("agf_update", skip_if_active=True) as lock:
        if not lock.acquired:
            payload["status"] = "SKIPPED_ALREADY_RUNNING"
        elif not selected.empty:
            selected["city_id"] = selected["race_id"].str.extract(r"^prog_[^_]+_(\d+)_")[0].astype(int)
            for city_id, group in selected.groupby("city_id"):
                race_nos = sorted({int(value) for value in group["race_no"].dropna()})
                args = ["--today", "--sehir-ids", str(city_id), "--tables", "1", "2", "--force-refresh"]
                if race_nos:
                    args += ["--race-nos", *map(str, race_nos)]
                result = run_step("download_agfv2.py", args, 900)
                payload["steps"].append(result)
                if result["exit_code"] != 0:
                    payload.update({"status": "failed", "failed_city": int(city_id)})
                    break
            else:
                payload["status"] = "success"
        else:
            payload["status"] = "success"
    payload["ended_at"] = datetime.now(timezone.utc).isoformat()
    write_run_log("agf_update", payload)
    return 0 if payload["status"] in {"success", "SKIPPED_ALREADY_RUNNING"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
