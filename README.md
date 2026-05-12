# PPT 学习笔记生成器

将 PPT/PDF 提取文本按**知识块**生成结构化中文学习笔记。

## 目录结构

```
├── input/                    ← 放入 PPT/PDF 提取文本（.md / .txt）
├── output/                   ← 生成的笔记 + 缓存
│   ├── final_notes.md        ← 最终输出
│   ├── .cache/               ← 各块 LLM 结果缓存（可安全删除）
│   └── prompts/              ← --save-prompts 模式下导出的 prompt
├── prompts/
│   ├── block_summarize.md    ← 知识块总结 prompt 模板
│   └── chapter_summary.md    ← 整章总结 prompt 模板
├── scripts/
│   ├── build_notes.py        ← 主编排脚本（入口）
│   ├── llm_client.py         ← LLM 客户端（Anthropic / 可替换）
│   └── text_splitter.py      ← 知识块切分器
└── .codex/
    └── ppt_skill.txt         ← 交互式系统 prompt（供 Codex 模式使用）
```

## 快速开始

### 1. 安装依赖

```bash
pip install anthropic
```

### 2. 设置 API Key

```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."

# 可选：指定模型（默认 claude-sonnet-4-6）
export ANTHROPIC_MODEL="claude-sonnet-4-6"
```

### 3. 放入提取文本

将 PPT 或 PDF 提取后的文本保存为 `.md` 或 `.txt`，放到 `input/` 目录。

默认读取 `input/chapter4.md`（可通过参数指定其他文件）。

### 4. 生成笔记

```bash
# 默认读取 input/chapter4.md
python scripts/build_notes.py

# 指定输入文件
python scripts/build_notes.py input/chapter3.md

# 自定义输出路径
python scripts/build_notes.py -o output/chapter3_notes.md

# 查看效果不调 LLM（仅预览切块）
python scripts/build_notes.py --dry-run

# 仅导出 prompt 文件，手动处理（不需要 API Key）
python scripts/build_notes.py --save-prompts

# 强制重新生成（忽略缓存）
python scripts/build_notes.py --no-cache
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

## 工作原理

```
源文件 (input/chapter4.md)
    │
    ▼
[text_splitter]  按幻灯片标记 / 标题切分，合并同主题块
    │
    ▼
[llm_client]     逐块调用 Claude API 生成总结（结果缓存到 .cache/）
    │
    ▼
[llm_client]     根据所有块总结，生成整章总结
    │
    ▼
[assemble]       拼接为 output/final_notes.md
```

## 缓存机制

每次 LLM 调用的结果会缓存到 `output/.cache/`。再次运行时会自动跳过已处理的块，只处理失败的或新增的块。

- 删除 `output/.cache/` 目录可强制全部重新生成
- 也可用 `--no-cache` 参数

## 扩展

- **换 LLM 提供方**：在 `scripts/llm_client.py` 中新增 `LLMClient` 子类
- **自定义切块逻辑**：修改 `scripts/text_splitter.py`
- **导出 docx/pdf**：在 `scripts/` 下新增导出模块，调用 `assemble_output()` 的输出
