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
                   dc.sheet, dc.timestamp, d.source_url, d.file_type
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE d.workspace_id = :workspace_id
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
                }
            )
        return matched_chunks

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #

    def construct_system_prompt(
        self, chunks: List[Dict[str, Any]]
    ) -> Tuple[str, Dict[str, Any]]:
        source_mapping = {}
        context_blocks = []

        for idx, chunk in enumerate(chunks):
            tag = f"source_{idx + 1}"
            source_mapping[tag] = {
                "tag": tag,
                "chunk_id": str(chunk["chunk_id"]),
                "document_id": str(chunk["document_id"]),
                "filename": chunk["filename"],
                "page_number": chunk["page_number"],
                "content": chunk["content"],
                "sheet": chunk.get("sheet"),
                "timestamp": chunk.get("timestamp"),
                "source_url": chunk.get("source_url"),
                "file_type": chunk.get("file_type"),
            }
            context_blocks.append(
                f"--- START SOURCE {tag} "
                f"(File: {chunk['filename']}, Page: {chunk['page_number']}) ---\n"
                f"{chunk['content']}\n"
                f"--- END SOURCE {tag} ---"
            )

        context_str = "\n\n".join(context_blocks)

        system_prompt = (
            "You are AtlasLM, a professional, strictly source-grounded research assistant.\n"
            "Your mission is to answer user questions using ONLY the provided sources below.\n\n"
            "=== STRICT RULES ===\n"
            "1. NEVER use knowledge outside the provided source blocks.\n"
            "2. Source blocks may contain STRUCTURED DATA: rows of 'Column: value' pairs "
            "from spreadsheets and CSV files, table rows, or lists. Scan every line of "
            "every source block carefully before concluding information is absent. An "
            "answer buried in the middle of a data block is still an answer.\n"
            "3. Only if the answer is truly not present in any source block, reply exactly "
            "with: 'I could not find that information in the uploaded sources.' "
            "Do not invent facts or add general knowledge under any circumstances.\n"
            "4. Every claim MUST carry the source tag in brackets where the fact was found "
            "(e.g. [source_1] or [source_2]). If multiple sources apply, cite all "
            "(e.g. [source_1][source_3]). Place citations at the end of clauses/sentences.\n"
            "5. NEVER mention tags that are not in the provided list.\n"
            "6. No emojis. Use clear, professional formatting.\n"
            "7. You may use the conversation history to resolve references "
            "(e.g. 'that section', 'the second point'), but facts must still come "
            "only from the sources.\n"
            "8. Punctuation style: write like a careful human editor. NEVER use em dashes, "
            "en dashes, or ellipsis characters in your output. Use commas, semicolons, "
            "colons, and periods instead. Hyphens are allowed only inside compound words "
            '(e.g. "re-ingestion", "key-value").\n\n'
            f"=== RETRIEVED SOURCES ===\n{context_str}\n"
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

        # 2. Conversational fast-path (greetings/thanks)
        conversational_response = self.get_conversational_response(user_message)
        if conversational_response:
            yield self._sse("data", {"type": "chunk", "content": conversational_response})
            self._save_assistant(session_id, conversational_response, [])
            yield "event: end\ndata: [DONE]\n\n"
            return

        # 2b. Empty-scope guard (when scope is present but empty)
        if scope_doc_ids is not None and len(scope_doc_ids) == 0:
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
        if ready_doc_count == 0:
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
        try:
            chunks = await self.retrieve_relevant_chunks(
                workspace_id, user_message, provider_name, scope_doc_ids=scope_doc_ids
            )
        except ProviderError as e:
            yield self._sse("error", {"error": e.public_message})
            return
        except Exception as e:
            logger.error("Retrieval failed: %s", e, exc_info=True)
            yield self._sse(
                "error",
                {"error": "AtlasLM could not search your sources right now. Please try again."},
            )
            return

        if not chunks:
            msg = "I could not find that information in the uploaded sources."
            yield self._sse("data", {"type": "chunk", "content": msg})
            self._save_assistant(session_id, msg, [])
            yield "event: end\ndata: [DONE]\n\n"
            return

        # 5. Prompt + citation metadata
        system_prompt, source_mapping = self.construct_system_prompt(chunks)
        yield self._sse("metadata", {"type": "metadata", "sources": source_mapping})

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
                   dc.sheet, dc.timestamp
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


