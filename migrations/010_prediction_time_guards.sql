CREATE TRIGGER IF NOT EXISTS prediction_snapshots_pre_race_guard
BEFORE INSERT ON prediction_snapshots
WHEN julianday(NEW.prediction_time) >= julianday(NEW.race_start_at)
BEGIN
    SELECT RAISE(ABORT, 'prediction_time must be before race_start_at');
END;
CREATE TRIGGER IF NOT EXISTS prediction_snapshots_provenance_guard
BEFORE INSERT ON prediction_snapshots
WHEN NOT EXISTS (
    SELECT 1 FROM program_snapshots s
    WHERE s.snapshot_id=NEW.feature_snapshot_id
      AND s.race_id=NEW.race_id
      AND s.horse_id=NEW.horse_id
      AND s.source_request_id=NEW.source_request_id
      AND julianday(s.captured_at) < julianday(NEW.race_start_at)
)
BEGIN
    SELECT RAISE(ABORT, 'prediction feature snapshot provenance mismatch');
END;
CREATE TRIGGER IF NOT EXISTS prediction_results_post_race_guard
BEFORE INSERT ON prediction_results
WHEN julianday(NEW.matched_at) <= (
    SELECT julianday(race_start_at) FROM prediction_snapshots
    WHERE prediction_id=NEW.prediction_id
)
BEGIN
    SELECT RAISE(ABORT, 'prediction result cannot be matched before race_start_at');
END;
