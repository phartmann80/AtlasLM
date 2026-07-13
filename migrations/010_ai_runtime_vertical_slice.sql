-- AtlasLM AI runtime vertical slice.
-- Additive and data-preserving. Apply after the existing numbered migrations.
-- Rollback: disable ATLAS_*_RUNTIME flags, then use 010_ai_runtime.down.sql
-- only after confirming no active runs depend on these records.

CREATE TABLE IF NOT EXISTS ai_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    notebook_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    workflow_id TEXT,
    runtime VARCHAR(32) NOT NULL DEFAULT 'legacy',
    model_id TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    request_id TEXT,
    idempotency_key TEXT,
    trace_id TEXT,
    latency_ms INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    error_code TEXT,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_runs_workspace_created
    ON ai_runs (workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_runs_user_created
    ON ai_runs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_runs_status
    ON ai_runs (status);
CREATE INDEX IF NOT EXISTS idx_ai_runs_trace
    ON ai_runs (trace_id);

CREATE TABLE IF NOT EXISTS ai_run_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES ai_runs(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    status VARCHAR(32),
    progress INTEGER,
    message VARCHAR(500),
    payload JSONB,
    trace_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_run_events_run_created
    ON ai_run_events (run_id, created_at ASC);

ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS runtime VARCHAR(32) NOT NULL DEFAULT 'legacy';
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS trace_id TEXT;
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS source_scope JSONB;
CREATE INDEX IF NOT EXISTS idx_chat_messages_trace ON chat_messages (trace_id);

ALTER TABLE studio_outputs ADD COLUMN IF NOT EXISTS run_id UUID REFERENCES ai_runs(id) ON DELETE SET NULL;
ALTER TABLE studio_outputs ADD COLUMN IF NOT EXISTS runtime VARCHAR(32) NOT NULL DEFAULT 'legacy';
ALTER TABLE studio_outputs ADD COLUMN IF NOT EXISTS source_scope JSONB;
ALTER TABLE studio_outputs ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE studio_outputs ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE studio_outputs ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
ALTER TABLE studio_outputs ADD COLUMN IF NOT EXISTS progress INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_studio_outputs_run ON studio_outputs (run_id);
CREATE INDEX IF NOT EXISTS idx_studio_outputs_idempotency ON studio_outputs (idempotency_key);

ALTER TABLE studio_output_citations ADD COLUMN IF NOT EXISTS chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL;
ALTER TABLE studio_output_citations ADD COLUMN IF NOT EXISTS quote TEXT;
ALTER TABLE studio_output_citations ADD COLUMN IF NOT EXISTS source_url TEXT;

CREATE TABLE IF NOT EXISTS workspace_layouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    layout JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unique_workspace_layout UNIQUE (user_id, workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_layouts_user
    ON workspace_layouts (user_id, workspace_id);
