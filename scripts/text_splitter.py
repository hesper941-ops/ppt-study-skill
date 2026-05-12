"""
将 PPT/PDF 提取文本按"知识块"切分。

三层策略（按优先级）:
  1. 手工知识块标记: "## Knowledge Block N" / "## 知识块 N" / "## Block N"
     前置内容 → "本章概览"，后置总结 → "本章总结"
  2. 自动提取格式 (## Slide N / ## Page N): 解析为 Unit → 智能合并为 Knowledge Block
     目标 5-10 个块，避免一页一块
  3. 回退: 按 ## 标题切分 + 同标题合并

无外部 NLP 依赖，仅用 Python 标准库。
"""

import re
from dataclasses import dataclass

# ============================================================
# 数据结构
# ============================================================


@dataclass
class Unit:
    """单个 Slide / Page 单元（中间结构）。"""
    index: int           # 原始序号
    heading: str         # "Slide 1" / "Page 3"
    title: str           # 提取的标题（可能为空）
    body: str            # 正文
    char_count: int      # 正文字符数
    raw: str             # 完整原始文本（含 heading）


@dataclass
class Block:
    """最终知识块。"""
    index: int
    title: str           # "Knowledge Block 1: Title"
    text: str            # "Source range: ...\n\n{merged body}"


# ============================================================
# 通用工具
# ============================================================

def _normalize(text: str) -> str:
    """统一换行符，压缩多余空行。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _tokenize(text: str) -> set[str]:
    """简单分词：提取长度 >= 2 的单词/中文词。"""
    # 英文单词
    words = set(re.findall(r"[a-zA-Z]{3,}", text.lower()))
    # 中文 2-gram（字符级）
    chinese_chars = re.findall(r"[一-鿿]", text)
    for i in range(len(chinese_chars) - 1):
        words.add(chinese_chars[i] + chinese_chars[i + 1])
    return words


def _keyword_overlap(a: str, b: str) -> float:
    """Jaccard 相似度（基于简单分词）。"""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _normalize_title(t: str) -> str:
    """规范化标题用于比较。"""
    t = t.strip().lower()
    t = re.sub(r"[^\w一-鿿\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


# ============================================================
# 策略一：手工 Knowledge Block 标记
# ============================================================

# 匹配: "## Knowledge Block N" / "## 知识块 N" / "## Block N"
_MANUAL_KB_RE = re.compile(
    r"^##\s*(?:Knowledge Block|知识块|Block)\s*(\d+)\s*[-:—]*\s*(.*)$",
    re.MULTILINE | re.IGNORECASE,
)

PREAMBLE_TITLE = "本章概览"
POSTAMBLE_TITLE = "本章总结"


def _split_by_manual_kb(text: str) -> list[Block] | None:
    """按手工知识块标记切分。未找到返回 None。"""
    matches = list(_MANUAL_KB_RE.finditer(text))
    if not matches:
        return None

    blocks: list[Block] = []
    idx = 1

    # 前置内容
    preamble = text[:matches[0].start()].strip()
    if _has_substance(preamble, min_chars=50):
        blocks.append(Block(
            index=idx,
            title=PREAMBLE_TITLE,
            text=f"Source range: (preamble)\n\n{preamble}",
        ))
        idx += 1

    # 各知识块
    for i, m in enumerate(matches):
        kb_num = m.group(1)
        kb_label = m.group(2).strip()
        block_title = f"知识块 {kb_num}: {kb_label}" if kb_label else f"知识块 {kb_num}"

        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()

        # 最后一个 KB：检查末尾是否混入了后置 slide/page
        trailing = _extract_trailing_units(content)
        if trailing:
            kb_body, postamble = trailing
            content = kb_body
            if _has_substance(postamble, min_chars=50):
                blocks.append(Block(
                    index=idx,
                    title=block_title,
                    text=f"Source range: Knowledge Block {kb_num}\n\n{content}",
                ))
                idx += 1
                blocks.append(Block(
                    index=idx,
                    title=POSTAMBLE_TITLE,
                    text=f"Source range: (summary)\n\n{postamble}",
                ))
                idx += 1
                continue

        if _has_substance(content, min_chars=30):
            blocks.append(Block(
                index=idx,
                title=block_title,
                text=f"Source range: Knowledge Block {kb_num}\n\n{content}",
            ))
            idx += 1

    return blocks if blocks else None


def _has_substance(text: str, min_chars: int = 30) -> bool:
    """判断是否有实质内容。"""
    cleaned = re.sub(r"^#{1,3}\s+.+$", "", text, flags=re.MULTILINE).strip()
    return len(cleaned) >= min_chars


def _extract_trailing_units(content: str) -> tuple[str, str] | None:
    """
    检查末尾是否混入了不属于本知识块的 ## Slide/## Page。
    如果末尾有两段以上 ## Slide/Page，且前面正文 >= 200 字，则分离。
    """
    pattern = re.compile(r"\n(?=## (?:Slide|Page)\s+\d+)")
    all_splits = list(pattern.finditer(content))
    if len(all_splits) < 2:
        return None
    cutoff = all_splits[-2].start()
    kb_body = content[:cutoff].strip()
    postamble = content[cutoff:].strip()
    if len(kb_body) >= 200:
        return kb_body, postamble
    return None


# ============================================================
# 策略二：自动 Slide/Page 智能合并（核心）
# ============================================================

# 匹配 ## Slide N / ## Page N / ## 第N页
_UNIT_HEADING_RE = re.compile(
    r"^##\s*(?:Slide|Page|第)\s*(\d+)\s*(?:[页張]|Slide|Page)?\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# 新主题边界词（英文）
_TOPIC_BOUNDARY_EN = {
    "introduction", "overview", "outline", "background", "preliminary",
    "definition", "method", "methodology", "approach", "algorithm",
    "experiment", "result", "discussion", "analysis", "evaluation",
    "conclusion", "summary", "application", "example", "case study",
    "future work", "reference", "appendix", "acknowledgement",
    "problem", "solution", "implementation", "comparison",
}
# 新主题边界词（中文）
_TOPIC_BOUNDARY_CN = {
    "介绍", "概述", "大纲", "背景", "预备知识", "定义", "方法", "算法",
    "实验", "结果", "讨论", "分析", "评估", "结论", "总结", "应用",
    "示例", "案例", "习题", "参考文献", "附录", "致谢",
    "问题", "求解", "实现", "对比", "比较",
}


def _parse_units(text: str) -> list[Unit] | None:
    """
    将 ## Slide N / ## Page N 格式文本解析为 Unit 列表。
    未找到则返回 None。
    """
    matches = list(_UNIT_HEADING_RE.finditer(text))
    if not matches:
        return None

    # 处理第一个 heading 之前的内容
    preamble = text[:matches[0].start()].strip()
    units: list[Unit] = []

    # 第一个 heading 之前的内容 → 作为 chapter intro
    if _has_substance(preamble, min_chars=30):
        units.append(Unit(
            index=0,
            heading="Preamble",
            title=_extract_title_from_body(preamble),
            body=preamble,
            char_count=len(preamble),
            raw=preamble,
        ))

    for i, m in enumerate(matches):
        heading = m.group(0).strip().lstrip("#").strip()
        unit_num = int(m.group(1))
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[content_start:content_end].strip()

        # 去掉 Title: 行作为标题
        title_match = re.match(r"^Title:\s*(.+)$", body, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
            body = body[title_match.end():].strip()
        else:
            title = _extract_title_from_body(body)

        units.append(Unit(
            index=len(units),
            heading=heading,
            title=title,
            body=body,
            char_count=len(body),
            raw=m.group(0) + "\n\n" + body,
        ))

    return units if units else None


def _extract_title_from_body(body: str) -> str:
    """
    从正文中提取标题。
    优先级: ### 标题 > 简短标题行 > 空。
    避免将完整句子误判为标题。
    """
    if not body.strip():
        return ""
    # 三级标题
    m = re.match(r"^###\s+(.+)$", body, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # 首行：需满足"看起来像标题"的条件
    first_line = body.split("\n")[0].strip()
    # 拒绝 bullet、编号
    if re.match(r"^[-*•‣▪▸◦\d]", first_line):
        return ""
    # 标题特征：短、无句号结尾、非完整句子
    if len(first_line) <= 50 and not first_line.rstrip().endswith("."):
        word_count = len(first_line.split())
        if word_count <= 8:
            return first_line
    return ""


# ---- 合并判定函数 ----

def _titles_similar(a: str, b: str) -> bool:
    """判断两个标题是否相同或高度相似。"""
    if not a or not b:
        return False
    na = _normalize_title(a)
    nb = _normalize_title(b)
    if na == nb:
        return True
    # 一个包含另一个
    if na in nb or nb in na:
        return True
    # 关键词重叠 > 60%
    ta = set(na.split())
    tb = set(nb.split())
    if not ta or not tb:
        return False
    overlap = ta & tb
    return len(overlap) / min(len(ta), len(tb)) > 0.6


def _is_topic_boundary(title: str) -> bool:
    """判断标题是否表示新主题开始。"""
    t = title.strip().lower()
    # 英文边界词
    for kw in _TOPIC_BOUNDARY_EN:
        if kw in t:
            return True
    # 中文边界词
    for kw in _TOPIC_BOUNDARY_CN:
        if kw in t:
            return True
    return False


def _is_continuation(body: str) -> bool:
    """
    判断正文是否是上一页内容的延续。
    特征：bullet 开头、数字编号开头、小写开头、无独立标题。
    """
    if not body.strip():
        return True
    first_line = body.strip().split("\n")[0].strip()
    # bullet
    if re.match(r"^[-*•‣▪▸◦]\s", first_line):
        return True
    # 编号
    if re.match(r"^(\d+[.)]\s|\(\d+\)|\d+\.\d)", first_line):
        return True
    # 英文小写开头（句子延续）
    if re.match(r"^[a-z]", first_line):
        return True
    # 冒号后短句（如 "Note:" "Example:" 后接内容）
    if re.match(r"^\w+:\s", first_line):
        return True
    return False


def _should_merge(
    prev: Unit, curr: Unit,
    prev_block_size: int,
) -> bool:
    """
    判断 curr 是否应合并到 prev 所在的块。

    合并信号（优先级从高到低）:
      1. 标题相同或高度相似 → 必合
      2. 当前极短且无标题 → 合
      3. 前一个极短且当前无标题 → 合
      4. 延续格式（bullet/编号/小写开头）→ 合
      5. 关键词重叠度高 → 合

    拆分信号（优先级从高到低）:
      1. 新主题边界词 → 必拆
      2. 当前有新标题、前一个没有 → 拆
      3. 双方都有不同标题 → 拆

    其他情况：短则合、大则拆。
    """
    # ---- 必合 ----
    # 同一标题系列
    if _titles_similar(prev.title, curr.title):
        return True

    # ---- 强合并 ----
    # 极短碎片 + 无独立标题
    if curr.char_count < 100 and not curr.title:
        return True
    if prev.char_count < 100 and not curr.title:
        return True
    # 延续格式
    if _is_continuation(curr.body):
        return True
    # 高关键词重叠（仅在内容足够大时可信）
    if (prev.char_count >= 200 and curr.char_count >= 200
            and _keyword_overlap(prev.body, curr.body) > 0.40):
        return True

    # ---- 强拆分 ----
    # 新主题边界词
    if curr.title and _is_topic_boundary(curr.title):
        return False
    # 当前有标题而前一个没有（新话题开始）
    if curr.title and not prev.title:
        return False
    # 双方都有不同标题（不同话题）
    if (curr.title and prev.title
            and not _titles_similar(prev.title, curr.title)):
        return False

    # ---- 兜底：按大小判断 ----
    if curr.char_count < 250 and prev.char_count < 250:
        return True
    return False


def _merge_units_into_blocks(units: list[Unit]) -> list[Block]:
    """
    将 Unit 列表智能合并为 Knowledge Block 列表。
    第一遍：贪婪合并。第二遍：如果块数过多，强制合并最小块。
    """
    if not units:
        return []

    # ---- 第一遍：贪婪合并 ----
    raw_blocks: list[list[Unit]] = []
    current_group: list[Unit] = [units[0]]
    current_size = units[0].char_count

    for i in range(1, len(units)):
        prev = units[i - 1]
        curr = units[i]
        if _should_merge(prev, curr, current_size):
            current_group.append(curr)
            current_size += curr.char_count
        else:
            raw_blocks.append(current_group)
            current_group = [curr]
            current_size = curr.char_count
    raw_blocks.append(current_group)

    # ---- 第二遍：过多块 → 合并最小相邻块 ----
    TARGET_MAX = 10
    while len(raw_blocks) > TARGET_MAX:
        # 找最小的块，将其合并到较小的邻居
        sizes = [sum(u.char_count for u in g) for g in raw_blocks]
        min_idx = min(range(len(sizes)), key=lambda j: sizes[j])
        # 合并到较小的邻居
        if min_idx == 0:
            raw_blocks[1] = raw_blocks[0] + raw_blocks[1]
            raw_blocks.pop(0)
        elif min_idx == len(raw_blocks) - 1:
            raw_blocks[-2] = raw_blocks[-2] + raw_blocks[-1]
            raw_blocks.pop(-1)
        else:
            left_size = sizes[min_idx - 1]
            right_size = sizes[min_idx + 1]
            if left_size <= right_size:
                raw_blocks[min_idx - 1] = raw_blocks[min_idx - 1] + raw_blocks[min_idx]
            else:
                raw_blocks[min_idx + 1] = raw_blocks[min_idx] + raw_blocks[min_idx + 1]
            raw_blocks.pop(min_idx)

    # ---- 格式化输出 ----
    blocks: list[Block] = []
    for i, group in enumerate(raw_blocks):
        heading_range = _format_source_range(group)
        merged_body = "\n\n".join(u.raw for u in group)
        block_title = _infer_block_title(group, i + 1)

        blocks.append(Block(
            index=i + 1,
            title=block_title,
            text=f"Source range: {heading_range}\n\n{merged_body}",
        ))

    return blocks


def _format_source_range(units: list[Unit]) -> str:
    """格式化来源范围: "Slide 1-4" / "Page 3-6" / "Slide 2, Page 5-7"。"""
    if not units:
        return ""
    if len(units) == 1:
        return units[0].heading

    # 按 heading 类型分组
    slides = [u for u in units if "slide" in u.heading.lower()]
    pages = [u for u in units if "page" in u.heading.lower()]
    others = [u for u in units if u not in slides and u not in pages]

    parts: list[str] = []
    if slides:
        nums = sorted(int(re.search(r"\d+", u.heading).group()) for u in slides if re.search(r"\d+", u.heading))
        parts.append(f"Slide {nums[0]}-{nums[-1]}" if len(nums) > 1 else f"Slide {nums[0]}")
    if pages:
        nums = sorted(int(re.search(r"\d+", u.heading).group()) for u in pages if re.search(r"\d+", u.heading))
        parts.append(f"Page {nums[0]}-{nums[-1]}" if len(nums) > 1 else f"Page {nums[0]}")
    if others:
        parts.extend(u.heading for u in others)

    return ", ".join(parts)


def _infer_block_title(units: list[Unit], block_num: int) -> str:
    """推断知识块标题。优先取第一个有意义的标题。"""
    for u in units:
        if u.title and len(u.title) >= 2:
            return f"Knowledge Block {block_num}: {u.title}"
    # 回退：取第一个 unit 的正文首句
    for u in units:
        first_line = u.body.strip().split("\n")[0].strip()
        if first_line and len(first_line) >= 2:
            short = first_line[:60]
            return f"Knowledge Block {block_num}: {short}"
    return f"Knowledge Block {block_num}"


def _split_by_slide_page_merge(text: str) -> list[Block] | None:
    """策略二：解析 ## Slide/## Page → 智能合并。"""
    units = _parse_units(text)
    if units is None:
        return None
    return _merge_units_into_blocks(units)


# ============================================================
# 策略三：回退 — 按 ## 标题切分 + 同标题合并
# ============================================================

def _split_by_headings_fallback(text: str) -> list[Block]:
    """按 ## 标题切分，然后合并相同标题的连续块。"""
    parts = re.split(r"\n(?=##\s)", text)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return []

    merged: list[list[str]] = []
    current_group: list[str] = []
    current_title = ""

    for raw in parts:
        m = re.search(r"^##\s+(.+)$", raw, re.MULTILINE)
        title = m.group(1).strip() if m else ""

        if title and current_title and title == current_title:
            current_group.append(raw)
        else:
            if current_group:
                merged.append(current_group)
            current_group = [raw]
            current_title = title or ""

    if current_group:
        merged.append(current_group)

    blocks: list[Block] = []
    for i, group in enumerate(merged):
        m = re.search(r"^##\s+(.+)$", group[0], re.MULTILINE)
        title = m.group(1).strip() if m else f"知识块 {i + 1}"
        body = "\n\n".join(group)
        blocks.append(Block(
            index=i + 1,
            title=f"知识块 {i + 1}: {title}",
            text=body,
        ))

    return blocks


# ============================================================
# 主入口
# ============================================================

def split_into_blocks(raw_text: str) -> list[Block]:
    """
    将原始 PPT/PDF 提取文本切分为知识块列表。

    策略优先级:
      1. 手工 Knowledge Block 标记 → 直接按标记切分
      2. 自动 ## Slide N / ## Page N → 智能合并
      3. 回退 → 按 ## 标题切分 + 同标题合并

    目标输出: 每章 5-10 个知识块，避免一页/一幻灯片一个块。
    """
    text = _normalize(raw_text)
    if not text:
        return []

    # 策略一：手工知识块标记
    result = _split_by_manual_kb(text)
    if result is not None:
        return result

    # 策略二：Slide/Page 智能合并
    result = _split_by_slide_page_merge(text)
    if result is not None:
        return result

    # 策略三：回退按标题切分
    return _split_by_headings_fallback(text)
