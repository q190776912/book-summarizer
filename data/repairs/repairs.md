# repairs.json（MM Repair 修复记录）

## 生成脚本
- `repairs.py`：合并多 agent 各自写出的 `repairs.json`。
- 类与构造函数：`Repairs` —— `from repairs import Repairs`；`Repairs.merge(mm_dir)` 构造，`Repairs(...).dump(path)`；
  亦可用 `Repairs.from_sections(corrections, ok, to_structured, deferred)`。`mm_repair_text_compare.py` 经 `Repairs(**repairs).dump(path)` 委托写出（裸 `json.dump` 已移出流程脚本，实例化归本目录）。
- **消费者**（`mm_repair_audit.py` / `mm_repair_text_compare.py` / `mm_repair_apply.py` /
  `rereview_montage.py`）属 MM Repair 链路编排，**留 `../../flows`**。

## 落盘位置
- `<book>/_extract/repairs.json`（由各 agent 的修复产出经 `merge_repairs.py` 合并得到）。

## 数据结构（要点）
`repairs.json` 是**按页 / 条目组织的修复记录集合**。每条修复记录承载：
- 定位信息：页码 `page`、条目坐标 `bbox` / 索引；
- 原文备份：`text_ocr` / `latex_ocr`（修正前）；
- 修正结果：`text` / `latex`（修正后）；
- 状态标记：`mm_repaired: true`（已回写）、`mm_reviewed: true`（已确认）、`mm_unavailable: true`（不可恢复、跳过）；
- 结构化转换 `to_structured`：文本↔公式双向转换的段列表
  `[{"type":"text","text":"("},{"type":"formula","latex":"k=0,1,\\dots,n"}, …]`；
- 判定：`ok` / `corrections`（已解决）/ `deferred`（交模式 A）/ `unavailable`（不可恢复，跳过）/ `resolved`。
- 不可恢复标记：`mm_unavailable: true`（per-entry，经多轮视觉审读仍不可恢复，或**无视觉识别（`VISION = no`）时模式 B 无法可靠修复**（公式 / 文本层损坏）；下游 `dump_chapter_ocr.py` 跳过、不污染内容；页级同时置 `MM_UNAVAILABLE: true`）。

> 具体字段以 MM Repair 链路运行时写出为准；本文件仅描述聚合层级与关键标记。

## JSON 示例

```json
{
  "corrections": {
    "p12": {
      "text:I": {
        "text_ocr": "定理2.1 设 X 为 …",
        "text": "定理 2.1 设 X 为 …",
        "bbox": [120, 300, 880, 1200],
        "mm_repaired": true,
        "mm_reviewed": true
      }
    }
  },
  "ok": {
    "p15": ["text:I", "formula:J"]
  },
  "to_structured": {
    "p18": {
      "s1": [
        {"type": "text", "text": "("},
        {"type": "formula", "latex": "k=0,1,\\dots,n"},
        {"type": "text", "text": ")"}
      ]
    }
  },
  "deferred": {
    "p20": ["formula:K"]
  },
  "unavailable": {
    "p91": ["text:23", "formula:4"]
  }
}
```

- `corrections`：需修正的条目，键为页码（如 `"p12"`），值为 `{条目键: {原文备份 / 修正结果 / 状态标记}}`；
- `ok`：无需修正的条目键列表，按页归集；
- `to_structured`：文本↔公式双向转换段列表，按页归集；
- `deferred`：`mm_repair_text_compare.py` 留给视觉 agent 的未决条目键列表，按页归集。
- `unavailable`：不可恢复条目的键列表（纯 OCR 噪声 / 严重乱码碎片，经多轮视觉审读仍不可恢复；或 `VISION = no`（用户拒绝视觉识别）时模式 B 无法可靠修复的公式 / deferred 条目），按页归集，形态同 `ok` / `deferred`；下游 `mm_repair_apply.py` 标 per-entry `mm_unavailable` + 页级 `MM_UNAVAILABLE` 并放行（`resolved=True`），writer 阶段（`dump_chapter_ocr.py`）跳过、不污染内容。

## 消费方
- `mm_repair_apply.py`：把 `repairs.json` 的修正**写回 `page_*.json`**（保持 schema 不变、
  UTF-8、JSON 合法），并完成 `to_structured` 双向转换。

## 详细流程
- 子流程文档：`../../flows/extract/mm_repair/mm_repair.md`
