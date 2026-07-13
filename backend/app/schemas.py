from pydantic import BaseModel, Field
from typing import List, Optional, Any, Literal
from uuid import UUID
from datetime import datetime

# Workspace schemas
class WorkspaceBase(BaseModel):
    name: str

class WorkspaceCreate(WorkspaceBase):
    pass

class WorkspaceUpdate(WorkspaceBase):
    pass

class WorkspaceOut(WorkspaceBase):
    id: UUID
    created_at: datetime
    user_id: Optional[str] = None
    
    class Config:
        from_attributes = True

# Document schemas
class DocumentOut(BaseModel):
    id: UUID
    workspace_id: UUID
    filename: str
    file_type: str
    source_url: Optional[str] = None
    status: str = "ready"
    error_message: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# Document Chunk details (for citations)
class CitationChunk(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: Optional[int] = None
    content: str
    score: Optional[float] = None

# ChatMessage schemas
class ChatMessageBase(BaseModel):
    role: str
    content: str

class ChatMessageCreate(BaseModel):
    content: str
    synthesis_node_id: Optional[UUID] = None
    mode: Literal["auto", "sources", "general"] = "auto"

class ChatMessageOut(ChatMessageBase):
    id: UUID
    session_id: UUID
    citations: Optional[List[Any]] = None
    runtime: str = "legacy"
    trace_id: Optional[str] = None
    source_scope: Optional[Any] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# ChatSession schemas
class ChatSessionCreate(BaseModel):
    title: Optional[str] = "New Chat"

class ChatSessionOut(BaseModel):
    id: UUID
    workspace_id: UUID
    title: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class ChatSessionDetailsOut(ChatSessionOut):
    messages: List[ChatMessageOut] = []
    
    class Config:
        from_attributes = True

# Ingestion URL Schema
class URLIngestRequest(BaseModel):
    url: str
    language: Optional[str] = None
    provider: Optional[str] = None

class TextIngestRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=180)
    content: str = Field(..., min_length=1)
    provider: Optional[str] = None

StudioOutputType = Literal["report", "mind_map", "study_guide", "quiz", "flashcards"]


class StudioOutputCreate(BaseModel):
    output_type: StudioOutputType
    title: str | None = None
    # Optional. When set, generation is scoped to this synthesis node's inputs,
    # exactly like scoped chat in Patch 007. When null, uses the whole workspace.
    synthesis_node_id: UUID | None = None
    source_ids: List[UUID] | None = None
    length: Literal["brief", "standard", "deep"] = "standard"
    focus: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=255)


class StudioCitationOut(BaseModel):
    document_id: UUID
    chunk_id: UUID | None = None
    page_number: int | None = None
    filename: str | None = None
    quote: str | None = None
    source_url: str | None = None

    class Config:
        from_attributes = True


class StudioOutputOut(BaseModel):
    id: UUID
    workspace_id: UUID
    synthesis_node_id: UUID | None
    output_type: StudioOutputType
    title: str
    status: str
    content: Any | None
    error: str | None
    run_id: UUID | None = None
    runtime: str = "legacy"
    source_scope: Any | None = None
    retry_count: int = 0
    version: int = 1
    progress: int = 0
    created_at: datetime
    citations: list[StudioCitationOut] = []

    class Config:
        from_attributes = True


class ReportCreate(BaseModel):
    title: str | None = None
    source_ids: List[UUID] | None = None
    length: Literal["brief", "standard", "deep"] = "standard"
    focus: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=255)


class AIRunEventOut(BaseModel):
    id: UUID
    run_id: UUID
    event_type: str
    status: str | None = None
    progress: int | None = None
    message: str | None = None
    payload: Any | None = None
    trace_id: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class AIRunOut(BaseModel):
    id: UUID
    user_id: str
    workspace_id: UUID
    notebook_id: UUID
    agent_id: str
    workflow_id: str | None = None
    runtime: str
    status: str
    request_id: str | None = None
    trace_id: str | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class WorkspaceLayoutOut(BaseModel):
    workspace_id: UUID
    layout: dict[str, Any]
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceLayoutUpdate(BaseModel):
    layout: dict[str, Any]


class GraphEdgeCreate(BaseModel):
    from_document_id: UUID
    to_document_id: UUID


class GraphEdgeOut(BaseModel):
    id: UUID
    workspace_id: UUID
    from_document_id: UUID
    to_document_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class NodePositionUpdate(BaseModel):
    document_id: UUID
    x_pos: float
    y_pos: float


class OnboardingFlagsOut(BaseModel):
    tour_completed: bool
    marketing_opt_in: bool


class OnboardingFlagsUpdate(BaseModel):
    tour_completed: Optional[bool] = None
    marketing_opt_in: Optional[bool] = None


class SynthesisNodeCreate(BaseModel):
    title: str = "Synthesis"
    x_pos: float = 0
    y_pos: float = 0


class SynthesisNodeUpdate(BaseModel):
    title: Optional[str] = None
    x_pos: Optional[float] = None
    y_pos: Optional[float] = None


class SynthesisNodeOut(BaseModel):
    id: UUID
    workspace_id: UUID
    title: str
    x_pos: float
    y_pos: float
    created_at: datetime
    input_document_ids: List[UUID] = []

    class Config:
        from_attributes = True


class SynthesisInputCreate(BaseModel):
    document_id: UUID


