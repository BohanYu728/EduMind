import json

import httpx
import pytest
from fastapi import HTTPException

from app.core.llm.base import ChatMessage
from app.core.llm.providers.deepseek import DeepSeekProvider
from app.knowledge.local_embedding import embed_texts


async def test_chat_and_vision_use_deepseek(tmp_path):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "实际内容"}}]})

    provider = DeepSeekProvider("test-key", transport=httpx.MockTransport(handle))
    assert (await provider.chat([ChatMessage("user", "备课")])).content == "实际内容"
    image = tmp_path / "test.png"
    image.write_bytes(b"test-image")
    assert await provider.vision(str(image), "识别") == "实际内容"
    assert requests[0].url == "https://api.deepseek.com/chat/completions"
    assert requests[0].headers["Authorization"] == "Bearer test-key"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "deepseek-flash"
    assert payload["thinking"] == {"type": "disabled"}
    vision = json.loads(requests[1].content)
    assert vision["messages"][0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


@pytest.mark.parametrize("status", [401, 402, 429, 500])
async def test_errors_are_explicit_without_leaking_keys(status):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text="secret-test-key"))
    provider = DeepSeekProvider("secret-test-key", transport=transport)
    with pytest.raises(HTTPException) as error:
        await provider.chat([ChatMessage("user", "备课")])
    assert error.value.status_code == 502
    assert "secret-test-key" not in error.value.detail
    assert str(status) in error.value.detail


async def test_malformed_response_is_failure():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []}))
    with pytest.raises(HTTPException):
        await DeepSeekProvider("test", transport=transport).chat([ChatMessage("user", "备课")])


async def test_embed_is_local_and_deterministic():
    def forbidden(request):
        raise AssertionError("embedding must not call DeepSeek")

    provider = DeepSeekProvider("test", transport=httpx.MockTransport(forbidden))
    vectors = await provider.embed(["TCP 三次握手", "三次握手 TCP", "苹果水果"])
    assert vectors == embed_texts(["TCP 三次握手", "三次握手 TCP", "苹果水果"])
    assert all(len(vector) == 512 for vector in vectors)
    similarity = lambda a, b: sum(x * y for x, y in zip(a, b))
    assert similarity(vectors[0], vectors[1]) > similarity(vectors[0], vectors[2])
    assert embed_texts([""])[0] == [0.0] * 512


def test_factory_requires_key_and_selects_deepseek(monkeypatch):
    from app.core.llm.factory import get_llm, settings

    get_llm.cache_clear()
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    with pytest.raises(HTTPException):
        get_llm()
    monkeypatch.setattr(settings, "deepseek_api_key", "test")
    try:
        assert isinstance(get_llm(), DeepSeekProvider)
    finally:
        get_llm.cache_clear()


def test_local_index_is_separate_and_filters_unrelated(monkeypatch, tmp_path):
    from app.config import settings
    from app.knowledge.vector_store import VectorStore

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    store = VectorStore()
    assert store.db_path == "data/vectors-local-v1.db"
    store.add("tcp", ["TCP 三次握手 SYN ACK"], embed_texts(["TCP 三次握手 SYN ACK"]))
    assert store.search(embed_texts(["三次握手"])[0])[0]["doc_id"] == "tcp"
    assert store.search(embed_texts(["香蕉水果"])[0]) == []
    monkeypatch.setattr(settings, "llm_provider", "stub")
    assert VectorStore().db_path == "data/vectors.db"


def test_reindex_preserves_source_and_new_local_chunks(tmp_path):
    import sqlite3

    from app.knowledge.reindex import rebuild_local_index
    from app.knowledge.vector_store import VectorStore

    source = tmp_path / "old.db"
    target = tmp_path / "vectors-local-v1.db"
    VectorStore(str(source)).add("old", ["三次握手"], [[1.0] * 8])
    source_bytes = source.read_bytes()
    assert rebuild_local_index(str(source), str(target), nodes=[]) == {"chunks": 1, "nodes": 0}
    VectorStore(str(target)).add("new", ["导数定义"], embed_texts(["导数定义"]))
    assert rebuild_local_index(str(source), str(target), nodes=[]) == {"chunks": 2, "nodes": 0}
    assert source.read_bytes() == source_bytes
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 2


def test_model_failure_is_not_reported_as_success(monkeypatch):
    from fastapi.testclient import TestClient

    import app.api.v1.chat as chat_module
    from app.core import orchestrator
    from app.core.intent import TeachingIntent
    from app.main import app

    async def intent(text):
        return TeachingIntent(topic="导数")

    async def fail(*args):
        raise HTTPException(502, "DeepSeek 请求失败（HTTP 402）：账户余额不足")

    async def retrieve(*args, **kwargs):
        return orchestrator.RetrievalResult("", [])

    monkeypatch.setattr(chat_module, "analyze_intent", intent)
    monkeypatch.setattr(orchestrator, "analyze_intent", intent)
    monkeypatch.setattr(orchestrator, "retrieve_knowledge", retrieve)
    monkeypatch.setattr(orchestrator, "generate_ppt_structure", fail)
    response = TestClient(app).post(
        "/api/v1/chat",
        json={
            "messages": [{"role": "user", "content": "导数，直接生成"}],
        },
    )
    assert response.status_code == 502
    assert "余额不足" in response.json()["detail"]
