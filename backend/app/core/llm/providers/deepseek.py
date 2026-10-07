"""DeepSeek 文字与图片接口；知识库特征向量在本地计算。"""

import base64
import mimetypes
from pathlib import Path

import httpx
from fastapi import HTTPException

from app.core.llm.base import ChatMessage, ChatResult, LLMProvider
from app.knowledge.local_embedding import embed_texts


class DeepSeekProvider(LLMProvider):
    name = "deepseek"

    def __init__(
        self,
        api_key: str,
        chat_model: str = "deepseek-flash",
        vision_model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = api_key
        self.chat_model = chat_model
        self.vision_model = vision_model
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    async def _complete(self, messages: list[dict], model: str) -> ChatResult:
        try:
            async with httpx.AsyncClient(timeout=180, transport=self.transport) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": model, "messages": messages, "thinking": {"type": "disabled"}},
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("empty response")
                return ChatResult(content=content, raw=data)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            hints = {
                401: "请检查 DEEPSEEK_API_KEY",
                402: "账户余额不足",
                429: "请求过于频繁，请稍后重试",
            }
            detail = hints.get(status, "请检查模型名称或稍后重试")
            raise HTTPException(502, f"DeepSeek 请求失败（HTTP {status}）：{detail}") from None
        except httpx.RequestError:
            raise HTTPException(502, "DeepSeek 连接失败或超时，请检查网络后重试") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise HTTPException(502, "DeepSeek 返回内容无效，请重试") from None

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        return await self._complete(
            [{"role": message.role, "content": message.content} for message in messages],
            kwargs.get("model", self.chat_model),
        )

    async def vision(self, image_path: str, prompt: str) -> str:
        mime = mimetypes.guess_type(image_path)[0] or "image/png"
        encoded = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        result = await self._complete(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{encoded}"},
                        },
                    ],
                }
            ],
            self.vision_model,
        )
        return result.content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(texts)
