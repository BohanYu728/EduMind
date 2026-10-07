"""从已保存的文本重建本地索引；保留旧向量库和后续上传的本地片段。"""

import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from app.knowledge.local_embedding import embed_texts
from app.knowledge.vector_store import VectorStore


def _read_chunks(path: str) -> list[tuple]:
    source = Path(path).resolve()
    if not source.is_file():
        return []
    with closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)) as connection:
        exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'"
        ).fetchone()
        return (
            connection.execute(
                "SELECT doc_id, content, chunk_index FROM chunks ORDER BY id"
            ).fetchall()
            if exists
            else []
        )


def rebuild_local_index(
    source: str = "data/vectors.db",
    target: str = "data/vectors-local-v1.db",
    nodes: list[tuple[str, str]] | None = None,
) -> dict:
    chunks = {}
    # 新索引优先，旧索引只补齐缺失片段。
    for doc_id, content, index in _read_chunks(target) + _read_chunks(source):
        chunks.setdefault((doc_id, index), content)
    if nodes is None:
        from app.db import SessionLocal
        from app.db.models import KnowledgeNode

        with SessionLocal() as db:
            nodes = [(node.id, node.title) for node in db.query(KnowledgeNode).all()]
    staging = Path(target).with_name(f"{Path(target).stem}.rebuild-{uuid.uuid4().hex}.db")
    store = VectorStore(str(staging))
    try:
        grouped = {}
        for (doc_id, index), content in sorted(chunks.items()):
            grouped.setdefault(doc_id, []).append(content)
        for doc_id, texts in grouped.items():
            store.add(doc_id, texts, embed_texts(texts))
        for node_id, title in nodes:
            if title.strip():
                store.add_node_title(node_id, title, embed_texts([title])[0])
        # 空库也落盘，后续启动无需反复迁移。
        with closing(sqlite3.connect(staging)):
            pass
        os.replace(staging, target)
    finally:
        if staging.is_file():
            staging.unlink()
    return {"chunks": len(chunks), "nodes": len(nodes)}
