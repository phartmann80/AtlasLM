import uuid
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Text, JSON, Float, Boolean, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, UUID as PG_UUID, JSONB
from datetime import datetime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from .core.database import Base

class Workspace(Base):
    __tablename__ = "workspaces"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user_id = Column(String(255), nullable=True) # Connect to Supabase Auth user ID
    
    documents = relationship("Document", back_populates="workspace", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="workspace", cascade="all, delete-orphan")
    studio_outputs = relationship("StudioOutput", back_populates="workspace", cascade="all, delete-orphan")

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False) # 'pdf', 'txt', 'md', 'url'
    source_url = Column(String(2083), nullable=True)
    idempotency_key = Column(String(255), nullable=True, index=True)
    embedding_model = Column(String(120), nullable=True)
    status = Column(String(20), nullable=False, default="ready", server_default="ready")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Provenance fields for Deep Research
    origin = Column(String, nullable=True)             # 'deep_research' | NULL
    source_label = Column(String, nullable=True)       # 'Web' | 'arXiv' | 'Crossref'
    external_url = Column(String, nullable=True)
    research_query = Column(String, nullable=True)
    
    storage_path = Column(String(1024), nullable=True)
    thumbnail_path = Column(String(1024), nullable=True)
    media_duration_ms = Column(Integer, nullable=True)
    youtube_video_id = Column(String(32), nullable=True)
    channel_name = Column(String(255), nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    workspace = relationship("Workspace", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    # Define vector embedding. Dimension 1536 is standard for OpenAI / Langdock.
    # For Ollama / local, we can standardise or use 1536.
    embedding = Column(Vector(1536), nullable=True) 
    page_number = Column(Integer, nullable=True) # 1-indexed for PDFs
    chunk_index = Column(Integer, nullable=False)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    sheet = Column(String(100), nullable=True)
    timestamp = Column(Float, nullable=True)
    source_kind = Column(String(40), nullable=True)
    speaker = Column(String(64), nullable=True)
    start_ms = Column(Integer, nullable=True)
    end_ms = Column(Integer, nullable=True)
    region = Column(String(40), nullable=True)
    video_id = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    document = relationship("Document", back_populates="chunks")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user_id = Column(String(255), nullable=True)
    
    workspace = relationship("Workspace", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False) # 'user', 'assistant'
    content = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True) # Grounded citations structure
    runtime = Column(String(32), nullable=False, default="legacy", server_default="legacy")
    trace_id = Column(String(128), nullable=True, index=True)
    source_scope = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    session = relationship("ChatSession", back_populates="messages")


class AIRun(Base):
    """Durable record for an agent or workflow execution."""

    __tablename__ = "ai_runs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    workspace_id = Column(PG_UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    notebook_id = Column(PG_UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(String(120), nullable=False)
    workflow_id = Column(String(120), nullable=True)
    runtime = Column(String(32), nullable=False, default="legacy", server_default="legacy")
    model_id = Column(String(160), nullable=True)
    status = Column(String(32), nullable=False, default="queued", server_default="queued", index=True)
    request_id = Column(String(128), nullable=True, index=True)
    idempotency_key = Column(String(255), nullable=True, index=True)
    trace_id = Column(String(128), nullable=True, index=True)
    latency_ms = Column(Integer, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    error_code = Column(String(120), nullable=True)
    error_message = Column(Text, nullable=True)
    run_metadata = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AIRunEvent(Base):
    """Append-only progress and diagnostic events for an AI run."""

    __tablename__ = "ai_run_events"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(PG_UUID(as_uuid=True), ForeignKey("ai_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=True)
    progress = Column(Integer, nullable=True)
    message = Column(String(500), nullable=True)
    payload = Column(JSONB, nullable=True)
    trace_id = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class WorkspaceLayout(Base):
    """Persisted dashboard layout, scoped to both user and workspace."""

    __tablename__ = "workspace_layouts"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id", name="unique_workspace_layout"),)

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    workspace_id = Column(PG_UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    layout = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class StudioOutput(Base):
    __tablename__ = "studio_outputs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    synthesis_node_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("synthesis_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    output_type = Column(String, nullable=False)  # mind_map|study_guide|quiz|flashcards|audio_overview|video_overview|infographic
    title = Column(String, nullable=False, default="Untitled")
    status = Column(String, nullable=False, default="pending")  # pending|processing|ready|failed
    content = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    run_id = Column(PG_UUID(as_uuid=True), ForeignKey("ai_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    runtime = Column(String(32), nullable=False, default="legacy", server_default="legacy")
    source_scope = Column(JSONB, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    idempotency_key = Column(String(255), nullable=True, index=True)
    progress = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    workspace = relationship("Workspace", back_populates="studio_outputs")


class StudioOutputCitation(Base):
    __tablename__ = "studio_output_citations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    studio_output_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("studio_outputs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    page_number = Column(Integer, nullable=True)
    quote = Column(Text, nullable=True)
    source_url = Column(String(2083), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WorkspaceGraphEdge(Base):
    """A user-drawn connection between two source nodes on the research canvas."""
    __tablename__ = "workspace_graph"
    __table_args__ = (
        UniqueConstraint("workspace_id", "from_document_id", "to_document_id", name="unique_edge"),
        CheckConstraint("from_document_id <> to_document_id", name="no_self_edge"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    from_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    to_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class CanvasPosition(Base):
    """Persisted x/y of a document node on the canvas."""
    __tablename__ = "canvas_positions"

    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    x_pos = Column(Float, nullable=False, default=0.0)
    y_pos = Column(Float, nullable=False, default=0.0)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class UserProfile(Base):
    """Stores user specific profile settings such as onboarding flags."""
    __tablename__ = "user_profiles"

    user_id = Column(String(255), primary_key=True)
    tour_completed = Column(Boolean, nullable=False, default=False)
    marketing_opt_in = Column(Boolean, nullable=False, default=False)


class SynthesisNode(Base):
    __tablename__ = "synthesis_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String, nullable=False, default="Synthesis")
    x_pos = Column(Float, nullable=False, default=0)
    y_pos = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SynthesisInput(Base):
    __tablename__ = "synthesis_inputs"
    __table_args__ = (
        UniqueConstraint(
            "synthesis_node_id", "document_id", name="unique_synthesis_input"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    synthesis_node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("synthesis_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AudioOverviewRow(Base):
    __tablename__ = "audio_overviews"

    id           = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False, index=True)
    title        = Column(String, nullable=False)
    style        = Column(String, nullable=False, default="deep_dive")
    voice        = Column(String, nullable=False, default="atlas-offline")
    duration     = Column(Float, nullable=False, default=0)
    audio_path   = Column(String, nullable=True)
    transcript   = Column(JSONB, nullable=False, default=list)
    share_token  = Column(String, unique=True, nullable=True, index=True)
    is_public    = Column(Boolean, nullable=False, default=False)
    status       = Column(String, nullable=False, default="ready")
    source_ids   = Column(JSONB, nullable=True)
    length_minutes = Column(Integer, nullable=True)
    failure_reason = Column(Text, nullable=True)
    job_id       = Column(UUID(as_uuid=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())


class MediaJob(Base):
    """Long-running media ingest and Studio generation jobs."""

    __tablename__ = "media_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    studio_output_id = Column(UUID(as_uuid=True), ForeignKey("studio_outputs.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(40), nullable=False)
    status = Column(String(20), nullable=False, default="queued", index=True)
    stage = Column(String(80), nullable=False, default="queued")
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=2)
    idempotency_key = Column(String(255), nullable=True)
    failure_reason = Column(Text, nullable=True)
    callback_token = Column(String(128), nullable=True, index=True)
    provider_job_id = Column(String(128), nullable=True, index=True)
    payload = Column(JSONB, nullable=False, default=dict)
    result = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)


class WorkspaceConnection(Base):
    __tablename__ = "workspace_connections"

    id                = Column(String, primary_key=True, default=lambda: "conn_" + uuid.uuid4().hex[:16])
    user_id           = Column(String, nullable=False, index=True)
    workspace_id      = Column(String, nullable=False, index=True)
    provider          = Column(String, nullable=False, default="google")   # 'google'
    account_email     = Column(String, nullable=True)
    scope             = Column(String, nullable=True)
    # encrypted refresh token (ciphertext only) + which key encrypted it
    refresh_token_enc = Column(String, nullable=False)
    key_id            = Column(String, nullable=False, default="v1")
    # cached short-lived access token (re-fetched on expiry)
    access_token      = Column(String, nullable=True)
    access_expires_at = Column(Float, nullable=True)
    status            = Column(String, nullable=False, default="connected")  # connected | revoked
    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DriveWatchChannel(Base):
    __tablename__ = "drive_watch_channels"

    id            = Column(String, primary_key=True, default=lambda: "wch_" + uuid.uuid4().hex[:16])
    workspace_id  = Column(String, nullable=False, index=True)
    source_id     = Column(String, nullable=False, index=True)
    file_id       = Column(String, nullable=False)
    channel_id    = Column(String, nullable=False, unique=True, index=True)
    resource_id   = Column(String, nullable=False)
    channel_token = Column(String, nullable=False)
    expiration    = Column(Float, nullable=True)
    last_synced   = Column(Float, nullable=True)
    status        = Column(String, nullable=False, default="active")
    created_at    = Column(DateTime(timezone=True), server_default=func.now())


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id           = Column(String, primary_key=True, default=lambda: "mem_" + uuid.uuid4().hex[:16])
    workspace_id = Column(String, nullable=False, index=True)
    user_id      = Column(String, nullable=False, index=True)
    role         = Column(String, nullable=False, default="viewer")  # owner | editor | viewer
    added_by     = Column(String, nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())


class WorkspaceInvite(Base):
    __tablename__ = "workspace_invites"

    id           = Column(String, primary_key=True, default=lambda: "inv_" + uuid.uuid4().hex[:16])
    workspace_id = Column(String, nullable=False, index=True)
    email        = Column(String, nullable=False, index=True)
    role         = Column(String, nullable=False, default="viewer")  # editor | viewer (never owner)
    token_hash   = Column(String, nullable=False, unique=True, index=True)
    invited_by   = Column(String, nullable=True)
    status       = Column(String, nullable=False, default="pending")
    expires_at   = Column(Float, nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    accepted_at  = Column(Float, nullable=True)
