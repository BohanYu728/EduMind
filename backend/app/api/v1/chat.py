"""对话接口：多轮追问澄清 + 编排备课流程。"""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.v1.reference_policy import ReferenceSelection, reference_options
from app.core.clarify import build_question, missing_fields
from app.core.intent import analyze_intent
from app.core.orchestrator import orchestrate

router = APIRouter()


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(ReferenceSelection):
    messages: list[Message]
    granularity: str = "标准"
    # 本次备课的参考资料（文档 id）：检索加权 + 回复/教案溯源；不传则行为与现状一致
    outputs: list[Literal["ppt", "word", "outline", "interactive"]] | None = Field(
        default=None, min_length=1, max_length=4
    )


class ChatResponse(BaseModel):
    content: str
    artifacts: dict | None = None
    clarifying: bool = False


_SKIP_WORDS = ["开始生成", "就这样", "生成吧", "够了", "可以了", "直接生成"]


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    policy = reference_options(req)
    history = req.messages
    message = history[-1].content if history else ""
    user_text = " ".join(m.content for m in history if m.role == "user")

    # 1. 意图分析（基于累积需求）
    intent = await analyze_intent(user_text)

    # 2. 追问判断
    if not intent.topic:
        return ChatResponse(
            content="请问你要讲什么课？可以告诉我主题、学段和大致时长。",
            clarifying=True,
        )

    missing = missing_fields(intent, req.granularity)
    skip = any(k in message for k in _SKIP_WORDS)
    if missing and not skip:
        q = build_question(missing)
        return ChatResponse(
            content=f"还差一点信息：{q}（也可以回复「开始生成」跳过追问）",
            clarifying=True,
        )

    # 3. 生成（携带参考资料标识：检索加权 + 溯源）
    options = {"outputs": list(dict.fromkeys(req.outputs))} if req.outputs is not None else {}
    result = await orchestrate(user_text, **policy, **options)
    topic = result["intent"].get("topic", "")
    generated = []
    if result.get("ppt"):
        generated.append(f"PPT {len(result['ppt']['slides'])} 页")
    if result.get("word"):
        generated.append("Word 教案")
    if result.get("outline"):
        generated.append("教学提纲")
    if result.get("interactive"):
        generated.append("互动内容")
    kb_note = "已融合本地知识库" if result["knowledge_hits"] else "知识库为空，已由 AI 直接生成"
    if req.use_reference_materials is False:
        kb_note = "未使用上传资料，已根据教学需求生成"
    elif req.use_reference_materials is True and not result["knowledge_hits"]:
        kb_note = "所选资料未检索到相关内容，已根据教学需求生成"
    content = f"已完成备课「{topic}」：生成{'、'.join(generated)}。（{kb_note}）"
    references = result.get("references") or []
    if references:
        content += f" 本次命中的来源文档：{'、'.join(references)}。"
    if result.get("interactive"):
        content += " 互动内容可在产物预览区打开。"
    for kind in ("ppt", "word"):
        if result.get(kind):
            result[kind]["filename"] = Path(result[kind]["path"]).name
    return ChatResponse(content=content, artifacts=result)
