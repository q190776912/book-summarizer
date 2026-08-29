# 遗漏标签处理策略（Missing-Label Policy）

> 🔴 **SSOT**：本书总结中"书中存在某条重要概念（定义/定理/引理/推论/命题），但 OCR 未识别其标题，导致总结缺失该条目"时的标准处理流程。
> 由用户 2026-08-05 制定，配套代码实现见 [`data_provider/data_provider.md`](data_provider/data_provider.md) 与 `data_provider/script/data_provider.py` 的"merged Q + over-mark 守卫"段；本文件只描述**策略与判定**，不重复代码。

## 1. 适用范围

书中某条重要概念（定义/定理/引理/推论/命题）**确实存在**，但：

- 其标题行被 OCR 的 DB 检测合并进后续段落而被"吞掉"（raw `page_*.json` 中根本无该标题块），或
- OCR 把编号/标签识别成乱码，致使抽取器未产出该条目。

→ 总结中因此**缺失该条目**，需要补回。

## 2. 两步法

### Step 1 — 先尝试让 OCR 识别出来（优先）

1. **调 OCR 参数**（`flows/write-source/structure/script/extract_items` 或抽取脚本）：
   - `--dpi`：`200` / `300` / `400`（清晰度）。
   - `det_db_unclip_ratio`：`1.6` / `1.2` / `1.0`（检测框膨胀度）。
   - `det_db_box_thresh`：`0.3` / `0.5`（检测灵敏度）。
2. **OCR 归一化**（编号重建，不改文本）：
   - 分隔符 `·` / `,` / `．` / `、` → `.`；
   - 章号首位字母↔数字容错（`A`→`4`、`B`→`8`、`O`→`0`、`S`→`5` …），用于重建被误读的键（如 `4·9-1` → `4.9-1`）。

> ⚠️ **关键限制**：若整条标题行被 DB 检测"吞掉"（raw JSON 无该块），参数调优与归一化都**无法**恢复其文本——此时该条目的标题与正文都进不了 `page_*.json`。这类情况 Step 1 必败，直接进入 Step 2。经验：调高 DPI 有时反而让相邻块分数下降（如 200→400 DPI 使邻居块 score 0.78→0.61），并非越高越好。

### Step 2 — 凭知识库补写并标注（Step 1 失败时）

1. **补写内容**：agent 依据自身数学知识 / 上下文（相邻条目、章节主题）补写该条目全文。
2. **标注来源**：在该条目标签上追加 `（OCR无法识别）`，例如：
   - `**4.9-4 定义（泛函序列的强收敛与弱星收敛）**：…（OCR无法识别）`
   - 英文书同源版同理：`**Definition 4.9.4 …（OCR 无法识别）**`。
3. **登记抽取覆盖**：在本章 `_extract/manual_overrides_ch{N}.json` 中追加该键（字段 `key` / `page` / `label` / `text`、JSON 结构与登记要点见公用配置文档 [`../config/manual_overrides_chN/manual_overrides_chN.md`](../config/manual_overrides_chN/manual_overrides_chN.md)），使抽取器承认其存在、解除 B 层序列缺口 BLOCKING。这是 skill 既定的"agent 恢复的 OCR 条目"机制（`flows/write-source/structure/script/extract_items` 第 350 行注释；覆盖项会被打 `agent_recovered` 标记）。

> ✅ Step 2 三项缺一不可：`manual_overrides` 只解 B 层 BLOCKING；`(OCR无法识别)` 标记向读者声明内容非 OCR 逐字核验、属 agent 推断；两者互补。

## 3. 两层查漏（均在 B / 查漏层，复用 `blocking` / `warnings` 键，无新契约键）

B 层本就是"查漏"层。下列两项为 B 层查漏能力的子集（整类首项缺失 + over-mark 守卫），复用 `blocking`/`warnings` 键，无新契约键。

### 3.1 整类首项缺失检测

- **仅 three-level 方案**启用（`en` / `gm` 走各自抽取，不查）。
- 扫描 raw `page_*.json` 文本块中按类别（定义/定理/引理/推论/命题）出现的标题（块首锚定 `^`，排除"由定义 4.7-1"式交叉引用），OCR 容错于章号首位字母↔数字。
- 若某节某类别在书中出现、但其**首项编号**在总结中完全缺失（该节任何同类别编号都不在 `.md`）→ 追加 `blocking`。
- **同号异类不误报**：如书为 `4.7-1` 定理、总结写成 `4.7-1` 例，因编号 `4.7-1` 已在总结中，不判首项缺失。
- 注意：标题被"吞"的条目（如 4.9-4）不会出现在 raw 扫描中，故本检查**不**负责此类；此类由 §2 Step 2 + 序列缺口兜底（见下）。

### 3.2 over-mark 守卫

- 扫描 `.md` 中带 `（OCR无法识别）` 的条目标签。
- 若该编号**已被原始 OCR 抽取识别**（即非经 `manual_overrides` 恢复）→ 追加 `warning`："标注（OCR无法识别）但书中 OCR 已识别该条目 → 可能误标，请复核"。
- **经 `manual_overrides` 恢复的条目不误报**：抽取项带 `agent_recovered` 标记，守卫跳过之（区分"真 OCR 识别"与"agent 推断恢复"）。

## 4. 序列缺口兜底（已在 B 层 `recover_missing_items`）

- `verify/script/check_structure_completeness.py`（提取侧 B 层 `_run_b_layer`）的序列连续性检查：某节抽取到 `…-1,2,3,5,6,7` 而缺 `-4` 时，先重扫页面；重扫无果 → 仍判 `blocking`（"still missing after auto-recovery"）。
- 这正是 4.9-4 被吞时的实际触发点；用 §2 Step 2 的 `manual_overrides` 登记后即解除。
- **（与 B 层 MD 侧检测的关系）** 提取侧的此 `blocking` 属辅助检测，最终受 B 层 `item_numbering_integrity.py` 的「MD 存在性过滤」约束：若被报缺的编号实际已正确写在 `.md` 中（OCR 漏检、agent 已写出），该 `blocking` 会被抑制、不阻断——故「OCR 漏检但 .md 已写对」不会误报。权威的缺号判定见 [`item_numbering_integrity/item_numbering_integrity.md`](item_numbering_integrity/item_numbering_integrity.md)（MD 侧首项检验 + 连续性）。
- 整类首项缺失（§3.1）与序列缺口（本节）是**互补**双保险：前者抓"整类首条连序列都不存在"的情形，后者抓"序列中间断号"。

## 5. 反例（为什么需要这整套机制）

- **参数调优对"标题被吞"无效**：4.9-4 整行被 DB 合并进段落，`定义` 二字在 200 / 400 DPI 下均未被识别；400 DPI 还使相邻块质量下降。必须走 Step 2。
- **只标 (OCR无法识别) 不登记 override → 验证仍 FAIL**：B 层序列缺口与 `.md` 内容无关，缺 `manual_overrides` 登记会持续 `blocking`。
- **只登记 override 不标 (OCR无法识别) → 读者无法分辨 agent 推断内容**：失去来源透明性，违背保真原则。

## 6. 相关文件

- 代码：`data_provider/script/data_provider.py`（`_scan_book_category_items` / `_merged_category_first_missing` / `_merged_ocr_overmark_guard`）。
- 抽取覆盖：`flows/write-source/structure/script/extract_items`（`manual_overrides` 合并 + `agent_recovered` 标记）、各书 `_extract/manual_overrides_ch{N}.json`。
- 注册表：[`verify.md`](verify.md) 第 1 节（B 层）、第 3 节同步清单（本策略无新契约键，仅复用 `blocking`/`warnings`）。
