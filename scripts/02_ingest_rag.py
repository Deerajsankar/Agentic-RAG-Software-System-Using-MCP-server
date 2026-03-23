from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

import lancedb
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer


def iter_policy_files(raw_policies_dir: Path) -> list[Path]:
    return sorted([p for p in raw_policies_dir.glob("*.txt") if p.is_file()])


def normalize_whitespace(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse runs of spaces/tabs; keep newlines.
    s = re.sub(r"[ \t]+", " ", s)
    # Trim trailing spaces on lines
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    return s.strip()


def split_by_paragraphs(text: str) -> list[str]:
    text = normalize_whitespace(text)
    if not text:
        return []
    # Split on blank lines (double newline or more)
    parts = re.split(r"\n\s*\n+", text)
    return [p.strip() for p in parts if p.strip()]


def split_long_chunk(chunk: str, max_chars: int = 900) -> list[str]:
    """
    Keep chunks reasonably sized for embedding/RAG.
    If a paragraph is huge, split by sentences and pack into <= max_chars.
    """
    chunk = chunk.strip()
    if len(chunk) <= max_chars:
        return [chunk] if chunk else []

    # Very simple sentence splitter (policy text is usually well-punctuated).
    sentences = re.split(r"(?<=[.!?])\s+", chunk)
    out: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for s in (x.strip() for x in sentences):
        if not s:
            continue
        if buf_len + len(s) + (1 if buf else 0) > max_chars and buf:
            out.append(" ".join(buf).strip())
            buf = [s]
            buf_len = len(s)
        else:
            buf.append(s)
            buf_len += len(s) + (1 if buf_len else 0)
    if buf:
        out.append(" ".join(buf).strip())

    # Fallback: if still too large (e.g. no punctuation), hard-split.
    final: list[str] = []
    for part in out:
        if len(part) <= max_chars:
            final.append(part)
        else:
            for i in range(0, len(part), max_chars):
                seg = part[i : i + max_chars].strip()
                if seg:
                    final.append(seg)
    return final


def chunk_text(text: str) -> list[str]:
    chunks: list[str] = []
    for para in split_by_paragraphs(text):
        chunks.extend(split_long_chunk(para, max_chars=900))
    return chunks


def batched(items: list[str], batch_size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    raw_policies_dir = root / "data" / "raw_policies"
    if not raw_policies_dir.exists():
        raise FileNotFoundError(f"Missing folder: {raw_policies_dir}")

    policy_files = iter_policy_files(raw_policies_dir)
    if not policy_files:
        raise FileNotFoundError(f"No .txt policy files found in: {raw_policies_dir}")

    print(f"Found {len(policy_files)} policy files in {raw_policies_dir}")

    # Load + chunk
    rows: list[dict] = []
    for fp in policy_files:
        text = fp.read_text(encoding="utf-8", errors="replace")
        chunks = chunk_text(text)
        print(f"- {fp.name}: {len(chunks)} chunks")
        for idx, chunk in enumerate(chunks):
            rows.append(
                {
                    "id": f"{fp.stem}:{idx}",
                    "source_file": fp.name,
                    "chunk_index": idx,
                    "text": chunk,
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("No chunks produced. Check your policy files.")

    print(f"Total chunks to embed: {len(df)}")

    # Embeddings
    model_name = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
    print(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)

    embeddings: list[np.ndarray] = []
    batch_size = int(os.getenv("EMBED_BATCH_SIZE", "64"))
    for i, batch in enumerate(batched(df["text"].tolist(), batch_size=batch_size), start=1):
        vecs = model.encode(batch, show_progress_bar=False, normalize_embeddings=True)
        vecs = np.asarray(vecs, dtype=np.float32)
        embeddings.append(vecs)
        done = min(i * batch_size, len(df))
        print(f"Embedded {done}/{len(df)} chunks")

    emb = np.vstack(embeddings)
    df["embedding"] = [row.tolist() for row in emb]

    # LanceDB
    db_dir = root / "databases" / ".lancedb"
    db_dir.mkdir(parents=True, exist_ok=True)
    print(f"Connecting to LanceDB at {db_dir}")
    db = lancedb.connect(str(db_dir))

    table_name = "hr_policies"
    existing_tables = set(db.table_names())
    if table_name in existing_tables:
        print(f"Opening existing table: {table_name}")
        tbl = db.open_table(table_name)
        print(f"Inserting {len(df)} rows...")
        tbl.add(df.to_dict(orient="records"))
    else:
        print(f"Creating table: {table_name}")
        tbl = db.create_table(table_name, data=df.to_dict(orient="records"))
        print(f"Inserted {len(df)} rows into new table.")

    print("Done.")


if __name__ == "__main__":
    main()
