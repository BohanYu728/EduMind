"""选择生成内容必须约束实际模型调用及文件渲染。"""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

import app.core.orchestrator as module
from app.core.intent import TeachingIntent
from app.core.orchestrator import RetrievalResult
from app.main import app


@pytest.mark.parametrize(
    "outputs", [["ppt"], ["word"], ["outline"], ["interactive"], ["ppt", "word"]]
)
def test_only_selected_outputs_are_generated(monkeypatch, outputs):
    monkeypatch.setattr(
        module, "analyze_intent", AsyncMock(return_value=TeachingIntent(topic="TCP"))
    )
    monkeypatch.setattr(
        module, "retrieve_knowledge", AsyncMock(return_value=RetrievalResult("", []))
    )
    generators = {
        "ppt": AsyncMock(return_value=[{"title": "TCP", "points": []}]),
        "word": AsyncMock(return_value={"objectives": {}}),
        "outline": AsyncMock(return_value="TCP教学提纲"),
        "interactive": AsyncMock(return_value="<html>互动</html>"),
    }
    for kind, function in {
        "ppt": "generate_ppt_structure",
        "word": "generate_word_structure",
        "outline": "generate_outline",
        "interactive": "generate_html_creative",
    }.items():
        monkeypatch.setattr(module, function, generators[kind])
    renderers = {
        "ppt": Mock(return_value="test.pptx"),
        "word": Mock(return_value="test.docx"),
        "interactive": Mock(return_value="test.html"),
    }
    for kind, function in {
        "ppt": "render_ppt",
        "word": "render_word",
        "interactive": "save_html",
    }.items():
        monkeypatch.setattr(module, function, renderers[kind])
    response = TestClient(app).post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "讲TCP，开始生成"}], "outputs": outputs},
    )
    assert response.status_code == 200
    artifacts = response.json()["artifacts"]
    assert set(artifacts["generated_outputs"]) == set(outputs)
    for kind in generators:
        assert generators[kind].await_count == (1 if kind in outputs else 0)
        assert bool(artifacts[kind]) == (kind in outputs)
        if kind in renderers:
            assert renderers[kind].call_count == (1 if kind in outputs else 0)


@pytest.mark.parametrize("outputs", [[], ["unknown"]])
def test_invalid_selection_is_rejected(outputs):
    assert (
        TestClient(app).post("/api/v1/chat", json={"messages": [], "outputs": outputs}).status_code
        == 422
    )
