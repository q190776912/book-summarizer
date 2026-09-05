# `ignore_ch{N}.json` / `ignore_fig_ch{N}.json` 配置说明

> 每章一个的 verify 豁免配置文件，位于本书 `_extract/`。不进 skill 目录。`verify_chapter.py` 经 `--ignore <ext>/ignore_ch{N}.json`、`--ignore-figure <ext>/ignore_fig_ch{N}.json` 传入；脚本会自动合并同章两份文件（存在即读）。**附录章**文件名段走 `chapter_label`：`ignore_appendix{X}.json`（X=A..Z），`manage_ignore.py --chapter A` 即读写该文件；"ch" 只属于数字章。

## 结构

两种写法均支持：

| 写法 | 形式 | 说明 |
|------|------|------|
| 列表 | `["1.7-0", "2.3-4"]` | 仅声明被忽略的键。 |
| 字典 | `{"1.7-0": "交叉引用误标", "2.3-4": "OCR 乱码"}` | 键 + 原因（便于审计举证）。 |

- `ignore_ch{N}.json`：条目级忽略键（编号项，如 `"1.7-0"`）。
- `ignore_fig_ch{N}.json`：图片级噪声豁免（`--ignore-figure`），数组如 `["6.7.9"]` 或字典。

## JSON 示例

列表写法（仅声明被忽略的键）：

```json
["1.7-0", "2.3-4"]
```

字典写法（键 + 原因，便于审计举证）：

```json
{
  "1.7-0": "交叉引用误标",
  "2.3-4": "OCR 乱码"
}
```

## 登记规则（强制）

1. **作用域：每章一个文件**（`ignore_ch{N}.json`），随章传入 `--ignore`。**禁止全局单一文件**。
2. **字符型编号键**须用规范短横形式（如 `1.7-0`）；与 `verify_config.json` 的 `ordinal` 分组同源。
3. **禁止忽略真实条目**：书里确有、应独立成条的编号项，**绝不可进 ignore**。
4. **举证责任**：每条 ignore 必须能在 raw 页面文本中定位到来源块并确认是乱码 / 交叉引用。
5. **暂定性质**：ignore 非永久删除；若后续发现该键实为真实项，必须从 ignore 移除并补写。
6. **B 层 BLOCKING 解决优先级**：先尝试补真实项；仅当确认是 (a) 乱码 / (b) 交叉引用时才进 ignore。

## 审核逻辑（强制 · 防误用隐藏真实缺项）

`ignore` 只应抑制「.md 中真实存在、但属 OCR 乱码 / 交叉引用误标」的条头，**绝不可用于掩盖源侧序列洞**（被忽略的编号在 .md 中本就不存在 —— 那是真实缺项，应经 `manual_overrides_chN.json` 补回）。2.1-4 / 4.9-3 即此类误用：把序列洞塞进 ignore 隐藏缺口。

每条 ignore 在登记 / 合入前，**必须由 agent 审核**是否真噪声：

- **审核工具**：`verify/script/audit_ignore.py`
  ```bash
  python verify/script/audit_ignore.py <_extract> [--chapter N] [--json]
  ```
    逐条核对 ignore 条目与契约（分章契约 book_structure/ch{N}.json）及源（page_*.json）的关系，给出判定：
    - **SUSPECT**（退出码 1）：ignore 了真实存在的条目 / 掩盖连续序列洞（前后皆契约正邻居且无证据）/ 源侧有『带标签但无编号』条头（OCR 丢号迹象）→ 优先用 `manual_overrides_ch{N}.json` 补回真实缺项；仅当确认确为书本身稀疏编号才保留 ignore 并补举证。
    - **SAFE**：契约无前后邻居、源侧无对应内容 → 疑似真·OCR 噪点 / 稀疏编号（agent 复核并举证）。
    - 🟢 **ACCEPTED**（非阻断）：序列洞型 ignore（`prev`/`nxt` 均在契约中），但**理由含显式证据标记**（`VERIFIED-SPARSE` / `源书真实跳号` / `已核实跳号` / `sparse numbering`）→ 判为「书源真实无此号，总结如实省略，非隐藏缺项」。该 verdict 不计入 SUSPECT、不抬高退出码（`audit_ignore.py` 退出码仍为 0，校验可 PASS），仅作非阻断记录。**无证据标记的序列洞 ignore 一律仍判 SUSPECT**——证据标记是本例外的唯一开关，防误用护栏不降级。
    - 📌 **证据标记约定（强制）**：要让序列洞 ignore 走 ACCEPTED 而非 SUSPECT，其理由字符串**必须包含**上述四个标记之一（推荐开头写 `VERIFIED-SPARSE ...`）。原因须明确指出该节在源书中的真实编号断点（如「§4.9 实际编号 4.9-1、4.9-2，随后直接跳到 4.9-4，page_280 末为 4.9-2、page_281 起为 4.9-4 Definition」），使后续审计 / 人工复核可一键确认。
- **B 层护栏**：`item_numbering_integrity` 的 `emit` 已加护栏——`ignore` 仅当被忽略编号在 .md 中**真实存在**（现令牌头）时才抑制；若被忽略的是序列洞（编号不存在），不再静默放行，而发出 `[IGNORE-SUSPECT]` 警告交由 agent 复核。
- **写书前校验**：`check_structure_completeness.py` 会在报告中附 `ignore_audit` 字段（SUSPECT 数），CLI 输出 `IGNORE-AUDIT(suspect=N)`，便于写书前发现误用。
- **🔴 B 层（D/B 结构完整性域）校验流程强制最后一步**：本审计只作用于**编号 ignore**（B 层 `item_numbering_integrity` 消费集合），是 D 层（§ 结构连续性）与 B 层（条目编号）这一"结构完整性"域的收尾步骤，**不是对所有校验层的全局末步**——Q 层 `formula.ignore`、E 层 `ignore_fig` 各有独立命名空间，不在此审计范围。`verify_chapter.py`（单章模式审该章、`--all` 模式审全书）已在 B 层收尾**自动执行本审计**，且仅当存在编号 ignore 时才生效（无编号 ignore 静默跳过）；出现 SUSPECT 时整体退出码非 0，校验不得判 PASS。即"有编号 ignore 的 D/B 校验流程就必须 agent 审计"不是建议而是流程硬步骤——登记 / 修改编号 ignore 后跑 `verify_chapter.py`，收尾的 `[IGNORE-AUDIT]` 报告即本步证据；SUSPECT 须先经 `manual_overrides` 补回或补举证再重验。

## 维护脚本

- `manage_ignore.py`：交互式登记 / 检视 `ignore_ch{N}.json`。
- `audit_ignore.py`：审核 ignore 条目是否真噪声（见上）。
