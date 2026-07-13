-- Safe rollback companion for 010_ai_runtime_vertical_slice.sql.
-- Run only after setting all ATLAS_*_RUNTIME flags back to legacy and
-- confirming that AI run/output history is no longer needed in this release.
-- Existing notebooks, documents, conversations, and recovered source data
-- are intentionally untouched.

DROP TABLE IF EXISTS workspace_layouts;
DROP TABLE IF EXISTS ai_run_events;
DROP TABLE IF EXISTS ai_runs;

ALTER TABLE chat_messages DROP COLUMN IF EXISTS source_scope;
ALTER TABLE chat_messages DROP COLUMN IF EXISTS trace_id;
ALTER TABLE chat_messages DROP COLUMN IF EXISTS runtime;

ALTER TABLE studio_outputs DROP COLUMN IF EXISTS idempotency_key;
ALTER TABLE studio_outputs DROP COLUMN IF EXISTS progress;
ALTER TABLE studio_outputs DROP COLUMN IF EXISTS version;
ALTER TABLE studio_outputs DROP COLUMN IF EXISTS retry_count;
ALTER TABLE studio_outputs DROP COLUMN IF EXISTS source_scope;
ALTER TABLE studio_outputs DROP COLUMN IF EXISTS runtime;
ALTER TABLE studio_outputs DROP COLUMN IF EXISTS run_id;
