#!/usr/bin/env python3
"""
build_notes.py — 从提取后的 Markdown 生成结构化中文学习笔记。

用法:
    # 默认读取 extracted/ 下第一个 .md 文件
    python scripts/build_notes.py

    # 指定提取后的 Markdown 文件
    python scripts/build_notes.py --input extracted/chapter4.md

    # 自定义输出路径
    python scripts/build_notes.py --input extracted/chapter4.md -o output/my_notes.md

    # 使用 DeepSeek
    python scripts/build_notes.py --input extracted/chapter4.md --provider deepseek

    # 使用 Anthropic Claude
    python scripts/build_notes.py --input extracted/chapter4.md --provider anthropic

    # 指定模型
    python scripts/build_notes.py --model deepseek-v4-pro
    python scripts/build_notes.py --model claude-opus-4-7

    # 仅切分 + 保存 prompt（不调 LLM，方便手动处理）
    python scripts/build_notes.py --input extracted/chapter4.md --save-prompts

    # 试运行（仅预览切块，不调 LLM）
    python scripts/build_notes.py --input extracted/chapter4.md --dry-run

    # 跳过最终统稿，直接拼接块级草稿与整章总结（调试旧流程）
    python scripts/build_notes.py --input extracted/chapter4.md --skip-final-editor

环境变量:
    LLM_PROVIDER        — "anthropic" 或 "deepseek"（默认: anthropic）
    ANTHROPIC_API_KEY   — Anthropic 调用必需
    DEEPSEEK_API_KEY    — DeepSeek 调用必需
    DEEPSEEK_BASE_URL   — DeepSeek API 地址（默认: https://api.deepseek.com）
    LLM_MAX_TOKENS      — max_tokens（Anthropic 默认 4096, DeepSeek 默认 8192）
"""

import argparse
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# 确保 scripts/ 目录可被导入（兼容不同调用方式）
_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from text_splitter import Block, split_into_blocks
from llm_client import create_client

# ---- 路径配置 ----
PROJECT_ROOT = _scripts_dir.parent
EXTRACTED_DIR = PROJECT_ROOT / "extracted"
OUTPUT_DIR = PROJECT_ROOT / "output"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
CACHE_DIR = OUTPUT_DIR / ".cache"

SUMMARY_KEYWORDS = (
    "summary",
    "本章总结",
    "章节总结",
    "chapter summary",
)

SANITIZE_LINE_PATTERNS = [
    re.compile(r"^\s*好的[，,：:].*$"),
    re.compile(r"^\s*我将.*$"),
    re.compile(r"^\s*我会.*$"),
    re.compile(r"^\s*你提供.*$"),
    re.compile(r"^\s*由于目前.*提供.*$"),
    re.compile(r"^\s*后续内容.*$"),
    re.compile(r"^\s*当你提供.*$"),
    re.compile(r"^\s*以上是.*$"),
    re.compile(r"^\s*如需.*$"),
    re.compile(r"^\s*本回答.*$"),
    re.compile(r"^\s*这份笔记.*$"),
    re.compile(r"^\s*PPT.*未.*提供.*$", re.IGNORECASE),
    re.compile(r"^\s*没有例题.*省略.*$"),
    re.compile(r"^\s*另行补充.*$"),
]


# ============================================================
# 通用工具
# ============================================================

def resolve_input_path(explicit_path: str | None) -> Path:
    """
    解析输入文件路径。
    优先级：--input 参数 > extracted/ 下第一个 .md/.txt
    """
    if explicit_path:
        p = Path(explicit_path)
        if not p.exists():
            raise FileNotFoundError(f"输入文件不存在: {p}")
        return p

    if not EXTRACTED_DIR.exists():
        raise FileNotFoundError(
            f"目录不存在: {EXTRACTED_DIR}\n"
            f"  请先运行提取脚本，例如:\n"
            f"  python scripts/extract_content.py --input input/你的文件.pptx"
        )

    candidates = sorted(
        f for f in EXTRACTED_DIR.iterdir()
        if f.suffix.lower() in (".txt", ".md") and f.name != ".gitkeep"
    )
    if not candidates:
        raise FileNotFoundError(
            f"{EXTRACTED_DIR}/ 中没有 .md 或 .txt 文件。\n"
            f"  请先运行提取脚本，例如:\n"
            f"  python scripts/extract_content.py --input input/你的文件.pptx\n"
            f"  或通过 --input 直接指定文件路径。"
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



def sanitize_cache_name(name: str) -> str:
    """将文件名规范化为适合缓存目录的 slug。"""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return slug or "default"



def get_run_cache_dir(input_path: Path) -> Path:
    """为当前输入文件返回独立缓存目录，避免不同章节互相污染。"""
    return CACHE_DIR / sanitize_cache_name(input_path.stem)



def extract_source_range(block: Block) -> str:
    """从 block.text 首行提取 Source range。"""
    match = re.match(r"^Source range:\s*(.+)$", block.text, re.MULTILINE)
    return match.group(1).strip() if match else ""



def is_summary_block(block: Block) -> bool:
    """判断该知识块是否属于总结/summary 类型，只作为终稿总结参考。"""
    haystack = f"{block.title}\n{extract_source_range(block)}".lower()
    return any(keyword.lower() in haystack for keyword in SUMMARY_KEYWORDS)



def sanitize_text(text: str) -> str:
    """清理常见模型元话术，但尽量避免误删正常学术内容。"""
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and any(pattern.match(stripped) for pattern in SANITIZE_LINE_PATTERNS):
            continue
        lines.append(line.rstrip())

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()



def save_prompts_to_files(
    source_name: str,
    blocks: list[Block],
    block_prompt: str,
    chapter_prompt: str,
    final_editor_prompt: str,
):
    """将 prompt 模板与占位输入保存到 output/prompts/，方便手动调试。"""
    prompts_out = OUTPUT_DIR / "prompts"
    prompts_out.mkdir(parents=True, exist_ok=True)

    for block in blocks:
        prompt_text = (
            f"【System Prompt】\n{block_prompt}\n\n"
            f"【待处理文本】\n{block.text}"
        )
        out_path = prompts_out / f"block_{block.index:02d}_prompt.md"
        out_path.write_text(prompt_text, encoding="utf-8")
        print(f"  [{block.index}] prompt → {out_path}")

    chapter_placeholder = (
        f"【System Prompt】\n{chapter_prompt}\n\n"
        "【待处理内容】\n"
        "将各块级草稿清洗后粘贴到这里，用于调试 --skip-final-editor 的旧流程。\n"
    )
    chapter_path = prompts_out / "chapter_summary_prompt.md"
    chapter_path.write_text(chapter_placeholder, encoding="utf-8")
    print(f"  [总结] prompt → {chapter_path}")

    final_editor_placeholder = (
        f"【System Prompt】\n{final_editor_prompt}\n\n"
        f"【待处理内容】\n章节名：{source_name}\n\n"
        "【正文知识块草稿】\n"
        "将清洗后的普通知识块草稿粘贴到这里。\n\n"
        "【总结参考材料】\n"
        "将 summary / 本章总结 类草稿粘贴到这里，仅供生成最后的整章总结。\n"
    )
    final_editor_path = prompts_out / "final_editor_prompt.md"
    final_editor_path.write_text(final_editor_placeholder, encoding="utf-8")
    print(f"  [终稿] prompt → {final_editor_path}")
    print(f"\n所有 prompt 已保存到 {prompts_out}/，可逐个复制给 LLM 处理。")


# ============================================================
# LLM 流水线
# ============================================================

def summarize_blocks(
    blocks: list[Block],
    client,
    block_prompt: str,
    cache_dir: Path,
    retries: int = 2,
) -> tuple[list[str], dict[str, int]]:
    """
    逐块调用 LLM 生成块级草稿。
    返回: (block_drafts, token_usage)
    """
    block_cache_dir = cache_dir / "block_drafts_v2"
    block_cache_dir.mkdir(parents=True, exist_ok=True)

    drafts: list[str] = []
    tokens = {"input": 0, "output": 0}

    for block in blocks:
        cache_path = block_cache_dir / f"block_{block.index:02d}.md"
        if cache_path.exists():
            cached = cache_path.read_text(encoding="utf-8")
            if cached.strip():
                print(f"  [{block.index}/{len(blocks)}] {block.title} ← 缓存命中，跳过")
                drafts.append(cached)
                continue

        print(f"  [{block.index}/{len(blocks)}] {block.title} — 调用 LLM...", end=" ", flush=True)
        last_error = None
        for attempt in range(1 + retries):
            try:
                result = client.summarize_block(
                    system_prompt=block_prompt,
                    block_text=block.text,
                    block_index=block.index,
                )
                drafts.append(result.content)
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
                        f"知识块 {block.index} 处理失败（已重试 {retries} 次）: {last_error}"
                    )

    return drafts, tokens



def generate_chapter_summary(
    client,
    chapter_prompt: str,
    block_drafts: list[str],
    cache_dir: Path,
    retries: int = 2,
) -> tuple[str, dict[str, int]]:
    """调试旧流程时生成整章总结。"""
    cache_path = cache_dir / "chapter_summary_v2.md"
    if cache_path.exists():
        cached = cache_path.read_text(encoding="utf-8")
        if cached.strip():
            print("  [整章总结] ← 缓存命中，跳过")
            return cached, {}

    blocks_joined = "\n\n---\n\n".join(block_drafts)
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

    raise RuntimeError("unreachable")



def build_final_editor_input(
    source_name: str,
    body_entries: list[tuple[Block, str]],
    summary_entries: list[tuple[Block, str]],
) -> str:
    """构造最终统稿阶段的输入。"""
    body_parts: list[str] = []
    for idx, (block, draft) in enumerate(body_entries, start=1):
        body_parts.append(
            "\n".join([
                f"### 正文草稿 {idx}",
                f"原知识块标题：{block.title}",
                f"来源：{extract_source_range(block) or '未知'}",
                draft.strip(),
            ])
        )

    summary_parts: list[str] = []
    for idx, (block, draft) in enumerate(summary_entries, start=1):
        summary_parts.append(
            "\n".join([
                f"### 总结参考 {idx}",
                f"原知识块标题：{block.title}",
                f"来源：{extract_source_range(block) or '未知'}",
                draft.strip(),
            ])
        )

    summary_section = (
        "\n\n".join(summary_parts)
        if summary_parts
        else "无单独 summary / 本章总结 参考材料；请根据正文知识块自行生成“整章总结”。"
    )

    return (
        f"章节名：{source_name}\n\n"
        f"【正文知识块草稿】\n\n{chr(10).join(body_parts).strip()}\n\n"
        f"【总结参考材料】\n\n{summary_section.strip()}"
    )



def generate_final_notes(
    client,
    final_editor_prompt: str,
    final_editor_input: str,
    cache_dir: Path,
    retries: int = 2,
) -> tuple[str, dict[str, int]]:
    """调用最终统稿 prompt，将块级草稿整理成终稿。"""
    cache_path = cache_dir / "final_notes_v2.md"
    if cache_path.exists():
        cached = cache_path.read_text(encoding="utf-8")
        if cached.strip():
            print("  [最终统稿] ← 缓存命中，跳过")
            return cached, {}

    print("  [最终统稿] 调用 LLM...", end=" ", flush=True)
    last_error = None
    for attempt in range(1 + retries):
        try:
            result = client.generate_final_notes(
                system_prompt=final_editor_prompt,
                drafts_text=final_editor_input,
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
                    f"最终统稿生成失败（已重试 {retries} 次）: {last_error}"
                )

    raise RuntimeError("unreachable")


# ============================================================
# 输出组装
# ============================================================

def assemble_legacy_output(
    source_name: str,
    block_count: int,
    block_drafts: list[str],
    chapter_summary: str,
) -> str:
    """组装跳过最终统稿时的旧式输出。"""
    blocks_md = "\n\n---\n\n".join(block_drafts)
    return (
        f"# {source_name} 学习笔记\n\n"
        f"> 由 PPT/PDF 提取文本自动生成 | {block_count} 个正文知识块 | "
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
        description="从提取后的 Markdown 生成结构化中文学习笔记。"
    )
    parser.add_argument(
        "--input", "-i", default=None,
        help="提取后的 .md 文件路径（默认: extracted/ 下第一个 .md）",
    )
    parser.add_argument(
        "positional_input", nargs="?", default=None,
        help=argparse.SUPPRESS,
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
        help="仅切分并保存各阶段 prompt 到 output/prompts/，不调用 LLM",
    )
    parser.add_argument(
        "--skip-final-editor", action="store_true",
        help="跳过最终统稿，直接拼接块级草稿与整章总结，用于调试旧流程",
    )
    parser.add_argument(
        "--provider", default=None,
        choices=["anthropic", "deepseek"],
        help="LLM 提供方: anthropic / deepseek（默认: 环境变量 LLM_PROVIDER，最终回退 anthropic）",
    )
    parser.add_argument(
        "--model", default=None,
        help="模型名（anthropic 默认 claude-sonnet-4-6, deepseek 默认 deepseek-v4-flash）",
    )
    parser.add_argument(
        "--retries", type=int, default=2,
        help="LLM 调用失败重试次数（默认: 2）",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="忽略当前输入文件的缓存，强制重新生成",
    )
    args = parser.parse_args()

    input_arg = args.input or args.positional_input
    input_path = resolve_input_path(input_arg)
    print(f"[build_notes] 输入: {input_path}")
    raw_text = load_source(input_path)

    blocks = split_into_blocks(raw_text)
    print(f"[build_notes] 切分为 {len(blocks)} 个知识块")

    if args.dry_run:
        for block in blocks:
            preview = re.sub(r'^#{1,3}\s+', '', block.text, flags=re.MULTILINE)
            preview = preview.strip()[:150].replace("\n", " ")
            role = " [summary-ref]" if is_summary_block(block) else ""
            print(f"  [{block.index}] {block.title}{role}")
            print(f"      {preview}...\n")
        print("[build_notes] 试运行结束，未调用 LLM。")
        return

    block_prompt = load_prompt("block_summarize.md")
    chapter_prompt = load_prompt("chapter_summary.md")
    final_editor_prompt = load_prompt("final_editor.md")

    if args.save_prompts:
        save_prompts_to_files(
            source_name=input_path.stem,
            blocks=blocks,
            block_prompt=block_prompt,
            chapter_prompt=chapter_prompt,
            final_editor_prompt=final_editor_prompt,
        )
        print("[build_notes] 已保存 prompt，未调用 LLM。")
        return

    run_cache_dir = get_run_cache_dir(input_path)
    if args.no_cache and run_cache_dir.exists():
        import shutil
        shutil.rmtree(run_cache_dir)
        print(f"[build_notes] 已清除缓存: {run_cache_dir}")

    client = create_client(provider=args.provider, model=args.model)
    provider_name = args.provider or os.getenv("LLM_PROVIDER", "anthropic")
    print(f"[build_notes] Provider: {provider_name}")
    print(f"[build_notes] Model: {client.model}")

    print(f"[build_notes] 开始生成块级草稿 ({len(blocks)} 块)...")
    block_drafts, block_tokens = summarize_blocks(
        blocks=blocks,
        client=client,
        block_prompt=block_prompt,
        cache_dir=run_cache_dir,
        retries=args.retries,
    )

    sanitized_block_drafts = [sanitize_text(draft) for draft in block_drafts]
    paired_entries = list(zip(blocks, sanitized_block_drafts))
    body_entries = [entry for entry in paired_entries if not is_summary_block(entry[0])]
    summary_entries = [entry for entry in paired_entries if is_summary_block(entry[0])]
    print(
        f"[build_notes] 本地清洗完成：正文块 {len(body_entries)} 个，"
        f"总结参考块 {len(summary_entries)} 个"
    )

    extra_tokens = {"input": 0, "output": 0}
    if args.skip_final_editor:
        print("[build_notes] 跳过最终统稿，生成旧式整章总结...")
        summary_source_drafts = [draft for _, draft in body_entries + summary_entries]
        chapter_summary, extra_tokens = generate_chapter_summary(
            client=client,
            chapter_prompt=chapter_prompt,
            block_drafts=summary_source_drafts,
            cache_dir=run_cache_dir,
            retries=args.retries,
        )
        final_md = assemble_legacy_output(
            source_name=input_path.stem,
            block_count=len(body_entries),
            block_drafts=[draft for _, draft in body_entries],
            chapter_summary=sanitize_text(chapter_summary),
        )
    else:
        print("[build_notes] 启动最终统稿阶段...")
        final_editor_input = build_final_editor_input(
            source_name=input_path.stem,
            body_entries=body_entries,
            summary_entries=summary_entries,
        )
        final_notes, extra_tokens = generate_final_notes(
            client=client,
            final_editor_prompt=final_editor_prompt,
            final_editor_input=final_editor_input,
            cache_dir=run_cache_dir,
            retries=args.retries,
        )
        final_md = sanitize_text(final_notes)

    output_path = Path(args.output) if args.output else (OUTPUT_DIR / "final_notes.md")
    write_output(final_md, output_path)

    total_in = block_tokens.get("input", 0) + extra_tokens.get("input", 0)
    total_out = block_tokens.get("output", 0) + extra_tokens.get("output", 0)
    print(f"[build_notes] Token 用量: 入 {total_in} / 出 {total_out}")
    print(f"[build_notes] 缓存目录: {run_cache_dir}")


if __name__ == "__main__":
    main()
