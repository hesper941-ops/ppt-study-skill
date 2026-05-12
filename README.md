# PPT 学习笔记生成器

将 PPT/PDF/文本按**知识块**生成结构化中文学习笔记。

## 目录结构

```
├── input/                    ← 原始素材（.pdf / .pptx / .md / .txt）
├── extracted/                ← 提取后的统一 Markdown（中间产物）
├── output/                   ← 最终学习笔记 + 缓存
│   ├── final_notes.md        ← 最终输出
│   ├── .cache/               ← LLM 块级缓存（可安全删除）
│   └── prompts/              ← --save-prompts 导出的 prompt 文件
├── prompts/
│   ├── block_summarize.md    ← 知识块总结 prompt
│   └── chapter_summary.md    ← 整章总结 prompt
├── scripts/
│   ├── extract_content.py    ← 内容提取（PDF/PPTX/MD/TXT → Markdown）
│   ├── build_notes.py        ← 笔记生成（Markdown → 结构化学习笔记）
│   ├── llm_client.py         ← LLM 客户端（Anthropic / 可替换）
│   └── text_splitter.py      ← 知识块切分器
└── .codex/
    └── ppt_skill.txt         ← 交互式系统 prompt
```

## 工作流

```
原始素材                    提取后的 Markdown            结构化笔记
──────────────────────────────────────────────────────────────────
input/chapter4.pdf    ──┐
input/chapter4.pptx   ──┤
input/chapter4.md     ──┤    extracted/chapter4.md
input/chapter4.txt    ──┘         │
                                  ▼
                         build_notes.py ──────► output/final_notes.md
                             （知识块总结）
```

未来扩展：`final_notes.md` → docx / pdf 导出。

## 环境准备

### 1. 安装依赖

```bash
pip install anthropic python-pptx pypdf
```

- `anthropic` — LLM 笔记生成
- `python-pptx` — PPTX 提取
- `pypdf` — PDF 提取

### 2. 设置 API Key（仅在运行笔记生成时需要）

```bash
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."

# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

## 使用说明

### 第一步：提取内容

将原始文件（PDF / PPTX / MD / TXT）放入 `input/`，运行提取：

```bash
# 从 PDF 提取
python scripts/extract_content.py --input input/chapter4.pdf

# 从 PPTX 提取
python scripts/extract_content.py --input input/chapter4.pptx

# 从 Markdown 提取（编码规范化）
python scripts/extract_content.py --input input/chapter4.md

# 自定义输出路径
python scripts/extract_content.py --input input/chapter4.pdf -o extracted/my_notes.md
```

**提取行为**：

| 格式 | 行为 |
|------|------|
| `.md` / `.txt` | 编码规范化（UTF-8），复制到 `extracted/` |
| `.pdf` | 逐页提取文本，添加 `## Page N` 标记 |
| `.pptx` | 逐幻灯片提取标题、文本框、备注，添加 `## Slide N` 标记 |

对于无法提取文本的页面/幻灯片，自动插入占位提示：
> [This page may contain images, charts, or non-extractable content.]

### 第二步：生成笔记

```bash
# 默认读取 extracted/ 下第一个 .md 文件
python scripts/build_notes.py

# 指定提取后的文件
python scripts/build_notes.py --input extracted/chapter4.md

# 自定义输出路径
python scripts/build_notes.py --input extracted/chapter4.md -o output/chapter4_notes.md

# 仅预览切块结果（不调 LLM）
python scripts/build_notes.py --input extracted/chapter4.md --dry-run

# 仅导出 prompt 文件（不需要 API Key）
python scripts/build_notes.py --input extracted/chapter4.md --save-prompts

# 忽略缓存，强制重新生成
python scripts/build_notes.py --input extracted/chapter4.md --no-cache
```

### 完整工作流示例

```bash
# 1. 从 PPTX 课件提取文本
python scripts/extract_content.py --input input/chapter4.pptx

# 2. 预览知识块切分
python scripts/build_notes.py --input extracted/chapter4.md --dry-run

# 3. 生成最终笔记
python scripts/build_notes.py --input extracted/chapter4.md

# 结果：output/final_notes.md
```

## 输出结构

生成的 `output/final_notes.md` 包含：

**每个知识块**（按主题归并，不逐页复述）：
- 这一块讲什么
- 核心内容
- 你要真正记住的点
- 小结
- 考试角度
- 例题与解题步骤（如有）

**整章总结**：
- 整章主线
- 重点知识块
- 高频考点
- 易错点
- 考前速记提纲

## 技术说明

### 知识块切分

`text_splitter.py` 按以下优先级切分：
1. 显式 `## Knowledge Block N` 标记（推荐在提取文本中手动标注）
2. 幻灯片/页分隔符（`## Slide N` / `## Page N` / `第N页`）
3. Markdown 标题（`##`）

同一标题的连续内容自动合并，短碎片智能归并。

### 缓存机制

LLM 结果缓存到 `output/.cache/`。再次运行自动跳过已处理的块。删除该目录或使用 `--no-cache` 可强制重新生成。

### 扩展

- **换 LLM 提供方**：在 `scripts/llm_client.py` 中新增 `LLMClient` 子类
- **新增提取格式**：在 `scripts/extract_content.py` 中新增 `BaseExtractor` 子类
- **自定义切块逻辑**：修改 `scripts/text_splitter.py`
- **导出 docx/pdf**：在 `scripts/` 下新增导出模块，接入 `assemble_output()` 的输出
