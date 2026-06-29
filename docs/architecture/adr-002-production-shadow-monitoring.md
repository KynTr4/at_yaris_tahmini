# ADR-002: Production Shadow Monitoring

## Status

Accepted — 2026-06-27

## Context

The leakage-safe feature path needs forward evidence before production use.
Retraining or automatic model selection during this period would confound the
measurement and invalidate a clean 90-day observation window.

## Decision

- Shadow mode loads fixed model artifacts and never trains or writes models.
- Every prediction is append-only, timestamped, feature-hashed, and linked to
  its immutable program snapshot.
- Results are attached in a separate append-only table.
- Daily metrics compare all four models on identical races; no automatic winner
  selection occurs.
- Monitoring uses the previous 30 calendar days as drift reference and reports
  90-day rolling performance.
- Leakage, contract and snapshot failures are always critical. Drift and
  calibration become blocking only after minimum sample thresholds are met.
- Production readiness requires 90 distinct shadow dates and remains separate
  from the daily pipeline health result.

## Trade-offs

- Warm-up periods produce `INSUFFICIENT_DATA` rather than fabricated metrics.
- Fixed thresholds are intentionally conservative and live in versioned code.
- CSV/report outputs are deterministic projections of immutable SQLite records,
  so they can be regenerated rather than incrementally edited.

## Consequences

- Positive: forward performance is reproducible and auditable.
- Negative: no production-ready claim is possible before 90 observed days.
- Mitigation: the dashboard exposes both daily health and readiness progress.
