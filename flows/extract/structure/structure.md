# Sub-flow: extract / structure（统一结构骨架 / extract 末尾强制生成）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
把原先两份独立产物——`ch<N>_skeleton.txt`（结构骨架契约）与 `ch<N>_items.txt`（编号项清单）——**合并为单一 JSON 树** `ch<N>_structure.json`，一次产出同时满足两类需求：

- **write-source 写作契约**：全书按章顺序的章节树，几节写几节、顺序照抄、每个编号项（定义/定理/例/…）必须落地、印刷标题进 `name`、练习全量纳入 `type:"exercise"`。
- **verify 编号项基准**：展平树、过滤 `type!="exercise"` 即得本书编号项 `key` 集合（data_provider 改为读此 JSON，不再重跑抽取器，见 `verify/layers/data_provider`）。

> 本文件是《结构契约 + verify 基准》的**唯一权威（SSOT）**。底层扫描/抽取（`scan_skeleton.py` / `extract_items*.py`）不再作为独立子流程暴露，仅作为 `build_structure.py` 的内部依赖被调用；本阶段只跑 `build_structure.py` 产 JSON。

## 前置
- 全书 `page_*.json` 已落盘且过 MM Repair（extract 主流程出口满足）。
- `verify_config.json` 已就绪（编号模式由 `ordinal` 自动判定；图检测是否完成不影响本产物）。

## 步骤（有序）

> 三步顺序：**第 1 步生成基线契约 → 第 2 步源侧查漏（dry-run，先 review）→ 第 3 步分流 + 回填**。
> 三步都必须在 **write-source 写书之前**完成，否则漏抓的编号项不会出现在总结 MD 里。

**第 1 步 · 生成结构契约（必做，先跑，作为查漏基线）**
```powershell
python flows/extract/structure/script/build_structure <extract_dir>
# 不传 <ch> 即扫全部章；也可指定章：build_structure.py <extract_dir> 1 2 3
# 编号模式（三级/两级/en/vakil/gm/roman/fraleigh）由 <extract_dir>/verify_config.json
# 的 ordinal 自动判定，无需 --scheme
```
产出全书 `ch<N>_structure.json`（每章一个），这是后续查漏对比的**基线契约**，也是 write-source 的写作契约 + verify 的编号项基准。

**第 2 步 · 源侧查漏（dry-run，只出报告、不写回，先 review）**
```powershell
python verify/script/check_structure_completeness.py <extract_dir> [ch ...]
# 不传 <ch> 即扫全部章；报告写到 <extract_dir>/completeness_reports/ch<N>_completeness_report.json
```
复用两个**公共校验能力**（不另造判定逻辑）：
- 章节完整性 → 复用公共子流程 `verify/layers/section_continuity`（`check_d_layer`）直接重扫 `page_*.json`；
- 条目完整性 → 本脚本「标题锚定」独立扫描（全方案 / 全类型，作为抽取器的交叉校验）。
比对「书中真值集」vs 第 1 步契约，产出 `missing_sections` 与 `missing_items[{key,label,page,snippet,canon,has_label,status}]`。
**这一步只生成报告，不动 JSON**，你先 review 报告里的遗漏项。

**第 3 步 · 分流 + 回填（写书前兜底）**
按第 2 步报告里每个 `missing_items` 的 `status` 分流：
- `readable`（编号 / 标签 / 页码 / 标题都能从 OCR 干净取出）→ 脚本可**自动回填**；
- `reference`（块内命中强引用标记 see/refer to/cf./the following…，或数字前置三级无显式标签）→ **不**自动回填，交人工 / agent 复核（多半是引用而非定义）；
- `needs_agent`（OCR 字母↔数字无法干净还原）→ 交 agent 凭读图 / 知识回填（沿用 `config/manual_overrides_chN` + `（OCR无法识别）`，见 `verify/missing_label_policy.md`）。

确认 `readable` 项无误后，**先备份再写回**：
```powershell
# 写回前建议备份（防止误填可秒回退）：
#   cp ch<N>_structure.json <备份目录>/
python verify/script/check_structure_completeness.py <extract_dir> [ch ...] --backfill
```
回填节点与第 1 步**逐字段一致**（`key` 三级=`C.S-N`、两级中文=`标签C.S`、两级英文=`标签 C.S`；
`type` 共用同一张 `_LABEL_TO_TYPE` 映射；`name = "key 印刷标题"`；`page_start/page_end = 页码`），
故 write-source / verify 可原样消费。
回填后**再跑一次第 2 步 dry-run 复核**：`readable` 项应归零，剩余仅 `reference` / `needs_agent`。

> 🔴 **顺序铁律**：第 1 → 2 → 3 步必须在 **write-source 之前**完成。回填后的编号项才会作为「必须落地」节点出现在总结 MD；若先写书再回填，已写的 MD 会缺这些条目。

## 源侧完整性校验与回填（写书前兜底）

### 动机
`build_structure` 本身只做「抽取 + 合并」，**不再内嵌源侧缺口恢复**（原 `recover_missing_items` 已迁 `_legacy_`；抽取器只负责把 raw 条目抓出来）。
若只靠抽取器，漏抓的定义/定理/例会安静地缺进 JSON；且非三级书在 structure 阶段原本就无源侧查漏。
本步骤在「写书之前」调用校验层的源侧重完整性工具（`verify/script/check_structure_completeness.py`，复用 `section_continuity` 公共子流程 + 独立标题锚定扫描），把查漏从
「写完 MD 才发现」提前到「抽完即查、源侧兜底」。

### 复用的公共校验能力
- **章节完整性** → 复用公共子流程 `verify/layers/section_continuity`（语义名 **section-continuity**，
  `check_d_layer`）的 raw 重扫能力（直接扫 `page_*.json`，独立于 `extract_items`，喂空 md 即得书中真值章节集）。
- **条目完整性** → 本脚本的「标题锚定」源侧扫描（覆盖全方案 three_level / two_level / en / fraleigh / gm / roman、
  全类型 定义/定理/引理/推论/命题/例/练习），作为抽取器的**独立交叉校验**
  （抽取器行内扫描、本扫描块首锚定，二者互补，抓出被漏检的标题行条目）。

### 比对与混合回填（用户 2026-08-12 选定「混合」）
比对「书中真值集」vs `structure.json` 契约，得到遗漏章节 / 遗漏定义定理例清单，按状态分流：
- **readable（可读遗漏项）**：编号 / 标签 / 页码 / 标题均能从 OCR 干净取出 → 脚本直接插回 `structure.json`。
  回填节点与 `build_structure` **逐字段一致**（`key` 三级=`C.S-N`、两级中文=`标签C.S`、两级英文=`标签 C.S`；
  `type` 由 label 经同一张 `_LABEL_TO_TYPE` 映射；`name = "key 印刷标题"`；`page_start/page_end = 页码`），
  故 write-source / verify 可原样消费。
- **reference（疑似引用）**：块内命中强引用标记（see / refer to / cf. / the following …）或数字前置三级**无显式标签**
  → 不自动回填，交人工 / agent 复核（可能是前向引用而非定义）。
- **needs_agent（乱码 / 被吞）**：OCR 字母↔数字无法干净还原 → 交 agent 凭知识 / 读图回填（沿用
  `config/manual_overrides_chN` + `（OCR无法识别）` 既定机制，见 `verify/missing_label_policy.md`）。

### 健壮性要点
- **多位数章节号**（ch10 / ch11 …）已支持：数字串按 OCR 容错（`A→4, B→8, O→0, S→5 …`）整段归一，不再因单字符捕获而漏扫整章。
- **两级数字前置无标签**的匹配（大概率是章节号，如 `10.2`）直接丢弃，避免把章节当条目录入。
- 章节查漏复用 `section_continuity` 公共能力，与 verify 端同源，不产生第二套判定逻辑。

### 产物
`<extract_dir>/completeness_reports/ch<N>_completeness_report.json`，含：
`contract_items / raw_items_scanned / raw_sections_present / missing_sections /
missing_items[{key,label,page,snippet,canon,has_label,status}] / backfilled_items / backfilled_sections`。
先 review 报告（dry-run），确认 `readable` 项无误后再 `--backfill` 写回。

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
- **顶层**为数组，按章顺序；每章一个 `type:"chapter"` 节点。
- **`name` 带序标**：序标位置随书（前/后皆可），与原文一致；只含标题不含正文内容。
- **练习全量纳入** `type:"exercise"`（verify 展平取 key 集时过滤掉即可，不强制写作落地）。
- **`page_end`**：叶子 `== page_start`；容器（chapter/section）取**末代子孙页**。

## 构建逻辑（与 `verify/data_provider` 同一套抽取分派）
1. **章节骨架**优先来自 `scan_skeleton` 的 `SEC` 扫描（含印刷标题）；当某方案 `SEC` 捕获不全（en 两级、vakil）时，用「条目键派生章节号」补齐缺失章节。
2. **条目节点权威来自抽取器**（`extract_items` / `extract_items_en` / `extract_items_vakil` / `extract_items_gm` 等，按 `ordinal` 选路，与 data_provider 一致），`label → type`：
   `定义→definition`、`定理→theorem`、`引理→lemma`、`推论→corollary`、`命题→proposition`、`例→example`、`评注/注→remark`、`uncat→uncat`。**抽取器里的 `练习/习题` 类键被排除**（练习只来自下一步的 `EXER`）。
3. **练习来自 `scan_skeleton` 的 `EXER` 扫描**（统一来源），与条目分开，避免重复计数。
4. **挂接**：每个条目/练习优先按「派生章节号命中」挂到对应 section；命中失败则按**页码归最近 SEC**。section 的 `page_start = 子项最小页`、`page_end = 末代子孙页`（叶子 `== start`）。

## 本阶段规则（🔴 内联）
- **JSON 是契约，不是参考**：
  - 有几个 `section` 就必须写几节 `## §N.M`，顺序照抄，一个不能少、不能颠倒；
  - 每个非 `exercise` 节点都必须在总结里落地；`exercise` 按习题收录规则处理（穿插习题原位保留，章末整块习题省略），故不强制落地；
  - 节点 `name` 的印刷标题必须写进条目标签，不得丢弃；
  - JSON 里没有的编号，不许出现在总结里（无中生有）。
- **不能只靠抽取器的裸键**：它不含节标题 / 练习 / 印刷标题；只拿它写作必然漏节、乱序、丢标题。统一消费本 JSON。
- **写完后自查**：`section` 数应等于总结 `## §` 数；非 exercise 节点 `key` 集合应与总结编号一致。

## 出口条件
- 出口：全书每章 `ch<N>_structure.json` 已生成，作为 write-source 的写作契约与 verify 的编号项基准采用。

## 已知局限（实现层，非契约缺陷）
- **en 两级（ordinal=4）章节检测为近似**：skeleton 的 `SEC` 行对部分 en 书乱匹配，章节号由条目键派生，可能多出空章节（条目仍正确捕获、按序归位）。写章时以「派生章节 + 源书实际节标题」为准。
- **非标准编号书（如中文散文式「第一章…、1中导出…」）可能抽不到条目**：属该书既有局限（正则未覆盖），JSON 退化为空章节节点，不崩溃。
- **配置错配书**（如 `language=cn` 但正文为英文的 Evans）：cn 解析器抓不到章节标题，section `name` 缺标题（仅派生章节号），结构/条目仍正确。

## 相关代码（路径相对 skill 根目录）
- `flows/extract/structure/script/build_structure`：统一结构骨架生成（本子流程）。
- `flows/extract/structure/script/scan_skeleton`：`SEC` / `EXER` 扫描（被 build_structure 调用）。
- `flows/extract/structure/script/extract_items` + 变体（`_en` / `_gm` / `_vakil` 等）：编号项抽取（被 build_structure 按 `ordinal` 调用）。

## 子流程
无（`scan_skeleton` 与 `extract_items*` 为 build_structure 的内部依赖模块，不单独作为子流程）。
