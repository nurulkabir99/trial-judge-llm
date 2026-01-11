# search_and_report.py

import sqlite3
from pathlib import Path
from typing import List

import requests
from qdrant_client import QdrantClient

BASE_DIR = Path(__file__).parent

# Ollama
OLLAMA_URL = "http://localhost:11434/api/embeddings"
OLLAMA_MODEL = "mxbai-embed-large:latest"

# Qdrant
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
QDRANT_COLLECTION = "oss_code_embeddings"

# SQLite
SQLITE_DB_PATH = BASE_DIR / "sca_metadata.db"


def get_embedding(text: str) -> List[float]:
    resp = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": text},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def search_similar_with_license(code_snippet: str, top_k: int = 5):
    query_vec = get_embedding(code_snippet)

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    hits = client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=query_vec,
        limit=top_k
    )

    conn = sqlite3.connect(SQLITE_DB_PATH)
    cur = conn.cursor()

    results = []
    for h in hits:
        score = h.score
        qdrant_id = h.id

        cur.execute("""
            SELECT ecosystem, package, file_path, chunk_index, file_fp, chunk_fp
            FROM code_chunks
            WHERE id = ?
        """, (qdrant_id,))
        row = cur.fetchone()
        if not row:
            continue
        eco, pkg, fp, idx, file_fp, chunk_fp = row

        # fetch license
        cur.execute("""
            SELECT license FROM licenses
            WHERE ecosystem = ? AND package = ?
        """, (eco, pkg))
        row2 = cur.fetchone()
        license_str = row2[0] if row2 else "UNKNOWN"

        results.append({
            "score": score,
            "ecosystem": eco,
            "package": pkg,
            "file_path": fp,
            "chunk_index": idx,
            "file_fp": file_fp,
            "chunk_fp": chunk_fp,
            "license": license_str
        })

    conn.close()
    return results


def main():
    print("Paste a code snippet (end with Ctrl+D / Ctrl+Z):")
    import sys
    snippet = sys.stdin.read()

    if not snippet.strip():
        print("No snippet provided.")
        return

    results = search_similar_with_license(snippet, top_k=5)

    print("\n=== Top Matches ===")
    for r in results:
        print(f"Score: {r['score']:.4f}")
        print(f"  Ecosystem : {r['ecosystem']}")
        print(f"  Package   : {r['package']}")
        print(f"  File      : {r['file_path']} (chunk {r['chunk_index']})")
        print(f"  License   : {r['license']}")
        print(f"  File FP   : {r['file_fp'][:12]}... (SHA1)")
        print(f"  Chunk FP  : {r['chunk_fp'][:12]}...")
        print("-" * 40)


if __name__ == "__main__":
    main()
