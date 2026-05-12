"""
将 PPT/PDF 提取文本按"知识块"切分。

切分策略（按优先级）：
1. 识别显式 "## Knowledge Block N - Title" 标记，以此为一级边界；
   前置幻灯片归入"本章概览"，后置总结幻灯片归入"本章总结"，
   每个 Knowledge Block 内的 ### Slide 保持为子内容。
2. 无 Knowledge Block 标记时，按幻灯片/页分隔符切分。
3. 再回退到按 Markdown ## 标题切分 + 同标题合并。
"""

import re
from dataclasses import dataclass


@dataclass
class Block:
    """知识块数据结构。"""
    index: int
    title: str
    text: str


# ---- 显式知识块标记 ----
KB_HEADING_RE = re.compile(r"^## Knowledge Block\s+(\d+)\s*[-:—]\s*(.+)$", re.MULTILINE)

# 前置/后置标题常量
PREAMBLE_TITLE = "本章概览"
POSTAMBLE_TITLE = "本章总结"

# ---- 幻灯片/页分隔符（回退策略）----
SLIDE_SEPARATORS = [
    r"\n(?=---+\s*(?:Slide|Page)\s*\d+)",
    r"\n(?==+\s*(?:Slide|Page)\s*\d+)",
    r"\n(?=(?:Slide|Page)\s*\d+\s*[:：\-—])",
    r"\n(?=第\s*\d+\s*[页張])",
    r"\n(?=幻灯片\s*\d+)",
]


def _normalize(text: str) -> str:
    """统一换行符，压缩多余空行。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ============================================================
# 策略一：显式 Knowledge Block 标记
# ============================================================

def _split_by_knowledge_blocks(text: str) -> list[Block] | None:
    """
    按显式 "## Knowledge Block N - Title" 标记切分。

    返回 None 表示未找到任何 Knowledge Block 标记，调用方应回退到其他策略。
    """
    matches = list(KB_HEADING_RE.finditer(text))
    if not matches:
        return None

    blocks: list[Block] = []
    idx = 1

    # ---- 前置内容：第一个 Knowledge Block 之前的所有文本 ----
    preamble_end = matches[0].start()
    preamble = text[:preamble_end].strip()
    if _has_substantial_content(preamble):
        blocks.append(Block(index=idx, title=PREAMBLE_TITLE, text=preamble))
        idx += 1

    # ---- 各 Knowledge Block ----
    for i, m in enumerate(matches):
        title = f"{m.group(1)}. {m.group(2).strip()}"
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()

        # 最后一个 Knowledge Block：检查是否混入了后置 ## Slide（本章总结）
        trailing = _extract_trailing_slides(content)
        if trailing is not None:
            kb_body, postamble = trailing
            content = kb_body
            has_postamble = True
        else:
            has_postamble = False

        if _has_substantial_content(content):
            blocks.append(Block(index=idx, title=title, text=content))
            idx += 1

        if has_postamble and _has_substantial_content(postamble):
            blocks.append(Block(index=idx, title=POSTAMBLE_TITLE, text=postamble))
            idx += 1

    return blocks if blocks else None


def _has_substantial_content(text: str) -> bool:
    """
    判断文本是否有实质内容（不只是章节标题或空白）。
    去除 # 标题和空白后，至少还有一定长度的有效文本。
    """
    cleaned = re.sub(r"^#\s+.+$", "", text, flags=re.MULTILINE).strip()
    cleaned = re.sub(r"^#{1,3}\s+.+$", "", cleaned, flags=re.MULTILINE).strip()
    return len(cleaned) >= 30


def _extract_trailing_slides(content: str) -> tuple[str, str] | None:
    """
    检查最后一个 Knowledge Block 的内容末尾是否混入了 ## Slide 标记。

    如果末尾存在 ## Slide 开头的段落（且非 ### Slide），将其分离出来。
    返回 (知识块正文, 后置内容) 或 None。
    """
    # 找到第一个出现在末尾区域的 ## Slide（非 ### Slide）
    pattern = re.compile(r"\n(?=## Slide\s+\d+)")
    parts = list(pattern.split(content))
    if len(parts) <= 1:
        return None

    # 只分离最后连续出现的 ## Slide 组
    # 策略：从后往前找 ## Slide 的连续段落
    # 更简单：判断最后一个 ## Slide 之前是否有足够的 KB 专属内容
    # 如果最后一个 part 是 ## Slide 内容且前面的 part 已有足够 KB 内容
    # 则把最后几个 ## Slide 段落分离

    # 简化处理：如果末尾有两段以上 ## Slide，分离整个尾部
    slide_count = len(pattern.findall(content))
    if slide_count >= 2:
        # 找到倒数第 slide_count 个 ## Slide 的位置
        # 重新匹配，取最后 slide_count 个
        all_splits = list(pattern.finditer(content))
        if len(all_splits) >= 2:
            cutoff = all_splits[-2].start()  # 从倒数第二个 ## Slide 开始
            # 但如果只剩一个 ## Slide 之前的内容很少，不分离
            kb_body = content[:cutoff].strip()
            postamble = content[cutoff:].strip()
            if len(kb_body) > 200:  # KB 主体至少 200 字
                return kb_body, postamble

    return None


# ============================================================
# 策略二 & 三：幻灯片分隔符 / Markdown 标题（回退）
# ============================================================

def _split_by_slides(text: str) -> list[str] | None:
    """按幻灯片/页分隔符切分。"""
    for pat in SLIDE_SEPARATORS:
        parts = re.split(pat, text)
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]
    return None


def _split_by_headings(text: str) -> list[str]:
    """按 Markdown ## 标题切分。"""
    parts = re.split(r"\n(?=##\s)", text)
    return [p.strip() for p in parts if p.strip()]


def _extract_heading_title(text: str) -> str:
    """从文本中提取第一个 #/## 标题。"""
    m = re.search(r"^#{1,3}\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _merge_related_blocks(parts: list[str]) -> list[Block]:
    """将相同标题的连续块合并。"""
    merged: list[Block] = []
    buffer: list[str] = []
    current_title = ""

    for raw in parts:
        title = _extract_heading_title(raw)

        if title and current_title and title == current_title:
            buffer.append(raw)
        else:
            if buffer:
                merged.append(Block(
                    index=len(merged) + 1,
                    title=current_title or f"知识块 {len(merged) + 1}",
                    text="\n\n".join(buffer),
                ))
            buffer = [raw]
            current_title = title or f"知识块 {len(merged) + 1}"

    if buffer:
        merged.append(Block(
            index=len(merged) + 1,
            title=current_title or f"知识块 {len(merged) + 1}",
            text="\n\n".join(buffer),
        ))

    return merged


# ============================================================
# 主入口
# ============================================================

def split_into_blocks(raw_text: str) -> list[Block]:
    """
    将原始 PPT/PDF 提取文本切分为知识块列表。

    优先级:
    1. 显式 "## Knowledge Block" 标记 → 层级切分
    2. 幻灯片/页分隔符 → 按页切分 + 合并
    3. Markdown ## 标题 → 按标题切分 + 合并
    """
    text = _normalize(raw_text)
    if not text:
        return []

    # 策略一：显式 Knowledge Block
    result = _split_by_knowledge_blocks(text)
    if result is not None:
        return result

    # 策略二：幻灯片分隔符
    parts = _split_by_slides(text)
    if parts is None:
        # 策略三：Markdown 标题
        parts = _split_by_headings(text)

    if not parts:
        return []

    return _merge_related_blocks(parts)
