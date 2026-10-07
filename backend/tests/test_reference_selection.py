"""关闭引用应完全跳过资料；开启引用只能读取当前会话所选文件。"""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.intent import TeachingIntent
from app.core.session_context import session_scope
from app.db import SessionLocal, init_db
from app.db.models import Document, KnowledgeEdge, KnowledgeNode
from app.knowledge.vector_store import VectorStore
from app.main import app

init_db()


@pytest.mark.asyncio
async def test_disabled_references_do_not_embed_or_search(monkeypatch):
    from app.core.llm import factory
    from app.core.orchestrator import retrieve_knowledge

    embed = AsyncMock()
    provider = type("Provider", (), {"embed": embed})()
    monkeypatch.setattr(factory, "get_llm", lambda: provider)
    result = await retrieve_knowledge(
        TeachingIntent(topic="TCP"), reference_doc_ids=["unused"], use_reference_materials=False
    )
    assert result.context == "" and result.sources == []
    embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_strict_selection_excludes_unchecked_chunks_and_graph_neighbors(
    monkeypatch, tmp_path
):
    import app.knowledge.vector_store as vector_module
    from app.core.llm import factory
    from app.core.orchestrator import retrieve_knowledge

    scope = "ref_" + uuid.uuid4().hex
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    with SessionLocal() as db:
        for doc_id, name in [(first, "已选.docx"), (second, "未选.docx")]:
            db.add(
                Document(
                    id=doc_id,
                    session_id=scope,
                    user_id="default",
                    filename=name,
                    file_path="unused",
                    file_type="docx",
                    status="已完成",
                )
            )
        a = KnowledgeNode(
            session_id=scope, user_id="default", title="种子", content="当前", source_docs=[first]
        )
        b = KnowledgeNode(
            session_id=scope,
            user_id="default",
            title="不该引用",
            content="未选图谱秘密",
            source_docs=[second],
        )
        db.add_all([a, b])
        db.flush()
        db.add(
            KnowledgeEdge(
                session_id=scope,
                user_id="default",
                from_node=a.id,
                to_node=b.id,
                relation_type="相关关联",
            )
        )
        db.commit()
    store = VectorStore(str(tmp_path / "vectors.db"))
    store.add(first, ["仅选中文件内容"], [[1.0] * 8])
    store.add(second, ["未选原文秘密"], [[0.0] * 8])
    monkeypatch.setattr(vector_module, "VectorStore", lambda: store)
    embed = AsyncMock(return_value=[[0.0] * 8])
    provider = type("Provider", (), {"embed": embed})()
    monkeypatch.setattr(factory, "get_llm", lambda: provider)
    token = session_scope.set(scope)
    try:
        result = await retrieve_knowledge(
            TeachingIntent(topic="TCP"),
            top_k=1,
            reference_doc_ids=[first],
            use_reference_materials=True,
        )
        assert result.context == "仅选中文件内容"
        assert result.sources == ["已选.docx"]
    finally:
        session_scope.reset(token)


@pytest.mark.parametrize("endpoint", ["chat", "exam/generate", "interactive/generate"])
def test_missing_or_foreign_reference_selection_is_rejected(endpoint):
    scope = "req_" + uuid.uuid4().hex
    with SessionLocal() as db:
        foreign = Document(
            session_id="foreign",
            user_id="default",
            filename="别人的资料",
            file_path="unused",
            file_type="txt",
            status="已完成",
        )
        busy = Document(
            session_id=scope,
            user_id="default",
            filename="正在解析",
            file_path="unused",
            file_type="txt",
        )
        db.add_all([foreign, busy])
        db.commit()
        ids = [foreign.id, busy.id]
    client = TestClient(app)
    for selected in [[], [ids[0]], [ids[1]]]:
        response = client.post(
            f"/api/v1/{endpoint}",
            headers={"X-EduMind-Session": scope},
            json={
                "messages": [],
                "intent": {"topic": "TCP"},
                "use_reference_materials": True,
                "reference_doc_ids": selected,
            },
        )
        assert response.status_code == 400
