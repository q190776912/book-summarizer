---
name: book-summarizer
description: Summarizes a textbook (from local PDF or the agent's knowledge base) into chapter-by-chapter markdown files. Output language follows the textbook's language: Chinese text→CN only; English text→CN+EN; other languages→original+CN+EN. Each chapter gets numbered definitions/theorems/examples, proof sketches, and KaTeX. HARD REQUIREMENTS: (0) Never copy OCR formulas directly — correct+rewrite; (1) NO mojibake; (2) ALL labeled/bare-numbered items AND all examples must be included; (3) bold inline labels NOT ### headings (gm-体例书例外：条目标题按原书排印用 `###`，见 docs/writing-rules.md §2「NO Item-Headings」下的 gm 体例书例外条款). CN version annotates key terms with (English) from the source text when available, else translated.
---

# Book Summarizer

把一本教材转化成逐章结构化 markdown 总结（定义 / 定理 / 例题 + 证明梗概 + KaTeX），用于复习、参考或间隔重复。

## When to Use

用户想要：
- 把本地 PDF 教材总结成逐章笔记
- 从知识库中的书生成结构化 markdown（定义 / 定理 / 证明）
- 产出 KaTeX 友好的数学笔记

## 目录结构（书目录契约）

```
D:\study\book\<书名>\       ← 每个书一个文件夹
  ├─ <书名>.pdf            ← 源 PDF（必须在此专属目录内）
  ├─ _extract\              ← 提取目录：所有后台数据（page_*.json / chapter_map.json / figure_* / _mm_repair/）
  ├─ 第1章_章名.md           ← 中文版
  ├─ Chapter1_Name.md       ← 英文版（仅英文/他语种书时有）
  └─ ...
```

> **临时文件隔离**：Agent 生成的所有临时脚本 / 日志必须放入 `_extract\`；根目录只允许 `.pdf`、`.md`、`_extract\` 三类。

## 主流程（Stage 0 → 3，唯一主干）

> 每个阶段是一个独立 `flows/<name>/<name>.md`（统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程）。点开链接看该阶段的完整规则与命令。通用校验 `verify` 是**顶层公用文档**（与 `flows` 并行，路径 `verify`），被 `write-source`（步骤 3）与 `derive-translate` 复用，不属于某个流程阶段。

| Stage | 流程 | 一句话 | 关键约束 |
|-------|------|--------|---------|
| 0 | [`prep`](flows/prep/prep.md) | 环境检查（conda pdfextract + torch CUDA） | — |
| 1 | [`extract`](flows/extract/extract.md) | 归位 PDF + 启动**后台**文本提取 + 轮询做 MM Repair；文本出口后跑 **config 子流程**（生成 `verify_config.json`）→ **figure_detection 子流程**（图检测+分配）→ **structure 子流程**（合并产出 `book_structure.json` 结构契约书对象，全书批量生成） | 防停滞（extract 规则1）；chapter_map 早建只一次（extract/chapter_map 规则1）；公式调参；**MM Repair 门（extract/mm_repair 流程 规则1）**；🔴 **图检测前必须 config 先行**（extract 内部顺序）；🔴 structure 为 extract 末尾 Step 5（结构契约在写源前就绪）；写源前可跑校验层 `verify/script/check_structure_completeness.py` 做源侧查漏 + 混合回填 |
| 2 | [`write-source`](flows/write-source/write-source.md) | 按骨架契约写源语言初稿 + 嵌图，末尾（步骤 3）批量校验至 PASS | 源语言优先（write-source 规则1）；拆章（write-source 规则3）；写源期间**禁逐章 verify（write-source 规则2）** |
| 3 | [`derive-translate`](flows/derive-translate/derive-translate.md) | 据已校验源版派生翻译版并校验至 PASS | 单向修复（derive-translate 规则1）；中英 1:1 同构 |

## 退出条件

**源语言 + 翻译版章数 == `chapter_map` 总章数，且两版均 `verify PASS + KaTeX OK`**。唯一退出信号是"已写章数 == 总章数"，不得提前停。

## 核心脚本速查（路径相对 skill 根目录）

| 阶段 | 脚本 |
|------|------|
| 提取（文本） | `flows/extract/pipeline/script/extract_pipeline` · `launch_pipeline.sh` |
| 配置（extract 子流程） | `config/verify_config/make_config.py`（生成 `verify_config.json`） |
| 图检测（extract 子流程） | `flows/script/extract_figures` · `…/assign_figures.py` |
| MM Repair | `flows/extract/mm_repair/script/mm_repair_audit.py` · `…/mm_repair_text_compare.py` · `…/mm_repair_apply.py` |
| 写作 | 消费 extract 阶段由 `build_structure` 生成的 `book_structure.json` 书对象（写作契约，不再重跑抽取器）；格式化 CLI 工具 `tools/wrap_examples_bq` · `tools/fmt_proofs.py` · `verify/format_verify/script/check_katex.py`（KaTeX 检测，已并入 verify）· `verify/format_verify/script/fix_katex.py`（KaTeX 修复，已并入 verify，`verify --fix` 自动调用）· `verify/script/audit_counts.py` · `tools/split_chapters.py`（注：源版「顶层例/证包裹进 `>` + 连续性」已由 verify 的 H 层 `h_mbq` + G 层在 `--fix` 自动兜底） |
| 嵌图 | `flows/script/embed_figures` |
| 校验 | `verify/script/verify_chapter.py` · `config/ignore_chN/manage_ignore.py` |
| 公式对账 | Q 层（`verify/formula_tag/`，opt-in `formula` 配置）覆盖序标集合成员 + 序列顺序(ORDER_MISMATCH) + 小节定位(MISPLACED)；公式内容保真人工核对 |

各脚本的详细用途与各层 `--fix` 范围见 [`flows`](flows) 对应流程文档；通用校验文档（层级语义 / 顺序 / 字节契约）见 [`verify`](verify)。

## 代码位置（重要）

代码按流程组织在对应 `flows/<stage>/script/<pkg>/` 目录；通用校验 `verify` 的代码在技能根级 `verify`（与 `flows` 并行），每层一个 `<语义名>/` 子包（实现 `<snake>.py` + 子流程文档 `<snake>.md`，位于 `verify/<语义名>/`），注册表与总编排见 `verify/verify.md` 与各校验层子包 `verify/<语义名>/`：

- `flows/extract/structure/script`（结构骨架 `scan_skeleton` + 编号项抽取 `extract_items*` + `build_structure`，合并产出 `book_structure.json` 书对象）· `flows/extract/pipeline/script` · `flows/extract/script`（共享库 `build_ocr`/`build_vakil_bundle`）。源侧查漏 + 混合回填由 `verify/script/check_structure_completeness.py` 负责。
- `flows/extract/mm_repair/script`
- `flows/script`
- `tools`（生产期格式化 CLI 工具：`wrap_examples_bq` / `fmt_proofs` / `fmt_extras` / `split_chapters` / `proof_steps` / `_wrap_raw_math` 等；原 `flows/write-source/script` 已并入此处；其中格式修复类由 verify 的 H/G 等层在 `--fix` 兜底，编辑性变换（证明步骤编号 / `$$` 归一）仍以 CLI 工具保留）
- `verify`：通用校验引擎顶层包（`verify_chapter.py` 总编排、`register_all.py` 自动注册、`report.py` 字节输出；每个校验层一个 `<语义名>/` 子包，位于 `verify/<语义名>/`，含实现 `<snake>.py` 与子流程文档 `<snake>.md`）。
- `data/<json_name>/`：每个中间产物 JSON **独占一个目录**（如 `data/chapter_map`、`data/figure_index`），内含 `<json_name>.md`（数据结构说明）+ `<json_name>.py`（模型类，继承 `data/lib/json_data.py` 基类）；JSON 数据结构索引见 `data/data_schema.md`。各 JSON 的校验/编排脚本就近放在消费它的流程或 `verify` 层内，不在 `data`。
- `lib`：**公用方法与变量锚点**，保留在技能根目录，被所有包 import。当前含：
  - `boot.py`：统一引导机制（`setup()` 把根目录 + `lib` + 所有 `flows/*/script`、`verify`（含各校验层 `<语义名>/` 子包）、`config/**/script`、`data/**/script` 注入 `sys.path`）。
  - `config.py` / `numbering.py` / `regexlib.py`：跨流程的配置、编号、正则常量。
  - `util.py`：`chapter_of_page()` 等无状态小工具（原在 figure 包内两处字节级重复，已上提）。
  - `figure_io.py`：`load_figure_index()`——`figure_index.json` 的统一读取（原 figure 包返回 `[]`、verify 包返回 `None`，已统一为 `[]`；verify 侧调用方仅做真值/迭代判断，行为一致）。
  - `normalize_math.py`：公式定界符修复库（`normalize()` / `fix_backticks()` / `stats()`）——纯函数、无第三方依赖，被格式 / 校验流水线按需 `from lib.normalize_math import ...` 调用。对应的命令行入口在 `tools/normalize_math_cli.py`（直接 `python tools/normalize_math_cli.py <files>` 改写文件，会写 `.bak_mathfix` 备份）。

各包仍用包名互相 `import`（如 `verify/section_continuity/script/section_continuity.py` → `from extract_items_gm import ...`）。为保证搬进嵌套目录后 import 不断，新增 **`lib/boot.py`**：每个入口脚本顶部有一段自包含引导——向上找到含 `SKILL.md` 的技能根，把根目录 + `lib` + 所有 `flows/*/script` 与 `verify/**/script` 注入 `sys.path`，再 `import lib.boot; lib.boot.setup()`。因此**无论从哪个目录运行哪个脚本，包都能按名 import**，兄弟关系不再依赖物理同居。

约定：
- `flows/<stage>/script/README.md`：本流程脚本索引（真实代码已在该目录内）。
- `flows/<stage>/ref/`：本流程 SSOT 文档（格式 / 保真 / 校验层 / 图片流水线等）。
- `tools`：**命令行修复 / 维护工具**目录（直接 `python tools/<x>.py` 运行，自举把技能根注入 `sys.path`，与流水线脚本分离，不在 `flows` 或 `lib` 内）。
- 公用的工具 / 常量请放进 `lib`，不要在各包间重复定义。
