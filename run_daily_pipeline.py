"""Linux/systemd daily pipeline with fail-closed step execution."""
from __future__ import annotations

from datetime import datetime, timezone

from pipeline_runner import run_step, runner_lock, write_run_log

STEPS = [
    ("update_race_programs.py", [], 1800),
    ("snapshot_store.py", [], 300),
    ("download_agfv2.py", ["--today", "--tables", "1", "2", "--force-refresh"], 1800),
    ("komiser.py", ["--today"], 1800),
    ("process_komiser.py", ["--today"], 1800),
    ("update_track_conditions.py", [], 900),
    ("update_workouts.py", [], 900),
    ("update_results.py", [], 1800),
    ("build_asof_features.py", [], 1800),
    ("validate_feature_provenance.py", [], 900),
    ("shadow_monitor.py", [], 1800),
]


def main() -> int:
    payload = {"runner": "daily", "started_at": datetime.now(timezone.utc).isoformat(), "steps": []}
    with runner_lock("daily_pipeline"):
        for script, args, timeout in STEPS:
            result = run_step(script, args, timeout)
            payload["steps"].append(result)
            if result["exit_code"] != 0:
                payload.update({"status": "failed", "failed_step": script})
                break
        else:
            payload["status"] = "success"
    payload["ended_at"] = datetime.now(timezone.utc).isoformat()
    write_run_log("run", payload)
    return 0 if payload["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
