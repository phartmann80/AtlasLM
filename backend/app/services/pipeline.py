import fitz  # PyMuPDF
import uuid
import logging
import asyncio
import os
import re
import tempfile
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from ..models import Document, DocumentChunk
from ..core.providers import provider_registry, ProviderError
from .parsers import (
    extract_text_from_xlsx,
    extract_text_from_pptx,
)
from .docx_extract import extract_docx_markdown, DocxExtractError
from .csv_extract import extract_csv_markdown, CsvExtractError
from .web_extract import extract_text_from_html

logger = logging.getLogger("atlaslm.ingestion")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(
    logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s")
)
if not logger.handlers:
    logger.addHandler(_handler)


class DocumentPipeline:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    # Extraction
    # ------------------------------------------------------------------ #

    def extract_text_from_pdf(
        self, file_bytes: bytes, filename: str
    ) -> List[Dict[str, Any]]:
        logger.info(
            "Starting PDF extraction: %s (%d bytes)", filename, len(file_bytes)
        )
        pages_content = []
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pages_content.append(
                    {"page_number": page_num + 1, "content": page.get_text("text")}
                )
            doc.close()
            logger.info(
                "PDF parsed: %s (%d pages)", filename, len(pages_content)
            )
        except Exception as e:
            logger.error("PDF parser failure for %s: %s", filename, e, exc_info=True)
            raise ValueError(f"Failed to parse PDF {filename}: {e}")
        return pages_content

    def extract_text_from_txt_or_md(
        self, file_bytes: bytes, filename: str
    ) -> List[Dict[str, Any]]:
        logger.info("Starting text extraction: %s", filename)
        try:
            text = file_bytes.decode("utf-8", errors="ignore")
            return [{"page_number": 1, "content": text}]
        except Exception as e:
            raise ValueError(f"Failed to parse text document: {e}")

    # ------------------------------------------------------------------ #
    # Chunking
    # ------------------------------------------------------------------ #

    def recursive_chunk_text(
        self,
        pages: List[Dict[str, Any]],
        chunk_size: int = 800,
        chunk_overlap: int = 150,
    ) -> List[Dict[str, Any]]:
        logger.info(
            "Chunking: size=%d overlap=%d", chunk_size, chunk_overlap
        )
        chunks = []
        chunk_idx = 0
        separators = ["\n\n", "\n", " ", ""]

        for page_data in pages:
            page_num = page_data["page_number"]
            text = page_data["content"]
            pos = 0
            text_len = len(text)
            if text_len == 0:
                continue

            while pos < text_len:
                end_pos = min(pos + chunk_size, text_len)
                if end_pos < text_len:
                    split_found = False
                    for sep in separators:
                        if sep == "":
                            continue
                        search_start = max(pos, end_pos - chunk_overlap)
                        last_sep = text.rfind(sep, search_start, end_pos)
                        if last_sep != -1:
                            end_pos = last_sep + len(sep)
                            split_found = True
                            break
                    if not split_found:
                        end_pos = pos + chunk_size

                chunk_text = text[pos:end_pos].strip()
                if chunk_text:
                    chunk_item = {
                        "content": chunk_text,
                        "page_number": page_num,
                        "chunk_index": chunk_idx,
                        "char_start": pos,
                        "char_end": end_pos,
                    }
                    if "timestamp" in page_data:
                        chunk_item["timestamp"] = page_data["timestamp"]
                    if "sheet" in page_data:
                        chunk_item["sheet"] = page_data["sheet"]
                    chunks.append(chunk_item)
                    chunk_idx += 1

                pos = max(end_pos - chunk_overlap, pos + 1)
                if end_pos >= text_len:
                    break

        logger.info("Chunking complete: %d chunks.", len(chunks))
        return chunks

    # ------------------------------------------------------------------ #
    # Embeddings
    # ------------------------------------------------------------------ #

    async def generate_embeddings_with_retry(
        self,
        contents: List[str],
        provider_name: Optional[str] = None,
        max_retries: int = 3,
        batch_size: int = 64,
    ) -> List[List[float]]:
        """
        Batched embedding generation with exponential backoff.
        RAISES on final failure - never returns fabricated vectors.
        """
        embedding_provider = provider_registry.get_embeddings(provider_name)
        all_embeddings: List[List[float]] = []

        for batch_start in range(0, len(contents), batch_size):
            batch = contents[batch_start: batch_start + batch_size]
            delay = 1.0
            last_error: Optional[Exception] = None

            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(
                        "Embedding batch %d-%d (%d items, attempt %d)",
                        batch_start, batch_start + len(batch), len(batch), attempt,
                    )
                    vectors = await embedding_provider.embed_documents(batch)
                    all_embeddings.extend(vectors)
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "Embedding failure (attempt %d/%d): %s",
                        attempt, max_retries, e,
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(delay)
                        delay *= 2.0

            if last_error is not None:
                logger.error(
                    "Embedding generation failed permanently: %s", last_error
                )
                raise last_error  # FAIL FAST - no zero-vector fallback.

        return all_embeddings

    # ------------------------------------------------------------------ #
    # Ingestion
    def _blocks_to_pages(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pages = []
        for idx, block in enumerate(blocks):
            text = (block.get("text") or "").strip()
            if not text:
                continue
            page = {
                "page_number": block.get("page") or idx + 1,
                "content": text,
            }
            if block.get("timestamp") is not None:
                page["timestamp"] = block.get("timestamp")
            if block.get("sheet") is not None:
                page["sheet"] = block.get("sheet")
            pages.append(page)
        return pages

    def _parse_media_file(self, file_bytes, file_type, filename):
        suffix = os.path.splitext(filename or "")[1]
        if not suffix:
            suffix = ".wav" if file_type == "audio" else ".png"

        from .ingest.dispatcher import extract_blocks

        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            return self._blocks_to_pages(extract_blocks(file_type, tmp_path))
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _parse(self, file_bytes, file_type, filename, source_url=None):
        ft = file_type.lower()
        if ft == "pdf":
            return self.extract_text_from_pdf(file_bytes, filename)
        elif ft == "docx":
            try:
                text = extract_docx_markdown(file_bytes)
            except DocxExtractError as e:
                raise ValueError(str(e))
            return [{"page_number": 1, "content": text}]
        elif ft == "csv":
            try:
                text = extract_csv_markdown(file_bytes)
            except CsvExtractError as e:
                raise ValueError(str(e))
            return [{"page_number": 1, "content": text}]
        elif ft == "xlsx":
            return extract_text_from_xlsx(file_bytes, filename)
        elif ft == "pptx":
            return extract_text_from_pptx(file_bytes, filename)
        elif ft == "url":
            html = file_bytes.decode("utf-8", errors="ignore")
            return extract_text_from_html(html, source_url or filename)
        elif ft == "youtube":
            text = file_bytes.decode("utf-8", errors="replace")
            sections = []
            pattern = r'^##\s+\[(\d{1,2}:\d{2}(?::\d{2})?)\]'
            matches = list(re.finditer(pattern, text, re.MULTILINE))
            
            if not matches:
                return [{"page_number": 1, "content": text, "timestamp": 0.0}]
                
            for i, match in enumerate(matches):
                ts_str = match.group(1)
                
                parts = list(map(int, ts_str.split(":")))
                if len(parts) == 2:
                    seconds = float(parts[0] * 60 + parts[1])
                elif len(parts) == 3:
                    seconds = float(parts[0] * 3600 + parts[1] * 60 + parts[2])
                else:
                    seconds = 0.0
                
                start_idx = match.start()
                end_idx = matches[i+1].start() if i + 1 < len(matches) else len(text)
                section_content = text[start_idx:end_idx].strip()
                
                sections.append({
                    "page_number": i + 1,
                    "content": section_content,
                    "timestamp": seconds
                })
            return sections
        elif ft in ("audio", "image"):
            return self._parse_media_file(file_bytes, ft, filename)
        else:
            return self.extract_text_from_txt_or_md(file_bytes, filename)

    def create_pending_document(
        self,
        workspace_id,
        filename,
        file_type,
        source_url=None,
    ):
        import uuid as _uuid
        from ..models import Document
        document = Document(
            id=_uuid.uuid4(),
            workspace_id=workspace_id,
            filename=filename,
            file_type=file_type,
            source_url=source_url,
            status="processing",
            error_message=None,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    async def run_ingestion_for_document(self, document, file_bytes, file_type):
        import uuid as _uuid
        from ..models import DocumentChunk
        from ..core.providers import provider_registry

        logger.info("Worker ingestion start: '%s' (doc %s)", document.filename, document.id)

        pages_data = self._parse(file_bytes, file_type, document.filename, source_url=getattr(document, "source_url", None))

        chunks_data = self.recursive_chunk_text(pages_data)
        if not chunks_data:
            raise ValueError(
                f"No extractable text found in '{document.filename}'. "
                "The file may be empty or contain only images "
                "(scanned PDFs need OCR, which is not yet enabled)."
            )

        contents = [c["content"] for c in chunks_data]
        embeddings = await self.generate_embeddings_with_retry(contents=contents)

        if len(embeddings) != len(chunks_data):
            raise ValueError(
                "Embedding count mismatch during ingestion; aborting to protect data integrity."
            )

        document.embedding_model = provider_registry.get_embeddings(None).model_id

        for idx, chunk_info in enumerate(chunks_data):
            self.db.add(
                DocumentChunk(
                    id=_uuid.uuid4(),
                    document_id=document.id,
                    content=chunk_info["content"],
                    embedding=embeddings[idx],
                    page_number=chunk_info["page_number"],
                    chunk_index=chunk_info["chunk_index"],
                    char_start=chunk_info["char_start"],
                    char_end=chunk_info["char_end"],
                    timestamp=chunk_info.get("timestamp"),
                    sheet=chunk_info.get("sheet"),
                )
            )
        # NOTE: commit is done by the caller (worker) together with status='ready'
        # so chunks + ready-state are atomic.
        self.db.flush()
        logger.info(
            "Worker ingestion parsed+embedded: '%s' (%d chunks)",
            document.filename, len(chunks_data),
        )

    # ------------------------------------------------------------------ #

    async def ingest_document(
        self,
        workspace_id: uuid.UUID,
        filename: str,
        file_bytes: bytes,
        file_type: str,  # 'pdf', 'txt', 'md', 'url'
        source_url: Optional[str] = None,
        provider_name: Optional[str] = None,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
    ) -> Document:
        logger.info(
            "Ingesting '%s' into workspace %s", filename, workspace_id
        )

        pages_data = self._parse(file_bytes, file_type, filename, source_url=source_url)

        # 2. Chunk
        chunks_data = self.recursive_chunk_text(
            pages_data, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

        if not chunks_data:
            raise ValueError(
                f"No extractable text found in '{filename}'. "
                "The file may be empty or contain only images "
                "(scanned PDFs need OCR, which is not yet enabled)."
            )

        # 3. Embed FIRST (so a failure leaves no orphaned document record)
        contents = [c["content"] for c in chunks_data]
        embeddings = await self.generate_embeddings_with_retry(
            contents=contents, provider_name=provider_name
        )

        if len(embeddings) != len(chunks_data):
            raise ValueError(
                "Embedding count mismatch during ingestion; aborting to protect data integrity."
            )

        embedding_model_id = provider_registry.get_embeddings(
            provider_name
        ).model_id

        # 4. Persist document + chunks atomically
        try:
            document = Document(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                filename=filename,
                file_type=file_type,
                source_url=source_url,
                embedding_model=embedding_model_id,
                status="ready",
            )
            self.db.add(document)
            self.db.flush()

            for idx, chunk_info in enumerate(chunks_data):
                self.db.add(
                    DocumentChunk(
                        id=uuid.uuid4(),
                        document_id=document.id,
                        content=chunk_info["content"],
                        embedding=embeddings[idx],
                        page_number=chunk_info["page_number"],
                        chunk_index=chunk_info["chunk_index"],
                        char_start=chunk_info["char_start"],
                        char_end=chunk_info["char_end"],
                        timestamp=chunk_info.get("timestamp"),
                        sheet=chunk_info.get("sheet"),
                    )
                )

            self.db.commit()
            self.db.refresh(document)
        except Exception as e:
            self.db.rollback()
            logger.error("Ingestion persistence failure: %s", e, exc_info=True)
            raise

        logger.info(
            "Ingestion successful: '%s' -> document %s (%d chunks, model=%s)",
            filename, document.id, len(chunks_data), embedding_model_id,
        )
        return document

    async def ingest_extracted_blocks(
        self,
        workspace_id: uuid.UUID,
        filename: str,
        file_type: Optional[str] = None,
        blocks: List[Dict[str, Any]] = [],
        source_url: Optional[str] = None,
        provider_name: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> Document:
        logger.info(
            "Ingesting extracted blocks for '%s' into workspace %s", filename, workspace_id
        )

        # 1. Embed first
        contents = [b["text"] for b in blocks]
        embeddings = await self.generate_embeddings_with_retry(
            contents=contents, provider_name=provider_name
        )

        if len(embeddings) != len(blocks):
            raise ValueError(
                "Embedding count mismatch during ingestion; aborting to protect data integrity."
            )

        embedding_model_id = provider_registry.get_embeddings(
            provider_name
        ).model_id

        # Extract provenance from block metadata if present
        meta = blocks[0].get("meta") if (blocks and isinstance(blocks[0], dict)) else None
        origin = None
        source_label = None
        external_url = None
        research_query = None
        if meta:
            origin = meta.get("origin")
            source_label = meta.get("source_label")
            external_url = meta.get("url")
            research_query = meta.get("query")

        # 2. Persist document + chunks atomically
        try:
            document = Document(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                filename=filename,
                file_type=file_type or source_type or "unknown",
                source_url=source_url or external_url,
                embedding_model=embedding_model_id,
                status="ready",
                origin=origin,
                source_label=source_label,
                external_url=external_url,
                research_query=research_query,
            )
            self.db.add(document)
            self.db.flush()

            for idx, b in enumerate(blocks):
                char_offset = b.get("char_offset", 0)
                if char_offset is None:
                    char_offset = 0
                self.db.add(
                    DocumentChunk(
                        id=uuid.uuid4(),
                        document_id=document.id,
                        content=b["text"],
                        embedding=embeddings[idx],
                        page_number=b.get("page"),
                        chunk_index=idx,
                        char_start=char_offset,
                        char_end=char_offset + len(b["text"]),
                        sheet=b.get("sheet"),
                        timestamp=b.get("timestamp"),
                    )
                )

            self.db.commit()
            self.db.refresh(document)
        except Exception as e:
            self.db.rollback()
            logger.error("Ingestion persistence failure: %s", e, exc_info=True)
            raise

        logger.info(
            "Ingestion successful: '%s' -> document %s (%d chunks, model=%s)",
            filename, document.id, len(blocks), embedding_model_id,
        )
        return document
