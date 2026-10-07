"""真实 DeepSeek 连通验证，只输出结果，不输出密钥。"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.config import settings
from app.core.llm.base import ChatMessage
from app.core.llm.factory import get_llm


async def main() -> int:
    print(f"Provider: {settings.llm_provider}; model: {settings.deepseek_model}")
    try:
        result = await get_llm().chat([ChatMessage("user", "请只回复：DeepSeek连接成功")])
        print(result.content[:200])
        print("DeepSeek live chat: PASS")
        return 0
    except HTTPException as error:
        print(f"DeepSeek live chat: FAIL — {error.detail}")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
