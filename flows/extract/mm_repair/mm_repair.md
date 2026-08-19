# Sub-flow: extract / mm_repair（MM Repair 链路）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
对 OCR / 公式识别置信度不足的区域，用多模态（或文本层）能力重新识别并**写回** `page_*.json`，降低后续写作的 OCR 噪声。
## 前置
- PDF 路径与 `_extract` 目录已知。

## 两种模式（A / B）

> 本流程本身即"混合策略"：文本类书先走模式 B 修文字、再走模式 A（若视觉识别启用 `VISION = yes`）处理公式；非文本类书直接走模式 A（同样受 `VISION` 决策约束，见 Step 1）。故不单列"混合策略"模式。

- **模式 A（多模态视觉审读）**：视觉识别启用（`VISION = yes`）且模型具备识图能力时，对审计标出的条目做 agent 视觉读真实印刷页修正。
- **模式 B（文本层补偿，无需看图）**：书籍为**文本类**（PDF 含可选中数字文本层）→ 从 PDF 抽干净数字文本与低置信 OCR 比对修正。

文本类 vs 扫描版可用 `mm_repair_text_compare.py` 自动探测（取样页可选中词数 ≥30/页判文本类），或 `--force-text` / `--force-scan` 覆盖。

## 步骤（有序，5 步）

**Step 1 — 视觉识别决策（询问式，全书仅此一次）**
- 本书是否做视觉识别（模式 A），已在 extract Step 2 启动后台提取**前**询问用户并写入 `_extract/_mm_repair/vision_decision.json`（`{"enabled": true|false}`）。此处**只读取、不再询问**：
  - `VISION = yes`（`enabled: true`，用户启用）→ 继续 Step 2，后续模式 A 照常跑。
  - `VISION = no`（`enabled: false`，用户拒绝）→ **全书跳过模式 A，不得做任何视觉识别**（除非用户主动要求恢复，见下）：
    - 文本类书 → 仅走模式 B（Step 3）；模式 B 无法可靠修复的条目（公式条目 / 文本层损坏的 deferred）在 Step 4 如实记 `unavailable`（成因：无视觉识别 → 不可恢复），由 apply 标 `mm_unavailable` 放行，**绝不编造修正值**；
    - 非文本类书 → **整书标 `MM_UNAVAILABLE`**（全部 flagged 条目直接 `resolved=True`，跳过修复），返回 extract 轮询循环。
- **中途续跑 / 未经询问**（如 `vision_decision.json` 缺失）→ 在此**补问一次**并写入该文件（补问措辞同 extract Step 2，须说明视觉识别**耗时会明显变长**）；全书合计仍只问一次。
- 模型实际无识图能力（即使 `VISION = yes`）→ 告知用户后按「无视觉识别」同等处理（文本类仅模式 B；非文本类整书 `MM_UNAVAILABLE`）。
- 🔴 **拒绝后恢复的唯一途径**：仅当用户**主动要求**时才临时启用模式 A，且只覆盖其要求范围（如某章公式修不好）；除此之外，不得因任何批次 / 任何理由重新询问或自行视觉识别。临时启用与全局决策的差异须在 `vision_decision.json` 备注说明。

**Step 2 — 审计（纯 CPU，无需看图）**〔原第一步〕
```powershell
python flows/extract/mm_repair/script/mm_repair_audit.py "<pdf_path>" "<_extract_dir>" --text-thresh 0.80 --formula-conf 0.30 --vpad-lines 0.5
```
产出：`_mm_repair/manifest.json`（待审条目）、`_mm_repair/page_NNN_sheet.png`（拼版图）、`_mm_repair/page_NNN/*.png`（单裁图）。无标记则输出 `MM_AUDIT DONE: nothing flagged`，本步完成，返回 extract 轮询循环。

**Step 3 — 模式 B（仅文本类书籍）**
- 若书籍为文本类 → 跑模式 B（加 `--hybrid`，公式与不可信文字保持未解决交模式 A）：
```powershell
python flows/extract/mm_repair/script/mm_repair_text_compare.py "<pdf_path>" "<_extract_dir>" --src-dpi 200 --hybrid
```
  - 数字文字干净且与 OCR 不同 → `corrections`（标 resolved）；一致 / 为空 → `ok`（标 resolved）；
  - 含白名单外字符（tofu）/ 差异过大 → 保持未解决（`deferred` 交模式 A）；
  - 公式条目无文本层 → 保持未解决，必须交模式 A（若 `VISION = no` 则按 Step 4 记 `unavailable`），不可直接跳过。
  - ⚠️ 文本层损坏（tofu，如 Ross《A First Course in Probability》）风险：若 `corrections` 几乎全是乱码、绝大多数被 KEEP，说明文本层损坏，应放弃模式 B（当 `--force-scan` / `MM_UNAVAILABLE` 跳过），公式改由模式 A 处理（若 `VISION = yes`）。
  - 🔴 **模式 B 信任复核（强制，见规则5）**：模式 B 写回的 `corrections` 是**候选修正**，数字文本层本身可能抽花（本书实测 p553 / p565 / p233 等把文本层抽成乱序 / 错位 / 正文串入）。跑完 `--hybrid` 后，agent **必须逐条审阅 `repairs.json` 的 `corrections`**：任一存疑 / 不可信条目，**从 `corrections` 删除并保留 / 移入 `deferred`**，确保 `apply` 只写回可信修正；**不可信数据一律不写回，交模式 A 视觉识别（若 `VISION = no` 则如实记 `unavailable`，见 Step 4）**。
- 非文本类 → 跳过本步。

**Step 4 — 模式 A（仅当视觉识别启用且模型具备识图能力）**
- 若 `VISION = yes`（Step 1 决策）且模型具备识图能力 → 跑模式 A：agent 读 `page_NNN_sheet.png` + manifest，按标签判断：
  - 正确 → 记 `ok`；错误 → 在 `corrections` 写正确文本 / LaTeX；
  - 实为公式（OCR 误当文本行）→ 在 `to_structured` 写结构化结果（见 Step 5 说明，apply 会转成 `formulas[]` 新条目）；
  - **公式 + 文本混合行** → 在 `to_structured` 用分段列表写出（一行可含**多个公式 + 多个文本**交错，例如 `("("` + `k=0,1,\dots,n` + `")"`）。
  - 实为文本（MFD 误把纯文本当公式）→ 在 `to_structured` 对该 `formula:<i>` 写文本串 / 分段，apply 会把公式项从 `formulas[]` 移回 `text[]`（见 Step 5 说明）。
  - **🔴 经多轮视觉审读仍不可恢复 → 记 `unavailable`（不可读，跳过）**：纯 OCR 噪声（孤立 `@` / `&` / 游标字符 / 近空行）或严重乱码碎片，经多轮（含重派）视觉审读一致判为不可恢复 → 在 `unavailable` 段按页列出条目键（`{"unavailable": {"091": ["text:23"], ...}}`，**形态同 `ok` 的列表**，不是字典）。apply 会标 `mm_unavailable` 并放行（见 Step 5 + 出口），**下游 write-source / verify 跳过、不污染内容**。🔴 绝不可为凑 resolved 计数而强行编造修正值——不可恢复就是不可恢复，诚实标 `unavailable` 优于假修正。
- 若 `VISION = no` 或模型无识图能力 → **跳过视觉审读**：deferred / 公式条目已无可信修复途径（无视觉识别即不可恢复），**如实记 `unavailable`**（逐条列进 `repairs.json` 的 `unavailable` 段，形态同 `ok`，见 Step 5），由 apply 标 `mm_unavailable` 放行、下游跳过，**绝不编造修正值**；整书无视觉的非文本类书走 Step 1 的整书 `MM_UNAVAILABLE` 路径。

**Step 5 — 应用（写回 page JSON）**
```powershell
python flows/extract/mm_repair/script/mm_repair_apply.py "<_extract_dir>"
```
  - `to_structured`：双向结构化转换，作用于两类被误判的条目：
    - **作用于 text 项**（OCR 误当文本、实为公式）：转成 `formulas[]` 新条目 + 行内文本段；
    - **作用于 formula 项**（MFD 误当公式、实为文本）：把公式项从 `formulas[]` 移回 `text[]`（设 `mm_converted=true`），还原为文本。
    - 两种形态（对 text / formula 都适用）：
      - ① 字符串：整行即一个公式（text 方向）/ 整条即一个文本串（formula 方向）；
      - ② 分段列表：`[{"type":"text","text":"("},{"type":"formula","latex":"k = 0,1,\\dots,n"},{"type":"text","text":")"}]` —— 一行是「文本 + 公式 + 文本 + …」交错，按各段权重切子区间、保留行内阅读顺序，而非压成单一公式。formula 方向的分段列表若同时含 formula 段，则文本段转回 `text[]`、公式段保留为原公式项的 `latex`。
    - text 方向：原 text 项被这些段整体替代 / 删除；formula 方向：原 formula 项被删除（纯文本）或保留（含公式段时更新 `latex`）。
  - 修正条目：`text`/`latex` 更新，原值存 `text_ocr`/`latex_ocr`，加 `mm_repaired: true`；
  - 确认 OK：加 `mm_reviewed: true`。
  - **`unavailable`（不可恢复，跳过，不污染内容）**：条目经多轮视觉审读仍判为不可恢复（纯 OCR 噪声 / 严重乱码碎片）→ 设 per-entry `mm_unavailable: true` + 页级 `data["MM_UNAVAILABLE"] = true` + manifest 该条目 `resolved = true`（闸门放行，满足出口「每页至少一标记」）。下游 `dump_chapter_ocr.py` 导出 OCR 时跳过（`if fo.get("mm_unavailable"): continue` / `if t.get("mm_unavailable"): continue`），writer agent 不会看到垃圾条目，内容不被污染。🔴 不可恢复必须诚实标 `unavailable`，**绝不强行编造修正值**（会污染书内容）。
  - **幂等**：manifest 已 `resolved` 的条目（含 `mm_repaired` / `mm_reviewed` / `mm_unavailable`）一律跳过（apply 开头 `if e.get("resolved"): continue`），重复跑安全。
- 回写后立即 `json.load` 复验（保持 schema 不变、UTF-8、JSON 合法）。

**完整命令序列（5 步）**
```powershell
# Step 1：视觉识别决策（询问式，extract Step 2 启动提取前已问一次；此处读 vision_decision.json，无命令）
# Step 2：审计
python flows/extract/mm_repair/script/mm_repair_audit.py      "<pdf>" "<_extract>" --src-dpi 200
# Step 3：模式 B（文本类，--hybrid 把公式/deferred 留给模式 A；VISION=no 时改记 unavailable）
python flows/extract/mm_repair/script/mm_repair_text_compare.py "<pdf>" "<_extract>" --src-dpi 200 --hybrid
# （可选）重跑审计：模式 B 已修文字跳过，仅公式/deferred 重新标出交模式 A
python flows/extract/mm_repair/script/mm_repair_audit.py      "<pdf>" "<_extract>" --src-dpi 200
# Step 4：模式 A（仅 VISION=yes）—— agent 读 *_sheet.png + manifest 写 repairs.json（含 to_structured）；VISION=no 时跳过读图，deferred 如实记 unavailable
# Step 5：应用写回
python flows/extract/mm_repair/script/mm_repair_apply.py      "<_extract>"
```

## 本阶段规则（🔴 内联）
- **规则1 — MM Repair 门（必须跑，且必须 `apply` 写回）**：提取 100% 完结也必须跑：无新页可轮询时不能跳过本步，须对全书跑**完整链路（audit → 模式 B/A → Step 5 `apply` 写回 `page_*.json` → 出口验证）**。🔴 只跑到 `audit` + `text_compare` 产出 `repairs.json` 而**未执行 `apply` 写回**，视为**未完成**，严禁流入 config / structure / write-source。
- **规则2 — 阈值**：`--text-thresh 0.80`（OCR `score<0.80` 才触发）、`--formula-conf 0.30`（`conf<0.30` 或 `latex` 含 `[MFR_ERR`/`[MFR_SKIPPED`/`.notdef`/替换字符 `�` 触发）、`--vpad-lines 0.5`。可按书调整。
- **规则3 — 回写纪律**：确认后必须**写回 `page_*.json`**（保持 schema 不变、UTF-8、JSON 合法），不可只写进 md；回写后立即 `json.load` 复验。仅"写法差异含义相同"不视为修正，无需回写。
- **规则4 — 职责边界**：MM Repair 只改 `page_*.json` 结构化数据，不动 `.md`；公式 / 文字的语义级"理解后重写"若发生在写作阶段则属另一阶段，与本节无关。
- **规则5 — 模式 B「可信才用」死规则（🔴 不可违背）**：模式 B 的 `corrections` 来自 PDF 数字文本层，**不等于已验证正确**，文本层本身可抽花（数字文本层 ≠ 印刷页真值）。agent 必须严格遵守以下四条，优先级高于"尽快修完"：
  1. **仅可信才写回（apply）**：`corrections` 仅当数字文本层值与上下文语义一致、无乱码 / 无错位 / 无孤立字符堆砌、且与 OCR 能对应上时，才允许 `apply` 写回 `page_*.json`；
  2. **不可信一律不写回**：任何判定为不可信的 `corrections` 都**不得 `apply`**——宁可该条目暂时漏修，也绝不可用不可信值覆盖原始 OCR；
  3. **不可信交模式 A**：凡是不可信条目，必须保留 / 移入 `deferred`，后续交给**模式 A 视觉识别**读真实印刷页重新修正（若 `VISION = no`，则按 Step 4 如实记 `unavailable`），**绝不允许**用模式 B 的不可信值替代；
  4. **存疑默认不可信**：判定存疑时**默认走模式 A**；"可信"需 agent 显式确认，"不可信"是默认态。
  - 🔴 **严禁**为追求 resolved 计数而把不可信 `corrections` 批量 `apply`。模式 B 是"辅助候选"，不是"权威结论"；信任权永远在 agent 手里，不可信数据一律走模式 A（`VISION = no` 时记 `unavailable`）。
- **规则6 — 视觉识别询问式（全书仅一次，🔴 不可违背）**：是否启用模式 A 由用户在 extract Step 2（启动后台提取前）决定一次，写入 `vision_decision.json`（`VISION = yes/no`）；中途续跑缺文件时由 Step 1 补问一次，全书合计只问一次。
  1. **拒绝后不视觉识别**：`VISION = no` → 全书跳过模式 A，**严禁** agent 自行读 `*_sheet.png` / 单裁图做视觉审读（含拆子代理时，须把决策传给子代理）；
  2. **拒绝后不重复询问**：不得因每个稳定批次 / 每章 / 每次审计再问「要不要视觉识别」；
  3. **恢复仅凭用户主动要求**：只有用户明确要求时才能临时启用模式 A，且只覆盖其要求范围；临时启用须在 `vision_decision.json` 备注，不得擅自扩大。
  4. `VISION = no` 时模式 B 无法可靠修复的条目（公式 / 文本层损坏）**如实记 `unavailable`**（无视觉识别即不可恢复），绝不编造修正值。

## 出口条件
- 🔴 **出口 = `apply` 已写回 `page_*.json`，不是 `repairs.json` 里有 resolved 条目，也不是 `manifest.status == "applied"`。** `page_*.json` 条目真正带上 `mm_repaired`/`mm_reviewed` 标记**才是唯一可靠信号**。`mm_repair_apply.py` 跑完会**无条件**把 `manifest.status` 设为 `"applied"`（与未 resolved 条目数无关），故 **`manifest.status == "applied"` 绝不能当完成判据**——会出现"已 applied 但仍有大量未修条目"的假绿（stochastic 实测：status=applied 但 2842 条目仅 979 resolved）。仅 `repairs.json` 含 resolved（由 `audit` + `text_compare` 产出）而未跑 `apply` 属**未完成**，config / structure / write-source 一律严禁启动。
- **完成判据（两者必须同时满足，且都只看 page_*.json 与 manifest 条目级，绝不依赖 `manifest.status`）**：
  1. **条目全部 resolved**：`_mm_repair/repairs.json` 中审计标出的条目**全部 resolved**（都有 `corrections` / `ok` / `to_structured` 处置），且 `manifest` 中**每个条目的 `resolved == true`**（统计 `manifest['pages'][p]['entries']` 全部 resolved，计数须 == 总条目数）；**且**
  2. **每页标记落盘**：`page_*.json` 条目里出现 `mm_repaired` / `mm_reviewed` 标记（修正已落盘），且**本书每一页** `page_*.json` 都至少含一个该类标记（或显式 `MM_UNAVAILABLE`）——任一页缺标记即视为未完成。
- 无视觉识别（用户拒绝 `VISION = no` 或模型无识图能力）且非文本类的书：记 `MM_UNAVAILABLE` **显式标注**（须在出口确认），表示该书/该章跳过修复，此时允许进入后续阶段。
- **`MM_UNAVAILABLE` 两种来源（出口「每页至少一标记」都接受，闸门都放行）**：
  1. **条目级 `unavailable`（本书有视觉能力、个别条目不可恢复）**：agent 在 `repairs.json` 的 `unavailable` 段逐条列出不可恢复条目 → apply 设 per-entry `mm_unavailable: true` + 页级 `MM_UNAVAILABLE: true` + 该条目 `resolved=True`。下游 `dump_chapter_ocr.py` 跳过这些条目，不污染内容（见 Step 4 / Step 5 说明）。
  2. **整书 / 整章无视觉识别（Step 1）**：`VISION = no`（用户拒绝）或模型无识图能力、且非文本类 → 整本书 / 章标 `MM_UNAVAILABLE`，全部 flagged 条目直接 `resolved=True`。文本类书 `VISION = no` 时，模式 B 无法修复的公式 / deferred 条目按条目级 `unavailable`（成因：无视觉识别，不可恢复）同样放行。
  - 两者页级标记都是 `MM_UNAVAILABLE`，出口判定都满足；区别在**成因**（个别不可恢复 vs 全书无法修），不影响闸门放行。🔴 **凡标 `MM_UNAVAILABLE` 的页，writer 阶段都不得把这些条目当作真实内容写入 `.md`**——它们是噪声 / 不可读，跳过是设计意图。

### 🔴 如何验证 `apply` 已真正写回（防误判，必做）
- **字段名只有 `mm_repaired` / `mm_reviewed`（及 `mm_converted`）；`page_*.json` 里根本不存在 `mm_status` 这个字段。** 不要再 grep `mm_status`——它会永远为 0。
- 🔴 **`manifest.status` 也是假信号，不可信**：`mm_repair_apply.py` 跑完即把 `status` 设为 `"applied"`，与未 resolved 条目数无关。stochastic 实测：`status=='applied'` 但 2842 条目仅 resolved 979、1863 未 resolved。所以**验证只看 page_*.json 标记 + manifest 条目级 resolved 计数，绝不单看 status**。
- **验证命令（任选其一，都只看真实落盘）**：
  ```bash
  # (A) 统计全书 page_*.json 中已写回的标记数量（列出仍为 :0 的页 = 未修完）
  grep -rc '"mm_repaired": true\|"mm_reviewed": true' <_extract>/page_*.json | grep -v ':0'
  # (B) 条目级 resolved 计数（须 == 总条目数才真完成；status 字段忽略）
  python -c "import json; m=json.load(open('<_extract>/_mm_repair/manifest.json')); e=[x for p in m['pages'].values() for x in p['entries']]; print('resolved', sum(1 for x in e if x.get('resolved')), '/', len(e))"
  ```
- **反例（本次踩坑，两类）**：
  - **类1（未跑 apply）**：只跑 `audit` + `text_compare` → 产出 `repairs.json`（含 856 条 resolved）但**从未执行 `apply`** → `page_*.json` 无标记 → 属**未完成**。
  - **类2（apply 假绿）**：跑过 `apply` 但只 resolve 了部分条目（如 979/2842）→ `manifest.status == "applied"` 为真，但 `page_*.json` 仍有大量缺标记 → 仍属**未完成**。两类都严禁据此进入 config / structure / write-source。

## 相关代码（路径相对 skill 根目录）
- `script/mm_repair_audit.py`：扫描低置信条目 + 裁图拼版（纯 CPU）。
- `script/mm_repair_text_compare.py`：模式 B 文本层补偿（含 `--hybrid`）。
- `script/mm_repair_apply.py`：把 `repairs.json` 写回 page JSON（含 `to_structured` 转换）。
- `../../../data/repairs/repairs.py`（数据结构见 [data/repairs/repairs.md](../../../data/repairs/repairs.md)）：合并多 agent 的 `repairs.json`。
- `script/rereview_montage.py`：重审拼版辅助。

## 子流程
无。
