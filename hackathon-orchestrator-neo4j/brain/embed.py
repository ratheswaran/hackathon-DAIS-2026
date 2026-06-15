"""Embedding encoder — pluggable backend, cached singleton.

Two backends, selected by ``BRAIN_EMBED_BACKEND`` (see config.py):

  "sentence-transformers" (default) — local all-MiniLM-L6-v2 (384-dim). Needs
      torch; great for the offline benchmark, but heavy to ship in a Model
      Serving image.
  "databricks"                       — calls a Databricks Foundation-Model
      embedding endpoint (default ``databricks-gte-large-en``, 1024-dim) over
      HTTPS. NO torch in the process → the find_skill serving image stays
      slim. The SAME endpoint is used at ingest (here) and at query time
      inside the orchestrator's find_skill tool, so the vectors match.

Both backends L2-normalise their output, so dot product == cosine — which the
offline kNN analytics in ingest.py assumes and the Neo4j cosine vector index
expects.
"""
from __future__ import annotations

import functools
import json
import os
import time
import urllib.error
import urllib.request

import numpy as np

from . import config


# --- sentence-transformers (local) -----------------------------------------
@functools.lru_cache(maxsize=1)
def _st_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(config.EMBED_MODEL)


def _encode_st(texts: list[str], normalize: bool) -> np.ndarray:
    vecs = _st_model().encode(
        texts, normalize_embeddings=normalize, show_progress_bar=False,
        convert_to_numpy=True, batch_size=64,
    )
    return np.asarray(vecs, dtype=np.float32)


# --- Databricks Foundation Model endpoint (no torch) ------------------------
def _databricks_host() -> str:
    host = os.environ.get("DATABRICKS_HOST", "").strip()
    if not host:
        raise RuntimeError("BRAIN_EMBED_BACKEND=databricks needs DATABRICKS_HOST")
    if not host.startswith("http"):
        host = f"https://{host}"
    return host.rstrip("/")


def _databricks_token() -> str:
    tok = (os.environ.get("DATABRICKS_TOKEN")
           or os.environ.get("DATABRICKS_API_TOKEN") or "").strip()
    if not tok:
        raise RuntimeError("BRAIN_EMBED_BACKEND=databricks needs DATABRICKS_TOKEN")
    return tok


def _post_with_retry(url: str, body: bytes, token: str, max_retries: int = 6) -> dict:
    """POST with exponential backoff on 429/5xx. Free-Edition FM endpoints
    rate-limit aggressively, so a tight ingest loop needs to back off."""
    delay = 2.0
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(
            url, data=body,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                # Honour Retry-After when present, else exponential backoff.
                ra = e.headers.get("Retry-After") if e.headers else None
                wait = float(ra) if (ra and ra.isdigit()) else delay
                time.sleep(wait)
                delay = min(delay * 2, 30.0)
                continue
            raise


def _encode_databricks(texts: list[str], normalize: bool) -> np.ndarray:
    """POST to the FM embeddings endpoint (OpenAI-style response). stdlib only.

    Batches are kept small with a brief inter-batch pause + retry/backoff so
    a full-corpus ingest survives the Free-Edition embeddings rate limit.
    """
    url = f"{_databricks_host()}/serving-endpoints/{config.EMBED_ENDPOINT}/invocations"
    token = _databricks_token()
    pause = float(os.environ.get("BRAIN_EMBED_PAUSE", "0.4"))
    out: list[list[float]] = []
    n_batches = (len(texts) + config.EMBED_BATCH - 1) // config.EMBED_BATCH
    for bi, i in enumerate(range(0, len(texts), config.EMBED_BATCH)):
        batch = texts[i:i + config.EMBED_BATCH]
        payload = _post_with_retry(url, json.dumps({"input": batch}).encode("utf-8"), token)
        # OpenAI-compatible: {"data": [{"embedding": [...]}, ...]}
        rows = payload.get("data") or payload.get("predictions") or []
        for r in rows:
            vec = r["embedding"] if isinstance(r, dict) and "embedding" in r else r
            out.append(vec)
        if pause and bi < n_batches - 1:
            time.sleep(pause)
    arr = np.asarray(out, dtype=np.float32)
    if normalize:
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        arr = arr / norms
    return arr


# --- public API -------------------------------------------------------------
def encode(texts: list[str], normalize: bool = True) -> np.ndarray:
    """Return an (n, EMBED_DIM) float32 array. Normalized => dot == cosine."""
    if config.EMBED_BACKEND == "databricks":
        return _encode_databricks(texts, normalize)
    return _encode_st(texts, normalize)


def encode_one(text: str, normalize: bool = True) -> list[float]:
    return encode([text], normalize=normalize)[0].tolist()


def warm() -> int:
    """Force model/endpoint load; return embedding dimension."""
    return int(encode(["warm"]).shape[1])
