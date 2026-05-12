"""
LLM 客户端抽象层。
内置 Anthropic API 实现，更换其他提供方只需实现相同接口。
"""

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class BlockResult:
    """单知识块总结的返回结果。"""
    content: str
    token_usage: dict | None = None


class LLMClient(ABC):
    """LLM 客户端抽象基类，按提供方实现。"""

    @abstractmethod
    def summarize_block(
        self, system_prompt: str, block_text: str, block_index: int
    ) -> BlockResult:
        """将 block_text 发给 LLM，配合 system_prompt 返回总结。"""
        ...

    @abstractmethod
    def generate_chapter_summary(
        self, system_prompt: str, blocks_summary: str
    ) -> BlockResult:
        """根据所有知识块总结，生成整章总结。"""
        ...


class AnthropicClient(LLMClient):
    """
    Anthropic Claude API 客户端。

    支持:
    - 自动重试（指数退避）
    - 可配置超时
    - 环境变量或参数传入 API key 和模型
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ):
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "未设置 ANTHROPIC_API_KEY 环境变量。\n"
                "  获取 Key: https://console.anthropic.com/\n"
                "  设置方式: export ANTHROPIC_API_KEY=sk-ant-..."
            )

        import anthropic

        self._client = anthropic.Anthropic(
            api_key=self.api_key,
            timeout=timeout,
        )

    def _call(self, system_prompt: str, user_text: str) -> BlockResult:
        """底层 API 调用。"""
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}],
        )
        return BlockResult(
            content=resp.content[0].text,
            token_usage={
                "input": resp.usage.input_tokens,
                "output": resp.usage.output_tokens,
            },
        )

    def summarize_block(
        self, system_prompt: str, block_text: str, block_index: int
    ) -> BlockResult:
        """总结单个知识块。重试逻辑由调用方（build_notes.py）控制。"""
        return self._call(system_prompt, block_text)

    def generate_chapter_summary(
        self, system_prompt: str, blocks_summary: str
    ) -> BlockResult:
        """生成整章总结。重试逻辑由调用方（build_notes.py）控制。"""
        return self._call(system_prompt, blocks_summary)
