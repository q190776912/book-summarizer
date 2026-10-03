# Flow: config_setting（生成书级配置 / write-source 子流程）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
在 extract 的 **MM Repair 全部完成**后（文本提取 100% 且全部稳定批次经模式 A+B 已 `mm_repair_apply` 写回 `page_*.json`；若用户拒绝视觉识别则模式 A 由模式 B / `MM_UNAVAILABLE` 替代，见 [`extract/mm_repair`](../../extract/mm_repair/mm_repair.md) Step 1；完成标记 `_extraction_done.json` 存在），依据**源 `page_*.json`** 一次性完成两件事：

1. **建章节映射** `_extract/chapter_map.json`（Step 1，统一在本阶段生成）；
2. **生成书级配置** `_extract/verify_config.json`（Step 2–3）——它是 `verify_chapter.py` / `flows/write-source/structure/script/scan_skeleton` 的**唯一配置源**，也是后续批量校验的硬性前置。

图检测子流程依赖本书 `ordinal` 里的 **Figure 组**（`{"type":<段数>,"name":[图号前缀词],"scope":<段数>}`；`type` 经 `ORDINAL_DEPTH` 派生的 `depth` 即图号段数 components）来确定图号前缀与段数；缺 Figure 组时回落默认前缀 `["图","Figure","Fig"]`，自定义前缀书须在 Figure 组 `name` 显式列出。🔴 仅文本 100% 落盘但未完成 MM Repair（尤其模式 A 视觉审读，若用户拒绝视觉识别则以模式 B / `MM_UNAVAILABLE` 替代）时不得跑本步——`chapter_map` 章边界与 `formula` map 都依赖校正后的页面。

## 前置
- **MM Repair 完成**（文本提取 100% 且全部稳定批次经模式 A+B 已 `mm_repair_apply` 写回 `page_*.json`；用户拒绝视觉识别时模式 A 由模式 B / `MM_UNAVAILABLE` 替代；完成标记 `_extraction_done.json` 存在）。🔴 仅文本 100% 落盘、模式 A 视觉审读（若启用）未做时，本步的配置会基于未修复页，属误用。
- 🔴 **翻译派生版不参与配置生成**。

## 步骤（有序）

1. **建章节映射（chapter_map，一步生成正确页码）**
   - agent 只校订**结构真相**（OCR 给不出、必须由人定的部分）：从 `_extract/page_*.json` 的目录页（TOC 通常位于 `page_001~005` 附近，MM 修复后可用全文检索章名交叉确认）读每章**章号 + 章名**（中 `name` + 英 `name_en`）+ 附录标记；写 `_extract/chapter_map.json`：
     ```json
     { "chapters": [ {"ch": 1, "name": "测度论", "name_en": "Measure Theory"}, ... ] }
     ```
     `start`/`end` 此时**不填或仅填 TOC 粗略值**——页码由下一步自动算出，无需人抄印刷页号。
   - 🔴 用 `build_chapter_map.py` **一步从 OCR 生成正确页码**（检测引擎已内联于该脚本，无外部依赖）：
     ```bash
     python tools/build_chapter_map.py <extract_dir>
     ```
     它扫描 `page_*.json` 自动定位每章真实起点（"Chapter N" 标题匹配 / 裸标题回退）、推断 `end`（下一章起点-1），写回 `chapter_map.json` 并产出 `chapter_map.build_report.md` 供 agent 判断。
     - 🔴 **中文书页眉「第N章」序列兜底（Mode C）**：中文教材常见「TOC 印刷页号与 PDF 页序累积漂移」（实测《数学分析教程》3ed 上册偏差 12→82 页递增），若只靠申报窗口内匹配会检测失败、静默保留错值。脚本内置 `scan_cn_heads` 扫全书页眉「第N章」→ 取每章首个连续段起点作为**独立于申报值的真值锚点**，在 Mode A0/A/B 均失败时自动纠正任意大的偏差（实测把 ch7 错值 351 纠正为 304、ch3 141→138 等，7 章全 CORRECTED、0 UNDTECTED）。agent 判断环节照常审阅 `chapter_map.build_report.md` 即可，无需手填中文漂移页码。
   - 🔴 `start`/`end` 是 **PDF 文件页码**（= `page_%03d.json` 序号，1-based），**不是**印刷页码；agent **不手写它**——`build_chapter_map.py` 从 OCR 证据算出，天然是 PDF 页号，规避"存了印刷页号"的经典坑（详见 [data/chapter_map/chapter_map.md](../../../data/chapter_map/chapter_map.md)）。
   - 它是后续"某章是否已可写"、`make_config.py` 编号判定（罗马数字章号 / 每章 `ordinal` / `chapter_first`）、figure 按章分配与 `build_structure` 页区间读取的**唯一判定依据**。
   - 🔴 **生成后 agent 判断（强制）**：读 `chapter_map.build_report.md`——确认 `CORRECTED` 值；若有 `UNDTECTED` 章（检测器未能从 OCR 定位起点），在 `chapter_map.json` 手动补 `start`/`end` 后重跑本工具。全章 `start`/`end` 非 null 才放行进入 Step 2–3 与下游 write-source（与"规则 B：暴露真实缺陷、禁止掩盖"一脉相承）。

2. **探测编号形态**（用全书 `page_*.json`）：
   - `ordinal` 分组（`type` / `name` / `scope`）、`language`、章节层级（`section_types`，深度经 `SECTION_TYPE_DEPTH` 派生，多数由 `primary_type` 自动反推，仅四级子小节 `1.1.1.1` 需显式覆盖）；
   - **公式序标形态**：若书含公式编号，扫 `page_*.json` 的 `text[]` 实测段数（如 `C.N` → `type 2`(depth 2)、`C.S.N` → `type 3`(depth 3)、章级 → `scope 2`），推导 `formula` map 的 `type` / `scope`（digit 家族 `depth` 由 `type` 经 `ORDINAL_DEPTH` 派生，不单独配置）；**字母章位** `(A.3)` 用 legacy `type:2 + letter_ch:true` 或 formula-only `type:15`、**罗马章位** `(II.5)` 用 formula-only `type:16`（`lead=roman`），`make_config.detect_formula` 依页区间证据保守自动择族；三家族的 `(lead, ncomp)` 一律经唯一入口 `resolve_formula_type(type, letter_ch)` 派生。专用码 15/16 **不进** `ORDINAL_CODES`/`ORDINAL_DEPTH`，条目 `ordinal` 组校验天然拒绝它们（两套 type 空间互不耦合）；
   - **图序标体例（🔴 在 `ordinal` 里放一个 Figure 组，不得留缺）**：无论书是否用自定义图号前缀，`verify_config.json` 的 `ordinal` **必须**含一个 Figure 组（见 [`../../../config/verify_config/verify_config.md`](../../../config/verify_config/verify_config.md)）；图号前缀词写进该组 `name`，图号段数（components）= 该组 `type` 经 `ORDINAL_DEPTH` 派生的 `depth`（`type:1`→全局整数、`type:2`→章.图、`type:3`→章.节.图），`scope` 同值：
     - 书以非默认前缀标注图（如 `Scheme` / `Illustration` / 仅 `图` / 仅 `Fig`）→ Figure 组 `name` 列出**本书全部**图号前缀词（如 `{"type":2,"name":["图","Fig"],"scope":2}`）；
     - 书**完全没有**图序标（正文不出现任何图号前缀）→ **不在 `ordinal` 放任何 Figure 组**即可（figure_io 回落默认前缀）；若需严格"零匹配"（禁止任何前缀，避免误匹配正文 `Figure`/`图`），保留过渡 `{"figure": {"labels": []}}` 由 figure_io 识别为标记号。
     - **图检测子流程严格依赖此 Figure 组（或其过渡 `figure` 标记）**。
   - **小节序标体例（🔴 尊重原书，禁止编造）**：`_extract/verify_config.json` 的 `section_types` 是**逐层级**列表（从**章层级**排到最深的 `## §` 层级），每个元素是该层级 `## §` 标题的序标段数（1=一级 `## §N`、2=二级 `## §N.M`、3=三级、4=四级、**0=无序号标**），深度经 `SECTION_TYPE_DEPTH` 派生。**列表长度必须 = 章节层级总数（章计入）**——单层级书 `[0]`、章+无序号标小节书 `[0, 0]`：
   - **全书全局单序标 + 裸字母子块书**（Arnold《数学方法》型：章=`# 第N章` 文件承载、节=§1..§52 跨章连续单序标、节内子块印裸字母 `A. 变分`、附录章的节本身即字母）：声明 `"section_types": [1, 1, 5]` + `"sections_global": true`，md 子块标题写纯 `### §A`（🔴 禁止投影父节数字写成 `### §12.A`——那是编造复合序标）；附录字母节由 build_structure 自动升格进契约。
     - 原书小节**带序标**（如 `§3.2`、`3.1.4`）→ 默认 `[1, 2]`（或按实际层级），总结写 `## §N.M 节名`，verify 缺节闸门按数字逐一对齐分章契约（`book_structure/ch{N}.json`）；
     - 原书小节**无序号标**（如 Silverman《A Friendly Introduction to Number Theory》：章是文件 `# 第N章` 无 `## §` 编号、文件内 `## § <标题>` 小节也无编号）→ **章层级与小节层级都显式写为 `0`**，即 `"section_types": [0, 0]`（第一个 `0`=章、第二个 `0`=小节，两个层级都无序号标），总结写 `## § 描述性标题`（数字留空、仅保留 `§`），verify 缺节闸门改为按「位置/数量」比对（只查契约要求的节是否都在、不计 md 多出的小节），**不强求加回原书没有的序标**。该配置是 per-book 配置，仅改本书行为，其他带序标书保持 `[1,2]` 之类、零回归。
   - 🔴 **中文标签紧贴三级编号（旧 cn3lab / `type 10`，已并入 `type 3`）**：此类书条头是「中文标签 + 紧贴编号」（`**定义1.2.1**：` / `**定理1.3.1**：`），「定义/定理/推论/例」各自独立计数，同一 `1.3-1` 既可能是定义1.3.1 又可能是定理1.3.1。`type 10` 已退役（写它直接 `exit 2`，加载期无透明映射）——**关键：用 `type 3`，但必须按标签族拆成多个 ordinal 组**（定义 / 定理类 / 例 / 习题 各自成组、均 `type:3`；习题单级则 `type:1`），独立计数器靠**分组**实现。`make_config.py` 依「是否同升序（共享计数器）」的整书证据自动分组：同升序并入一组、独立序列各自成组，故探测结果通常已正确拆分。🔴 手改时**切勿塌成单个 `type 3` `uncat` 组**（会把同号多标签并成一条计数器 → B 层假缺号 TAIL/EXTRA、门控假报「编号不递增」）。改分组后须整书重跑 `build_structure` + 重拆单元（重排契约键须人工确认）。
3. 生成配置：
   ```powershell
   python config/verify_config/make_config.py <extract_dir>   # 半自动探测 + 人工核对（公用配置脚本）
   # 或手填 _extract/verify_config.json
   ```

## 本阶段规则（🔴 内联）
- **规则0 — chapter_map 统一在本阶段生成、且只建一次**：**全书的 chapter_map 只生成一份**，不重复生成（除非用户明确要改章节划分）。判定"某章可写"的硬标准：`info.end <= current_max_page`（该章末页已落盘；extract 出口时全书页必已齐）。
- **规则1 — 书级配置强制前置（最高优先级）**：`verify_chapter.py` 由 `ConfigLoader.require_complete()` 强制：
  - 文件缺失 → **不能用默认配置，必须重新配置**（`make_config --force` 或手填），不得静默沿用默认 `ordinal`；
  - 文件存在但缺 `ordinal` → 硬报错 `exit 2`；
  - 🔴 **`ordinal` 各组的 `scope` 与 `name` 均为必填、无默认值**（与 `formula.scope` 同则）：凡声明了真实体例（`type != 0`）的组须**同时**显式给出 `scope`∈{1=book/2=chapter/3=section} 和**非空** `name`（本组要匹配的条目标签数组）——缺 `scope`/取值越界/非整数，或缺 `name`/空数组 `[]`/非数组/含非字符串元素，加载期 `from_dict` 直接 `ConfigError`（exit 2）：`scope` **绝不静默回落 `SCOPE_CHAPTER`**（重置窗口设错会致跨章/跨节计数串号、伪造缺号），`name` **绝不静默回落 `["uncat"]`**（省略＝伪造「本组不匹配任何具名标签」的体例事实；通用兜底桶须**显式**写 `["uncat"]`，那是真实决策）。唯一例外：`type 0`（UNNUMBERED，无编号）组的 scope/name 均无语义，允许省略（写了仍按合法性校验）。`make_config` 每条 ordinal 生成分支（含 Figure 继承分支、`_repaste_old_scopes` 只覆写不删）都显式写 scope 与检出标签，故 `--force` 重生成产出必可通过本校验；
  - 存在 `formula` 块但字段非法 → 强制校验并 `exit 2`：`type` 合法集 = digit 家族 `1/2/3`（经 `ORDINAL_DEPTH` 派生 depth）+ formula-only 字母/罗马 `15/16`（经 `resolve_formula_type` 派生 lead+ncomp，不进 `ORDINAL_CODES`；弃用码 4/9/10/11 已退役）；🔴 **`scope`∈{1=book/2=chapter/3=section} 为必填、无默认值**——声明了 `type` 却缺 `scope` 或取值越界，加载期 `from_dict` 直接 `ConfigError`（exit 2），绝不静默按章级；`depth` 由 `type` 派生不单独校验。（🔴 `bare_number` 亦为 no-default 必填，但**不在 `from_dict` 这层**强制——为保程序化/测试构造的 formula map 宽容，其缺席校验落在 `require_complete` 逐段门，详见规则3。）
  - 🔴 **主配置必填四件套 `strict` / `chapter_first` / `section_scoped` / `language`，无默认值**（no-default，2026-10-01）：这四项直接决定整本书如何被解析（`strict`=缺号是否严格判失败 / `chapter_first`=首分量是章还是节 / `section_scoped`=是否额外抽取「数字在前」标题与编号图表 / `language`=正文主体语言 `cn`\|`en`，决定编号解析、条目标签匹配与渲染语种），旧文档「默认 True/False/cn」＝静默兜底，一律禁止。**由 `require_complete` 在「主配置」（外层 map 的 `ch` 段 / 扁平正文）上强制「必须在场」**：缺任一项 → `ConfigError`（exit 2），文案指引 `make_config --force` 或人工依书补定。与 `scope`/`type` 的加载期 `from_dict` 校验**不同层**——`from_dict` 保持宽容（程序化/测试构造照旧可用，`language` 仍按 `primary_type` 家族尽力派生以兜底），强制只落在真实书加载闸 `require_complete`；判据是字段「在不在场」（`declared_fields` 记账），故 `chapter_first:false`（节基真实判定）、`language:"cn"`（= 旧默认）等「取值恰等于旧默认」也照样被接受。appendix/supplement 覆盖段「省略＝继承正文」，**不受此约束**。`make_config` 无条件写出这四项，故 `--force` 重生成恒通过。其余结构开关（`sections_global` / `numeric_local_sections` / `exercise_shared_numbering` / `chapter_scoped_items` / `gm_bare_numbered` / `chapter_local_sections` / `chapter_local_numbering`）沿用「缺席＝中性 False、探测器只落 True」既有约定（其缺席表达「本书无此特殊结构」而非伪造错误解释），不在强制之列。
- **规则2 — 判定不清回归全部 json**：编号 / 小节层级判定不清时，**必须回归本书全部 `page_*.json` 依据上下文判断**，不得仅抽几页原文或只看 TOC 草率定稿，更不得依赖静默默认值。
- **规则3 — formula map 必含且由 `page_*.json` 推导（`type` 与 `scope` 皆无默认值）**：书含公式序标时，`verify_config.json` **必须**含合法 `formula` map；`type`（编号段数/家族）与 `scope`（重置窗口 1/2/3）都须按 `page_*.json` 实测编号推导写入，不得留空、不得跳过、**更不得依赖任何静默默认值**。`make_config` 从首分量重置证据派生 `scope`；若整书首分量证据不足以判定（仅见单一前缀），探测会**省略 `scope`**——此时**必须由 agent 依书实际体例显式补定** `scope` 后才能通过加载校验（缺 `scope` 一律 `ConfigError`/exit 2），绝不容许把窗口猜成章级蒙混过关。🔴 **`bare_number` 同为必填、无默认值（no-default，2026-10-02）**：凡 `formula` 声明了 `type`（开启 Q 层）就必须显式带**布尔** `bare_number`（是否额外收录正文裸 `N.M`）。`make_config.detect_bare_number` **据书页证据探测**该值——逐块比较「公式号落点」里裸排 `N.M` 与括号/`Eq.`/`式` 标注形态：裸落点成规模→写 `true`（关掉即漏收）；括号主导且裸落点≈0→写 `false`（开裸只把页码/表值/交叉引用收成幻影 MISSING，Lee/Apostol 型）；样本过少或混叠无明确优势→**判不交、留空**，交由加载闸挡下后**由 agent 依书补定**（绝不再无条件播种 true、也绝不静默兜底）；单级 / 字母 / 罗马章位等 `build_formula_patterns` **恒不 emit 裸变体**的 inert 形状，该值对抽取无作用，探测器给可复核的显式 `true`。操作者旧登记值优先由 `_load_old_formula` 回贴、探测器不覆盖，故 `--force` 重生成对判得清的书多能自动补。其**缺席强制落在 `require_complete` 逐段完整性门**（非 `from_dict`，故程序化/测试构造的 formula map 仍宽容；appendix/supplement 段同样受此门约束），缺 `bare_number` 或非布尔一律 `ConfigError`/exit 2；判据是 raw dict 里 key 在不在场，故显式 `false` 合法。只含 `ignore`/`known_book` 而无 `type` 的**登记式**残块不选体例、豁免本门。
- **规则4 — 图序标配置强制显式（Figure 组必现，含"无图序标"标记号）**：`ordinal` **必须**含一个 Figure 组（见步骤 2），**不得因"懒得定"而留缺让下游静默回落默认**：
  - 有自定义图号前缀 → Figure 组 `name` 列出本书全部前缀词，`type`/`scope` 设对应段数（components）；
  - **无任何图序标** → 不在 `ordinal` 放 Figure 组（回落默认前缀）即可；若需严格零匹配，保留过渡 `{"figure": {"labels": []}}`（空数组标记号，figure_io 返回真正的零匹配，不回落默认）。
  - 反"隐藏问题"：无图号书若只因缺 Figure 组而静默用默认前缀，会把正文中碰巧出现的 `Figure`/`图` 等词误判为图号，污染图检测与 E 层（图引用 MISSING 检查）；故强制显式（或显式零匹配标记）。
- **规则5 — 序标类型不强制匹配、可增量扩展（🔴 强制）**：对定义/定理/引理/推论/命题/公式/图等带序标的类别，扫描 `page_*.json` 时若遇到一种**已知类型都匹配不上**的序标形态（新标签词、新编号体例、或新类别如"公理/Axiom""注记/Remark""练习/Exercise"等）：
  - **禁止强制匹配**：不得将陌生序标硬塞进已有 `ordinal` 组的 `name`/`type`，也不得凭"长得像"归入 `uncat` 或最近似类型——这会污染编号计数与跨章 `scope` 判定，等同"为通过校验而改被校验对象"（明确禁止）。
  - **允许增量扩展**：agent 找不到匹配时，**可以**增量式引入新类型：在 `verify_config.json` 的 `ordinal` 中新增一个 `type` 码（沿用既有 1–6 / 8 / 9 判定树，超出则顺延新码，如 `10`）+ 对应 `name` 标签；若该新类型需要新的抽取/匹配/校验脚本，agent **可增量添加相关脚本**（置于对应 flow 的 `script/` 下，并登记到 `../../../lib/boot.py` 注入路径与 `verify.md` 注册表），而非临时 hack 或强塞。
  - **判定不清仍须回归全书**：新类型的判定同样适用 规则2（回归全部 `page_*.json` 上下文），不得抽样定稿。
  - 补充：本规则与 `missing_label_policy.md` 互补——后者管"已识别类别但 OCR 漏抽的条目"（§2 凭知识库补写），本规则管"类别本身未知、需要扩展类型体系"的情形。
- **规则6 — chapter_map 一步生成 + agent 判断（🔴 强制）**：Step 1 用 `build_chapter_map.py` 一步从 OCR 算出正确 `start`/`end` 写回 `chapter_map.json`，**不得**让人从 TOC 手抄印刷页号当 PDF 页号。生成后 agent **必须**审阅 `chapter_map.build_report.md`：
  - `CORRECTED` 值（检测值 ≠ 原 TOC 粗略值）→ 确认接受（已自动写入）；
  - `UNDTECTED` 章（检测器未能从 OCR 定位起点）→ **必须**在 `chapter_map.json` 手动补 `start`/`end` 后重跑本工具；
  - 全章 `start`/`end` 非 null 方可进入 Step 2–3 与下游 write-source。此规则与"规则 B：暴露真实缺陷、禁止用 ignore 掩盖"一脉相承——页码由证据生成。
- **配置一次性生成**：配置**不是边写边填**，而是在文本提取全部完成后一次性生成（非增量）。`scan_skeleton` 对缺失配置仅告警、不阻断（安全网）；配置必须完整合法，且 `ordinal` 必须含 Figure 组（自定义前缀→`name` 非空、无图序标→不放 Figure 组或显式 `{"figure":{"labels":[]}}` 零匹配标记，二者皆不可"字段缺失而静默回落默认"）。
- **配置字段**见公用配置文档 [`../../../config/verify_config/verify_config.md`](../../../config/verify_config/verify_config.md)；`type` 为编号风格码（合法值 = `ORDINAL_CODES` {0,1,2,3,8,12,13,14}；🔴 已弃用码 4/9/10/11 已于 2026-09-21 退役并入 2/3/3/1，写它们直接 `exit 2`——EN 两级（含 `chapter_first:false` 两级组合）用 `type 2`；**附录字母章位 = 13（三级）/ 14（两段）**；**中文三级「标签紧贴编号」书（`定义1.3.1` / `定理1.3.1` 同印 .1、各自独立计数）用 `type 3` 并按标签族拆成多个 ordinal 组**（旧 `type 10` 已退役），🔴 切勿塌成单个 `type 3` `uncat` 组（会把同节内定义/定理/推论并成一组计数器 → 假缺号），见该文档 type 码表与「cn3lab」警示块）。
- **附录与正文体例不一致**：若本书附录编号体例与正文不同（如正文数字三级 `Theorem 10.9.13`、附录字母章位 `Definition A.1.1`），`make_config.py` 会**只扫附录页区间**额外生成 `_extract/appendix_verify_config.json`（`ConfigLoader` 对附录章自动路由到此文件，正文零回归）。若附录与正文同体例则**不生成**该文件（回退主配置）。`chapter_map.json` 中附录章须以字母章号（`"ch": "A"`）或章名含 `Appendix`/`附录` 登记，否则检测器无法识别其为附录。详见 [`../../../config/verify_config/verify_config.md` §附录专用配置](../../../config/verify_config/verify_config.md)。

## 出口条件
- 出口：`_extract/chapter_map.json` 存在且含章节（作为 make_config 编号判定与下游页区间依据，先行产出）；`_extract/verify_config.json` 完整合法（含 `formula` map 若书有公式；**`ordinal` 含 Figure 组必现**——有自定义前缀则 Figure 组 `name` 非空、无图序标则不放 Figure 组或显式 `{"figure":{"labels":[]}}` 零匹配标记，二者皆不可"字段缺失而静默回落默认"）。

## 相关代码（路径相对 skill 根目录）
- `data/chapter_map/chapter_map.py`：chapter_map 模板工具（数据结构见 `data/chapter_map/chapter_map.md`，相对本文件 `../../../data/chapter_map/`）。
- `../../../config/verify_config/make_config.py`：半自动配置生成（**公用配置脚本**，与流程解耦，说明见 `../../../config/verify_config/verify_config.md`）。
- `../../../verify/script/verify_chapter.py`：消费配置做校验（`ConfigLoader.require_complete()`）。
- `../../../config/verify_config/verify_config.py`：`BookConfig` / `GroupConfig` 数据模型（schema 实现 SSOT）。

## 子流程
- 无独立子文档——本文件即 write-source 步骤 1 的 config 子流程本体（chapter_map 建映射 = Step 1，配置生成 = Step 2–3）。