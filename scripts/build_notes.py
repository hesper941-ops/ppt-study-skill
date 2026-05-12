#!/usr/bin/env python3
"""
build_notes.py — 从 PPT/PDF 提取文本生成结构化中文学习笔记。

用法:
    # 默认读取 input/chapter4.md
    python scripts/build_notes.py

    # 指定输入文件
    python scripts/build_notes.py input/other_chapter.md

    # 仅切分 + 保存 prompt（不调 LLM，方便手动处理）
    python scripts/build_notes.py --save-prompts

    # 试运行（仅预览切块）
    python scripts/build_notes.py --dry-run

    # 指定模型
    python scripts/build_notes.py --model claude-opus-4-7

    # 自定义输出路径
    python scripts/build_notes.py -o output/my_notes.md

环境变量:
    ANTHROPIC_API_KEY   — LLM 调用必需
    ANTHROPIC_MODEL     — 默认模型（未指定时: claude-sonnet-4-6）
"""

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# 确保 scripts/ 目录可被导入（兼容不同调用方式）
_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from text_splitter import split_into_blocks
from llm_client import AnthropicClient

# ---- 路径配置 ----
PROJECT_ROOT = _scripts_dir.parent
INPUT_DIR = PROJECT_ROOT / "input"
OUTPUT_DIR = PROJECT_ROOT / "output"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
CACHE_DIR = OUTPUT_DIR / ".cache"
DEFAULT_INPUT = "chapter4.md"


# ============================================================
# 流水线各步骤（独立函数，方便后续扩展 docx/pdf 导出）
# ============================================================

def resolve_input_path(explicit_path: str | None) -> Path:
    """
    解析输入文件路径。
    优先级：命令行参数 > input/chapter4.md > input/ 下第一个 .md/.txt
    """
    if explicit_path:
        p = Path(explicit_path)
        if not p.exists():
            raise FileNotFoundError(f"输入文件不存在: {p}")
        return p

    # 默认优先找 input/chapter4.md
    default = INPUT_DIR / DEFAULT_INPUT
    if default.exists():
        return default

    # 回退：扫描 input/ 目录
    candidates = sorted(
        f for f in INPUT_DIR.iterdir()
        if f.suffix.lower() in (".txt", ".md") and f.name != ".gitkeep"
    )
    if not candidates:
        raise FileNotFoundError(
            f"未找到输入文件。请将 PPT/PDF 提取文本放入 {INPUT_DIR}/\n"
            f"  默认期望文件: {default}"
        )
    return candidates[0]


def load_source(path: Path) -> str:
    """读取源文件，返回文本内容（自动处理 BOM）。"""
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError(f"输入文件为空: {path}")
    return text


def load_prompt(name: str) -> str:
    """从 prompts/ 目录加载 prompt 模板。"""
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt 文件不存在: {path}")
    return path.read_text(encoding="utf-8")


def save_prompts_to_files(blocks: list, block_prompt: str, chapter_prompt: str):
    """将每个知识块对应的完整 prompt 保存到 output/prompts/，方便手动处理。"""
    prompts_out = OUTPUT_DIR / "prompts"
    prompts_out.mkdir(parents=True, exist_ok=True)

    for b in blocks:
        prompt_text = f"【System Prompt】\n{block_prompt}\n\n【待处理文本】\n{b.text}"
        out_path = prompts_out / f"block_{b.index:02d}_prompt.md"
        out_path.write_text(prompt_text, encoding="utf-8")
        print(f"  [{b.index}] prompt → {out_path}")

    # 章节总结的 prompt 留空占位，实际使用时需填入各块结果
    summary_path = prompts_out / "chapter_summary_prompt.md"
    summary_path.write_text(chapter_prompt, encoding="utf-8")
    print(f"  [总结] prompt → {summary_path}")
    print(f"\n所有 prompt 已保存到 {prompts_out}/，可逐个复制给 LLM 处理。")


def summarize_blocks(
    blocks: list,
    client,
    block_prompt: str,
    retries: int = 2,
) -> tuple[list[str], dict]:
    """
    逐块调用 LLM 生成总结。
    返回: (block_summaries, token_usage)
    支持缓存：若某块已有缓存文件，跳过 LLM 调用。
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    summaries: list[str] = []
    tokens = {"input": 0, "output": 0}

    for b in blocks:
        cache_path = CACHE_DIR / f"block_{b.index:02d}.md"
        if cache_path.exists():
            cached = cache_path.read_text(encoding="utf-8")
            if cached.strip():
                print(f"  [{b.index}/{len(blocks)}] {b.title} ← 缓存命中，跳过")
                summaries.append(cached)
                continue

        print(f"  [{b.index}/{len(blocks)}] {b.title} — 调用 LLM...", end=" ", flush=True)

        last_error = None
        for attempt in range(1 + retries):
            try:
                result = client.summarize_block(
                    system_prompt=block_prompt,
                    block_text=b.text,
                    block_index=b.index,
                )
                summaries.append(result.content)
                # 写入缓存
                cache_path.write_text(result.content, encoding="utf-8")
                if result.token_usage:
                    tokens["input"] += result.token_usage.get("input", 0)
                    tokens["output"] += result.token_usage.get("output", 0)
                print("✓")
                break
            except Exception as e:
                last_error = e
                if attempt < retries:
                    wait = 2 ** attempt
                    print(f"失败，{wait}s 后重试...")
                    time.sleep(wait)
                else:
                    print(f"✗ ({e})")
                    raise RuntimeError(
                        f"知识块 {b.index} 处理失败（已重试 {retries} 次）: {last_error}"
                    )

    return summaries, tokens


def generate_chapter_summary(
    client,
    chapter_prompt: str,
    block_summaries: list[str],
    retries: int = 2,
) -> tuple[str, dict]:
    """
    调用 LLM 生成整章总结。
    返回: (summary_text, token_usage)
    """
    cache_path = CACHE_DIR / "chapter_summary.md"
    if cache_path.exists():
        cached = cache_path.read_text(encoding="utf-8")
        if cached.strip():
            print("  [整章总结] ← 缓存命中，跳过")
            return cached, {}

    blocks_joined = "\n\n---\n\n".join(block_summaries)
    print("  [整章总结] 调用 LLM...", end=" ", flush=True)

    last_error = None
    for attempt in range(1 + retries):
        try:
            result = client.generate_chapter_summary(
                system_prompt=chapter_prompt,
                blocks_summary=blocks_joined,
            )
            cache_path.write_text(result.content, encoding="utf-8")
            tokens = result.token_usage or {}
            print("✓")
            return result.content, tokens
        except Exception as e:
            last_error = e
            if attempt < retries:
                wait = 2 ** attempt
                print(f"失败，{wait}s 后重试...")
                time.sleep(wait)
            else:
                print(f"✗ ({e})")
                raise RuntimeError(
                    f"整章总结生成失败（已重试 {retries} 次）: {last_error}"
                )

    # unreachable, but satisfy type checker
    raise RuntimeError("unreachable")


def assemble_output(
    source_name: str,
    block_count: int,
    block_summaries: list[str],
    chapter_summary: str,
) -> str:
    """组装最终 Markdown 输出。"""
    blocks_md = "\n\n---\n\n".join(block_summaries)
    return (
        f"# {source_name} 学习笔记\n\n"
        f"> 由 PPT/PDF 提取文本自动生成 | {block_count} 个知识块 | "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"{blocks_md}\n\n"
        f"---\n\n"
        f"{chapter_summary}"
    )


def write_output(content: str, output_path: Path):
    """写出最终笔记文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"\n[build_notes] 输出 → {output_path}")


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="从 PPT/PDF 提取文本生成结构化中文学习笔记。"
    )
    parser.add_argument(
        "input", nargs="?", default=None,
        help=f"输入 .md/.txt 文件路径（默认: input/{DEFAULT_INPUT}）",
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="输出文件路径（默认: output/final_notes.md）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅切分知识块并打印预览，不调用 LLM",
    )
    parser.add_argument(
        "--save-prompts", action="store_true",
        help="仅切分并保存各块的 prompt 到 output/prompts/，不调用 LLM",
    )
    parser.add_argument(
        "--model", default=None,
        help="Anthropic 模型覆盖（环境变量: ANTHROPIC_MODEL）",
    )
    parser.add_argument(
        "--retries", type=int, default=2,
        help="LLM 调用失败重试次数（默认: 2）",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="忽略缓存，强制重新生成所有块",
    )
    args = parser.parse_args()

    # ---- 第 1 步：加载源文件 ----
    input_path = resolve_input_path(args.input)
    print(f"[build_notes] 输入: {input_path}")
    raw_text = load_source(input_path)

    # ---- 第 2 步：切分知识块 ----
    blocks = split_into_blocks(raw_text)
    print(f"[build_notes] 切分为 {len(blocks)} 个知识块")

    if args.dry_run:
        for b in blocks:
            # 去除标题和多余空白做预览
            preview = re.sub(r'^#{1,3}\s+', '', b.text, flags=re.MULTILINE)
            preview = preview.strip()[:150].replace("\n", " ")
            print(f"  [{b.index}] {b.title}")
            print(f"      {preview}...\n")
        print("[build_notes] 试运行结束，未调用 LLM。")
        return

    # ---- 第 3 步：加载 prompt 模板 ----
    block_prompt = load_prompt("block_summarize.md")
    chapter_prompt = load_prompt("chapter_summary.md")

    if args.save_prompts:
        save_prompts_to_files(blocks, block_prompt, chapter_prompt)
        print("[build_notes] 已保存 prompt，未调用 LLM。")
        return

    # ---- 第 4 步：清理缓存（可选）----
    if args.no_cache and CACHE_DIR.exists():
        import shutil
        shutil.rmtree(CACHE_DIR)
        print("[build_notes] 已清除缓存")

    # ---- 第 5 步：初始化 LLM 客户端 ----
    client = AnthropicClient(model=args.model)

    # ---- 第 6 步：逐块总结 ----
    print(f"[build_notes] 开始逐块总结 ({len(blocks)} 块)...")
    block_summaries, block_tokens = summarize_blocks(
        blocks, client, block_prompt, retries=args.retries
    )

    # ---- 第 7 步：整章总结 ----
    print("[build_notes] 生成整章总结...")
    chapter_summary, chapter_tokens = generate_chapter_summary(
        client, chapter_prompt, block_summaries, retries=args.retries
    )

    # ---- 第 8 步：组装并写出 ----
    final_md = assemble_output(
        source_name=input_path.stem,
        block_count=len(blocks),
        block_summaries=block_summaries,
        chapter_summary=chapter_summary,
    )

    output_path = Path(args.output) if args.output else (OUTPUT_DIR / "final_notes.md")
    write_output(final_md, output_path)

    # ---- 统计 ----
    total_in = block_tokens.get("input", 0) + chapter_tokens.get("input", 0)
    total_out = block_tokens.get("output", 0) + chapter_tokens.get("output", 0)
    print(f"[build_notes] Token 用量: 入 {total_in} / 出 {total_out}")
    print(f"[build_notes] 缓存目录: {CACHE_DIR}")


if __name__ == "__main__":
    main()
