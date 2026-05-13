# PPT 学习笔记生成器

将 PPT / PDF / Markdown / TXT 学习资料按**知识块**生成结构化中文学习笔记。

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
│   └── text_splitter.py      ← 知识块切分器（三层策略）
├── requirements.txt          ← Python 依赖
└── .codex/
    └── ppt_skill.txt         ← 交互式系统 prompt
```

## 工作流

```
原始素材                      提取后的 Markdown              结构化笔记
────────────────────────────────────────────────────────────────────
input/chapter4.pdf    ──┐
input/chapter4.pptx   ──┤
input/chapter4.md     ──┤   extracted/chapter4.md
input/chapter4.txt    ──┘         │
                                  ▼
                          text_splitter.py  ──► 按知识块智能切分
                                  │
                                  ▼
                          build_notes.py    ──► output/final_notes.md
                              （调用 LLM 逐块总结 + 整章总结）
```

未来扩展：`final_notes.md` → docx / pdf 导出。

## 环境准备

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

依赖：
- `anthropic` — Anthropic Claude API
- `openai` — DeepSeek（OpenAI-compatible API）
- `python-pptx` — PPTX 文本提取
- `pypdf` — PDF 文本提取

### 2. 设置 LLM Provider

支持两种 LLM 后端：**Anthropic Claude** 和 **DeepSeek**。

#### 方式 A：Anthropic Claude

```bash
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."

# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

可选指定模型（默认 `claude-sonnet-4-6`）：

```bash
export ANTHROPIC_MODEL="claude-opus-4-7"
```

#### 方式 B：DeepSeek

```bash
# macOS / Linux
export LLM_PROVIDER="deepseek"
export DEEPSEEK_API_KEY="sk-..."

# Windows PowerShell
$env:LLM_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = "sk-..."
```

可选指定模型（默认 `deepseek-v4-flash`）：

```bash
export DEEPSEEK_MODEL="deepseek-v4-pro"
```

DeepSeek 使用 OpenAI-compatible API，默认 base_url 为 `https://api.deepseek.com`，可通过 `DEEPSEEK_BASE_URL` 覆盖。

#### 切换 Provider

除了环境变量，也可通过 `--provider` 命令行参数切换：

```bash
# 用 DeepSeek 生成笔记
python scripts/build_notes.py --input extracted/chapter4.md --provider deepseek

# 用 Anthropic Claude 生成笔记
python scripts/build_notes.py --input extracted/chapter4.md --provider anthropic
```

## 使用说明

### 第一步：提取内容

将原始文件（PDF / PPTX / MD / TXT）放入 `input/`，运行提取：

```bash
# 从 PPTX 提取（逐幻灯片：标题 + 文本框 + 备注）
python scripts/extract_content.py --input input/chapter4.pptx

# 从 PDF 提取（逐页文本）
python scripts/extract_content.py --input input/chapter4.pdf

# 从 Markdown 提取（编码规范化）
python scripts/extract_content.py --input input/chapter4.md

# 从纯文本提取
python scripts/extract_content.py --input input/chapter4.txt

# 自定义输出路径
python scripts/extract_content.py --input input/chapter4.pptx -o extracted/my_notes.md
```

**支持格式**：

| 格式 | 行为 |
|------|------|
| `.pptx` | 逐幻灯片提取标题、文本框、备注 → `## Slide N` |
| `.pdf` | 逐页提取文本 → `## Page N` |
| `.md` | 编码规范化（UTF-8），复制到 `extracted/` |
| `.txt` | 编码规范化，自动补章节标题 |

无法提取文本的页面/幻灯片自动插入占位提示。

### 第二步：生成笔记

```bash
# 默认读取 extracted/ 下第一个 .md 文件
python scripts/build_notes.py

# 指定提取后的文件
python scripts/build_notes.py --input extracted/chapter4.md

# 自定义输出路径
python scripts/build_notes.py --input extracted/chapter4.md -o output/my_notes.md

# 仅预览切块结果（不调 LLM，验证切分质量）
python scripts/build_notes.py --input extracted/chapter4.md --dry-run

# 仅导出 prompt（不需要 API Key，手动处理）
python scripts/build_notes.py --input extracted/chapter4.md --save-prompts

# 强制重新生成（忽略 LLM 缓存）
python scripts/build_notes.py --input extracted/chapter4.md --no-cache

# 指定模型
python scripts/build_notes.py --input extracted/chapter4.md --model claude-opus-4-7
```

### 完整工作流示例

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 从 PPTX 课件提取文本
python scripts/extract_content.py --input input/chapter4.pptx

# 3. 预览知识块切分效果
python scripts/build_notes.py --input extracted/chapter4.md --dry-run

# 4. 确认切分合理后，生成最终笔记

# 使用 DeepSeek（推荐国内用户）
# PowerShell:
$env:LLM_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = "sk-..."
# Bash:
export LLM_PROVIDER="deepseek"
export DEEPSEEK_API_KEY="sk-..."

python scripts/build_notes.py --input extracted/chapter4.md

# 或使用 Anthropic Claude
export ANTHROPIC_API_KEY="sk-ant-..."
python scripts/build_notes.py --input extracted/chapter4.md --provider anthropic

# 结果：output/final_notes.md
```

## 输出结构

`output/final_notes.md` 包含：

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

## 知识块切分原理

`text_splitter.py` 采用三层策略：

| 优先级 | 策略 | 触发条件 |
|--------|------|---------|
| 1 | 手工标记 | 文本包含 `## Knowledge Block N` / `## 知识块 N` / `## Block N` |
| 2 | 智能合并 | 文本包含 `## Slide N` / `## Page N`（自动提取产物） |
| 3 | 标题切分 | 回退到 `##` 标题 + 同标题合并 |

策略 2 的核心逻辑：
- 解析所有 Slide/Page 为单元（提取标题、统计字数）
- 按规则判断合并/拆分：短碎片合并、同标题合并、延续格式合并、新主题拆分
- 目标输出 5-10 个知识块（二遍合并控制上限）

## 缓存机制

LLM 结果缓存到 `output/.cache/`（每个知识块一个文件）。再次运行自动跳过已处理块。删除该目录或使用 `--no-cache` 强制重新生成。

## 扩展

- **新增提取格式**：在 `scripts/extract_content.py` 中实现 `BaseExtractor` 子类
- **换 LLM 提供方**：在 `scripts/llm_client.py` 中实现 `LLMClient` 子类
- **自定义切块逻辑**：修改 `scripts/text_splitter.py` 中的合并规则
- **导出 docx / pdf**：在 `scripts/` 下新增导出模块，接入 `assemble_output()` 输出
