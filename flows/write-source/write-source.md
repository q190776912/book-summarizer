# Flow: write-source（源语言总结 / Stage 2）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
承接 extract 阶段（MM Repair 完成）之后的**全部写作前置与产出**：依次跑 **config 子流程**（chapter_map + `verify_config.json`）→ **figure_detection 子流程**（图检测 + 分配）→ **structure 子流程**（生成结构契约 + 🔴 完整性闸门）→ **拆分基本总结单元**（内容化分章契约 + 内容完整性闸门 + 拆分为每 item 一单元的 `units/ch{N}/` 目录）→ **agent 逐个按写作要求改好每个单元**（🔴 强制门控确保每个 item 都不漏）→ **脚本拼接**（`merge_units.py` 纯机械执行，无 agent 参与）写出**源语言**章节总结（英文书 = 英文 `ChapterN_*.md`；中文书 = 中文 `第N章_*.md`）→ 批量校验。

> 🔴 **2026-08-31 流程重构（单元化）**：原「整章草稿 `draft_ch{N}.md` → agent 基于整章草稿逐章调整」被**「每 item 一单元目录 `units/ch{N}/` → agent 逐个改好（`gate_units.py` 强制门控）→ `merge_units.py` 拼接」**取代——根治 agent「不按照草稿总结来总结」的问题：单元拆细后每个编号项都必须单独改好，门控机械核对每个单元（存在 + DONE + 内容改写）一个不漏，拼接脚本按 V-F 规则重建 `---` 分隔线。
> 🔴 **2026-08-29 流程重构**：原 extract 阶段的 Step 4–6（config / figure_detection / structure + 内容化分章契约）全部移入本流程——**结构完整性（章节 / 定理定义等缺项查漏回填）闸门必须在单元拆分之前完整通过**，然后脚本拆出基本总结单元（**完整性由脚本保证**：内容完整性闸门校验描述信息 / 证明 / 图片 / 文字公式块齐备），agent 在单元基础上按 writing-rules 修改（聚焦公式与数学变量渲染正确、证明与描述按写作要求），最后完整校验一次。

## 前置
- 🔴 **extract 阶段出口 = 写源硬闸（不可绕过）**：`_extraction_done.json` 已写出——该章页码区间对应的 `page_*.json` **必须已经过 `mm_repair_apply` 写回**（条目含 `mm_repaired`/`mm_reviewed` 标记、`_mm_repair/manifest.json` 中该章对应页的**每条目 `resolved == true`**），该章无未 resolved 的待修条目，否则**严禁写任何章节**。"`_mm_repair/repairs.json` 有 resolved 条目" ≠ "apply 已写回"——前者只是 agent 视觉补全的**中间产物**，后者才是出口。`manifest.status == "applied"` **不可信**（apply 无条件设置），验证须看 `page_*.json` 标记 + 条目级 resolved 计数，详见 [`extract/mm_repair/mm_repair.md`](../extract/mm_repair/mm_repair.md) 出口条件。启动本流程前**必须先用**该文档的「如何验证 apply 已写回」命令确认写回真实发生。
- 已知该书的源语言（英文书源语言为英文版，中文书源语言为中文版）。

## 步骤（有序）
1. **config 子流程（chapter_map + 书级配置）**
   - 🔴 **真正的门控是「MM Repair 完成」，不是「文本 100% 落盘」**：先建章节映射 `_extract/chapter_map.json`（步骤 1，全书只此一份、不重复生成），再依据修复后的 `page_*.json` 一次性生成 `_extract/verify_config.json`（编号形态 / 语言 / `formula` map / `ordinal` 里的 Figure 组）。`formula` map 与乱码文本依赖模式 A（若启用）校正后的 `page_*.json`；仅观察到文本 100% 落盘（或后台 `Pipeline finished.` 日志 / 仅靠 `_extraction_done.json` 存在）就提前跑 config，会得到基于未修复页的错误配置。
   - 🔴 **图检测之前必须完成此步**：图检测严格读 `ordinal` 的 Figure 组（图号前缀 `name` + 段数 `type`），缺 Figure 组则退化默认前缀，自定义图号书（Scheme / Illustration 等）会漏识。
2. **figure_detection 子流程（图检测 + 分配）**
   - 运行 **figure_detection 子流程** [`figure_detection`](figure_detection/figure_detection.md)：全本书 DocLayout-YOLO 检测 + `图X.X.X` 分配，产出 `figure_detect.json` + `figure_index.json` + `figure/` 裁剪图。书若无图可跳过本步。
3. **structure 子流程（完整契约一步产出 + 🔴 完整性闸门）**
   - 运行 **structure 子流程** [`structure`](structure/structure.md)：`build_structure` **一步**产出含全部正文内容的完整分章契约 `ch{N}.json`（附录 `appendix{X}.json`；章节按层级嵌套 → 条目/练习递归，携带 `description` / `proof` / `text` / `formula`（含 `tag`）/ `image` 内容块），作为写作契约与 verify 的编号项基准（合一）。
   - 随后按 structure 子流程第 2–4 步做**章节 / 定理定义等缺项的查漏回填与闸门**：章节漏用 D 层、条目漏用 B 层检，`readable` 项自动回填、`needs_agent` 项人工回填，**重跑至 `gate.passed == true`**。
   - 🔴 **本步是步骤 4 的硬闸**：`gate.passed != true` 严禁拆分单元——否则漏抓的编号项不会出现在总结里。只有 `gate.passed == true` 才允许进入步骤 4。
4. **拆分基本总结草稿为「每 item 一单元」目录（全书批量，纯脚本）**
   - 本步 = **拆分（脚本机械执行）**：把整章草稿细分为每 item 一单元的目录
     `units/ch{N}/`，供步骤 5 agent 逐个改写。agent 的全部写作工作在**步骤 5**
     完成；本步无需 agent 参与。
   - 🔴 **内容完整性闸门**（完整契约已由步骤 3 产出，本步只校验 + 拆分）：
     ```bash
     python verify/script/check_content_completeness.py "<extract_dir>" [ch ...]
     ```
     确定性复算比对（`attach_content.build_chapter_contract` 纯函数重建 vs 磁盘契约，公式块按 latex + display + **tag** 比对）+ 图片独立真值比对（`figure_index.json` 每张图必须在契约中）+ **公式序标独立真值比对**（`page_*.json` 中独立成块的 `(C.N)` 编号须在契约中“被交代”：挂上 tag 为正常；仍在正文 → WARN 待调；既无 tag 也无该文本 → FAIL）+ 证明覆盖审计。**FAIL 严禁进入拆分**——初始总结的完整性由脚本输出直接得到保证。
     ⚠️ **别把「复算比对 PASS」当成「内容没漏」**：该项是同管线自证，只能发现「磁盘与管线不一致」；管线本身漏抓的内容只有独立真值项（图片 / 公式序标）能发现。
   - 🔴 **拆分单元（取代整章草稿 draft_ch{N}.md，2026-08-31 起）**：
     ```bash
     python flows/write-source/script/split_draft_units.py "<extract_dir>" [ch ...]
     ```
     由内容化分章契约 `ch{N}.json` **拆出按写作顺序排列的单元目录**
     `<extract_dir>/book_structure/units/ch{N}/`——**每个单元一个独立 md 文件**：
       * `chapter` 单元：`# 章标题`；
       * `section` 单元：`## §…` 标题行（其下描述 / 编号项各为独立单元）；
       * `desc` 单元：描述散文（章首序言 / 节导语 / 条目尾随段，无标题纯段落）；
       * `item` 单元：**单个编号项**（定义 / 定理 / 例等，含其内部 proof 子节点）。
     文件名 `NNNN_<type>.md`（`0001`、`0002` … 写作顺序，4 位零填充防超千单元），另附 `manifest.json`
     （单元序列 + 类型 / key / 内容指纹）。每个单元文件**首行为 HTML 标记**
     `<!-- book-summarizer DRAFT unit: … -->`——agent 改好后须把 `DRAFT` 改为
     `DONE`，门控据此判定「已处理」。
     🔴 **单元全量保真、零压缩（硬契约）**：契约里多少内容块，单元就写多少——
     证明与描述信息逐块原样输出，**不摘要化、不跳步、不按 Tier 压缩、不因长度截断**
     （唯一例外是章末集中习题块 `consolidated=true` 按习题收录规则省略）。证明块
     标签用 `> **证明**：` / `> **Proof**:`（完整证明）而非 `证明思路`。Tier 1/2/3
     只压**表述**、不删内容，且**只发生在步骤 5 的调整（agent 改单元时）**，绝不在
     拆分器内。
     单元排版：证明 `> **证明**：…` 块引用（**完整证明原文**，不压成步骤）+ 描述
     独立成段 + 图片按**原嵌图格式**（flex div + `<img>`，例块内整体 `>` 前缀）+
     `line_start`/`indent` 缩进带分段 + 章末集中习题块（`consolidated`）省略。
     **内容仍为 OCR 原文（初版保留完整信息）**：公式须逐条重写、证明须压缩为编号
     步骤、Tier 压缩与英文标注在调整时执行。🔴 **单元文件不经 verify、也不受任何
     校验层约束**——verify 全部 8 层（含 P 层冗长/反照抄闸门）只挂在本流程最终校验
     （步骤 7），作用于 agent 调整后拼接的最终 md；单元上的 verbose/序标/裸算符类
     告警均为预期现象（初版全量保真所致）。页眉 / 页脚 / 版权行 / 页码已由
     `attach_content` 尽力过滤，条目正文开头与契约 `name` 重复的印刷标题已剥离。
   - 单元是「逐单元调整 + 强制门控 + 拼接」的**底稿**，不是成品——单元留存于
     `_extract/book_structure/units/ch{N}/`，最终 md 落书根目录。
5. **agent 逐个按写作要求改好每个单元 + 强制门控（agent 核心步）**
   - 本步 = **agent 逐个改写单元（写作要求在此全部落实）+ 门控**：agent 的全部
     写作工作都在本步完成——每个单元按 writing-rules 改好后置 `DONE`，第 6 步
     只是纯脚本拼接，**不再需要 agent 参与**。
   - **(a) 🔴 agent 逐个打开 `units/ch{N}/` 下每个单元文件**，以该单元为底稿，
     书写严格遵循 [`docs/writing-rules.md`](../../docs/writing-rules.md)（**写源阶段
     唯一必读规则文档 / SSOT**）改好该单元，**并把首行 `DRAFT` 标记改为 `DONE`**。
     初版总结的完整性已由脚本输出 + 内容完整性闸门保证（描述信息 / 证明 / 图片 /
     文字公式块齐备），调整聚焦两件事——**公式与数学变量渲染正确**（OCR 原样必须
     重写校正）与**证明、描述信息按写作要求呈现**（Tier 压缩 / 编号步骤）：
     - 公式逐条重写校正（硬要求）：`$...$` / `$$...$$` 公式是 OCR（UniMERNet）
       原样输出——🔴 **严禁直接照抄**，须读懂语义后按学科知识重写为正确 KaTeX
       （含归一 `{ \begin{array}` 类噪声）；公式序标（Q 层）照 writing-rules 校对，
       书无号不编造。
     - 内容清理与保真：剔除残余 OCR 噪声（乱码重复片段、证明结尾框「口」、图注
       文字、跨页粘连）；正文存疑处回归 `page_*.json` 原文核对（按节点
       `page_start..page_end` 经 `data/page_json/page_json.py` 适配器读取）。随后
       按 Tier 1/2/3 分级压缩**表述**（定义 / 定理 / 例题题面 / 证明梗概的保真硬
       底线不变），**不得省略任何契约编号项**。
     - 🔴 **Tier 只压表述、不删内容**：三档分级决定"写得多紧凑"，**不决定"这段留
       不留"**——Tier 2 描述性内容须守「三不删」（不删数学对象 / 不删任何公式 /
       不删概念名）且**不得整段删除**源段落；Tier 3 推导过程压成 `1. 2. …` 核心
       步骤时，每步一句话、**跳步不得跳过关键变量替换或关键等式**（详见
       `docs/writing-rules.md` 保真分级硬性要求 7 / 8，那是唯一权威）。**证明与描述
       信息不得因"太长"而丢信息**——宁可保留完整推导，也不要删掉步骤。
     - 格式落地：编号项格式模板（粗体标签 / 例块 `>` 包裹 / 证明思路块引用）、
       `## §` 标题体系（无序号标书 `## § <标题>`）、章标题（`# 第N章` / `# Chapter N:`）、
       图片（单元已按原嵌图格式含 `<img>`，调整时核对归属层级：caption 含 `证明/例`
       的图须在对应 `>` 块内；剔除图注文字）——全部按 writing-rules.md。
     - 结构回查：单元骨架由拆分器从契约生成、天然同构；调整时**不得重排、不得自创
       层级、不得无中生有**；章首序言（`# 章标题` 之后的 `desc` 单元）必须保留在
       最终 md 最前（规则 5）。
   - **(b) 🔴 强制门控（确保每个 item 都改好且**写对**，一个不漏）**：
     ```bash
     python flows/write-source/script/gate_units.py "<extract_dir>" [ch ...]
     ```
     exit 0 = 该章全部单元文件存在、首行 `DONE`、**单元级质量校验通过**。
     🔴 **2026-09-01 起判断标准是「写对」而非「重写」**（拦"模型瞎改就标 DONE"）：
     `check_unit_quality.py` 对每个 item / desc 单元做**质量校验**——全部引用 verify
     已有检测函数，不重复造轮子：
     - **公式闭合**：`check_katex.check_display_math_closure`（同 verify F 层）
     - **裸数学/箭头**：`katex_heuristics.find_bare_math_errors` / `find_raw_arrow_errors`
       （同 verify F 层）
     - **证明过长**：`verbose_gates.check_verbose_proofs`（同 verify P 层）
     - **结构标签**：`struct_labels.TOP_LEVEL_HEADER_RE`（同 verify H 层）
     - **example blockquote**：`format_verify.check_example_blockquote_lines`（同 verify G 层）
     - **OCR 残留**：verify 不覆盖的 OCR 公式模式由薄封装补充
     任一项不过 → 该单元列「质量未达标」，须真正按写作要求改对后再标 DONE。
     未过 gate 严禁进入步骤 6 拼接。超大章（字符 > 60000）按规则 3 拆节后，
     逐节单元组分别门控。
6. **拼接全部单元成最终源语言章 md（纯脚本，无 agent 参与）**
   - 🔴 本步**只是机械拼接**：agent 的全部写作要求已在步骤 5 逐个改好单元时落实
     （每单元 DONE + 门控通过），本步仅运行拼接脚本，**不需要也不允许 agent 再做
     任何写作调整**。
   - **拼接**：
     ```bash
     python flows/write-source/script/merge_units.py "<extract_dir>" <ch> [-o <out_md>]
     ```
     🔴 **门控强制到脚本层（2026-09-01 强化）**：`merge_units.py` **拼接前默认先跑
     `gate_units` 门控**——任一单元未改好（首行非 `DONE` / 内容未改写 / 缺失）即
     **直接报错拒绝拼接**，即使 agent 绕过 `gate_units` 单独跑 merge 也会被拦截。
     按 manifest 顺序读取全部单元文件，拼接成 `ChapterN_*.md` / `第N章_*.md`
     （默认文件名按语种 + 契约章名自动生成），并**按 V-F 规则重建条目级 `---`
     分隔线**：节标题之前（非首单元）加 `---`；`item`↔`item`、`item`↔`desc`、
     `desc`→`item`（条目尾随）加 `---`；章 / 节标题之下第一元素、连续 `desc` 不加；
     复用 `_tidy_separators` 合并堆叠 `---`、保证上下空行（幂等）。
7. **最后：使用 `verify/verify.md` 完整校验所有总结文件**（源语言全部章节初稿写完后执行，🚫 仍须遵守规则 2 的批量纪律，禁止逐章校验）：
   ```bash
   python verify/script/verify_chapter.py --all <extract_dir> <book_dir>   # exit 0 才算通过
   ```
   未过则修复其中可修复层——🔴 **全层 `--fix` 已默认禁用**（2026-08-28 用户裁定，防止 G 层等邻接启发式修复在内容未归位时污染正文）：默认走**选择性单层修复 / 手工定点修改**；确需整章自动修复时先跑 `--preflight` 确认 `$$` 围栏配对且无块外 `\tag`，再显式 `--fix --fix-force`（仍受 PREFLIGHT 门约束），随后**不带 fix 旗标复验**确认 `exit 0`；至多 2 次仍不过则继续修，**严禁停下来问用户**。校验层语义 / `--fix`（含默认禁用与强制开关）范围 / 字节契约键见 [`verify/verify.md`](../../verify/verify.md) 与各 `verify/<snake>/<snake>.md`（每层 SSOT）。

## 本阶段规则（🔴 内联 + 核心原则）
- **🔴 规则0 — 写源硬闸（MM Repair `apply` 未完成 = 禁止写任何章节）**：启动本流程前，必须确认本书（或本批章节）的 MM Repair 已 `apply` 写回 `page_*.json`（验证法见 [`../extract/mm_repair/mm_repair.md`](../extract/mm_repair/mm_repair.md) 出口条件）。**凡 `page_*.json` 仍无 `mm_repaired`/`mm_reviewed` 标记、或 manifest 中该章对应页仍有 `resolved != true` 条目的章节，一律不得动笔。**（`manifest.status` 因 `apply` 无条件设置而不可信，勿以它为放行依据。）宁可先补完 MM Repair（含模式 A 视觉审读——若用户拒绝视觉识别则按 [`../extract/mm_repair/mm_repair.md`](../extract/mm_repair/mm_repair.md) Step 1 的 `VISION = no` 路径：仅模式 B / `MM_UNAVAILABLE`），也不要带着未修复的 OCR 噪声去写总结——写错源再返工的成本远高于先修数据。
- **🔴 规则1 — 源语言写作（硬底线）**：本步骤（write-source）只写**源语言**初稿——英文书每章写英文 `ChapterN_*.md`，中文书每章写中文 `第N章_*.md`。
- **🔴 规则2 — 写初稿期间禁止任何 per-chapter verify**：`verify` 统一在源语言全部初稿写完后、由步骤 7 用 `verify_chapter.py --all` 一次性批量进行。🚫 禁止"写完一章 verify 一章"，也禁止"第 1 章 pilot verify 后扇出"。
- **🔴 规则3 — 超大章按"节"拆分**（字符 > 60000 触发，中英文配对拆分）：`tools/split_chapters` 按节标题格式（`§N` 节标题式 / `N.M` 编号式）拆成每节一个文件，命名 `第{N}章_{M}_{名称}.md` / `Chapter{N}_{M}_{名称}.md`（章号后、节号后各一个下划线）；只拆到"节"一级，子节留父节内。幂等，拆分后默认删源合并文件（`--keep` 保留）。
- **🔴 规则4 — 写源唯一规则文档 = `writing-rules.md`**：本步骤格式与保真约束**只来自 [`docs/writing-rules.md`](../../docs/writing-rules.md)**（含其末尾「verify 规则 ↔ 写作规则映射表」）。verify 各子文档（`verify/<snake>/<snake>.md`、含 `format_verify.md`）仅承载机器判定 / `--fix` 实现，写源阶段**不必读**；校验失败时再查对应子文档。此举收敛 skill 的 token 开销——写源上下文不再重复注入整组 verify 规则文档。
- **🔴 规则5 — 章首序言保全（单元改写不丢章级信息）**：按步骤 5 逐个改好单元时，**章标题单元、章首序言 `desc` 单元、章内全局记号约定等「`# 章标题` 之后、第一个 `## §` 之前的章级内容」必须完整保留在对应单元内**，拼接后位于最终 md 最前。禁止把章首信息并入「第一节」或丢弃——否则会丢失跨节共享的记号定义与章级动机。
- **🔴 规则6 — 校验是翻译前不可省略的硬闸（死规则）**：本阶段步骤 7（`verify_chapter.py --all` 复验 `exit 0`）**必须**完成，源语言版才算就绪。图片不再单独嵌图——初始总结由脚本输出、内容完整性闸门保证其含全部图片（image 块随草稿继承到最终 md）；**严禁「写完源语言但未校验就跳去 derive 翻译」**——该行为违反 flow_gate 顺序闸（write_source 末步 `verify_source` 未 `done`，`derive` 硬拒），且会造成翻译版两版分叉、需全盘返工。源语言「写完 + 校验 PASS」齐备，才是进入 `derive-translate` 的唯一合法起点（详见 [`../derive-translate/derive-translate.md`](../derive-translate/derive-translate.md) 翻译硬闸）。
- **🔴 规则7 — structure 完整性闸门是拆分的硬闸**：步骤 3 的查漏回填闸门（章节缺项 + 定理 / 定义等条目缺项，D 层 + B 层）**必须重跑至 `gate.passed == true`** 才允许进入步骤 4 拆分单元——先拆分再回填会让已拆的单元缺这些条目，返工成本远高于闸门前补齐。
- **🔴 规则8 — write_chapters 落账证据 = 「逐单元改好 + 门控通过」的机械核对（死规则）**：`write_source.write_chapters` 的证据复核（`flow_runner verify / mark`）**不只看章数**——对每个有单元的章机械核对：① **单元门控通过**：`units/ch{N}/manifest.json` 中每个单元文件存在、首行 `DONE`、内容指纹已变（= 每个 item 都被 agent 改好，一个不漏）；② **最终 md 存在**：merge_units 拼接产物；③ **骨架同构**：结构契约全部 `section` 名必须在最终 md 中在位；④ **条目在位**：契约全部编号项 `name` 必须在最终 md 中在位。任何一项不过 → mark 被硬拒，必须回归 `units/ch{N}/` 对应单元补齐改好、重跑 `gate_units.py` 通过后再 merge。**严禁跳过单元目录直接凭 `page_*.json` / 印象写作**——脱离单元导致的漏项、自创层级与格式漂移在落账前即被拦截，而不是堆积到步骤 7 verify 后全盘返工（证据实现见 `flows/_flow_contract.py` 的 `write_chapters_ok`）。
- **核心原则（保真底线）**：OCR 噪声可修、表述可精简但**不得省略编号项 / 描述性内容中的公式概念**；**不编造**内容、**不编造结构**（不得新建原书没有的标题层级、不得重排条目顺序）；**严禁照抄 OCR 文本流**（页眉 / 页脚 / 版权行属噪声须剔除）；非核心内容须"摘要"而非整段照抄（Tier 1/2/3 分级见 `docs/writing-rules.md`）。
- **双源铁律（结构 ≠ 内容）**：单元 = 结构契约（骨架）+ `page_*.json`（内容）的**预合并视图**，只是调整底稿而**非免检成品**——正文**必须忠于单元所载原文并回归 `page_*.json` 核对存疑处**，禁止脱离契约自创结构或重排顺序（单元骨架即契约骨架）；单元中的公式是 OCR 原样，**严禁照抄**（步骤 5 重写校正）。
- **公式序标铁律**：书无号**不编造**；已标须**正确、不重复、不跨章**。

## 出口条件
- 出口：源语言全部章节初稿写完（图片由内容化分章契约随单元继承），且 `verify/script/verify_chapter.py --all` 对全书 `exit 0`（`verify PASS + KaTeX OK`）；格式修复在步骤 7 校验失败时按 [`verify/verify.md`](../../verify/verify.md) 修复纪律进行（🔴 全层 `--fix` 默认禁用，须 `--fix --fix-force` + PREFLIGHT）。

## 相关代码（路径相对 skill 根目录）
- `flows/write-source/structure/script/build_structure`：统一结构 + 内容契约生成器（步骤 3，按章产出含内容的完整 `ch{N}.json`，内部调用 `scan_skeleton` / `extract_items` 系列并即时挂载内容）。
- `flows/write-source/structure/script/attach_content`：structure 第 5 步正文内容化 + 按章拆分（步骤 4 单元数据源；见 `flows/write-source/structure/structure.md`）。
- `flows/write-source/script/render_draft.py`：单元渲染库（拆分 / 拼接脚本复用其纯渲染函数，如 `_chapter_heading` / `_render_item` / `_walk_mixed` / `_tidy_separators`；不再单独产出整章 `draft_ch{N}.md`）。
- `flows/write-source/script/split_draft_units.py`：步骤 4 单元拆分（`ch{N}.json` → `units/ch{N}/` 每 item 一 md + `manifest.json`，首行 DRAFT 标记）。
- `flows/write-source/script/gate_units.py`：步骤 5 强制门控（agent 逐个改好单元后跑；每个单元 DONE + 内容改写才 exit 0；未过严禁进入步骤 6 拼接）。
- `flows/write-source/script/merge_units.py`：步骤 6 拼接（纯脚本；按 manifest 顺序合并全部单元成最终 `ChapterN_*.md` / `第N章_*.md`，按 V-F 重建 `---` 分隔线）。
- `flows/write-source/structure/script/scan_skeleton`：结构骨架（章节标题扫描，仅被 `build_structure` 调用）。
- `flows/write-source/structure/script/extract_items` + 变体（`_en` / `_gm` / `_vakil` / `_hom` / `_kt`）：编号项抽取，按 `ordinal` 被 `build_structure` 调用。
- `config/verify_config/make_config.py`：步骤 1 书级配置生成（`verify_config.json`）。
- `data/page_json/page_json.py`：`PageJson.load(fp).page_text()` / `.text_blocks` —— 调整时存疑处按节点 `page_start..page_end` 回查 OCR 原文（步骤 5 agent 改单元时）。
- `tools/wrap_examples_bq` / `tools/fmt_proofs`：生产期格式变换脚本（可用 `cli.py` 的 `wrap-examples` / `fmt-proofs` 子命令单独调用，亦由 `derive-translate` 阶段对翻译版调用）。源版「顶层例/证包裹进 `>` + 连续性」已由 verify 的 **format_verify（F 层）的 `h_mbq` 检测规则与同层格式 fixer**（原「H 层 + G 层」，已并入 F 层）在步骤 7 `verify --fix`（🔴 2026-08-28 起全层 `--fix` 默认禁用，须 `--fix --fix-force` + PREFLIGHT）自动兜底，**无需** write-source 另行调用；其「证明步骤编号 / `$$` 形态归一」属编辑性生产变换，受 verify 字节契约（fix-dict 键 `{h,h_stmt,h_ul,h_mbq,c,g,i,j,k,l,m,n}` 不可扩）约束无法成为 verify fixer，故仍以 `tools/` 下的 CLI 工具形式保留，供翻译版 / 手动批处理使用。
- `../../verify/script/audit_counts.py`：逐节条数核对（OCR 侧启发式工具）。原「逐节条数核对须另行挂接」的缺口已由规则8 的 write_chapters 落账证据闭合——**契约条目在位核对**以结构契约为真值（优于 OCR 启发式），在 mark 前强制拦截漏项；本脚本保留为 OCR 侧独立交叉核对，供疑议时人工复核。
- `tools/split_chapters`：规则3 拆章（文件级结构拆分，非格式/校验，故归入 `tools/`）。
- `verify/script/verify_chapter.py`：步骤 7 批量校验（`--all` / `--fix`，语言无关，源/译共用）。

## 子流程
- [`config_setting`](config_setting/config_setting.md) — chapter_map 建映射 + 书级配置生成（步骤 1，MM Repair 之后、图检测之前）
- [`figure_detection`](figure_detection/figure_detection.md) — 图检测 + 分配（步骤 2，config 之后）
- [`structure`](structure/structure.md) — 统一结构骨架 + 完整性闸门（步骤 3，写作契约 + verify 基准合一；第 5 步产出内容化分章契约）
- [`写作规则`](../../docs/writing-rules.md) — **写源阶段唯一必读规则文档（SSOT）**，已含 verify 全部写作期规则收敛（末尾映射表）
- [`figures`](figures/figures.md) — 嵌图子流程（**已废弃**：图片经内容化分章契约 image 块随草稿继承，无需单独嵌图；文档保留供参考）
- [`verify`](../../verify/verify.md) — 批量校验关卡（步骤 7 引用；写源阶段不必读各子文档，校验失败排查时再查）
