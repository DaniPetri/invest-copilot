"""Hybrid search over the KID chunks (SPEC §6).

Modes: `bm25`, `dense`, `hybrid` (Reciprocal Rank Fusion, k = 60, top 50 of each) and `hybrid_rerank`
(cross-encoder over the fused top 20, behind RERANK=1). Chunks flagged as possible injection are quarantined:
they never appear in the returned chunks (unless asked for) and are reported in `quarantined_ids`.
"""

import atexit
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Literal, Protocol

import numpy as np
from qdrant_client import QdrantClient, models

from ..config import get_settings
from ..schemas.tools import Chunk, SearchKidOutput
from .chunk import KidChunk
from .index import COLLECTION, PICKLE_VERSION, embed, paths, tokenize

Mode = Literal["hybrid", "dense", "bm25", "hybrid_rerank"]
RRF_K = 60
CANDIDATES = 50
RERANK_TOP = 20


class IndexMissingError(RuntimeError):
    pass


class RerankUnavailableError(RuntimeError):
    pass


class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class FastembedReranker:
    """Cross-encoder via fastembed (`jinaai/jina-reranker-v2-base-multilingual`, about 1.1 GB, loaded lazily)."""

    def __init__(self) -> None:
        self._model = None

    def score(self, query: str, texts: list[str]) -> list[float]:
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            s = get_settings()
            s.model_cache_dir.mkdir(parents=True, exist_ok=True)
            self._model = TextCrossEncoder(s.rerank_model, cache_dir=str(s.model_cache_dir))
        return [float(x) for x in self._model.rerank(query, texts)]


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion: score(d) = sum over rankings of 1 / (k + rank), rank starting at 1."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


# Local-mode Qdrant allows one client per folder and process, so clients are shared and closed explicitly.
_clients: dict[str, QdrantClient] = {}


def get_client(path: Path) -> QdrantClient:
    key = str(path.resolve())
    if key not in _clients:
        _clients[key] = QdrantClient(path=key)
    return _clients[key]


@atexit.register
def close_all_clients() -> None:
    for key in list(_clients):
        _clients.pop(key).close()


def close_client(path: Path) -> None:
    client = _clients.pop(str(path.resolve()), None)
    if client is not None:
        client.close()


class KidIndex:
    def __init__(self, root: Path | None = None, reranker: Reranker | None = None):
        self.root = root or get_settings().data_dir
        self.qdrant_path, bm25_path = paths(self.root)
        if not bm25_path.exists() or not self.qdrant_path.exists():
            raise IndexMissingError(f"No retrieval index in {self.root}. Run `make ingest` first.")
        with bm25_path.open("rb") as fh:
            blob = pickle.load(fh)  # written by build_index() in this repo, never user input
        if blob.get("version") != PICKLE_VERSION:
            raise IndexMissingError("Index was built by another version. Run `make ingest` again.")
        self.chunks: list[KidChunk] = blob["chunks"]
        self.bm25 = blob["bm25"]
        self.reranker = reranker
        self._product_rows: dict[str, list[int]] = {}
        for i, c in enumerate(self.chunks):
            self._product_rows.setdefault(c.product_id, []).append(i)

    def close(self) -> None:
        close_client(self.qdrant_path)

    # ── single retrievers ───────────────────────────────────────────────────

    def _allowed(self, product_ids: list[str] | None) -> np.ndarray | None:
        if product_ids is None:
            return None
        rows = [i for pid in product_ids for i in self._product_rows.get(pid, [])]
        return np.array(sorted(rows), dtype=int)

    def _bm25(self, query: str, allowed: np.ndarray | None, n: int) -> list[tuple[int, float]]:
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = np.asarray(self.bm25.get_scores(tokens), dtype=float)
        if allowed is not None:
            mask = np.full(len(scores), -np.inf)
            mask[allowed] = scores[allowed]
            scores = mask
        order = np.argsort(-scores, kind="stable")[:n]
        return [(int(i), float(scores[i])) for i in order if np.isfinite(scores[i]) and scores[i] > 0]

    def _dense(self, query: str, product_ids: list[str] | None, n: int) -> list[tuple[int, float]]:
        if product_ids is not None and not product_ids:
            return []
        flt = None
        if product_ids is not None:
            flt = models.Filter(
                must=[models.FieldCondition(key="product_id", match=models.MatchAny(any=list(product_ids)))]
            )
        vector = embed([query])[0].tolist()
        hits = get_client(self.qdrant_path).query_points(COLLECTION, query=vector, limit=n, query_filter=flt).points
        return [(int(h.id), float(h.score)) for h in hits]

    # ── ranking ─────────────────────────────────────────────────────────────

    def rank(self, query: str, mode: Mode, product_ids: list[str] | None, n: int) -> list[tuple[int, float]]:
        """(chunk index, score) best first, before quarantine. Score meaning depends on the mode."""
        allowed = self._allowed(product_ids)
        if allowed is not None and len(allowed) == 0:
            return []
        if mode == "bm25":
            return self._bm25(query, allowed, n)
        if mode == "dense":
            return self._dense(query, product_ids, n)
        if mode not in ("hybrid", "hybrid_rerank"):
            raise ValueError(f"unknown mode {mode!r}")

        lexical = self._bm25(query, allowed, CANDIDATES)
        semantic = self._dense(query, product_ids, CANDIDATES)
        fused = rrf([[i for i, _ in lexical], [i for i, _ in semantic]])
        if mode == "hybrid":
            return fused[:n]

        reranker = self.reranker
        if reranker is None:
            if not get_settings().rerank:
                raise RerankUnavailableError("hybrid_rerank needs RERANK=1 (or an injected reranker).")
            reranker = self.reranker = FastembedReranker()
        top = fused[:RERANK_TOP]
        scores = reranker.score(query, [self.chunks[i].index_text for i, _ in top])
        reranked = sorted(zip((i for i, _ in top), scores, strict=True), key=lambda t: -t[1])
        return [(i, float(s)) for i, s in reranked][:n]

    def retrieve(
        self,
        query: str,
        product_ids: list[str] | None = None,
        k: int = 5,
        mode: Mode = "hybrid",
        include_quarantined: bool = False,
    ) -> SearchKidOutput:
        """Top-k chunks. Flagged chunks that would have ranked among them are listed in `quarantined_ids`."""
        ranked = self.rank(query, mode, product_ids, max(k * 3, RERANK_TOP))
        chunks: list[Chunk] = []
        quarantined: list[str] = []
        for i, score in ranked:
            c = self.chunks[i]
            if c.flags and not include_quarantined:
                quarantined.append(c.id)
                continue
            chunks.append(c.to_chunk(score))
            if len(chunks) == k:
                break
        return SearchKidOutput(chunks=chunks, quarantined_ids=quarantined)


@lru_cache
def get_index(root: Path | None = None) -> KidIndex:
    return KidIndex(root)


def search_kid(
    query: str,
    product_ids: list[str] | None = None,
    k: int = 5,
    mode: Mode = "hybrid",
) -> list[Chunk]:
    """SPEC §6 API. Quarantined chunks are excluded; use `get_index().retrieve(...)` to also get their IDs."""
    return get_index().retrieve(query, product_ids, k, mode).chunks
