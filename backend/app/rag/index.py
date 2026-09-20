"""Build the retrieval index: fastembed embeddings in Qdrant local mode plus a pickled BM25 (SPEC §6).

uv run python -m app.rag.index            # = make ingest; needs `make data` first
"""

import pickle
import re
import shutil
import sys
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient, models
from rank_bm25 import BM25Okapi

from ..config import get_settings
from ..data.store import Store
from .chunk import KidChunk, chunk_kid
from .parse import parse_kid

COLLECTION = "kid"
PICKLE_VERSION = 1

# ── tokenisation for BM25 ───────────────────────────────────────────────────

STOPWORDS = frozenset(
    """
    der die das den dem des ein eine einen einem einer eines und oder aber auch nicht kein keine
    ist sind war wird werden wurde hat haben kann gibt gibt's wie was welche welcher welchen welches wer wo wann
    bei beim im in von vom zu zum zur fur mit auf aus am an es ich mir mich mein dein sie er wir ihr
    nach uber unter als so noch nur sich dass da dann dieses dieser diesem diesen dies
    """.split()
)
_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[a-z]+")


def fold(text: str) -> str:
    """Lowercase and fold umlauts and accents: 'Ausschlüsse' -> 'ausschlusse', 'Straße' -> 'strasse'."""
    text = text.lower().replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


STEM_LEN = 6  # German compounds and inflections share a prefix: Ertrag/Erträge/Ertragsverwendung -> "ertrag"


def stem(token: str) -> str:
    """Truncation stemmer: long alphabetic tokens keep their first STEM_LEN characters, numbers stay whole."""
    return token[:STEM_LEN] if token.isalpha() and len(token) > STEM_LEN else token


def tokenize(text: str) -> list[str]:
    return [stem(t) for t in _TOKEN.findall(fold(text)) if t not in STOPWORDS]


# ── models ──────────────────────────────────────────────────────────────────


@lru_cache
def get_embedder():
    from fastembed import TextEmbedding

    s = get_settings()
    s.model_cache_dir.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(s.embed_model, cache_dir=str(s.model_cache_dir))


def embed(texts: list[str]) -> np.ndarray:
    return np.array(list(get_embedder().embed(texts)), dtype=np.float32)


# ── build ───────────────────────────────────────────────────────────────────


def paths(root: Path) -> tuple[Path, Path]:
    return root / "qdrant", root / "bm25.pkl"


def build_index(root: Path | None = None) -> dict:
    """Parse and chunk every KID in `root` (default data/generated), then write Qdrant and BM25."""
    root = root or get_settings().data_dir
    t0 = time.time()
    store = Store(root)
    chunks: list[KidChunk] = []
    for p in store.products:
        chunks += chunk_kid(parse_kid(store.kid_path(p.id), p.id))

    vectors = embed([c.index_text for c in chunks])
    qdrant_path, bm25_path = paths(root)
    from .search import close_client

    close_client(qdrant_path)
    shutil.rmtree(qdrant_path, ignore_errors=True)
    client = QdrantClient(path=str(qdrant_path))
    client.create_collection(
        COLLECTION,
        vectors_config=models.VectorParams(size=int(vectors.shape[1]), distance=models.Distance.COSINE),
    )
    client.upsert(
        COLLECTION,
        [
            models.PointStruct(
                id=i,
                vector=vectors[i].tolist(),
                payload={
                    "chunk_id": c.id,
                    "product_id": c.product_id,
                    "page": c.page,
                    "section": c.section,
                    "text": c.text,
                    "flags": list(c.flags),
                },
            )
            for i, c in enumerate(chunks)
        ],
    )
    client.close()

    bm25 = BM25Okapi([tokenize(c.index_text) for c in chunks])
    with bm25_path.open("wb") as fh:
        pickle.dump({"version": PICKLE_VERSION, "chunks": chunks, "bm25": bm25}, fh)
    return {
        "chunks": len(chunks),
        "flagged": sum(bool(c.flags) for c in chunks),
        "dim": int(vectors.shape[1]),
        "seconds": round(time.time() - t0, 1),
    }


def main() -> int:
    root = get_settings().data_dir
    if not (root / "manifest.json").exists():
        print(f"{root} has no generated data. Run `make data` first.", file=sys.stderr)
        return 1
    stats = build_index(root)
    print(f"indexed {stats['chunks']} chunks ({stats['flagged']} quarantined) in {stats['seconds']}s -> {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
