"""资料归档、旧产物认领和会话清理。会话标题由浏览器保存。"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.core.session_context import current_session_id
from app.db import get_session
from app.db.models import (
    Conflict,
    Document,
    GeneratedArtifact,
    KnowledgeNode,
    Question,
    QuestionKnowledge,
)
from app.knowledge.cleanup import remove_document, remove_node

router = APIRouter()


@router.get("/sessions/legacy")
def legacy_info(db: Annotated[Session, Depends(get_session)]):
    count = (
        db.query(Document)
        .execution_options(all_sessions=True)
        .filter_by(session_id="legacy")
        .count()
    )
    return {"id": "legacy", "name": "以前的资料", "document_count": count}


class ImportFiles(BaseModel):
    filenames: list[str]


@router.post("/sessions/import-files")
def import_files(req: ImportFiles, db: Annotated[Session, Depends(get_session)]):
    # 仅认领迁移前没有所属记录的文件，已绑定的文件不能转移会话。
    for name in set(req.filenames):
        if not name or Path(name).name != name or "/" in name or "\\" in name:
            continue
        existing = (
            db.query(GeneratedArtifact)
            .execution_options(all_sessions=True)
            .filter_by(filename=name)
            .first()
        )
        if not existing and (Path("data/output") / name).is_file():
            db.execute(
                insert(GeneratedArtifact)
                .values(filename=name, session_id=current_session_id())
                .on_conflict_do_nothing(index_elements=["filename"])
            )
    db.commit()
    return {"status": "ok"}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, db: Annotated[Session, Depends(get_session)]):
    if session_id != current_session_id():
        raise HTTPException(status_code=403, detail="会话标识不一致")
    docs = db.query(Document).all()
    if any(d.status in ("处理中", "解析中") for d in docs):
        raise HTTPException(status_code=409, detail="这个会话仍有资料正在解析，请稍后删除")
    for doc in docs:
        remove_document(db, doc)
    for node in db.query(KnowledgeNode).all():
        remove_node(db, node)
    for question in db.query(Question).all():
        db.query(QuestionKnowledge).filter_by(question_id=question.id).delete(
            synchronize_session=False
        )
        db.delete(question)
    db.query(Conflict).delete(synchronize_session=False)
    for artifact in db.query(GeneratedArtifact).all():
        (Path("data/output") / artifact.filename).unlink(missing_ok=True)
        db.delete(artifact)
    db.commit()
    return {"status": "deleted"}
