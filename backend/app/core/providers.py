"""
AtlasLM Engine provider layer.

Design rules enforced here:
  1. FAIL FAST  - embedding failures RAISE. We never fabricate zero vectors,
                  because storing fake vectors silently corrupts retrieval.
  2. NO LEAKAGE - exceptions raised to callers are wrapped in ProviderError with
                  sanitized, AtlasLM-branded messages. Raw provider names/URLs
                  never reach the client.
  3. POOLING    - one shared httpx.AsyncClient per provider instance
                  (connection reuse = lower latency).
"""

import httpx
import json
import logging
from typing import List, AsyncGenerator, Optional

from .config import settings

logger = logging.getLogger("atlaslm.providers")


def normalize_model_name(value: Optional[str], fallback: str = "gpt-5-mini") -> str:
    """Resolve operator-friendly placeholders to a concrete provider model."""
    model = (value or "").strip()
    if not model or model.lower() in {"auto", "default"}:
        return fallback
    return model


class ProviderError(Exception):
    """Sanitized error safe to surface to API clients."""

    def __init__(self, public_message: str, internal_detail: str = ""):
        super().__init__(public_message)
        self.public_message = public_message
        # Internal detail goes to server logs ONLY - never to the client.
        if internal_detail:
            logger.error("Provider failure (internal): %s", internal_detail)


# Shared connection limits for all clients
_HTTP_LIMITS = httpx.Limits(max_keepalive_connections=10, max_connections=20)


class EmbeddingProvider:
    #: dimension of vectors this provider emits (DB column is Vector(1536))
    dimensions: int = 1536
    #: model identifier persisted per-document so we never mix vector spaces
    model_id: str = "unknown"

    async def embed_query(self, text: str) -> List[float]:
        raise NotImplementedError

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    async def aclose(self):
        pass


class LLMProvider:
    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    async def generate_stream(
        self, messages: List[dict]
    ) -> AsyncGenerator[str, None]:
        """messages: full OpenAI-style message list (system + history + user)."""
        raise NotImplementedError

    async def aclose(self):
        pass


# ---------------------------------------------------------------------------
# Embedding implementations
# ---------------------------------------------------------------------------

class OpenAICompatibleEmbedding(EmbeddingProvider):
    def __init__(self, base_url: str, api_key: str, model: str = "text-embedding-3-small"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.model_id = model
        self.dimensions = 1536
        self.timeout = 30.0

    @property
    def client(self) -> httpx.AsyncClient:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if not hasattr(self, "_clients"):
            self._clients = {}
        if loop not in self._clients:
            self._clients[loop] = httpx.AsyncClient(limits=_HTTP_LIMITS, timeout=self.timeout)
        return self._clients[loop]

    async def aclose(self):
        if hasattr(self, "_clients"):
            for c in self._clients.values():
                await c.aclose()
            self._clients.clear()

    async def embed_query(self, text: str) -> List[float]:
        res = await self.embed_documents([text])
        return res[0]

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not self.api_key:
            # FAIL FAST: a missing key must surface as an error, not mock vectors.
            raise ProviderError(
                "The AtlasLM engine is not configured. Please contact your administrator.",
                internal_detail=f"No API key configured for embedding endpoint {self.base_url}",
            )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"input": texts, "model": self.model}
        try:
            response = await self.client.post(
                f"{self.base_url}/embeddings", headers=headers, json=payload
            )
            response.raise_for_status()
            data = response.json()
            vectors = [item["embedding"] for item in data["data"]]
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                "The AtlasLM engine could not process this content right now. Please try again.",
                internal_detail=f"Embedding call failed ({self.base_url}): {exc!r}",
            ) from exc

        if len(vectors) != len(texts):
            raise ProviderError(
                "The AtlasLM engine returned an incomplete result. Please try again.",
                internal_detail=f"Embedding count mismatch: sent {len(texts)}, got {len(vectors)}",
            )
        return vectors



class OllamaEmbedding(EmbeddingProvider):
    def __init__(self, base_url: str, model: str = "nomic-embed-text"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_id = f"ollama/{model}"
        # nomic-embed-text is 768-dim; we pad to the 1536 column size.
        # Padding is consistent ONLY within this model space - which is why
        # model_id is persisted per document and enforced at query time.
        self.dimensions = 1536
        self.timeout = 30.0

    @property
    def client(self) -> httpx.AsyncClient:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if not hasattr(self, "_clients"):
            self._clients = {}
        if loop not in self._clients:
            self._clients[loop] = httpx.AsyncClient(limits=_HTTP_LIMITS, timeout=self.timeout)
        return self._clients[loop]

    async def aclose(self):
        if hasattr(self, "_clients"):
            for c in self._clients.values():
                await c.aclose()
            self._clients.clear()

    async def embed_query(self, text: str) -> List[float]:
        res = await self.embed_documents([text])
        return res[0]

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings: List[List[float]] = []
        for text in texts:
            try:
                response = await self.client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                )
                response.raise_for_status()
                vector = response.json()["embedding"]
            except Exception as exc:
                # FAIL FAST - do not append a zero vector.
                raise ProviderError(
                    "The local AtlasLM engine is unavailable. Please verify it is running.",
                    internal_detail=f"Ollama embedding failed ({self.base_url}): {exc!r}",
                ) from exc
            if len(vector) < 1536:
                vector = vector + [0.0] * (1536 - len(vector))
            elif len(vector) > 1536:
                vector = vector[:1536]
            embeddings.append(vector)
        return embeddings



# ---------------------------------------------------------------------------
# LLM implementations
# ---------------------------------------------------------------------------

class OpenAICompatibleLLM(LLMProvider):
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = 90.0

    @property
    def client(self) -> httpx.AsyncClient:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if not hasattr(self, "_clients"):
            self._clients = {}
        if loop not in self._clients:
            self._clients[loop] = httpx.AsyncClient(limits=_HTTP_LIMITS, timeout=self.timeout)
        return self._clients[loop]

    async def aclose(self):
        if hasattr(self, "_clients"):
            for c in self._clients.values():
                await c.aclose()
            self._clients.clear()

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return await self.generate_messages(messages)

    async def generate_messages(self, messages: List[dict], temperature: float = 0.1) -> str:
        payload = {"model": self.model, "messages": messages, "temperature": temperature}
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            raise ProviderError(
                "The AtlasLM engine could not generate a response. Please try again.",
                internal_detail=f"LLM generate failed ({self.base_url}): {exc!r}",
            ) from exc

    async def generate_stream(
        self, messages: List[dict]
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "stream": True,
        }
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0]["delta"]
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except ProviderError:
            raise
        except Exception as exc:
            # RAISE, never yield error text into the user's chat transcript.
            raise ProviderError(
                "The AtlasLM engine connection was interrupted. Please try again.",
                internal_detail=f"LLM stream failed ({self.base_url}): {exc!r}",
            ) from exc



class OllamaLLM(LLMProvider):
    def __init__(self, base_url: str, model: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = 120.0

    @property
    def client(self) -> httpx.AsyncClient:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if not hasattr(self, "_clients"):
            self._clients = {}
        if loop not in self._clients:
            self._clients[loop] = httpx.AsyncClient(limits=_HTTP_LIMITS, timeout=self.timeout)
        return self._clients[loop]

    async def aclose(self):
        if hasattr(self, "_clients"):
            for c in self._clients.values():
                await c.aclose()
            self._clients.clear()

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.1},
            "stream": False,
        }
        try:
            response = await self.client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()["message"]["content"]
        except Exception as exc:
            raise ProviderError(
                "The local AtlasLM engine is unavailable. Please verify it is running.",
                internal_detail=f"Ollama generate failed ({self.base_url}): {exc!r}",
            ) from exc

    async def generate_stream(
        self, messages: List[dict]
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model,
            "messages": messages,
            "options": {"temperature": 0.1},
            "stream": True,
        }
        try:
            async with self.client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                "The local AtlasLM engine connection was interrupted.",
                internal_detail=f"Ollama stream failed ({self.base_url}): {exc!r}",
            ) from exc



# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """
    Server-side provider routing. Clients NEVER pick a provider; routing is
    controlled by ATLAS_* settings only. Internal keys are never exposed.
    """

    def __init__(self):
        self._llms = {}
        self._embeddings = {}

        langdock_api_key = settings.LANGDOCK_API_CODE or settings.LANGDOCK_API_KEY
        langdock_model = normalize_model_name(
            settings.LANGDOCK_MODEL or settings.MODEL,
            fallback="gpt-5-mini",
        )

        if langdock_api_key:
            self._llms["langdock"] = OpenAICompatibleLLM(
                base_url=settings.LANGDOCK_ENDPOINT_URL,
                api_key=langdock_api_key,
                model=langdock_model,
            )
            self._embeddings["langdock"] = OpenAICompatibleEmbedding(
                base_url=settings.LANGDOCK_ENDPOINT_URL,
                api_key=langdock_api_key,
                model="text-embedding-ada-002",
            )

        if settings.BLACKBOX_API_KEY:
            self._llms["blackbox"] = OpenAICompatibleLLM(
                base_url="https://api.blackbox.ai/api/v1",
                api_key=settings.BLACKBOX_API_KEY,
                model="blackboxai",
            )

        if settings.OPENROUTER_API_KEY:
            self._llms["openrouter"] = OpenAICompatibleLLM(
                base_url=settings.OPENROUTER_ENDPOINT_URL,
                api_key=settings.OPENROUTER_API_KEY,
                model=settings.OPENROUTER_MODEL,
            )
            self._embeddings["openrouter"] = OpenAICompatibleEmbedding(
                base_url=settings.OPENROUTER_ENDPOINT_URL,
                api_key=settings.OPENROUTER_API_KEY,
                model="text-embedding-3-small",
            )

        if settings.OPENAI_API_KEY:
            self._llms["openai"] = OpenAICompatibleLLM(
                base_url="https://api.openai.com/v1",
                api_key=settings.OPENAI_API_KEY,
                model="gpt-4o",
            )
            self._embeddings["openai"] = OpenAICompatibleEmbedding(
                base_url="https://api.openai.com/v1",
                api_key=settings.OPENAI_API_KEY,
                model="text-embedding-3-small",
            )

        # Ollama is always registered as the offline fallback.
        self._llms["ollama"] = OllamaLLM(
            base_url=settings.OLLAMA_ENDPOINT_URL, model="llama3"
        )
        self._embeddings["ollama"] = OllamaEmbedding(
            base_url=settings.OLLAMA_ENDPOINT_URL, model="nomic-embed-text"
        )

    # -- server-side routing -------------------------------------------------

    def _resolve(self, table: dict, preferred: Optional[str]) -> str:
        order = [
            preferred or settings.ATLAS_ACTIVE_PROVIDER,
            "langdock",
            "openrouter",
            "openai",
            "blackbox",
            "ollama",
        ]
        for name in order:
            if name and name in table:
                return name
        raise ProviderError(
            "No AtlasLM engine is configured. Please contact your administrator.",
            internal_detail="Provider registry is empty for the requested capability.",
        )

    def get_llm(self, provider_name: Optional[str] = None) -> LLMProvider:
        return self._llms[self._resolve(self._llms, provider_name)]

    def get_embeddings(self, provider_name: Optional[str] = None) -> EmbeddingProvider:
        return self._embeddings[self._resolve(self._embeddings, provider_name)]

    def get_active_embedding_model_id(self) -> str:
        return self.get_embeddings().model_id


provider_registry = ProviderRegistry()


def describe_visual_source(image_bytes: bytes, mime: str, prompt: str) -> str:
    """Synchronous vision describe used by image ingest. Lives here so the
    leak audit can inspect provider URLs in one file.
    """
    import base64
    import httpx as _httpx

    api_key = settings.LANGDOCK_API_CODE or settings.LANGDOCK_API_KEY
    if not api_key:
        return ""
    model = normalize_model_name(settings.LANGDOCK_MODEL or settings.MODEL)
    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are AtlasLM visual ingestion. Describe only what is "
                    "visible. Do not infer facts that are not in the image."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    }
    try:
        response = _httpx.post(
            f"{settings.LANGDOCK_ENDPOINT_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=90.0,
        )
        response.raise_for_status()
        return (response.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:
        raise ProviderError(
            "Atlas could not describe this image. Try again, or upload a clearer photo.",
            internal_detail=f"vision describe failed: {exc!r}",
        ) from exc
