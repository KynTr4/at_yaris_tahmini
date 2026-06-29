# ADR-001: Immutable As-Of Snapshots

## Status

Accepted — 2026-06-27

## Context

Historical `horse_races` rows combine race context and post-race results and do
not retain the time at which each value was observed. Field semantics alone
cannot prove that a training value existed before race start.

## Decision

- New program, AGF and odds observations are append-only snapshots.
- Every snapshot carries `captured_at` and a source request identifier.
- Certified feature rows use the latest observation satisfying
  `captured_at < race_start_at`.
- Post-race values live in `race_results`; the certified builder has no query
  against `horse_races`.
- Existing undated history remains available to legacy reports but is not
  relabelled as certified snapshot data.
- The leakage gate fails closed when provenance or eligible snapshots are absent.

## Rationale

This preserves the existing pipeline while creating an independently auditable
path for new data. Fabricating capture times for historical rows would make the
schema look compliant without providing evidence.

## Trade-offs

- Certified rolling histories begin cold and grow as snapshots/results accrue.
- Storage grows because observations are never overwritten.
- Program/result identity mapping remains explicit and must be monitored.

## Consequences

- Positive: point-in-time correctness is testable with SQL and CI.
- Negative: old backtests cannot receive a PASS retroactively.
- Mitigation: retain legacy outputs with an uncertified label and use the new
  snapshot path for forward validation and live predictions.
