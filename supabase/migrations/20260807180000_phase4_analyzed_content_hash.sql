-- Tracks which opportunities.content_hash a project_analyses row was computed against,
-- so re-analysis only happens when the source G2B data actually changed (not on every
-- scheduler tick) - see docs/DATA_PIPELINE.md's idempotency section and
-- worker/repositories/project_analyses.py.

alter table project_analyses add column analyzed_content_hash text;
