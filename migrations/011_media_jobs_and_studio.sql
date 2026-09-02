-- Media ingestion jobs, citation metadata, and Studio media outputs.
-- Additive and idempotent. Safe to run after 010_ai_runtime_vertical_slice.

CREATE TABLE IF NOT EXISTS media_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR(255) NOT NULL,
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    document_id     UUID REFERENCES documents(id) ON DELETE SET NULL,
    studio_output_id UUID REFERENCES studio_outputs(id) ON DELETE SET NULL,
    kind            VARCHAR(40) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'queued',
    stage           VARCHAR(80) NOT NULL DEFAULT 'queued',
    retry_count     INTEGER NOT NULL DEFAULT 0,
    max_retries     INTEGER NOT NULL DEFAULT 2,
    idempotency_key VARCHAR(255),
    failure_reason  TEXT,
    callback_token  VARCHAR(128),
    provider_job_id VARCHAR(128),
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    result          JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    last_heartbeat_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_media_jobs_workspace_status
    ON media_jobs (workspace_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_media_jobs_user_status
    ON media_jobs (user_id, status);
CREATE INDEX IF NOT EXISTS idx_media_jobs_document
    ON media_jobs (document_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_media_jobs_idempotency
    ON media_jobs (workspace_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_media_jobs_provider
    ON media_jobs (provider_job_id)
    WHERE provider_job_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_media_jobs_callback
    ON media_jobs (callback_token)
    WHERE callback_token IS NOT NULL;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS storage_path VARCHAR(1024);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS thumbnail_path VARCHAR(1024);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS media_duration_ms INTEGER;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS youtube_video_id VARCHAR(32);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS channel_name VARCHAR(255);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extra_metadata JSONB;

ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS source_kind VARCHAR(40);
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS speaker VARCHAR(64);
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS start_ms INTEGER;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS end_ms INTEGER;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS region VARCHAR(40);
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS video_id VARCHAR(32);

ALTER TABLE studio_outputs ALTER COLUMN output_type TYPE VARCHAR(50);

ALTER TABLE audio_overviews ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'ready';
ALTER TABLE audio_overviews ADD COLUMN IF NOT EXISTS source_ids JSONB;
ALTER TABLE audio_overviews ADD COLUMN IF NOT EXISTS length_minutes INTEGER;
ALTER TABLE audio_overviews ADD COLUMN IF NOT EXISTS failure_reason TEXT;
ALTER TABLE audio_overviews ADD COLUMN IF NOT EXISTS job_id UUID;
