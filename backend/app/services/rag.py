import uuid
import json
import logging
import time
import re
from typing import List, Dict, Any, AsyncGenerator, Tuple, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from ..models import ChatMessage, Document
from ..core.providers import provider_registry, ProviderError

logger = logging.getLogger("atlaslm.rag")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(
    logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s")
)
if not logger.handlers:
    logger.addHandler(_handler)

# How many prior conversation turns to replay to the model.
HISTORY_TURNS = 6

# Matches [source_12] style tags exactly (used for citation extraction).
CITATION_TAG_RE = re.compile(r"\[(source_\d+)\]")


class RAGService:
    GREETING_PATTERN = re.compile(
        r"^\s*(hi|hello|hey|yo|howdy|good morning|good afternoon|good evening|"
        r"thanks|thank you|thx)\s*[!.]*\s*$",
        re.IGNORECASE,
    )

    @classmethod
    def get_conversational_response(cls, user_message: str) -> Optional[str]:
        normalized = user_message.strip().lower().rstrip("!. ")
        if not normalized:
            return None
        if normalized in {"thanks", "thank you", "thx"}:
            return (
                "You're welcome. I can help you analyze your sources "
                "whenever you're ready."
            )
        capability_markers = (
            "what can you do",
            "what are your capabilities",
            "capabilities",
            "help",
        )
        if any(marker in normalized for marker in capability_markers):
            return (
                "Atlas AI can answer questions about your notebook, summarize "
                "ready sources with citations, compare source claims, draft notes, "
                "and help generate study guides, quizzes, flashcards, maps, and "
                "audio overview scripts. Add or index at least one source for "
                "grounded answers."
            )
        if cls.GREETING_PATTERN.match(user_message):
            return "Hello. How can I help you with your research today?"
        return None

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    # Retrieval
    # ------------------------------------------------------------------ #

    async def retrieve_relevant_chunks(
        self,
        workspace_id: uuid.UUID,
        query: str,
        provider_name: Optional[str] = None,
        top_k: int = 8,
        scope_doc_ids: Optional[List[uuid.UUID]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Embeds the query and runs a pgvector cosine search, restricted to
        chunks whose documents were embedded with the SAME embedding model
        (prevents cross-model vector-space corruption).
        """
        logger.info(
            "Retrieving context for query: '%s...' (workspace: %s)",
            query[:60],
            workspace_id,
        )
        start_time = time.time()

        embedding_provider = provider_registry.get_embeddings(provider_name)
        query_vector = await embedding_provider.embed_query(query)
        logger.info(
            "Query vector generated with %s in %.2fs",
            embedding_provider.model_id,
            time.time() - start_time,
        )

        vector_str = "[" + ",".join(map(str, query_vector)) + "]"

        scope_filter = ""
        params = {
            "query_vector": vector_str,
            "workspace_id": workspace_id,
            "model_id": embedding_provider.model_id,
            "top_k": top_k,
        }
        if scope_doc_ids is not None:
            scope_filter = "AND d.id IN :scope_doc_ids"
            params["scope_doc_ids"] = tuple(scope_doc_ids)

        db_start = time.time()
        sql_query = text(
            f"""
            SELECT dc.id, dc.content, dc.page_number, dc.chunk_index,
                   d.id AS document_id, d.filename,
                   (dc.embedding <=> :query_vector) AS distance,
                   dc.sheet, dc.timestamp, d.source_url, d.file_type,
                   dc.speaker, dc.start_ms, dc.end_ms, dc.region,
                   dc.video_id, dc.source_kind, d.youtube_video_id
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE d.workspace_id = :workspace_id
              AND d.status = 'ready'
              {scope_filter}
              AND (d.embedding_model IS NULL OR d.embedding_model = :model_id)
            ORDER BY distance ASC
            LIMIT :top_k
            """
        )
        results = self.db.execute(sql_query, params).fetchall()
        logger.info(
            "pgvector returned %d matches in %.3fs",
            len(results),
            time.time() - db_start,
        )

        matched_chunks = []
        for idx, row in enumerate(results):
            score = 1.0 - float(row[6])
            logger.info(
                "Match #%d: File='%s', Page=%s, Distance=%.4f (Score=%.4f)",
                idx + 1, row[5], row[2], float(row[6]), score,
            )
            matched_chunks.append(
                {
                    "chunk_id": row[0],
                    "content": row[1],
                    "page_number": row[2],
                    "chunk_index": row[3],
                    "document_id": row[4],
                    "filename": row[5],
                    "score": score,
                    "sheet": row[7],
                    "timestamp": row[8],
                    "source_url": row[9],
                    "file_type": row[10],
                    "speaker": row[11],
                    "start_ms": row[12],
                    "end_ms": row[13],
                    "region": row[14],
                    "video_id": row[15],
                    "source_kind": row[16],
                    "youtube_video_id": row[17],
                }
            )
        return matched_chunks

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #

    def construct_system_prompt(
        self,
        chunks: List[Dict[str, Any]],
        answer_mode: str = "sources",
    ) -> Tuple[str, Dict[str, Any]]:
        source_mapping = {}
        context_blocks = []

        for idx, chunk in enumerate(chunks):
            tag = f"source_{idx + 1}"
            video_id = chunk.get("video_id") or chunk.get("youtube_video_id")
            start_s = None
            if chunk.get("start_ms") is not None:
                start_s = int(chunk["start_ms"]) // 1000
            elif chunk.get("timestamp") is not None:
                start_s = int(chunk["timestamp"])
            source_url = chunk.get("source_url")
            if video_id and start_s is not None:
                source_url = f"https://www.youtube.com/watch?v={video_id}&t={start_s}"
            source_mapping[tag] = {
                "tag": tag,
                "chunk_id": str(chunk["chunk_id"]),
                "document_id": str(chunk["document_id"]),
                "filename": chunk["filename"],
                "page_number": chunk["page_number"],
                "content": chunk["content"],
                "sheet": chunk.get("sheet"),
                "timestamp": chunk.get("timestamp"),
                "source_url": source_url,
                "file_type": chunk.get("file_type"),
                "speaker": chunk.get("speaker"),
                "start_ms": chunk.get("start_ms"),
                "end_ms": chunk.get("end_ms"),
                "region": chunk.get("region") or ("full" if chunk.get("file_type") == "image" else None),
                "video_id": video_id,
                "source_kind": chunk.get("source_kind"),
            }
            loc = f"File: {chunk['filename']}"
            if chunk.get("speaker"):
                loc += f", Speaker: {chunk['speaker']}"
            if start_s is not None:
                loc += f", t={start_s}s"
            elif chunk.get("region"):
                loc += f", region={chunk['region']}"
            elif chunk.get("page_number"):
                loc += f", Page: {chunk['page_number']}"
            context_blocks.append(
                f"--- START SOURCE {tag} ({loc}) ---\n"
                f"{chunk['content']}\n"
                f"--- END SOURCE {tag} ---"
            )

        context_str = "\n\n".join(context_blocks)

        if answer_mode == "sources":
            mode_rules = (
                "You are AtlasLM, a professional, strictly source-grounded research assistant.\n"
                "Use ONLY the provided sources below. If the answer is not present, say exactly: "
                "'I could not find that information in the uploaded sources.' Do not add general knowledge.\n"
                "Every factual claim MUST carry the source tag where the fact was found, such as [source_1].\n"
            )
        elif answer_mode == "general":
            mode_rules = (
                "You are AtlasLM, a capable general-purpose AI research assistant.\n"
                "Answer from your broad knowledge. Do not pretend a claim came from a user source unless you cite it.\n"
                "If the question asks for current facts, explain that a live research search may be needed.\n"
            )
        else:
            mode_rules = (
                "You are AtlasLM, a capable general-purpose AI research assistant with access to the user's sources.\n"
                "Use the provided source blocks when they directly answer or materially inform the question, and cite those claims with [source_N].\n"
                "If the sources are unrelated or do not contain the answer, answer from your broad general knowledge instead. Do not say you cannot answer merely because the sources do not mention something.\n"
                "When an answer is primarily general knowledge, start with 'General knowledge'. When it is source-backed, cite the relevant claims.\n"
            )

        system_prompt = (
            f"{mode_rules}\n"
            "Source blocks may contain structured data, tables, lists, and timestamped transcripts. Scan them carefully.\n"
            "Never cite tags that are not in the provided list. No emojis. Use clear, professional formatting.\n"
            "You may use conversation history to resolve references.\n"
            "Punctuation style: write like a careful human editor. NEVER use em dashes, en dashes, or ellipsis characters.\n\n"
            f"=== RETRIEVED SOURCES ===\n{context_str or 'No source excerpts were retrieved for this question.'}\n"
        )
        logger.info("Grounded prompt constructed with %d context sources.", len(chunks))
        return system_prompt, source_mapping

    def _load_history_messages(self, session_id: uuid.UUID) -> List[dict]:
        """Loads the last HISTORY_TURNS*2 messages for conversational context."""
        rows = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(HISTORY_TURNS * 2)
            .all()
        )
        history = []
        for msg in reversed(rows):
            role = "assistant" if msg.role == "assistant" else "user"
            # Strip citation tags from prior assistant turns to keep them
            # from confusing the model about the CURRENT source numbering.
            content = CITATION_TAG_RE.sub("", msg.content)
            history.append({"role": role, "content": content})
        return history

    # ------------------------------------------------------------------ #
    # Main streaming entry point
    # ------------------------------------------------------------------ #

    async def execute_rag_chat_stream(
        self,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        user_message: str,
        provider_name: Optional[str] = None,
        answer_mode: str = "auto",
        scope_doc_ids: Optional[List[uuid.UUID]] = None,
    ) -> AsyncGenerator[str, None]:
        logger.info(
            "Starting RAG chat stream for session %s in workspace %s",
            session_id, workspace_id,
        )

        # Load history BEFORE saving the new user message (so it isn't doubled).
        history = self._load_history_messages(session_id)

        # 1. Persist user message
        self.db.add(
            ChatMessage(
                id=uuid.uuid4(),
                session_id=session_id,
                role="user",
                content=user_message,
            )
        )
        self.db.commit()

        answer_mode = answer_mode if answer_mode in {"auto", "sources", "general"} else "auto"

        # 2. Conversational fast-path (greetings/thanks)
        conversational_response = self.get_conversational_response(user_message)
        if conversational_response:
            yield self._sse("data", {"type": "chunk", "content": conversational_response})
            self._save_assistant(session_id, conversational_response, [])
            yield "event: end\ndata: [DONE]\n\n"
            return

        # 2b. Empty-scope guard (when scope is present but empty)
        if answer_mode == "sources" and scope_doc_ids is not None and len(scope_doc_ids) == 0:
            msg = (
                "No sources are wired into this synthesis node yet. "
                "Connect one or more sources to it, then ask again."
            )
            yield self._sse("data", {"type": "chunk", "content": msg})
            self._save_assistant(session_id, msg, [])
            yield "event: end\ndata: [DONE]\n\n"
            return

        # 3. Empty-ready-source guard (failed or indexing docs cannot ground chat)
        ready_query = (
            self.db.query(Document)
            .filter(Document.workspace_id == workspace_id)
            .filter(Document.status == "ready")
        )
        if scope_doc_ids is not None:
            ready_query = ready_query.filter(Document.id.in_(scope_doc_ids))
        ready_doc_count = ready_query.count()
        if answer_mode == "sources" and ready_doc_count == 0:
            msg = (
                "I can answer quick AtlasLM questions right now, but grounded "
                "research answers need at least one ready source. Add a document, "
                "paste text, or wait for indexing to finish, then ask again."
            )
            yield self._sse("data", {"type": "chunk", "content": msg})
            self._save_assistant(session_id, msg, [])
            yield "event: end\ndata: [DONE]\n\n"
            return

        # 4. Retrieval
        chunks: List[Dict[str, Any]] = []
        if answer_mode != "general":
            try:
                chunks = await self.retrieve_relevant_chunks(
                    workspace_id, user_message, provider_name, scope_doc_ids=scope_doc_ids
                )
            except ProviderError as e:
                if answer_mode == "sources":
                    yield self._sse("error", {"error": e.public_message})
                    return
                logger.warning("Optional source retrieval failed, continuing with general knowledge: %s", e)
            except Exception as e:
                if answer_mode == "sources":
                    logger.error("Retrieval failed: %s", e, exc_info=True)
                    yield self._sse(
                        "error",
                        {"error": "AtlasLM could not search your sources right now. Please try again."},
                    )
                    return
                logger.warning("Optional source retrieval failed, continuing with general knowledge: %s", e)

        if answer_mode == "sources" and not chunks:
            msg = "I could not find that information in the uploaded sources."
            yield self._sse("data", {"type": "chunk", "content": msg})
            self._save_assistant(session_id, msg, [])
            yield "event: end\ndata: [DONE]\n\n"
            return

        # 5. Prompt + citation metadata
        system_prompt, source_mapping = self.construct_system_prompt(chunks, answer_mode=answer_mode)
        yield self._sse(
            "metadata",
            {
                "type": "metadata",
                "sources": source_mapping,
                "answer_mode": answer_mode,
                "has_source_context": bool(chunks),
            },
        )

        # 6. Build full message list: system + history + current question
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        # 7. Stream the answer
        full_content = ""
        try:
            llm = provider_registry.get_llm(provider_name)
            stream_start = time.time()
            chunk_count = 0
            async for piece in llm.generate_stream(messages):
                full_content += piece
                chunk_count += 1
                yield self._sse("data", {"type": "chunk", "content": piece})
            logger.info(
                "Stream finished: %d chunks in %.2fs",
                chunk_count, time.time() - stream_start,
            )
        except ProviderError as e:
            yield self._sse("error", {"error": e.public_message})
            return
        except Exception as e:
            logger.error("LLM stream error: %s", e, exc_info=True)
            yield self._sse(
                "error",
                {"error": "AtlasLM could not complete the response. Please try again."},
            )
            return

        # 8. Extract citations actually used (exact tag matching, no
        #    source_1/source_10 substring collisions).
        used_tags = set(CITATION_TAG_RE.findall(full_content))
        used_citations = [
            details for tag, details in source_mapping.items() if tag in used_tags
        ]
        logger.info("Verified %d active source citations.", len(used_citations))

        # 9. Persist assistant message
        self._save_assistant(session_id, full_content, used_citations)
        yield "event: end\ndata: [DONE]\n\n"

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _sse(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload)}\n\n"

    def _save_assistant(
        self, session_id: uuid.UUID, content: str, citations: List[dict]
    ):
        try:
            self.db.add(
                ChatMessage(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    role="assistant",
                    content=content,
                    citations=citations,
                )
            )
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error("Failed to persist assistant message: %s", e)


# ------------------------------------------------------------------ #
# Studio Helper Functions (Patch 002)
# ------------------------------------------------------------------ #

_studio_loop = None
_studio_thread = None

def get_studio_loop():
    global _studio_loop, _studio_thread
    import asyncio
    import threading
    if _studio_loop is None:
        _studio_loop = asyncio.new_event_loop()
        def run_loop():
            asyncio.set_event_loop(_studio_loop)
            _studio_loop.run_forever()
        _studio_thread = threading.Thread(target=run_loop, daemon=True)
        _studio_thread.start()
    return _studio_loop


def _run_coroutine_sync(coro):
    import asyncio
    loop = get_studio_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


def retrieve_chunks(notebook_id: str, query: str, source_ids: List[str], k: int) -> List[Dict[str, Any]]:
    from app.core.database import SessionLocal
    import uuid
    from sqlalchemy import text
    
    # Resolve workspace ID
    ws_id = uuid.UUID(notebook_id) if isinstance(notebook_id, str) else notebook_id
    
    async def _retrieve():
        # RAGService embeds the query using the default provider.
        from app.core.providers import provider_registry
        embedding_provider = provider_registry.get_embeddings(None)
        query_vector = await embedding_provider.embed_query(query)
        return query_vector, embedding_provider.model_id

    # Run embedding query synchronously and safely
    query_vector, model_id = _run_coroutine_sync(_retrieve())
        
    vector_str = "[" + ",".join(map(str, query_vector)) + "]"
    
    db = SessionLocal()
    try:
        source_filter = ""
        params = {
            "query_vector": vector_str,
            "workspace_id": ws_id,
            "model_id": model_id,
            "top_k": k,
        }
        if source_ids:
            source_filter = "AND d.id IN :source_ids"
            params["source_ids"] = tuple(uuid.UUID(sid) if isinstance(sid, str) else sid for sid in source_ids)

        sql_query = text(
            f"""
            SELECT dc.id, dc.content, dc.page_number, dc.chunk_index,
                   d.id AS document_id, d.filename,
                   dc.sheet, dc.timestamp, dc.speaker, dc.start_ms, dc.end_ms,
                   dc.region, dc.video_id, dc.source_kind, d.youtube_video_id, d.source_url
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE d.workspace_id = :workspace_id
              {source_filter}
              AND (d.embedding_model IS NULL OR d.embedding_model = :model_id)
            ORDER BY dc.embedding <=> :query_vector ASC
            LIMIT :top_k
            """
        )
        results = db.execute(sql_query, params).fetchall()
        
        matched_chunks = []
        for row in results:
            matched_chunks.append({
                "chunk_id": row[0],
                "text": row[1],
                "page": row[2],
                "chunk_index": row[3],
                "document_id": row[4],
                "filename": row[5],
                "sheet": row[6],
                "timestamp": row[7],
                "speaker": row[8],
                "start_ms": row[9],
                "end_ms": row[10],
                "region": row[11],
                "video_id": row[12],
                "source_kind": row[13],
                "youtube_video_id": row[14],
                "source_url": row[15],
            })
        return matched_chunks
    finally:
        db.close()


def call_model(system: str, user: str, stream: bool = False) -> str:
    from app.core.providers import provider_registry
    
    llm = provider_registry.get_llm(None)
    
    async def _run():
        return await llm.generate(prompt=user, system_prompt=system)
        
    return _run_coroutine_sync(_run())


def build_citation_map(chunks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    citation_map = {}
    for idx, chunk in enumerate(chunks):
        tag = f"source_{idx + 1}"
        citation_map[tag] = {
            "filename": chunk.get("filename", "source"),
            "page": chunk.get("page", "?"),
            "text": chunk.get("text", ""),
            "sheet": chunk.get("sheet"),
            "timestamp": chunk.get("timestamp"),
        }
    return citation_map


def persist_blocks(workspace_id, filename: str, kind: str, blocks: list, origin: str = "google_drive") -> str:
    import uuid
    from app.core.database import SessionLocal
    from app.services.pipeline import DocumentPipeline
    
    # Inject meta if it doesn't exist
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if "meta" not in b or b["meta"] is None:
            b["meta"] = {}
        b["meta"].setdefault("origin", origin)
        b["meta"].setdefault("source_label", "Google Drive")
    
    db = SessionLocal()
    try:
        pipeline = DocumentPipeline(db)
        async def _run():
            doc = await pipeline.ingest_extracted_blocks(
                workspace_id=uuid.UUID(str(workspace_id)),
                filename=filename,
                file_type=kind,
                blocks=blocks,
                source_type=origin,
            )
            return str(doc.id)
        
        return _run_coroutine_sync(_run())
    finally:
        db.close()


