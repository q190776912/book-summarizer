# `manual_overrides_ch{N}.json` 配置说明

> 每章一个的抽取覆盖配置文件，位于本书 `_extract/manual_overrides_ch{N}.json`。当 OCR 完全吃掉某条目标题、且调参 / 归一化均无法识别时，agent 凭知识库补写该条目并登记本文件，使 `flows/extract/structure/script/extract_items` 承认其存在、解除 B 层序列缺口 BLOCKING。覆盖项会被抽取器打 `agent_recovered` 标记（与"真 OCR 识别"区分）。

## 结构

JSON **对象数组**，每个元素：

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | `str` | 编号键（如 `"4.9-4"`），须能在 raw 页面文本中定位来源块。 |
| `label` | `str` | 条目名（如 `"定义"`、`"定理"`）。 |
| `page` | `int` | 该条目所在页。 |
| `text` | `str` | 条目文本 / 内容（agent 推断补写）。

## JSON 示例

```json
[
  {
    "key": "4.9-4",
    "label": "定义",
    "page": 73,
    "text": "（OCR 完全吃掉标题，凭知识库补写）该定义阐述 …"
  }
]
``` |

## 登记要点

- 与 `ignore_ch{N}.json` 互补：**`manual_overrides` 解 B 层 BLOCKING（承认条目存在）**，`(OCR无法识别)` 标记向读者声明内容非 OCR 逐字核验、属 agent 推断。只标 `(OCR无法识别)` 而不登记本文件 → 验证仍 FAIL（B 层序列缺口与 `.md` 内容无关）。
- 完整两步法策略见 [`../../verify/missing_label_policy.md`](../../verify/missing_label_policy.md)（SSOT）。
