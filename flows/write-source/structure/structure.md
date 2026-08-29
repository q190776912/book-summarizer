# Sub-flow: write-source / structure（统一结构骨架 + 完整性闸门 / write-source 内强制生成）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
**统一结构骨架 / 写作契约 + verify 编号项基准**：structure 子流程按章产出分章契约 `ch{N}.json`（附录 `appendix{X}.json`，骨架与内容同文件），一次产出同时满足两类需求：

- **write-source 写作契约**：全书按章顺序的章节树，几节写几节、顺序照抄、每个编号项（定义/定理/例/…）必须落地、印刷标题进 `name`、练习全量纳入 `type:"exercise"`。
- **verify 编号项基准**：展平树、过滤 `type!="exercise"` 即得本书编号项 `key` 集合（data_provider 直接读此 JSON 作为编号项基准，不经抽取器，见 `verify/data_provider`）。

> 本文件是《结构契约 + verify 基准》的**唯一权威（SSOT）**。底层扫描/抽取（`scan_skeleton.py` / `extract_items*.py`）仅作为 `build_structure.py` 的内部依赖被调用；本阶段只跑 `build_structure.py` 产 JSON。

## 前置
- 全书 `page_*.json` 已落盘且过 MM Repair（extract 主流程出口满足）。
- `verify_config.json` 已就绪（编号模式由 `ordinal` 自动判定；图检测是否完成不影响本产物）。

## 步骤（有序）

> 🔴 **2026-08-29 二次重构**：**第 1 步即产出含全部正文内容的完整契约**——`build_structure` 生成骨架后**立即**调 `build_chapter_contract` 挂入 description / proof / text / formula / image 内容块并写回同一文件，`ch{N}.json` 自此就是"整章信息的唯一载体"；**不再有独立的 attach_content 内容化步骤**。后续只剩校验与回填：**第 1 步生成完整契约 → 第 2 步 `section_continuity` 校验遗漏章节并回填 → 第 3 步 `item_numbering_integrity` 校验遗漏定义/定理/例等重要概念并回填 → 第 4 步「完整 + 连续」闸门复核**。
> 四步都必须在 **write-source 写书之前**完成，否则漏抓的编号项不会出现在总结 MD 里。
> 第 2 / 3 步都建议先 `--backfill` 之前的 dry-run 报告 review，确认 `readable` 项无误后再写回。

**第 1 步 · 生成完整契约（骨架 + 内容一步到位）**
```powershell
python flows/write-source/structure/script/build_structure <extract_dir>
# 不传 <ch> 即扫全部章；也可指定章：build_structure.py <extract_dir> 1 2 3
# 编号模式（三级/两级/en/vakil/gm/roman）由 <extract_dir>/verify_config.json
# 的 ordinal 自动判定，无需 --scheme
```
按章产出完整契约 `ch{N}.json`（附录 `appendix{X}.json`）：`sub_sec` 内按章顺序**层级嵌套**全部章节（`1.2.1` 挂进 `1.2` 的 `sub_sec`、`1.2.1.1` 挂进 `1.2.1`，与原书标题层级同构）与条目，并携带**描述信息（章首序言 / 节导语 / 证明后尾随段落 → `description` 节点，与定理同级）+ 每个编号项 / 练习的文字、公式内容块 + 条目内证明（`proof` 子节点）+ 图片（`image` 路径）块**。要点：
- 🔴 与 MM Repair 同一硬闸：缺 `_extraction_done.json` 拒绝运行。
- **层级归属保真**：小节按 key 数字段嵌套；条目默认按其编号末段派生所属节，`verify_config.json` 置 `"chapter_scoped_items": true` 时（章内计数器书，如编著集 "Theorem 2.6" = 第2章第6个定理而非 §2.6 的条目）**只按页码就近归节**，禁止号→节绑定（否则条目错挂数字巧合节、B 层乱序）。
- 内容块自动处理：页眉 / 页脚 / 版权行 / 页码噪声过滤；行内公式（MFD `cls=0`）按 x 位置拼回宿主文本行恢复阅读序；行间公式同行右缘的编号 tag（`(2.17)` 独立文本块）挂到公式块 `tag` 键并从散文流剔除；条目 / 小节正文开头按序匹配契约 `name` 的归一化前缀时剥离印刷标题（宁重复不误删）；证明标记 / QED 识别失败不拆（宁整不碎）。
- 本步幂等：重跑即整章重建（内容随骨架重挂）。

**第 2 步 · 章节查漏 + 回填（复用 `section_continuity` / D 层）**
```powershell
python verify/script/check_structure_completeness.py <extract_dir> [ch ...]            # dry-run：只出报告
python verify/script/check_structure_completeness.py <extract_dir> [ch ...] --backfill  # 写回分章契约
```
- 章节完整性 → 复用公共子流程 `verify/section_continuity`（语义名 **section-continuity**，`check_d_layer`）的 raw 重扫能力（直接扫 `page_*.json`，独立于 `extract_items`）。
- 把分章契约派生出「合成 md」（`## §C.S` 标题）喂给 D 层，D 层比对「书中真值章节集」vs 契约，检出**遗漏章节**：内部洞（`continuity_sections`）+ 尾部缺节（`missing_sections`），回填分章契约的 `section` 节点。
- 🔴 **只校验章节级（level 2 = C.S）**：`book_structure` 建模 `chapter → section（递归嵌套子节）→ 条目`，D 层只取 `levels[2]`（level 1 = 章前缀、level 2 = 节），不查 subsection（否则会把每个 C.S-K 条目误报成「缺失 subsection」）。

**第 3 步 · 重要概念查漏 + 回填（复用 `item_numbering_integrity` / B 层）**
- 条目完整性 → 复用公共子流程 `verify/item_numbering_integrity`（语义名 **item-numbering-integrity**，B 层）的编号完整性逻辑。为避免与 verify 端（B 层读「已写好的 .md」）冲突，structure 阶段把契约派生出「合成 md」（非练习条目 → `**key Label**` 粗体头，按 `type` 反推标签，确保 B 层能解析）喂给 B 层，让其分组 / 编号 / ignore 逻辑校验条目连续性。
- 具体**回填**由「源条目集（`scan_raw_items` 跨校验：标题锚定、全方案 / 全类型，抓抽取器漏检）− 契约」的结构化差集驱动（保留 `scan_raw_items` 作为稳健源侧交叉校验），只回填**重要概念**（排除练习类）：
  - `readable`（编号 / 标签 / 页码 / 标题都能从 OCR 干净取出）→ 脚本**自动回填**；
  - `reference`（块内命中强引用标记 see/refer to/cf./the following…，或数字前置三级无显式标签）→ **不**自动回填，交人工 / agent 复核（多半是引用而非定义）；
  - `needs_agent`（OCR 字母↔数字无法干净还原）→ 交 agent 凭读图 / 知识回填（沿用 `config/manual_overrides_chN` + `（OCR无法识别）`，见 `verify/missing_label_policy.md`）。

确认 `readable` 项无误后，**先备份再写回**：
```powershell
# 写回前建议备份（防止误填可秒回退）：
#   cp -r book_structure <备份目录>/
python verify/script/check_structure_completeness.py <extract_dir> [ch ...] --backfill
```
回填节点与第 1 步**逐字段一致**（`key` 三级=`C.S-N`、两级中文=`标签C.S`、两级英文=`标签 C.S`；
`type` 共用同一张 `_LABEL_TO_TYPE` 映射；`name = "key 印刷标题"`；`page_start/page_end = 页码`），
故 write-source / verify 可原样消费。🔴 **回填写回时同步重建该章内容**：树被原地修改后先 `clear_raw_recursive()` 丢过期保真视图，再 `build_chapter_contract` 幂等重挂（新回填条目同样获得 text/formula 内容块），写回单章文件——`ch{N}.json` 恒为完整契约。

**第 4 步 · 完整 + 连续 闸门（收尾保证）**
回填后**重跑第 2 / 第 3 步**，断言：遗漏章节 / 可读遗漏项 / B 层 `blocking`**全部归零**，保证 `book_structure` 既**完整**（无遗漏章节 / 无遗漏定义定理例）又**连续**（章节序列 / 条目编号无洞）。闸门结果在报告 `gate` 字段（`passed` / `residual_sections` / `residual_readable_items` / `residual_b_blocking`）。只有 `gate.passed == true` 才允许进入 write-source 的草稿渲染。

> 🔴 **顺序铁律**：第 1 → 2 → 3 → 4 步（含完整性闸门）必须在**write-source 渲染基本总结草稿**之前完成。回填后的编号项会作为「必须落地」节点出现在总结 MD；若先写书再回填，已写的 MD 会缺这些条目。B 层报「缺号」但核对源书确认是**稀疏编号**（作者跳号，如 ch5 无 Theorem 5.1、ch20 无 Theorem 20.4/20.5）时，按 verify 规则登记 `ignore_ch{N}.json` 豁免，**不得**为凑连续而编造条目。

## 源侧完整性校验与回填（写书前兜底）

### 动机
`build_structure` 本身只做「抽取 + 合并」，**不内嵌源侧缺口恢复**（源侧缺口恢复由校验层负责；抽取器只负责把 raw 条目抓出来）。
若只靠抽取器，漏抓的定义/定理/例会安静地缺进 JSON；非三级书不在 structure 阶段做源侧查漏。
本步骤在「写书之前」调用校验层的源侧重完整性工具（`verify/script/check_structure_completeness.py`，复用 `section_continuity` 公共子流程 + 独立标题锚定扫描），把查漏从
「写完 MD 才发现」提前到「抽完即查、源侧兜底」。

### 复用的公共校验能力
章节 / 条目完整性均复用 verify 的 `section_continuity`（D 层）与 `item_numbering_integrity`（B 层）公共能力（语义名 **section-continuity** / **item-numbering-integrity**）——本阶段只把 `book_structure` 派生「合成 md」喂入，不另立评判逻辑。具体 raw 重扫方式、levels 取值、合成 md 格式与回填状态分流见 **§步骤 第 2 / 3 步**，此处不重复逐步行文。

### 比对与混合回填
比对「书中真值集」vs 分章契约得到遗漏清单，按 `readable` / `reference` / `needs_agent` 三态分流回填（状态定义、回填节点字段约束与 §步骤 第 3 步**逐字段一致**，均见 **§步骤 第 3 步**，此处不重复）。回填写回命令与闸门判定见 **§步骤 第 2 / 4 步**。

### 健壮性要点
- **多位数章节号**（ch10 / ch11 …）已支持：数字串按 OCR 容错（`A→4, B→8, O→0, S→5 …`）整段归一，避免单字符捕获导致漏扫整章。
- **两级数字前置无标签**的匹配（大概率是章节号，如 `10.2`）直接丢弃，避免把章节当条目录入。
- 章节查漏复用 `section_continuity` 公共能力，与 verify 端同源。

### 产物
`<extract_dir>/completeness_reports/ch<N>_completeness_report.json`，含：
`contract_items / raw_items_scanned / raw_sections_present / missing_sections /
missing_items[{key,label,page,snippet,canon,has_label,status}] / backfilled_items / backfilled_sections /
section_detail{continuity,tail} / b_layer{blocking,b_gap_warnings,b_tail_warnings} /
gate{passed,residual_sections,residual_readable_items,residual_b_blocking}`。
先 review 报告（dry-run），确认 `readable` 项无误后再 `--backfill` 写回；写回后**第 4 步闸门**
（`gate.passed == true`）才允许进入 write-source。

## 节点 Schema
```jsonc
{
  "key": "1.1-1",        // 书原生编号（语言无关）：三级 "1.1-1" / en "定义 1.2" /
                        //   vakil "1.2.1" / 练习 "1.2.A" / 章节 "1.1" / 章 "1"
  "type": "definition", // chapter | section | definition | theorem | lemma |
                        //   corollary | proposition | example | exercise | remark | uncat
  "name": "1.1-1 Definition (Metric space, metric).",  // 带序标的纯标题，不含正文
  "page_start": 18,
  "page_end": 18,       // 叶子 == page_start；容器取末代子孙页
  "sub_sec": [ /* 仅 chapter / section 含此键，递归同结构 */ ]
}
```
- **顶层**为书对象（`key=-1, type=-1, name=<书名>, page_start/page_end=<全书起止页>），`sub_sec` 内按章顺序嵌套 `type:"chapter"` 节点；章/`section` 递归继续挂 `sub_sec`。全文件只有一个 JSON 对象，单文件承载全书章节。
- **`name` 带序标**：序标位置随书（前/后皆可），与原文一致；只含标题不含正文内容。
- **练习全量纳入** `type:"exercise"`（verify 展平取 key 集时过滤掉即可，不强制写作落地）。
- **`page_end`**：叶子 `== page_start`；容器（chapter/section）取**末代子孙页**。

### 内容块与派生节点（第 5 步产出，仅分章内容契约）

分章文件顶层即该章 `chapter` 节点；其 `sub_sec`（含章 / 节的 `sub_sec`）在**文档顺序**下混合四类元素：① 结构节点（与单文件同 schema）、② `description` 节点（描述信息，与定理同级）、③ `proof` 节点（证明，条目子节点）、④ 内容块（`text` / `formula`+`display` / `image`）。

> 🔴 **节点与内容块的完整 Schema、实书样例、字段语义（`line_start` / `indent` / `display` 等）的 SSOT 见 [`data/book_structure/book_structure.md`](../../../data/book_structure/book_structure.md) §2–§5**——本节只承载产出规则与流程语义，不重复 schema。

- **产生规则**：章 / 节的描述散文聚合为 `description` 节点置于各自 `sub_sec` 最前；条目正文内容块与 `proof` 子节点按陈述 → 证明的阅读序挂在条目节点 `sub_sec`；条目末个 proof 之后的尾随散文聚合为与该条目**同级**的 description 节点（插在其后）。
- **proof 拆分**：证明标记（`PROOF` / `Proof` / `Solution` / `证明` / `证：` / `解：`，块首匹配；中文与陈述同行被 OCR 合并时按句末标点 + 「证」边界内联拆分）开启，至 QED（`口` / `□` / `∎` / `证毕` / `Q.E.D.` / 纯 `\square` 型公式）或块流末尾收束；识别失败**不拆**（宁整不碎）；练习（exercise）的「证明：…」属题干任务不拆。
- **图片**：取自 `figure_index.json`（page/bbox 并入阅读序，路径**相对书根**）；无图管线则零图片块；渲染按原嵌图格式（flex div + `<img>`），**无单独嵌图步骤**。
- **已知近似（调整步骤兜底）**：无证明条目之后的游离段落仍留在该条目正文内（无边界信号不做切分）；证明无 QED 收尾时收束到该条目块流末尾（可能并入条目后段讨论，调整时拆出）；OCR 文本行与其行内公式的校正 latex 天然并存（内容重复，调整时保留公式、清理乱码）；图注文字 / 证明结尾框等残余噪声由调整清理。
- **完整性闸门**：由 `verify/script/check_content_completeness.py` 校验（确定性复算比对 + 图片独立真值 + 证明覆盖审计），在 write-source 步骤 4（渲染草稿）前执行，FAIL 严禁渲染。
- 消费方：`flows/write-source/script/render_draft.py`（渲染基本总结草稿）；`_is_block` 判定与派生节点指纹排除见 `attach_content.py`。

## 构建逻辑（与 `verify/data_provider` 同一套抽取分派）
1. **章节骨架**优先来自 `scan_skeleton` 的 `SEC` 扫描（含印刷标题）；当某方案 `SEC` 捕获不全（en 两级、vakil）时，用「条目键派生章节号」补齐缺失章节。
2. **条目节点权威来自抽取器**（`extract_items` / `extract_items_en` / `extract_items_vakil` / `extract_items_gm` 等，按 `ordinal` 选路，与 data_provider 一致），`label → type`：
   `定义→definition`、`定理→theorem`、`引理→lemma`、`推论→corollary`、`命题→proposition`、`例→example`、`评注/注→remark`、`uncat→uncat`。**抽取器里的 `练习/习题` 类键被排除**（练习只来自下一步的 `EXER`）。
3. **练习来自 `scan_skeleton` 的 `EXER` 扫描**（统一来源），与条目分开，避免重复计数。
4. **挂接**：每个条目/练习优先按「派生章节号命中」挂到对应 section；命中失败则按**页码归最近 SEC**。`verify_config.json` 置 `"chapter_scoped_items": true`（章内计数器书）时一律页码归节。section 的 `page_start = 子项最小页`、`page_end = 末代子孙页`（叶子 `== start`）。产出前按 key 数字段**层级嵌套**（`1.2.1` → `1.2.sub_sec`）并重排为文档序。

## 本阶段规则（🔴 内联）
- **JSON 是契约，不是参考**：
  - 有几个 `section` 就必须写几节 `## §N.M`（原书小节**带序标**时），顺序照抄，一个不能少、不能颠倒；原书小节**无序号标**时写 `## § <标题>`（数字留空，仅保留 `§`，详见 `docs/writing-rules.md`「小节序标必须尊重原书」），并须在 `verify_config.json` 的 `section_types` 里把**章层级与小节层级都写为 `0`**（如 Silverman `"section_types": [0, 0]`，第一个 `0`=章层级、第二个 `0`=小节层级，对应 `type 0` / `depth 0`；单层级无序号标书才用 `[0]`）；
  - 每个非 `exercise` 节点都必须在总结里落地；`exercise` 按习题收录规则处理（穿插习题原位保留，章末整块习题省略），故不强制落地；
  - 节点 `name` 的印刷标题必须写进条目标签，不得丢弃；
  - JSON 里没有的编号，不许出现在总结里（无中生有）。
- **不能只靠抽取器的裸键**：它不含节标题 / 练习 / 印刷标题；只拿它写作必然漏节、乱序、丢标题。统一消费本 JSON。
- **写完后自查**：非 exercise 的 `section` 数应等于总结 `## §` 标题数（`section_types` 含 `0` 时按位置/数量对齐，允许 md 小节多于契约未记的小节）；非 exercise 节点 `key` 集合应与总结编号一致。

## 出口条件
- 出口：全部章的**完整契约** `ch{N}.json` / `appendix{X}.json` 已生成（第 1 步：骨架 + description / proof / 内容块一步到位；章节按层级嵌套），且第 2–4 步查漏回填闸门通过（回填后内容同步重建）。分章契约作为 write-source 的写作契约、verify 的编号项基准与草稿渲染（`render_draft`）输入采用。

## 已知局限（实现层，非契约缺陷）
- **en 两级（ordinal=4）章节检测为近似**：skeleton 的 `SEC` 行对部分 en 书乱匹配，章节号由条目键派生，可能多出空章节（条目仍正确捕获、按序归位）。写章时以「派生章节 + 源书实际节标题」为准。
- **非标准编号书（如中文散文式「第一章…、1中导出…」）可能抽不到条目**：属该书既有局限（正则未覆盖），JSON 退化为空章节节点，不崩溃。
- **配置错配书**（如 `language=cn` 但正文为英文的 Evans）：cn 解析器抓不到章节标题，section `name` 缺标题（仅派生章节号），结构/条目仍正确。

## 相关代码（路径相对 skill 根目录）
- `flows/write-source/structure/script/build_structure`：统一结构 + 内容契约生成（本子流程；第 1 步一步产出完整契约）。
- `flows/write-source/structure/script/attach_content`：`build_chapter_contract` 内容挂载实现（由 build_structure 与 completeness 回填共用；`attach()` CLI 保留作全章重挂的手动维护入口，不再是流程步骤）。
- `flows/write-source/structure/script/scan_skeleton`：`SEC` / `EXER` 扫描（被 build_structure 调用）。
- `flows/write-source/structure/script/extract_items` + 变体（`_en` / `_gm` / `_vakil` 等）：编号项抽取（被 build_structure 按 `ordinal` 调用）。

## 子流程
无（`scan_skeleton` 与 `extract_items*` 为 build_structure 的内部依赖模块，不单独作为子流程）。
