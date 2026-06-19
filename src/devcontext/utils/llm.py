"""LLM API 封装 — MiniMax + GLM（OpenAI 兼容接口）。

统一 LLM 调用接口，支持 MiniMax 和 GLM provider 切换。
使用 OpenAI Python SDK（两者均兼容 OpenAI API 格式）。

提供：
- ``LLMClient``：抽象基类
- ``OpenAICompatibleClient``：MiniMax/GLM 通用实现
- ``MockLLMClient``：测试用 mock（内存返回预设响应）
- ``create_llm_client``：工厂函数（从 Settings 创建）
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from openai import OpenAI

from devcontext.config import settings

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """LLM 客户端抽象基类。

    所有 LLM provider 实现此接口，提供统一的 ``chat()`` 方法。
    """

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """调用 LLM 对话接口。

        Args:
            messages: OpenAI 格式的消息列表。
            model: 模型名称（None 用默认）。
            temperature: 采样温度。
            max_tokens: 最大输出 token 数。
            response_format: 响应格式约束（如 ``{"type": "json_object"}``）。

        Returns:
            OpenAI 格式的响应 dict：
            ``{"choices": [{"message": {"content": "..."}}],
               "usage": {"total_tokens": N, ...}}``
        """
        ...


class OpenAICompatibleClient(LLMClient):
    """OpenAI 兼容 LLM 客户端（MiniMax / GLM 通用）。

    使用 OpenAI Python SDK，通过 ``base_url`` + ``api_key`` 切换 provider。

    Args:
        api_key: API 密钥。
        base_url: API 基础 URL。
        model: 默认模型名称。
        timeout: 请求超时秒数。
        max_retries: 最大重试次数。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """调用 LLM 对话接口（含重试）。

        重试策略：指数退避（2s → 4s → 8s），最多 ``max_retries`` 次。
        超时和 5xx 错误重试，4xx 错误直接抛出。

        Raises:
            RuntimeError: 重试耗尽仍失败。
        """
        target_model = model or self._model
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                kwargs: dict[str, Any] = {
                    "model": target_model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                if response_format is not None:
                    kwargs["response_format"] = response_format

                response = self._client.chat.completions.create(**kwargs)

                return {
                    "choices": [
                        {
                            "message": {
                                "content": choice.message.content,
                                "role": choice.message.role,
                            }
                        }
                        for choice in response.choices
                    ],
                    "usage": {
                        "total_tokens": response.usage.total_tokens if response.usage else 0,
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": (
                            response.usage.completion_tokens if response.usage else 0
                        ),
                    },
                }

            except Exception as e:
                last_error = e
                logger.warning(
                    "LLM call attempt %d/%d failed: %s",
                    attempt + 1,
                    self._max_retries,
                    e,
                )
                if attempt < self._max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.info("Retrying in %ds...", wait)
                    time.sleep(wait)

        raise RuntimeError(
            f"LLM call failed after {self._max_retries} attempts: {last_error}"
        ) from last_error


class MockLLMClient(LLMClient):
    """测试用 Mock LLM 客户端。

    预设响应或按函数生成响应，不发起真实 API 调用。

    Args:
        response: 预设的响应内容字符串（message.content）。
        response_func: 可选的响应生成函数，接收 messages 返回 content。
        usage: 预设的 token 用量。
    """

    def __init__(
        self,
        response: str = "",
        response_func: Any = None,
        usage: dict[str, int] | None = None,
    ) -> None:
        self._response = response
        self._response_func = response_func
        self._usage = usage or {"total_tokens": 100, "prompt_tokens": 70, "completion_tokens": 30}
        self.call_history: list[list[dict[str, str]]] = []

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """返回预设响应（记录调用历史）。"""
        self.call_history.append(messages)
        if self._response_func is not None:
            content = self._response_func(messages)
        else:
            content = self._response
        return {
            "choices": [{"message": {"content": content, "role": "assistant"}}],
            "usage": dict(self._usage),
        }


def create_llm_client(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> LLMClient:
    """从 Settings 创建 LLM 客户端（工厂函数）。

    Args:
        api_key: 覆盖配置的 API 密钥。
        base_url: 覆盖配置的 base URL。
        model: 覆盖配置的模型名。

    Returns:
        ``OpenAICompatibleClient`` 实例。
    """
    return OpenAICompatibleClient(
        api_key=api_key or settings.llm_api_key,
        base_url=base_url or settings.llm_base_url,
        model=model or settings.llm_model,
    )
