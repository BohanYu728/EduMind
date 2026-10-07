"""教学智能体编排器：对话 → 意图 → 检索 → 生成。"""

import asyncio
import logging
from pathlib import Path
from typing import NamedTuple

from fastapi import HTTPException

from app.core.intent import TeachingIntent, analyze_intent, wants_interactive_content
from app.generate.creative import generate_html_creative, save_html
from app.generate.outline import generate_outline
from app.generate.ppt import generate_ppt_structure, render_ppt
from app.generate.word import generate_word_structure, render_word

logger = logging.getLogger(__name__)

# 生成上下文总预算（字符）：命中片段优先，图谱节点内容在剩余空间内截断。
# 与生成 prompt 的知识窗口（knowledge[:6000]）对齐，保证图谱段不被下游二次截断。
CONTEXT_BUDGET_CHARS = 6000
_CHUNKS_HEADER = "=== 知识片段 ===\n"
_NODES_HEADER = "=== 图谱关联知识点（按知识递进） ===\n"


class RetrievalResult(NamedTuple):
    """检索结果：拼好的生成上下文 + 按排名去重的命中来源文档名（溯源共用）。"""

    context: str
    sources: list[str]


async def retrieve_knowledge(
    intent: TeachingIntent,
    top_k: int = 5,
    reference_doc_ids: list[str] | None = None,
    use_reference_materials: bool | None = None,
) -> RetrievalResult:
    """RAG 语义检索（参考资料加权）+ 图谱邻接子图融合。向量库为空或检索失败时降级为空。"""
    if use_reference_materials is False or (
        use_reference_materials is True and not reference_doc_ids
    ):
        return RetrievalResult(context="", sources=[])
    query = " ".join([intent.topic, *intent.knowledge_points]).strip()
    if not query:
        return RetrievalResult(context="", sources=[])
    try:
        from app.core.llm.factory import get_llm
        from app.knowledge.vector_store import VectorStore

        emb = await get_llm().embed([query])
        options = {"allowed_doc_ids": reference_doc_ids} if use_reference_materials is True else {}
        hits = VectorStore().search(
            emb[0], k=top_k, boost_doc_ids=reference_doc_ids or None, **options
        )
        chunks = [h["content"] for h in hits if h.get("content")]
        sources = _source_names([h["doc_id"] for h in hits])
    except Exception:
        logger.warning("知识检索失败，降级为空上下文", exc_info=True)
        return RetrievalResult(context="", sources=[])
    try:
        # 明确选择文件时只使用这些文件的原文片段，避免图谱扩展带入未勾选资料。
        context = (
            "\n\n".join(chunks)
            if use_reference_materials is True
            else _fused_context(chunks, [h["doc_id"] for h in hits])
        )
    except Exception:
        logger.warning("图谱邻接子图拉取失败，降级为仅片段上下文", exc_info=True)
        context = "\n\n".join(chunks)
    return RetrievalResult(context=context, sources=sources)


def _source_names(doc_ids: list[str]) -> list[str]:
    """命中 doc_id 按排名映射为文档名（去重）；文档已删除时回退为 doc_id。"""
    names: dict[str, str] = {}
    try:
        from app.db import SessionLocal
        from app.db.models import Document

        db = SessionLocal()
        try:
            rows = db.query(Document).filter(Document.id.in_(doc_ids)).all()
            names = {d.id: d.filename for d in rows}
        finally:
            db.close()
    except Exception:
        logger.warning("来源文档名查询失败，回退为 doc_id", exc_info=True)
    ordered: list[str] = []
    for doc_id in doc_ids:
        name = names.get(doc_id, doc_id)
        if name not in ordered:
            ordered.append(name)
    return ordered


def _fused_context(chunks: list[str], doc_ids: list[str]) -> str:
    """命中片段经来源文档定位知识点，沿图谱边拉取邻接子图，拼入同一上下文。"""
    from app.knowledge.graph import neighborhood, nodes_for_docs

    seed_ids = [n["id"] for n in nodes_for_docs(doc_ids)]
    adjacent = neighborhood(seed_ids)
    return _assemble_context(chunks, adjacent)


def _assemble_context(
    chunks: list[str], nodes: list[dict], budget: int = CONTEXT_BUDGET_CHARS
) -> str:
    """预算内组装：命中片段优先完整保留，图谱节点内容按剩余空间截断。"""
    parts: list[str] = []
    used = 0

    chunk_block = "\n\n".join(c for c in chunks if c)
    if chunk_block:
        piece = (_CHUNKS_HEADER + chunk_block)[: budget - used]
        if piece:
            parts.append(piece)
            used += len(piece)

    if nodes and used < budget:
        # 预留段头与分段符（"\n\n".join），避免拼接后总量超出预算
        room = budget - used - len(_NODES_HEADER) - (2 if parts else 0)
        lines: list[str] = []
        used_lines = 0
        for n in nodes:
            sep = 2 if lines else 0
            line_room = room - used_lines - sep
            if line_room <= 0:
                break
            line = f"【{n['title']}】{n.get('content') or ''}"[:line_room]
            lines.append(line)
            used_lines += sep + len(line)
        if lines:
            parts.append(_NODES_HEADER + "\n\n".join(lines))
    return "\n\n".join(parts)


async def orchestrate(
    message: str,
    reference_doc_ids: list[str] | None = None,
    outputs: list[str] | None = None,
    use_reference_materials: bool | None = None,
) -> dict:
    """按教师选择生成材料；未传 outputs 的旧客户端保留原有行为。"""
    intent = await analyze_intent(message)
    intent_dict = intent.model_dump()
    policy = (
        {"use_reference_materials": use_reference_materials}
        if use_reference_materials is not None
        else {}
    )
    retrieval = await retrieve_knowledge(intent, reference_doc_ids=reference_doc_ids, **policy)
    knowledge = retrieval.context
    references = retrieval.sources if reference_doc_ids else []
    selected = set(outputs if outputs is not None else ["ppt", "word", "outline"])
    if outputs is None and wants_interactive_content(intent):
        selected.add("interactive")
    calls = {}
    if "ppt" in selected:
        calls["ppt"] = generate_ppt_structure(intent_dict, knowledge)
    if "word" in selected:
        calls["word"] = generate_word_structure(intent_dict, knowledge)
    if "outline" in selected:
        calls["outline"] = generate_outline(intent_dict, knowledge)
    if "interactive" in selected:
        calls["interactive"] = generate_html_creative(knowledge or intent.topic)
    values = await asyncio.gather(*calls.values(), return_exceptions=True)
    results = dict(zip(calls, values))
    for result in results.values():
        if isinstance(result, HTTPException):
            raise result
        if isinstance(result, BaseException):
            logger.error("教学材料生成失败: %s", result)
            raise HTTPException(status_code=502, detail="教学材料生成失败，请重试")
    ppt = word = interactive = None
    if "ppt" in results:
        slides = results["ppt"]
        path = render_ppt(slides, style=intent_dict.get("style", ""))
        ppt = {"slides": slides, "path": path, "filename": Path(path).name}
    if "word" in results:
        data = results["word"]
        path = render_word(data, references=references)
        word = {"data": data, "path": path, "filename": Path(path).name}
    if "interactive" in results and str(results["interactive"]).strip():
        html = str(results["interactive"])
        path = save_html(html)
        interactive = {"html": html, "path": path, "filename": Path(path).name}
    return {
        "intent": intent_dict,
        "knowledge_hits": bool(knowledge),
        "references": references,
        "ppt": ppt,
        "word": word,
        "outline": results.get("outline", ""),
        "interactive": interactive,
        "generated_outputs": list(calls),
    }
