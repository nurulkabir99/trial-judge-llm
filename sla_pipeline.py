import os
import hashlib
import sqlite3
from pathlib import Path
from typing import List, Dict

import requests
from tqdm import tqdm
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

# ==============================
# CONFIG
# ==============================

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# Ollama
OLLAMA_URL = "http://localhost:11434/api/embeddings"
OLLAMA_MODEL = "mxbai-embed-large:latest"

# Qdrant
QDRANT_HOST = "host.docker.internal"
QDRANT_PORT = 6333
QDRANT_COLLECTION = "oss_code_embeddings"

# SQLite
SQLITE_DB_PATH = BASE_DIR / "sca_metadata.db"

# Which file types to index
CODE_EXT = {".py", ".js", ".ts", ".c", ".cpp", ".cc", ".h", ".hpp", ".java"}

# 🔻 DATA SIZE REDUCTION KNOBS 🔻

# Maximum files to index per package (None = no limit)
MAX_FILES_PER_PACKAGE = 200   # reduce this to shrink size

# Skip directories with these names (common noise)
EXCLUDE_DIR_NAMES = {"tests", "test", "docs", "doc", "examples", "example", "benchmarks"}

# Maximum file size in bytes (skip bigger files)
MAX_FILE_BYTES = 300 * 1024   # 300 KB

# Max characters per chunk passed to embedding
MAX_CHARS_PER_CHUNK = 800

# Maximum chunks per file (None = no limit)
MAX_CHUNKS_PER_FILE = 10

# Embed only N packages (per ecosystem) for experiments (None = no limit)
MAX_PACKAGES_PER_ECOSYSTEM = None  # e.g. set to 3 for very small experiment


# ==============================
# LICENSE DB (simple mapping)
# ==============================

# You can refine these with real SPDX IDs later
LICENSE_MAP = {
    # PyPI
    ("pypi", "requests"): "Apache-2.0",
    ("pypi", "numpy"): "BSD-3-Clause",
    ("pypi", "pandas"): "BSD-3-Clause",
    ("pypi", "flask"): "BSD-3-Clause",
    ("pypi", "scikit-learn"): "BSD-3-Clause",
    ("pypi", "pytest"): "MIT",

    # npm
    ("npm", "lodash"): "MIT",
    ("npm", "axios"): "MIT",
    ("npm", "express"): "MIT",
    ("npm", "react"): "MIT",
    ("npm", "typescript"): "Apache-2.0",
    ("npm", "jest"): "MIT",

    # C/C++
    ("cpp", "openssl"): "Apache-2.0 OR OpenSSL",  # simplified
    ("cpp", "curl"): "curl",
    ("cpp", "zlib"): "Zlib",
    ("cpp", "ffmpeg"): "GPL-2.0-or-later AND LGPL-2.1-or-later",  # simplified
    ("cpp", "libpng"): "libpng-2.0",
    ("cpp", "opencv"): "Apache-2.0",

    # high_risk
    ("high_risk", "busybox"): "GPL-2.0-only",
    ("high_risk", "ffmpeg-gpl"): "GPL-2.0-or-later",
    ("high_risk", "samba"): "GPL-3.0-or-later",
    ("high_risk", "glibc"): "LGPL-2.1-or-later",
    ("high_risk", "libav"): "LGPL-2.1-or-later AND GPL-2.0-or-later",
    ("high_risk", "spidermonkey"): "MPL-2.0",
    ("high_risk", "mozilla-central"): "MPL-2.0"
}


# ==============================
# OLLAMA EMBEDDINGS
# ==============================

def get_embedding(text: str) -> List[float]:
    resp = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": text},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["embedding"]


# ==============================
# CODE NORMALIZATION & CHUNKING
# ==============================

def normalize_code(code: str) -> str:
    """
    Simple normalization:
    - drop empty lines
    - drop pure comment lines (#, //)
    - strip surrounding whitespace
    """
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def file_fingerprint(normalized_code: str) -> str:
    return hashlib.sha1(normalized_code.encode("utf-8")).hexdigest()


def chunk_fingerprint(chunk: str) -> str:
    return hashlib.sha1(chunk.encode("utf-8")).hexdigest()


def chunk_code(normalized: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> List[str]:
    """
    Simple fixed-size chunking. For more precision you could later use function-level
    parsing, but this is enough for a strong thesis prototype.
    """
    if len(normalized) <= max_chars:
        return [normalized]
    chunks = [normalized[i:i + max_chars] for i in range(0, len(normalized), max_chars)]
    if MAX_CHUNKS_PER_FILE is not None:
        return chunks[:MAX_CHUNKS_PER_FILE]
    return chunks


# ==============================
# DATASET CRAWLER (WITH SIZE REDUCTION)
# ==============================

def iter_code_files():
    """
    Yield (ecosystem, package, file_path) for all selected code files.
    Applies:
    - MAX_PACKAGES_PER_ECOSYSTEM limit
    - MAX_FILES_PER_PACKAGE limit
    - EXCLUDE_DIR_NAMES filters
    - MAX_FILE_BYTES filter
    """
    base = DATA_DIR
    for ecosystem_dir in base.iterdir():
        if not ecosystem_dir.is_dir():
            continue
        ecosystem = ecosystem_dir.name  # pypi / npm / cpp / high_risk

        pkg_counter = 0
        for pkg_dir in sorted(ecosystem_dir.iterdir()):
            if not pkg_dir.is_dir():
                continue
            package = pkg_dir.name

            if (MAX_PACKAGES_PER_ECOSYSTEM is not None and
                pkg_counter >= MAX_PACKAGES_PER_ECOSYSTEM):
                break
            pkg_counter += 1

            files_in_package = 0

            for root, dirs, files in os.walk(pkg_dir):
                # filter out big noise directories
                dirs[:] = [d for d in dirs if d.lower() not in EXCLUDE_DIR_NAMES]

                for fname in files:
                    ext = Path(fname).suffix.lower()
                    if ext not in CODE_EXT:
                        continue

                    fpath = Path(root) / fname

                    # size filter
                    try:
                        size = fpath.stat().st_size
                        if size > MAX_FILE_BYTES:
                            continue
                    except Exception:
                        continue

                    yield ecosystem, package, fpath
                    files_in_package += 1

                    if MAX_FILES_PER_PACKAGE is not None and files_in_package >= MAX_FILES_PER_PACKAGE:
                        break
                if MAX_FILES_PER_PACKAGE is not None and files_in_package >= MAX_FILES_PER_PACKAGE:
                    break


# ==============================
# SQLITE SETUP (METADATA + LICENSES)
# ==============================

def init_sqlite(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Chunks table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS code_chunks (
            id INTEGER PRIMARY KEY,
            qdrant_id INTEGER,
            ecosystem TEXT,
            package TEXT,
            file_path TEXT,
            chunk_index INTEGER,
            file_fp TEXT,
            chunk_fp TEXT
        )
    """)

    # License table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ecosystem TEXT,
            package TEXT,
            license TEXT,
            source TEXT
        )
    """)

    # Add/refresh license mapping
    for (ecosystem, package), license_str in LICENSE_MAP.items():
        cur.execute("""
            INSERT OR REPLACE INTO licenses (id, ecosystem, package, license, source)
            VALUES (
                COALESCE(
                    (SELECT id FROM licenses WHERE ecosystem = ? AND package = ?),
                    NULL
                ),
                ?, ?, ?, ?
            )
        """, (ecosystem, package, ecosystem, package, license_str, "static_map_v1"))

    conn.commit()
    return conn


# ==============================
# QDRANT SETUP
# ==============================

def ensure_qdrant_collection(client: QdrantClient, dim: int):
    cols = client.get_collections().collections
    names = [c.name for c in cols]
    if QDRANT_COLLECTION in names:
        print(f"[Qdrant] Collection '{QDRANT_COLLECTION}' already exists.")
        return
    client.recreate_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
    )
    print(f"[Qdrant] Created collection '{QDRANT_COLLECTION}' with dim={dim}.")


# ==============================
# MAIN PIPELINE
# ==============================

def main():
    # 1. SQLite
    conn = init_sqlite(SQLITE_DB_PATH)
    cur = conn.cursor()
    print(f"[SQLite] Using DB at {SQLITE_DB_PATH}")

    # 2. Qdrant
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # 3. Embedding dimension
    print("[Ollama] Getting dummy embedding...")
    dummy_vec = get_embedding("test")
    dim = len(dummy_vec)
    print(f"[Ollama] Embedding dimension = {dim}")
    ensure_qdrant_collection(qdrant, dim)

    # Determine start ID (in case of reruns)
    cur.execute("SELECT MAX(id) FROM code_chunks")
    row = cur.fetchone()
    point_id = (row[0] or 0) + 1

    # 4. Crawl and index
    files_list = list(iter_code_files())
    print(f"[Pipeline] Will index {len(files_list)} code files (after filters).")

    batch: List[PointStruct] = []
    batch_size = 64

    for ecosystem, package, fpath in tqdm(files_list, desc="Indexing files"):
        try:
            raw = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"\n[WARN] Failed to read {fpath}: {e}")
            continue

        normalized = normalize_code(raw)
        if not normalized.strip():
            continue

        f_fp = file_fingerprint(normalized)
        chunks = chunk_code(normalized)

        for idx, chunk in enumerate(chunks):
            chunk_text = chunk.strip()
            if not chunk_text:
                continue

            try:
                vec = get_embedding(chunk_text)
            except Exception as e:
                print(f"\n[WARN] Embedding failed for {fpath} chunk {idx}: {e}")
                continue

            c_fp = chunk_fingerprint(chunk_text)

            payload = {
                "ecosystem": ecosystem,
                "package": package,
                "file_path": str(fpath.relative_to(DATA_DIR)),
                "chunk_index": idx,
                "extension": fpath.suffix.lower(),
                "file_fp": f_fp,
                "chunk_fp": c_fp
            }

            point = PointStruct(
                id=point_id,
                vector=vec,
                payload=payload
            )
            batch.append(point)

            # Also record in SQLite
            cur.execute("""
                INSERT INTO code_chunks (id, qdrant_id, ecosystem, package, file_path, chunk_index, file_fp, chunk_fp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                point_id,
                point_id,
                ecosystem,
                package,
                str(fpath.relative_to(DATA_DIR)),
                idx,
                f_fp,
                c_fp
            ))

            point_id += 1

            if len(batch) >= batch_size:
                qdrant.upsert(collection_name=QDRANT_COLLECTION, points=batch)
                conn.commit()
                batch = []

    if batch:
        qdrant.upsert(collection_name=QDRANT_COLLECTION, points=batch)
        conn.commit()

    print("[Pipeline] Indexing complete.")
    conn.close()


if __name__ == "__main__":
    main()
