"""
LLM 客户端抽象层。
支持 Anthropic Claude 与 DeepSeek（通过 OpenAI-compatible API）。
通过 create_client() 工厂函数按 provider 创建对应客户端。

环境变量:
    LLM_PROVIDER        — "anthropic" 或 "deepseek"（默认: anthropic）
    LLM_MAX_TOKENS      — max_tokens（默认: Anthropic 4096, DeepSeek 8192）

    Anthropic:
        ANTHROPIC_API_KEY   — API Key（必需）
        ANTHROPIC_MODEL     — 模型（默认: claude-sonnet-4-6）

    DeepSeek:
        DEEPSEEK_API_KEY    — API Key（必需）
        DEEPSEEK_BASE_URL   — API 地址（默认: https://api.deepseek.com）
"""

import os
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


# ============================================================
# Anthropic Claude
# ============================================================

class AnthropicClient(LLMClient):
    """
    Anthropic Claude API 客户端。

    默认模型: claude-sonnet-4-6
    环境变量: ANTHROPIC_API_KEY, ANTHROPIC_MODEL
    """

    DEFAULT_MODEL = "claude-sonnet-4-6"
    DEFAULT_MAX_TOKENS = 4096

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
        timeout: float = 120.0,
    ):
        self.model = model or os.getenv("ANTHROPIC_MODEL", self.DEFAULT_MODEL)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.max_tokens = max_tokens or int(
            os.getenv("LLM_MAX_TOKENS", str(self.DEFAULT_MAX_TOKENS))
        )

        if not self.api_key:
            raise ValueError(
                "未设置 ANTHROPIC_API_KEY 环境变量。\n"
                "  获取 Key: https://console.anthropic.com/\n"
                "  设置方式:\n"
                "    macOS/Linux: export ANTHROPIC_API_KEY=sk-ant-...\n"
                "    PowerShell:  $env:ANTHROPIC_API_KEY=\"sk-ant-...\""
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
            max_tokens=self.max_tokens,
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
        """总结单个知识块。"""
        return self._call(system_prompt, block_text)

    def generate_chapter_summary(
        self, system_prompt: str, blocks_summary: str
    ) -> BlockResult:
        """生成整章总结。"""
        return self._call(system_prompt, blocks_summary)


# ============================================================
# DeepSeek（OpenAI-compatible API）
# ============================================================

class DeepSeekClient(LLMClient):
    """
    DeepSeek API 客户端（使用 OpenAI SDK，兼容接口）。

    默认模型: deepseek-v4-flash
    可选模型: deepseek-v4-pro
    环境变量: DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

    调用方式:
        from openai import OpenAI
        client = OpenAI(api_key=..., base_url="https://api.deepseek.com")
        response = client.chat.completions.create(...)
    """

    DEFAULT_MODEL = "deepseek-v4-flash"
    DEFAULT_MAX_TOKENS = 8192
    DEFAULT_BASE_URL = "https://api.deepseek.com"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int | None = None,
        timeout: float = 180.0,
    ):
        self.model = model or os.getenv("DEEPSEEK_MODEL", self.DEFAULT_MODEL)
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", self.DEFAULT_BASE_URL)
        self.max_tokens = max_tokens or int(
            os.getenv("LLM_MAX_TOKENS", str(self.DEFAULT_MAX_TOKENS))
        )

        if not self.api_key:
            raise ValueError(
                "未设置 DEEPSEEK_API_KEY 环境变量。\n"
                "  获取 Key: https://platform.deepseek.com/\n"
                "  设置方式:\n"
                "    macOS/Linux: export DEEPSEEK_API_KEY=sk-...\n"
                "    PowerShell:  $env:DEEPSEEK_API_KEY=\"sk-...\""
            )

        from openai import OpenAI

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
        )

    def _call(self, system_prompt: str, user_text: str) -> BlockResult:
        """底层 API 调用（Chat Completions）。"""
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        )
        choice = resp.choices[0]
        return BlockResult(
            content=choice.message.content or "",
            token_usage={
                "input": resp.usage.prompt_tokens if resp.usage else 0,
                "output": resp.usage.completion_tokens if resp.usage else 0,
            },
        )

    def summarize_block(
        self, system_prompt: str, block_text: str, block_index: int
    ) -> BlockResult:
        """总结单个知识块。"""
        return self._call(system_prompt, block_text)

    def generate_chapter_summary(
        self, system_prompt: str, blocks_summary: str
    ) -> BlockResult:
        """生成整章总结。"""
        return self._call(system_prompt, blocks_summary)


# ============================================================
# 工厂函数
# ============================================================

def create_client(
    provider: str | None = None,
    model: str | None = None,
) -> LLMClient:
    """
    根据 provider 创建对应的 LLM 客户端。

    Args:
        provider: "anthropic" | "deepseek"（默认从 LLM_PROVIDER 环境变量读取，最终回退 anthropic）
        model: 模型名（None 则使用各 provider 的默认模型）

    Returns:
        AnthropicClient 或 DeepSeekClient 实例
    """
    provider = provider or os.getenv("LLM_PROVIDER", "anthropic").lower()

    if provider == "deepseek":
        return DeepSeekClient(model=model)
    elif provider == "anthropic":
        return AnthropicClient(model=model)
    else:
        raise ValueError(
            f"不支持的 LLM provider: {provider}\n"
            f"  支持的值: anthropic, deepseek\n"
            f"  通过 --provider 参数或 LLM_PROVIDER 环境变量设置。"
        )
