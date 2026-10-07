"""三种客户端策略：旧客户端自动检索、明确关闭、仅检索所选资料。"""

from fastapi import HTTPException
from pydantic import BaseModel

from app.db import SessionLocal
from app.db.models import Document


class ReferenceSelection(BaseModel):
    use_reference_materials: bool | None = None
    reference_doc_ids: list[str] = []


def reference_options(req: ReferenceSelection) -> dict:
    if req.use_reference_materials is None:
        return {"reference_doc_ids": req.reference_doc_ids} if req.reference_doc_ids else {}
    if not req.use_reference_materials:
        return {"use_reference_materials": False, "reference_doc_ids": []}
    ids = list(dict.fromkeys(req.reference_doc_ids))
    if not ids:
        raise HTTPException(status_code=400, detail="请先勾选至少一份参考资料")
    with SessionLocal() as db:
        available = {
            d.id
            for d in db.query(Document)
            .filter(Document.id.in_(ids), Document.status.in_(["已完成", "有冲突"]))
            .all()
        }
    if set(ids) != available:
        raise HTTPException(
            status_code=400, detail="所选资料已删除、尚未解析完成或不属于当前会话，请重新勾选"
        )
    return {"use_reference_materials": True, "reference_doc_ids": ids}
