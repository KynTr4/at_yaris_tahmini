"""
Storage lifecycle manager — disk monitoring, retention enforcement, SQLite maintenance.

Run standalone: python storage_manager.py [--dry-run] [--vacuum] [--report]
Called from cleanup.sh nightly at 04:00.

Exit codes
----------
0 — success, disk below alert threshold
2 — run succeeded but disk usage is at or above --threshold (caller can alert)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import shutil
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_config import (
    BACKUP_DIR,
    DB_PATH,
    LOG_DIR,
    OUTPUT_DIR,  # noqa: F401  — re-exported for callers that import from here
    PROJECT_ROOT,
    REPORTS_DIR,
)

# ---------------------------------------------------------------------------
# Logging — stream to stdout so systemd / journald captures everything
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("storage_manager")

# ---------------------------------------------------------------------------
# Byte-unit constants
# ---------------------------------------------------------------------------

_GB: int = 1_073_741_824
_MB: int = 1_048_576

# ---------------------------------------------------------------------------
# Protected outputs
# Entries are relative POSIX paths **or** fnmatch patterns relative to
# PROJECT_ROOT.  Files matching any entry are never auto-deleted.
# ---------------------------------------------------------------------------

PROTECTED_OUTPUTS: frozenset[str] = frozenset(
    {
        # Core model artefacts
        "output/model_predictions.parquet",
        "output/asof_features.parquet",
        "output/final_benter_dataset.parquet",
        # Wildcard patterns — fnmatch resolved in _is_protected()
        "output/calibration_table*.csv",
        "output/model_scores*.csv",
        # Live / monitoring files
        "output/feature_drift.csv",
        "output/live_metrics.csv",
        "output/model_drift.csv",
        "output/shadow_predictions.csv",
        "output/prediction_history.csv",
        # Root-level operational CSVs
        "failed_updates.csv",
        "archived_failed_updates.csv",
    }
)


def _is_protected(path: Path, root: Path = PROJECT_ROOT) -> bool:
    """Return *True* if *path* matches any entry in :data:`PROTECTED_OUTPUTS`."""
    try:
        rel_str = path.relative_to(root).as_posix()
    except ValueError:
        # Path outside root — treat as unprotected so the caller can decide
        return False
    return any(fnmatch.fnmatch(rel_str, pattern) for pattern in PROTECTED_OUTPUTS)


# ---------------------------------------------------------------------------
# RetentionPolicy
# ---------------------------------------------------------------------------


@dataclass
class RetentionPolicy:
    """Describes the lifecycle of a category of files.

    Attributes:
        pattern:      Glob pattern relative to ``PROJECT_ROOT``
                      (passed to :py:meth:`pathlib.Path.glob`).
        max_age_days: Files older than this are eligible for deletion.
                      ``0`` means delete regardless of age.
        category:     Short human-readable label used in logs and reports.
        keep_last:    When set, always preserve the *N* most-recently-modified
                      matching files even if they exceed ``max_age_days``.
                      Files beyond position *N* are deleted only when they
                      also exceed ``max_age_days``.
    """

    pattern: str
    max_age_days: int
    category: str
    keep_last: int | None = field(default=None)


# ---------------------------------------------------------------------------
# RETENTION_POLICIES
#
# Ordered from most-specific to most-general.  enforce_retention() tracks
# which files have already been claimed by an earlier policy and skips them
# when evaluating later (broader) patterns, so ordering is significant.
# ---------------------------------------------------------------------------

RETENTION_POLICIES: list[RetentionPolicy] = [
    # ── output/ — specific patterns first ──────────────────────────────────
    # Backtest snapshots: keep the 5 most recent, delete anything older than 90 d
    RetentionPolicy(
        pattern="output/backtest_predictions*.parquet",
        max_age_days=90,
        category="backtest_parquet",
        keep_last=5,
    ),
    # ROI simulation runs: keep the 5 most recent, delete anything older than 90 d
    RetentionPolicy(
        pattern="output/roi_simulation*.parquet",
        max_age_days=90,
        category="roi_parquet",
        keep_last=5,
    ),
    # Race-day feature snapshots are only needed on the day they're built
    RetentionPolicy(
        pattern="output/today_features_base.*",
        max_age_days=1,
        category="today_features",
    ),
    # General parquet files in output/ — 14-day rolling window.
    # Files already claimed by the three policies above are skipped.
    RetentionPolicy(
        pattern="output/*.parquet",
        max_age_days=14,
        category="output_parquet",
    ),
    # Unprotected CSVs in output/ — remove immediately; parquet is the
    # source of truth.  PROTECTED_OUTPUTS guard prevents touching live files.
    RetentionPolicy(
        pattern="output/*.csv",
        max_age_days=0,
        category="output_csv_temp",
    ),
    # ── lake/ ───────────────────────────────────────────────────────────────
    # Analytics CSVs are transient exports — parquet copy already exists
    RetentionPolicy(
        pattern="lake/analytics/*.csv",
        max_age_days=0,
        category="lake_analytics_csv",
    ),
    # ── reports/ ────────────────────────────────────────────────────────────
    # Daily coverage reports: 7-day window (cleanup.sh used 30 d; tighter here)
    RetentionPolicy(
        pattern="reports/results_coverage_*.md",
        max_age_days=7,
        category="reports_coverage",
    ),
    RetentionPolicy(
        pattern="reports/deploy_report_*.md",
        max_age_days=7,
        category="reports_deploy",
    ),
    # ── logs/ ───────────────────────────────────────────────────────────────
    # logrotate handles compression/rotation of .log files; this handles any
    # app-level log accumulation that slips through
    RetentionPolicy(
        pattern="logs/*.log",
        max_age_days=30,
        category="app_logs",
    ),
    # ── data/ ───────────────────────────────────────────────────────────────
    # AGF scraper HTML cache — kept in sync with cleanup.sh (30 d)
    RetentionPolicy(
        pattern="data/agfv2_raw/html/*.html",
        max_age_days=30,
        category="html_cache",
    ),
    # ── komiser_raporlari/ ──────────────────────────────────────────────────
    RetentionPolicy(
        pattern="komiser_raporlari/*.pdf",
        max_age_days=90,
        category="komiser_pdf",
    ),
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _human_size(size_bytes: int | float) -> str:
    """Format *size_bytes* as a human-readable string (e.g. ``1.4 GB``)."""
    if size_bytes < 0:
        return "N/A"
    val = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if val < 1_024.0:
            return f"{val:.1f} {unit}"
        val /= 1_024.0
    return f"{val:.1f} TB"


def _dir_size(path: Path) -> int:
    """Return total size in bytes of all files under *path*, or ``-1`` on
    permission error and ``0`` if *path* does not exist."""
    if not path.exists():
        return 0
    try:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except PermissionError as exc:
        log.warning("Cannot read size of %s: %s", path, exc)
        return -1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_disk_usage(path: Path) -> dict[str, float]:
    """Return disk usage for the filesystem that contains *path*.

    Uses :py:func:`shutil.disk_usage` — no external commands required.

    Returns:
        Dict with keys ``total_gb``, ``used_gb``, ``free_gb``,
        ``used_percent`` (all floats).
    """
    usage = shutil.disk_usage(path)
    total_gb = round(usage.total / _GB, 2)
    used_gb = round(usage.used / _GB, 2)
    free_gb = round(usage.free / _GB, 2)
    used_percent = round(usage.used / usage.total * 100, 1) if usage.total > 0 else 0.0
    return {
        "total_gb": total_gb,
        "used_gb": used_gb,
        "free_gb": free_gb,
        "used_percent": used_percent,
    }


def get_dir_sizes(root: Path) -> dict[str, int]:
    """Compute on-disk size (bytes) for key directories and the SQLite DB.

    Measured paths
    --------------
    ``lake``, ``output``, ``logs``, ``backups``, ``models``, ``reports``,
    ``data``, ``db`` (key file).  ``.venv/`` is intentionally excluded.

    ``logs`` and ``backups`` use the configured :data:`LOG_DIR` /
    :data:`BACKUP_DIR` paths so they work correctly on VPS deployments where
    those directories live outside the project root.

    Returns:
        Dict mapping a short name → size in bytes.
        ``-1`` means the path exists but is not readable (permission error).
        ``0`` means the path does not exist.
    """
    target_dirs: dict[str, Path] = {
        "lake": root / "lake",
        "output": root / "output",
        "logs": LOG_DIR,
        "backups": BACKUP_DIR,
        "models": root / "models",
        "reports": root / "reports",
        "data": root / "data",
    }

    result: dict[str, int] = {
        name: _dir_size(path) for name, path in target_dirs.items()
    }

    # Key file: SQLite database
    if DB_PATH.exists():
        result["db"] = DB_PATH.stat().st_size
    else:
        result["db"] = 0

    return result


def vacuum_sqlite(db_path: Path, dry_run: bool = False) -> dict[str, Any]:
    """Run WAL checkpoint → VACUUM → ANALYZE on the SQLite database.

    Steps
    -----
    1. ``PRAGMA wal_checkpoint(TRUNCATE)`` — flush WAL back into the main DB
       file and truncate the WAL to zero bytes.
    2. ``VACUUM`` — rebuild the database file, reclaiming free pages.
    3. ``ANALYZE`` — refresh query-planner statistics.

    Args:
        db_path:  Path to the SQLite database.
        dry_run:  When *True*, skip all writes and return simulated metrics.

    Returns:
        Dict with keys:

        * ``wal_checkpoint`` — pages written during checkpoint.
        * ``size_before_mb`` / ``size_after_mb`` / ``saved_mb`` — floats.
        * ``dry_run`` — present and *True* only in dry-run mode.
        * ``error`` — present only when an error occurred.
    """
    if not db_path.exists():
        log.warning("SQLite DB not found: %s — skipping vacuum", db_path)
        return {"error": "db_not_found", "db_path": str(db_path)}

    size_before = db_path.stat().st_size
    size_before_mb = round(size_before / _MB, 2)

    if dry_run:
        log.info(
            "[DRY-RUN] Would vacuum SQLite: %s (%.1f MB)", db_path.name, size_before_mb
        )
        return {
            "wal_checkpoint": 0,
            "size_before_mb": size_before_mb,
            "size_after_mb": size_before_mb,
            "saved_mb": 0.0,
            "dry_run": True,
        }

    log.info("SQLite maintenance — %s (%.1f MB before)", db_path.name, size_before_mb)

    wal_ckpt: int = 0
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        # 1. WAL checkpoint: flush WAL pages into the main DB and truncate WAL
        cur = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        row = cur.fetchone()
        # Row format: (busy, log_pages, checkpointed_pages)
        wal_log: int = row[1] if row else 0
        wal_ckpt = row[2] if row else 0
        log.info("WAL checkpoint: log_pages=%d, checkpointed=%d", wal_log, wal_ckpt)

        # 2. VACUUM: rebuild the database file, reclaiming deleted-row pages
        _ = conn.execute("VACUUM")
        log.info("VACUUM complete")

        # 3. ANALYZE: update query-planner statistics for all tables/indexes
        _ = conn.execute("ANALYZE")
        log.info("ANALYZE complete")

    except sqlite3.Error as exc:
        log.error("SQLite maintenance error: %s", exc)
        conn.close()
        return {
            "error": str(exc),
            "size_before_mb": size_before_mb,
            "size_after_mb": size_before_mb,
            "saved_mb": 0.0,
        }
    finally:
        conn.close()

    size_after = db_path.stat().st_size
    size_after_mb = round(size_after / _MB, 2)
    saved_mb = round((size_before - size_after) / _MB, 2)

    log.info(
        "SQLite done: %.1f MB → %.1f MB  (saved %.1f MB)",
        size_before_mb,
        size_after_mb,
        saved_mb,
    )
    return {
        "wal_checkpoint": wal_ckpt,
        "size_before_mb": size_before_mb,
        "size_after_mb": size_after_mb,
        "saved_mb": saved_mb,
    }


def enforce_retention(
    root: Path,
    policies: list[RetentionPolicy],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Delete files that have exceeded their configured retention window.

    Policy evaluation
    -----------------
    Policies are applied in order.  Once a file is claimed by a policy it is
    **not** re-evaluated by subsequent policies — ordering from specific →
    general in :data:`RETENTION_POLICIES` is therefore important.

    Deletion criteria for a given policy
    -------------------------------------
    * ``keep_last`` is ``None`` → delete when ``age > max_age_days``
      (or always when ``max_age_days == 0``).
    * ``keep_last = N`` → the *N* most-recently-modified files are always
      kept; files beyond position *N* are deleted when they also exceed
      ``max_age_days``.

    Files matching any :data:`PROTECTED_OUTPUTS` entry are never deleted.

    Args:
        root:     Project root used to resolve policy glob patterns.
        policies: Ordered list of :class:`RetentionPolicy` objects.
        dry_run:  When *True*, simulate deletions without touching the disk.

    Returns:
        Dict with keys ``deleted`` (list[str]), ``freed_bytes`` (int),
        ``errors`` (list[str]).
    """
    deleted: list[str] = []
    freed_bytes: int = 0
    errors: list[str] = []
    # Track files claimed by earlier (more-specific) policies
    seen_files: set[Path] = set()
    now: float = time.time()

    for policy in policies:
        # Glob and sort newest-first so index 0 == most recent (for keep_last)
        try:
            raw_matches = [p for p in root.glob(policy.pattern) if p.is_file()]
            matched: list[Path] = sorted(
                raw_matches,
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"glob failed for '{policy.pattern}': {exc}"
            log.warning(msg)
            errors.append(msg)
            continue

        # Skip files already handled by an earlier, more-specific policy
        candidates = [f for f in matched if f not in seen_files]
        seen_files.update(candidates)

        for idx, fpath in enumerate(candidates):
            # Protection guard — never delete model/live artefacts
            if _is_protected(fpath, root):
                log.debug("PROTECTED — skipping %s", fpath.relative_to(root))
                continue

            try:
                stat = fpath.stat()
            except FileNotFoundError:
                continue  # Deleted between glob and stat — ignore
            except OSError as exc:
                msg = f"stat({fpath.relative_to(root)}): {exc}"
                log.warning(msg)
                errors.append(msg)
                continue

            age_days: float = (now - stat.st_mtime) / 86_400

            # --- Determine whether this file should be deleted ---
            age_expired: bool = (
                policy.max_age_days == 0 or age_days > policy.max_age_days
            )
            if policy.keep_last is not None:
                # Within the top-N most recent → always keep, regardless of age
                beyond_keep: bool = idx >= policy.keep_last
                should_delete = beyond_keep and age_expired
            else:
                should_delete = age_expired

            if not should_delete:
                continue

            rel_str = str(fpath.relative_to(root))
            size = stat.st_size
            tag = "[DRY-RUN] would delete" if dry_run else "DELETE"
            log.info(
                "%s  %-70s  [age=%.1fd, category=%s]",
                tag,
                rel_str,
                age_days,
                policy.category,
            )

            if not dry_run:
                try:
                    fpath.unlink()
                    deleted.append(rel_str)
                    freed_bytes += size
                except OSError as exc:
                    msg = f"unlink({rel_str}): {exc}"
                    log.error(msg)
                    errors.append(msg)
            else:
                deleted.append(rel_str)
                freed_bytes += size

    log.info(
        "Retention: %d file(s) %s, %s freed, %d error(s)",
        len(deleted),
        "would be deleted" if dry_run else "deleted",
        _human_size(freed_bytes),
        len(errors),
    )
    return {"deleted": deleted, "freed_bytes": freed_bytes, "errors": errors}


def clean_caches(root: Path, dry_run: bool = False) -> dict[str, Any]:
    """Remove Python build and test cache artefacts from the project tree.

    Targets
    -------
    ``__pycache__/``, ``.pytest_cache/``, ``build/``, ``dist/``,
    ``*.egg-info/``, ``.cache/``.

    The ``.venv/`` subtree is always skipped regardless of what it contains.

    Args:
        root:    Project root to search under.
        dry_run: When *True*, report what *would* be removed without deletion.

    Returns:
        Dict with keys ``freed_bytes`` (int) and ``dirs_removed`` (int).
    """
    freed_bytes: int = 0
    dirs_removed: int = 0
    venv_root = root / ".venv"

    patterns: list[str] = [
        "**/__pycache__",
        "**/.pytest_cache",
        "**/build",
        "**/dist",
        "**/*.egg-info",
        "**/.cache",
    ]

    for pattern in patterns:
        for dpath in sorted(root.glob(pattern)):
            if not dpath.is_dir():
                continue

            # Never touch anything inside .venv/
            try:
                _ = dpath.relative_to(venv_root)
                continue  # Under .venv — skip
            except ValueError:
                pass

            size = _dir_size(dpath)
            rel = dpath.relative_to(root)
            tag = "[DRY-RUN] would remove" if dry_run else "REMOVE"
            log.info("%s  cache dir: %s  (%s)", tag, rel, _human_size(size))

            if not dry_run:
                try:
                    shutil.rmtree(dpath)
                    freed_bytes += max(size, 0)
                    dirs_removed += 1
                except OSError as exc:
                    log.warning("Failed to remove %s: %s", rel, exc)
            else:
                freed_bytes += max(size, 0)
                dirs_removed += 1

    log.info(
        "Caches: %d dir(s) %s, %s freed",
        dirs_removed,
        "would be removed" if dry_run else "removed",
        _human_size(freed_bytes),
    )
    return {"freed_bytes": freed_bytes, "dirs_removed": dirs_removed}


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _build_markdown_report(report: dict[str, Any]) -> str:
    """Render a *report* dict as a human-readable Markdown document."""
    disk = report.get("disk", {})
    dirs = report.get("dirs", {})
    retention = report.get("retention", {})
    caches = report.get("caches", {})
    vacuum = report.get("vacuum", {})

    lines: list[str] = []
    a = lines.append

    a("# Storage Report")
    a("")
    a(f"**Run at:** {report.get('run_at', 'unknown')}  ")
    dry = report.get("dry_run", False)
    a(f"**Mode:** {'⚠️ DRY-RUN — no files were deleted' if dry else '✅ LIVE'}  ")
    a("")

    if report.get("alert"):
        a(f"> ⚠️ **DISK ALERT:** {report.get('alert_reason', '')}  ")
        a("> Consider freeing space or expanding the volume.")
        a("")

    # ── Disk ───────────────────────────────────────────────────────────────
    a("## Disk Usage")
    a("")
    a("| Metric | Value |")
    a("|--------|-------|")
    a(f"| Total  | {disk.get('total_gb', 0):.1f} GB |")
    a(
        f"| Used   | {disk.get('used_gb', 0):.1f} GB &nbsp;({disk.get('used_percent', 0):.1f}%) |"
    )
    a(f"| Free   | {disk.get('free_gb', 0):.1f} GB |")
    a("")

    # ── Dir sizes ──────────────────────────────────────────────────────────
    if dirs:
        a("## Directory Sizes")
        a("")
        a("| Directory | Size |")
        a("|-----------|------|")
        for name, sz in sorted(dirs.items(), key=lambda kv: kv[1], reverse=True):
            a(f"| `{name}` | {_human_size(sz)} |")
        a("")

    # ── Retention ──────────────────────────────────────────────────────────
    deleted: list[str] = retention.get("deleted", [])
    freed: int = retention.get("freed_bytes", 0)
    errs: list[str] = retention.get("errors", [])
    a("## Retention Enforcement")
    a("")
    a(f"- **Files deleted:** {len(deleted)}")
    a(f"- **Space freed:** {_human_size(freed)}")
    a(f"- **Errors:** {len(errs)}")
    a("")
    if deleted:
        show = deleted[:50]
        a("<details>")
        a(f"<summary>Deleted files ({len(deleted)} total)</summary>")
        a("")
        for f in show:
            a(f"- `{f}`")
        if len(deleted) > 50:
            a(f"- *(and {len(deleted) - 50} more…)*")
        a("")
        a("</details>")
        a("")
    if errs:
        a("**Errors encountered:**")
        a("")
        for e in errs:
            a(f"- `{e}`")
        a("")

    # ── Caches ─────────────────────────────────────────────────────────────
    a("## Cache Cleanup")
    a("")
    a(f"- **Directories removed:** {caches.get('dirs_removed', 0)}")
    a(f"- **Space freed:** {_human_size(caches.get('freed_bytes', 0))}")
    a("")

    # ── Vacuum ─────────────────────────────────────────────────────────────
    if vacuum and "error" not in vacuum and not vacuum.get("dry_run"):
        a("## SQLite Maintenance")
        a("")
        a("| Metric | Value |")
        a("|--------|-------|")
        a(f"| Database | `{DB_PATH.name}` |")
        a(f"| Before   | {vacuum.get('size_before_mb', 0):.1f} MB |")
        a(f"| After    | {vacuum.get('size_after_mb', 0):.1f} MB |")
        a(f"| Saved    | {vacuum.get('saved_mb', 0):.1f} MB |")
        a(f"| WAL pages checkpointed | {vacuum.get('wal_checkpoint', 0)} |")
        a("")
    elif vacuum.get("dry_run"):
        a("## SQLite Maintenance")
        a("")
        a(
            f"[DRY-RUN] Would vacuum `{DB_PATH.name}` "
            f"({vacuum.get('size_before_mb', 0):.1f} MB)"
        )
        a("")
    elif "error" in vacuum:
        a("## SQLite Maintenance")
        a("")
        a(f"> ❌ Vacuum skipped: `{vacuum.get('error', 'unknown error')}`")
        a("")

    return "\n".join(lines)


def write_storage_report(report: dict[str, Any], reports_dir: Path) -> None:
    """Write *report* to ``storage_report.json`` and ``storage_report.md``.

    Both files are written atomically (Python's :py:meth:`Path.write_text`
    creates a new inode, so a concurrent reader always sees a complete file).

    Args:
        report:      The dict returned by :func:`run_all`.
        reports_dir: Directory to write into (created if absent).
    """
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = reports_dir / "storage_report.json"
    json_path.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )
    log.info("Storage report (JSON) → %s", json_path)

    md_path = reports_dir / "storage_report.md"
    md_path.write_text(_build_markdown_report(report), encoding="utf-8")
    log.info("Storage report (MD)   → %s", md_path)


def run_all(
    dry_run: bool = False,
    skip_vacuum: bool = False,
    threshold: float = 80.0,
) -> dict[str, Any]:
    """Run the complete storage lifecycle in sequence.

    Order of operations:

    1. :func:`get_disk_usage` — snapshot current disk state.
    2. :func:`get_dir_sizes` — per-directory size breakdown.
    3. :func:`enforce_retention` — delete expired files per policy.
    4. :func:`clean_caches` — remove Python build/test artefacts.
    5. :func:`vacuum_sqlite` — WAL checkpoint + VACUUM + ANALYZE (skippable).
    6. :func:`write_storage_report` — persist JSON + Markdown reports.

    Args:
        dry_run:      When *True*, simulate all destructive operations.
        skip_vacuum:  When *True*, skip the SQLite maintenance step.
        threshold:    Disk-usage percentage that sets ``alert = True``.

    Returns:
        Complete report dict with keys ``run_at``, ``dry_run``, ``disk``,
        ``dirs``, ``retention``, ``caches``, ``vacuum``, ``alert``,
        ``alert_reason``.
    """
    run_at = datetime.now(tz=timezone.utc).isoformat()
    log.info(
        "=== storage_manager started  run_at=%s  dry_run=%s  skip_vacuum=%s ===",
        run_at,
        dry_run,
        skip_vacuum,
    )

    disk = get_disk_usage(PROJECT_ROOT)
    dirs = get_dir_sizes(PROJECT_ROOT)
    retention = enforce_retention(PROJECT_ROOT, RETENTION_POLICIES, dry_run=dry_run)
    caches = clean_caches(PROJECT_ROOT, dry_run=dry_run)

    vacuum: dict[str, Any] = {}
    if not skip_vacuum:
        vacuum = vacuum_sqlite(DB_PATH, dry_run=dry_run)

    alert: bool = disk["used_percent"] >= threshold
    alert_reason: str = (
        f"Disk usage {disk['used_percent']:.1f}% >= threshold {threshold:.0f}%"
        if alert
        else ""
    )

    if alert:
        log.warning("DISK ALERT: %s", alert_reason)

    report: dict[str, Any] = {
        "run_at": run_at,
        "dry_run": dry_run,
        "delete_mode": not dry_run,
        "disk": disk,
        "dirs": dirs,
        "retention": retention,
        "caches": caches,
        "vacuum": vacuum,
        "alert": alert,
        "alert_reason": alert_reason,
    }

    write_storage_report(report, REPORTS_DIR)

    total_freed = retention["freed_bytes"] + caches["freed_bytes"]
    vac_saved: float = vacuum.get("saved_mb", 0.0)
    log.info(
        "=== storage_manager done: %d file(s) deleted, %s freed by retention, "
        "%s freed by cache cleanup, vacuum saved %.1f MB ===",
        len(retention["deleted"]),
        _human_size(retention["freed_bytes"]),
        _human_size(caches["freed_bytes"]),
        vac_saved,
    )
    log.info("Total space recovered: %s", _human_size(total_freed))

    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Command-line interface.

    Usage examples::

        # Dry-run + SQLite maintenance (default, no files deleted)
        python storage_manager.py

        # Real deletion + SQLite maintenance
        python storage_manager.py --delete

        # SQLite VACUUM / ANALYZE only (no file operations)
        python storage_manager.py --vacuum

        # Print the last persisted report as JSON (for monitoring scripts)
        python storage_manager.py --report

        # Alert when disk usage exceeds 90 %
        python storage_manager.py --threshold 90

    Exit codes
    ----------
    * ``0`` — success, disk below alert threshold.
    * ``2`` — run succeeded but disk usage >= ``--threshold``.
    """
    parser = argparse.ArgumentParser(
        prog="storage_manager",
        description=(
            "Storage lifecycle manager — disk monitoring, retention enforcement, "
            "SQLite maintenance."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Dosyaları gerçekten sil (olmadan: dry-run)",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run SQLite WAL checkpoint + VACUUM + ANALYZE only, then exit.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print the last stored storage_report.json to stdout and exit.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=80.0,
        metavar="PERCENT",
        help=(
            "Disk-usage percent that triggers the alert flag and exit code 2.  "
            "Default: 80."
        ),
    )
    args = parser.parse_args()

    # ── --report ──────────────────────────────────────────────────────────
    if args.report:
        report_path = REPORTS_DIR / "storage_report.json"
        if report_path.exists():
            sys.stdout.write(report_path.read_text(encoding="utf-8"))
            sys.stdout.write("\n")
        else:
            log.error(
                "No storage report found at %s — run without --report first.",
                report_path,
            )
            sys.exit(1)
        return

    dry_run: bool = not args.delete

    # ── --vacuum ──────────────────────────────────────────────────────────
    if args.vacuum:
        result = vacuum_sqlite(DB_PATH, dry_run=dry_run)
        sys.stdout.write(json.dumps(result, indent=2, default=str))
        sys.stdout.write("\n")
        return

    # ── full run ──────────────────────────────────────────────────────────
    report = run_all(dry_run=dry_run, threshold=args.threshold)

    if report["alert"]:
        log.warning(
            "Exiting with code 2: %s — consider freeing disk space.",
            report["alert_reason"],
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
