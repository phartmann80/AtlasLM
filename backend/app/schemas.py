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

class ChatMessageOut(ChatMessageBase):
    id: UUID
    session_id: UUID
    citations: Optional[List[Any]] = None
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

StudioOutputType = Literal["mind_map", "study_guide", "quiz", "flashcards"]


class StudioOutputCreate(BaseModel):
    output_type: StudioOutputType
    title: str | None = None
    # Optional. When set, generation is scoped to this synthesis node's inputs,
    # exactly like scoped chat in Patch 007. When null, uses the whole workspace.
    synthesis_node_id: UUID | None = None


class StudioCitationOut(BaseModel):
    document_id: UUID
    page_number: int | None = None

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
    created_at: datetime
    citations: list[StudioCitationOut] = []

    class Config:
        from_attributes = True


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


