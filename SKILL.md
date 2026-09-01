---
name: book-summarizer
description: "Summarizes a textbook (local PDF or knowledge base) into chapter-by-chapter markdown notes: numbered definitions/theorems/examples, proof sketches, KaTeX. Language: CN book→CN only; EN book→CN+EN; other→original+CN+EN. HARD REQUIREMENTS: (0) never copy OCR formulas directly — correct+rewrite; (1) no mojibake; (2) include ALL labeled/bare-numbered items and examples; (3) bold inline labels, not ### headings (gm-style books excepted: item titles stay as printed ###, see docs/writing-rules.md 编号项格式模板下的 gm 体例书条款). CN version annotates key terms with (English) from source text when available."
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
<corpus_root>\<书名>\       ← 每个书一个文件夹（corpus_root 见 user_config.json / README 配置章节）
  ├─ <书名>.pdf            ← 源 PDF（必须在此专属目录内，保留原名）
  ├─ _extract\              ← 提取目录：所有后台数据（page_*.json / chapter_map.json / figure_* / _mm_repair/）
  │   └─ book_structure\    ← 内容化分章契约 ch{N}.json（附录 appendix{X}.json）+ units\ch{N}\ 每 item 一单元的拆分目录（write-source 步骤 4）
  ├─ 第1章_章名.md           ← 中文版
  ├─ Chapter1_Name.md       ← 英文版（仅英文/他语种书时有）
  └─ ...
```

> **附录单元命名**：原书后部附录（结构契约章节点 `name` 含 `Appendix X`）按附录命名——英文 `AppendixX_Name.md`、中文 `附录X_中文名.md`（X=A..Z，取自契约名，不重排号）；`chapter_md_groups` / flow 物理证据均已识别该形态。内部标题体系照旧用原书序标（如 `## §E.5`、`**Proposition E.1**`）。

> **上下册 / 多册书**：PDF 与总结 md 均留在书级目录（`<书名>.pdf` 保持原位**原名不动**）；`_extract\` 内按册分子目录（`_extract\上册\`、`_extract\下册\`），各册提取数据（page_*.json / chapter_map.json / figure_* / _mm_repair/ 及 flow 账本 `.flow_gate.json`）落在对应册目录，由流水线 `--extract-dir` 指定（见 `flows/extract/extract.md` 分支 D）；每册的后续子流程与 flow_runner 操作均以 `<书目录>/_extract/<册>` 为该册 extract_dir。

> **临时文件隔离**：Agent 生成的所有临时脚本 / 日志必须放入 `_extract\`；根目录只允许 `.pdf`、`.md`、`_extract\` 三类。

## 首次使用配置（前置，prep 之前）

机器特定路径集中在 **skill 根目录 `user_config.json`**（gitignored，不随仓库上传；加载优先级：`BKS_*` env > `user_config.json` > 代码内置默认值；`lib/user_config.py` 统一读取，权重子路径由 `model_root` 派生，无需手配）。**首次使用（`user_config.json` 缺失或依赖路径失效）时，Agent 必须走下面流程，禁止静默使用内置默认值开工**：

1. 跑 `python lib/user_config.py status`，读 JSON 的 `resolved`（各键 `exists` 真假）与 `missing`（含 `default` / `discovered` 候选）。
2. 依赖探测：`missing` 为空 → 直接开工；非空 → 逐项**向用户提问**，顺序：先给 `discovered` 自动探测结果与内置 `default` 作选项 → 用户选已有目录或填新路径。
3. 依赖确实不存在（用户回答"没有"）→ **询问是否安装**：是 → 按 [`flows/prep/ref/environment.md`](flows/prep/ref/environment.md) 引导安装（conda 环境 + ModelScope 权重 + cudnn 对齐）；否 → 停在 prep，不强行继续。
4. 确认后把最终值写入 `user_config.json`（UTF-8），再进 prep。

> env 覆盖 `BKS_CORPUS_ROOT` / `BKS_MODEL_ROOT` / `BKS_CONDA_ENV_NAME` / `BKS_CONDA_ENV_PATH` / `BKS_PADDLEOCR_CACHE` 仅供脚本直调场景，交互式首次配置以写 `user_config.json` 为准。

## 主流程（Stage 0 → 3，唯一主干）

> 每个阶段是一个独立 `flows/<name>/<name>.md`（统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程）。点开链接看该阶段的完整规则与命令。通用校验 `verify` 是**顶层公用文档**（与 `flows` 并行，路径 `verify`），被 `write-source`（最终校验步骤 7；步骤 4 另有内容完整性闸门脚本）与 `derive-translate` 复用，不属于某个流程阶段。

| Stage | 流程 | 一句话 | 关键约束 |
|-------|------|--------|---------|
| 0 | [`prep`](flows/prep/prep.md) | 环境检查（conda pdfextract + torch CUDA） | — |
| 1 | [`extract`](flows/extract/extract.md) | 归位 PDF + 启动**后台**文本提取 + 轮询做 MM Repair，以 `_extraction_done.json` 收尾 | 防停滞（extract 规则1）；多册书逐册串行（extract 规则2）；视觉识别询问式全书一次（extract 规则3）；**MM Repair 门（extract/mm_repair 流程 规则1）** |
| 2 | [`write-source`](flows/write-source/write-source.md) | 步骤 1 **config 子流程**（chapter_map + `verify_config.json`）→ 步骤 2 **figure_detection 子流程**（图检测+分配）→ 步骤 3 **structure 子流程**（`build_structure` 按章**一步产出含内容的完整契约** `ch{N}.json`（层级嵌套小节 + description/proof/text/formula含tag/image 内容块）+ 🔴 章节/条目完整性查漏回填闸门，`gate.passed` 才放行；回填后自动重建该章内容）→ 步骤 4 **拆分单元**（纯脚本：内容完整性闸门 `check_content_completeness` + `split_draft_units` 拆出 `units/ch{N}/` 每 item 一单元目录）→ 步骤 5 **逐个按写作要求改好（agent 核心步）+ 强制门控**（agent **逐个改好每个单元**：写作要求全部在此落实（公式重写 / Tier 压缩 / 格式），并把首行 DRAFT→DONE → 🔴 `gate_units` 强制门控：每单元存在+DONE+**单元级质量校验通过**（公式闭合 / 无裸命令·裸 Unicode 字符·裸箭头（数学必须 KaTeX）/ 结构标签 / 无 OCR 残留，check_unit_quality.py 复用 katex_heuristics，判断标准是「写对」而非「重写」）才 exit 0（每个 item 都不漏））→ 步骤 6 **拼接**（`merge_units` 纯脚本机械执行，按 manifest 顺序合并全部单元成最终 `ChapterN_*.md` / `第N章_*.md` 并按 V-F 重建 `---` 分隔线，**无 agent 参与**；🔴 落账证据强制「逐单元改好+门控通过」：每章 gate 通过 + 契约骨架节/编号项在位，脱离单元 = mark 硬拒）→ 步骤 7 批量校验至 PASS | config 在 MM 修复后统一生成只一次（config_setting 步骤 1）；🔴 **图检测前必须 config 先行**；🔴 **structure 完整性闸门是拆分的硬闸（规则7）**；内容完整性闸门（描述/证明/图片/文字块齐备）在步骤 4；源语言优先（规则1）；拆章（规则3）；写源期间**禁逐章 verify（规则2）**；单元公式是 OCR 原样**严禁照抄**（步骤 5 重写校正）；单元不经 verify（初版全量保真） |
| 3 | [`derive-translate`](flows/derive-translate/derive-translate.md) | 据已校验源版派生翻译版并校验至 PASS（**仅英文书**：英文书→派生中文 `第N章_*.md`；**中文书无翻译阶段，本阶段整体跳过**） | 单向修复（derive-translate 规则4）；中英 1:1 同构（规则3） |

> 🔴 **写源硬闸（全阶段不可绕过）**：Stage 2 `write-source` 严禁在 MM Repair 的 `apply` 写回 `page_*.json` 完成前启动。验证标准：该章 `page_*.json` 含 `mm_repaired`/`mm_reviewed` 标记、且 `_mm_repair/manifest.json` 中该章对应页**每条目 `resolved == true`**。`manifest.status == "applied"` 因 `apply` 无条件设置而**不可作为完成判据**（会出现"已 applied 但大量未修"假绿）；`repairs.json` 有 resolved 条目 ≠ `apply` 已写回（前者只是中间产物，后者才是出口）。MM Repair 全流程与验证命令见 [`extract/mm_repair`](flows/extract/mm_repair/mm_repair.md) 出口条件；extract 出口 = `_extraction_done.json`（见 [`extract`](flows/extract/extract.md) 出口条件）。

## 🔒 流程强制顺序执行（flow_gate，死命令：上一步没做完不能进下一步）

所有 flow（prep → extract → write_source → derive）的步骤**严格有序、机械不可跳步**。
违规会被两层同时拦截：① `tools/flow_runner.py` 的顺序闸（flow 前置 + 同 flow 内顺序）；
② 关键加载器自断言上游（`make_config` / `ConfigLoader` / `mm_repair_apply` /
`build_structure` / `verify_chapter`）。机制、顺序、判据、标准工作流与**禁止清单**
见 [`flows/_flow_gate.md`](flows/_flow_gate.md)（唯一权威）。要点：

- `_extraction_done.json` 只能由 `mm_repair_apply.py` 在「条目全 resolved + 每页有
  mm 标记」**真完成时**写出；历史书用 `flow_runner.py bootstrap` 依物理证据补写，
  **禁止手 touch 冒充完成**。
- `make_config.py` 缺 `_extraction_done.json` 时**硬退出、绝不写退化默认文件**；
  生成的 `verify_config.json` 带 `_provenance` 戳，`ConfigLoader` 据此 + marker
  双重识别，**手写 config 再也无法被下游消费**。
- 推进步骤走 `python tools/flow_runner.py run <book_dir> <flow> <step>`；agent 步
  做完用 `verify` 复核 + `mark` 落账。**禁止手填账本、禁止手写/手改 config 绕过护栏。**

## 退出条件

**英文书：源语言（英文）+ 翻译版（中文）章数 == `chapter_map` 总章数，且两版均 `verify PASS + KaTeX OK`；中文书无翻译阶段，源语言（中文）章数 == `chapter_map` 总章数即达成**。唯一退出信号是"已写章数 == 总章数"，不得提前停。

## 核心脚本速查（路径相对 skill 根目录）

| 阶段 | 脚本 |
|------|------|
| 提取（文本） | `flows/extract/pipeline/script/extract_pipeline.py` · `launch_pipeline.sh` |
| 配置（write-source 步骤 1） | `config/verify_config/make_config.py`（生成 `verify_config.json`） |
| 图检测（write-source 步骤 2） | `flows/script/extract_figures` · `…/assign_figures.py` |
| 内容化 + 拆分（write-source 步骤 3–4） | `flows/write-source/structure/script/build_structure.py`（第 1 步一步产出含内容完整契约，描述信息 `description` 节点 + 条目文字/公式/图片内容块 + 证明 `proof` 子节点按 `sub_sec` 文档顺序挂入分章契约 `_extract/book_structure/ch{N}.json`（附录 `appendix{X}.json`），幂等可重跑；噪声过滤 / 行内公式拼接 / 标题剥离 / 行间公式 tag 键）+ `flows/write-source/script/split_draft_units.py`（步骤 4：由内容化契约拆出 `units/ch{N}/` 每 item 一单元目录 + `manifest.json`，首行 DRAFT 标记；渲染复用 `render_draft.py` 纯函数） |
| MM Repair | `flows/extract/mm_repair/script/mm_repair_audit.py` · `…/mm_repair_text_compare.py` · `…/mm_repair_apply.py` |
| 写作（步骤 5 改单元 + 步骤 6 拼接） | `flows/write-source/script/gate_units.py`（🔴 步骤 5 强制门控：每单元 DONE + **单元级质量校验通过**（check_unit_quality.py：公式闭合 / 无裸命令·裸 Unicode 字符·裸箭头（数学必须 KaTeX）/ 结构标签 / 无 OCR 残留，「写对」非「重写」）才 exit 0）+ `flows/write-source/script/merge_units.py`（🔴 步骤 6 纯脚本拼接：**自带强制门控**——拼接前先跑 gate_units，任一单元未改对即直接报错拒绝拼接；按 manifest 合并全部单元成最终 md，按 V-F 重建 `---` 分隔线，无 agent 参与）；格式化 CLI 工具 `tools/wrap_examples_bq` · `tools/fmt_proofs.py` · `verify/format_verify/script/check_katex.py`（KaTeX 检测，由 `verify/format_verify/` 提供）· `verify/format_verify/script/fix_katex.py`（KaTeX 修复，由 `verify/format_verify/` 提供；注：2026-08-28 起全层 `--fix` 默认禁用，须 `--fix --fix-force` 并通过 PREFLIGHT 围栏门才执行；独立 CLI 自 2026-09 起内置同款 PREFLIGHT 写回守卫）· `verify/script/audit_counts.py` · `tools/split_chapters.py`（注：源版「顶层例/证包裹进 `>` + 连续性」已由 verify 的 format_verify（F 层，原称 H/G 层）的 `h_mbq` 检测规则及 `{h,h_stmt,h_ul,h_mbq,c,g,…}` 系列 fixer 在 `--fix`（🔴 2026-08-28 起默认禁用，须 `--fix-force` + PREFLIGHT）自动兜底） |
| ~~嵌图~~ | **已删除**（2026-08-29）：图片经内容化分章契约 image 块随草稿继承（内容完整性闸门保证齐备）；`flows/script/embed_figures.py` 保留为其格式逻辑的来源参考 |
| 校验 | `verify/script/verify_chapter.py` · `config/ignore_chN/manage_ignore.py` |
| 公式对账 | Q 层（`verify/formula_tag/`，opt-in `formula` 配置）覆盖序标集合成员 + 序列顺序(ORDER_MISMATCH) + 小节定位(MISPLACED)；公式内容保真人工核对 |
| 结构修复（写源后 remediation） | `tools/restructure_by_ocr.py`：B 层报 ORDERING BLOCKING（条目被放错 §）时，以 OCR `page_*.json` 派生 item→section 真值图 + 贪心单调门把条目归位到源书真实 §（逐字保真、不编造）；先 report 模式核对移动项，确认后 `--apply` 写回（自动备份）。与 write-source「不得重排」规则互补：仅纠正确定性错节，不动正确顺序 |

各脚本的详细用途与各层 `--fix`（🔴 2026-08-28 起全层默认禁用，须 `--fix --fix-force` + PREFLIGHT）范围见 [`flows`](flows) 对应流程文档；通用校验文档（层级语义 / 顺序 / 字节契约）见 [`verify`](verify)。

## 代码位置（重要）

代码按流程组织在对应 `flows/<stage>/script/<pkg>/` 目录；通用校验 `verify` 的代码在技能根级 `verify`（与 `flows` 并行），每层一个 `<语义名>/` 子包（实现 `<snake>.py` + 子流程文档 `<snake>.md`，位于 `verify/<语义名>/`），注册表与总编排见 `verify/verify.md` 与各校验层子包 `verify/<语义名>/`：

- `flows/write-source/structure/script`（结构骨架 `scan_skeleton` + 编号项抽取 `extract_items*` + `build_structure` + `attach_content` 的 `build_chapter_contract` 内容挂载，按章产出含内容完整契约 `ch{N}.json`）· `flows/extract/pipeline/script` · `flows/extract/script`（共享库 `build_ocr`/`build_vakil_bundle`）。源侧查漏 + 混合回填由 `verify/script/check_structure_completeness.py` 负责。
- `flows/write-source/script`（`split_draft_units.py`：步骤 4 由内容化分章契约拆出每 item 一单元目录 `units/ch{N}/`；`gate_units.py`：步骤 5 agent 逐个改好单元后跑强制门控；`merge_units.py`：步骤 6 纯脚本按 manifest 顺序拼接单元成最终 md；`render_draft.py`：单元渲染库——纯渲染函数被 split/merge 复用，不再单独产出整章草稿）。
- `flows/extract/mm_repair/script`
- `flows/script`
- `tools`（生产期格式化 CLI 工具：`wrap_examples_bq` / `fmt_proofs` / `fmt_extras` / `split_chapters` / `proof_steps` / `_wrap_raw_math` 等；生产期格式化 CLI 工具集中于此处；其中格式修复类由 verify 的 H/G 等层在 `--fix`（🔴 2026-08-28 起默认禁用，须 `--fix --fix-force` + PREFLIGHT）兜底，编辑性变换（证明步骤编号 / `$$` 归一）仍以 CLI 工具保留）🔴 **`tools/` 只放通用、可跨书复用的工具**；特定书/章节的处理脚本（如硬编码某书路径的 `_diag_ch5.py` / `_dump_contract.py`）必须放进对应书的 `_extract/`，**不得留在本目录**。
- `verify`：通用校验引擎顶层包（`verify_chapter.py` 总编排、`register_all.py` 自动注册、`report.py` 字节输出；每个校验层一个 `<语义名>/` 子包，位于 `verify/<语义名>/`，含实现 `<snake>.py` 与子流程文档 `<snake>.md`）。
> ⚠️ **共享基础件定位（消除"extract 依赖 verify"错觉）**：`verify_config`（位于 `config/verify_config/`）与 `key_parse`（位于 `lib/key_parse.py`，已从 `verify/script/` 迁出）属跨流程**共用基础件**——extract、config 工具与 verify 均依赖，并非 verify 私有；extract 反向 import 它们属正常基础件复用，不构成流程耦合。`verify/script/gm_scan.py` 与 `verify/script/ordinal.py` 中的 `scan_gm_blocks` / `int_to_roman` 等是从 `flows/write-source/structure/script/extract_items_gm.py` **解耦复制**的纯函数副本，单一真源仍在 `extract_items_gm.py`，修改须同步两处。

- `data/<json_name>/`：每个中间产物 JSON **独占一个目录**（如 `data/chapter_map`、`data/figure_index`），内含 `<json_name>.md`（数据结构说明）+ `<json_name>.py`（模型类；统一基类 `JsonData` 位于 `data/lib/json_data.py`，chapter_map / figure_index / figure_embed_overrides / repairs 已接入，其余模型类暂为普通类——新增模型建议接入基类）；JSON 数据结构索引见 `data/data_schema.md`。各 JSON 的校验/编排脚本就近放在消费它的流程或 `verify` 层内，不在 `data`。
- `lib`：**公用方法与变量锚点**，保留在技能根目录，被所有包 import。当前含：
  - `boot.py`：统一引导机制（`setup()` 把根目录 + `lib` + `flows`/`verify`/`config`/`data` 四树下任意深度的 `script` 目录、以及 `data/` 与 `config/` 的每个直接子目录注入 `sys.path`）。
  - `user_config.py`：用户配置加载器（`user_config.json` + `BKS_*` env 覆盖 + 代码内置 `_DEFAULTS` 默认值；`weight_paths()` 由 `model_root` 派生 PDF-Extract-Kit 权重路径）。
  - `numbering.py` / `regexlib.py`：跨流程的编号、正则常量。
  - `util.py`：`chapter_of_page()` 等无状态小工具（集中提供，无状态、无第三方依赖，供各包按需 `from lib.util import ...` 调用）。
  - `figure_io.py`：`load_figure_index()`——`figure_index.json` 的统一读取（原 figure 包返回 `[]`、verify 包返回 `None`，已统一为 `[]`；verify 侧调用方仅做真值/迭代判断，行为一致）。
  - `normalize_math.py`：公式定界符修复库（`normalize()` / `fix_backticks()` / `stats()`）——纯函数、无第三方依赖，被格式 / 校验流水线按需 `from lib.normalize_math import ...` 调用。对应的命令行入口在 `tools/normalize_math_cli.py`（直接 `python tools/normalize_math_cli.py <files>` 改写文件，会写 `.bak_mathfix` 备份）。

各包仍用包名互相 `import`（如 `verify/section_continuity/script/section_continuity.py` → `from extract_items_gm import ...`）。为保证搬进嵌套目录后 import 不断，新增 **`lib/boot.py`**：每个入口脚本顶部有一段自包含引导——向上找到含 `SKILL.md` 的技能根，把根目录 + `lib` + 上述四树全部 `script` 目录与 `data/`、`config/` 直接子目录注入 `sys.path`，再 `import lib.boot; lib.boot.setup()`。因此**无论从哪个目录运行哪个脚本，包都能按名 import**，兄弟关系不再依赖物理同居。

约定：
- `flows/<stage>/script/README.md`：本流程脚本索引（真实代码已在该目录内）。
- `flows/<stage>/ref/`：本流程 SSOT 文档（格式 / 保真 / 校验层 / 图片流水线等）。
- `tools`：**命令行修复 / 维护工具**目录（直接 `python tools/<x>.py` 运行，自举把技能根注入 `sys.path`，与流水线脚本分离，不在 `flows` 或 `lib` 内）。
- 公用的工具 / 常量请放进 `lib`，不要在各包间重复定义。
