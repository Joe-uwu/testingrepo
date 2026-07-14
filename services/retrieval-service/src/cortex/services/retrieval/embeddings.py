"""Text embeddings for the vector retrieval arm.

The default `HashingEmbedder` is deterministic, dependency-free, and offline: it hashes
character n-grams and word tokens into a fixed-dimension vector and L2-normalizes it, so
texts that share substrings land near each other under cosine similarity. It is not a
neural model, but it makes the vector arm real and testable without a GPU, an API key, or
network access; a sentence-transformers / OpenAI embedder drops in behind the same
`Embedder` protocol.

`CachedEmbedder` wraps any embedder with an LRU cache so repeated text (the same node
re-indexed, a repeated query) is not re-embedded.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import OrderedDict
from typing import Protocol, runtime_checkable

_TOKEN = re.compile(r"[a-z0-9]+")


@runtime_checkable
class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one L2-normalized vector per input text."""


def _stable_hash(token: str) -> int:
    # blake2b is stable across processes (unlike Python's salted hash()), so vectors are
    # reproducible — required for a persistent vector index.
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")


class HashingEmbedder:
    def __init__(self, dim: int = 256) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _tokens(text):
            h = _stable_hash(token)
            vec[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


def _tokens(text: str) -> list[str]:
    words = _TOKEN.findall(text.lower())
    tokens: list[str] = list(words)
    for word in words:
        padded = f"#{word}#"
        tokens.extend(padded[i : i + 3] for i in range(len(padded) - 2))  # char 3-grams
    return tokens


class CachedEmbedder:
    """LRU cache in front of an embedder. Keyed by exact text."""

    def __init__(self, inner: Embedder, *, maxsize: int = 4096) -> None:
        self._inner = inner
        self.dim = inner.dim
        self._maxsize = maxsize
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float] | None] = [None] * len(texts)
        missing_idx: list[int] = []
        missing_text: list[str] = []
        for i, text in enumerate(texts):
            cached = self._cache.get(text)
            if cached is not None:
                self._cache.move_to_end(text)
                results[i] = cached
                self.hits += 1
            else:
                self.misses += 1
                missing_idx.append(i)
                missing_text.append(text)
        if missing_text:
            for i, vec in zip(missing_idx, self._inner.embed(missing_text)):
                results[i] = vec
                self._store(texts[i], vec)
        return [vec for vec in results if vec is not None]

    def _store(self, text: str, vec: list[float]) -> None:
        self._cache[text] = vec
        self._cache.move_to_end(text)
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)


# Known embedding models -> vector dimensionality (so the vector index is sized correctly).
_MODEL_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
}


class OpenAIEmbedder:
    """Neural embedder over an OpenAI-compatible ``/v1/embeddings`` endpoint.

    Works with OpenAI, Azure OpenAI, and local Ollama/vLLM by changing ``base_url`` + ``model``.
    Returns the provider's vectors as-is (already normalized by the model). The HTTP client is
    injectable so tests drive it with a mock transport, no network or key required.
    """

    def __init__(
        self,
        *,
        model: str = "text-embedding-3-small",
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        dim: int | None = None,
        http=None,
        timeout: float = 30.0,
    ) -> None:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("OpenAIEmbedder requires httpx (the 'embeddings' extra)") from exc
        self.model = model
        self.dim = dim if dim is not None else _MODEL_DIMS.get(model, 1536)
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._http = http if http is not None else httpx.Client(timeout=timeout)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        resp = self._http.post(
            f"{self._base}/embeddings",
            headers=headers,
            json={"model": self.model, "input": texts},
        )
        resp.raise_for_status()
        rows = sorted(resp.json()["data"], key=lambda r: r["index"])
        return [row["embedding"] for row in rows]


def build_embedder(
    *, provider: str = "hashing", model: str = "text-embedding-3-small",
    api_key: str = "", base_url: str = "https://api.openai.com/v1", dim: int = 256,
    cache: bool = True,
) -> Embedder:
    """Select the embedder from config. ``hashing`` (default, offline) or ``openai``
    (any OpenAI-compatible endpoint). Wrapped in an LRU cache unless disabled."""
    if provider == "openai":
        inner: Embedder = OpenAIEmbedder(model=model, api_key=api_key, base_url=base_url)
    else:
        inner = HashingEmbedder(dim=dim)
    return CachedEmbedder(inner) if cache else inner
