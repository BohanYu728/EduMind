"""会话及文档删除共用的资料清理。"""

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import or_

from app.db.models import Conflict, KnowledgeEdge, KnowledgeNode, QuestionKnowledge
from app.knowledge.vector_store import VectorStore


def remove_node(db, node):
    db.query(KnowledgeEdge).filter(
        or_(KnowledgeEdge.from_node == node.id, KnowledgeEdge.to_node == node.id)
    ).delete(synchronize_session=False)
    db.query(QuestionKnowledge).filter_by(knowledge_id=node.id).delete(synchronize_session=False)
    db.query(Conflict).filter(Conflict.existing_knowledge["id"].as_string() == node.id).delete(
        synchronize_session=False
    )
    db.delete(node)
    for index in ("data/vectors.db", "data/vectors-local-v1.db"):
        if Path(index).exists():
            VectorStore(index).remove_node_title(node.id)


def remove_document(db, doc):
    if doc.status in ("处理中", "解析中"):
        raise HTTPException(status_code=409, detail="资料正在解析，请完成后再删除")
    for node in db.query(KnowledgeNode).all():
        sources = node.source_docs or []
        if doc.id in sources:
            remaining = [source for source in sources if source != doc.id]
            if remaining:
                node.source_docs = remaining
            else:
                remove_node(db, node)
    db.query(Conflict).filter_by(doc_id=doc.id).delete(synchronize_session=False)
    for index in ("data/vectors.db", "data/vectors-local-v1.db"):
        if Path(index).exists():
            VectorStore(index).remove_document(doc.id)
    Path(doc.file_path).unlink(missing_ok=True)
    db.delete(doc)
