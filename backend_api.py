# backend_api.py

import sqlite3
from pathlib import Path
from typing import List

import requests
from fastapi import FastAPI, Body
from pydantic import BaseModel
from qdrant_client import QdrantClient

# ----------------------
# CONFIG
# ----------------------

BASE_DIR = Path(__file__).parent
SQLITE_PATH = BASE_DIR / "sca_metadata.db"

OLLAMA_URL = "http://localhost:11434/api/embeddings"
OLLAMA_MODEL = "mxbai-embed-large:latest"

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
QDRANT_COLLECTION = "oss_code_embeddings"

# ----------------------
# FastAPI app
# ----------------------

app = FastAPI(title="SCA Backend API", version="1.0")

# ----------------------
# Request model
# ----------------------

class CodeRequest(BaseModel):
    code: str
    file_path: str | None = None
    language: str | None = None
    top_k: int = 5


# ----------------------
# Utils
# ----------------------

def get_embedding(code: str) -> List[float]:
    """Call Ollama to embed user snippet."""
    resp = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": code},
        timeout=120
    )
    resp.raise_for_status()
    return resp.json()["embedding"]

def qdrant_search(vec: List[float], top_k: int = 5):
    client = QdrantClient(url=f"http://{QDRANT_HOST}:{QDRANT_PORT}")

    result = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=vec,
        limit=top_k,
        with_payload=False,
        with_vectors=False
    )

    return result.points



def lookup_metadata(qdrant_id: int):
    """Fetch fingerprints + metadata + license from SQLite."""
    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT ecosystem, package, file_path, chunk_index,
               file_fp, chunk_fp
        FROM code_chunks
        WHERE id = ?
    """, (qdrant_id,))
    row = cur.fetchone()

    if row is None:
        conn.close()
        return None

    ecosystem, pkg, fp, idx, file_fp, chunk_fp = row

    cur.execute("""
        SELECT license FROM licenses
        WHERE ecosystem = ? AND package = ?
    """, (ecosystem, pkg))
    lic_row = cur.fetchone()
    license_name = lic_row[0] if lic_row else "UNKNOWN"

    conn.close()

    return {
        "ecosystem": ecosystem,
        "package": pkg,
        "file_path": fp,
        "chunk_index": idx,
        "file_fp": file_fp,
        "chunk_fp": chunk_fp,
        "license": license_name
    }


# ----------------------
# ROUTE: similarity search
# ----------------------

@app.post("/similarity")
def similarity_analysis(req: CodeRequest):
    """
    This is the backend entrypoint for n8n.

    n8n sends: { code: "...", language: "py", file_path: "...", top_k: 5 }
    Backend returns: Qdrant matches + license data + fingerprints.
    """

    # 1. Embed the user code snippet
    embedding = get_embedding(req.code)

    # 2. Search Qdrant
    hits = qdrant_search(embedding, top_k=req.top_k)

    results = []

    # 3. For each hit → fetch metadata from SQLite
    for h in hits:
        metadata = lookup_metadata(h.id)
        if metadata is None:
            continue

        result = {
            "score": h.score,
            "qdrant_id": h.id,
            "ecosystem": metadata["ecosystem"],
            "package": metadata["package"],
            "file_path": metadata["file_path"],
            "chunk_index": metadata["chunk_index"],
            "file_fp": metadata["file_fp"],
            "chunk_fp": metadata["chunk_fp"],
            "license": metadata["license"]
        }
        results.append(result)

    return {
        "snippet_length": len(req.code),
        "matches": results
    }
