# PostgreSQL Migration Plan

## Current Decision

PostgreSQL is **not installed** for the first deployment. SQLite WAL mode is
adequate while writes come from a small number of serialized systemd jobs, the
database remains on one VPS, and snapshot growth remains operationally modest.

## Revisit Thresholds

Migrate when any of these persist:

- database size exceeds 20–30 GB;
- write-lock waits or `database is locked` errors occur repeatedly;
- more than one application host needs concurrent writes;
- monitoring queries materially delay snapshot ingestion;
- recovery objectives require streaming replication or point-in-time recovery.

## First Tables to Move

1. `program_snapshots`
2. `agf_snapshots`
3. `odds_snapshots`
4. `prediction_snapshots`
5. `prediction_results`
6. `shadow_monitoring_runs`

## Risks

- SQLite text timestamps must become timezone-aware PostgreSQL timestamps.
- Append-only triggers and unique constraints must be recreated and tested.
- SQLite dynamic types require explicit conversion validation.
- Sequence values, foreign keys, WAL-era writes, and cutover lag require audit.
- As-of query plans need composite indexes and `EXPLAIN ANALYZE` verification.

## Migration Outline

1. Freeze schema changes and inventory row counts/checksums.
2. Create PostgreSQL tables, indexes, constraints, and immutable triggers.
3. Bulk-copy a consistent SQLite backup into staging.
4. Compare row counts, key uniqueness, timestamp ordering, and feature hashes.
5. Dual-write append-only snapshots for a limited verification window.
6. Pause ingestion, copy the final delta, switch `DB_PATH`/adapter, and run gates.
7. Keep the SQLite backup read-only for rollback until acceptance completes.
