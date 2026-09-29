# repairs.json（MM Repair 修复记录）

## 生成脚本
- `repairs.py`：合并多 agent 各自写出的分片（`repairs_part_*.json` / `_frag_*.json`）为 `repairs.json`。
  - `python data/repairs/repairs.py <mm_repair_dir> [<extract_dir>] [--base <repairs.modeB.json>]`
  - 🔴 **模式 B + 模式 A 并存的书必须带 `--base`**：模式 B 的候选就写在 `repairs.json` 本身，
    先 `cp` 留底再当 base 折叠，否则合并会用分片覆盖、把模式 B 的成果整体丢掉。
  - 🔴 **跨段裁决**：base 里的条目一旦被某个分片改判，会从**所有其他段**清除后再落新判。
    原因 = `mm_repair_apply.py` 按固定优先序 `corrections > ok > to_structured > unavailable`
    逐条取段，同键跨段并存时旧文本层候选会静默压过新的视觉裁决。
  - **三道 fail-closed 闸门全过才写 `repairs.json`**：① manifest 覆盖（每条有裁决，`deferred` 不算）；
    ② 无碰撞（同一条不被两个分片裁决，否则 apply 只能按段优先序任意挑一个）；③ **模式 B 声明逐条已裁决**
    （`ok` 在内嵌文本层本身是老 OCR 的书里只是**同源同错的假确证**，沉默≠确认）。
    任一失败 = `exit 1` 且**不产出** `repairs.json`（磁盘上若残留旧文件即 STALE），同时写
    `<mm_repair_dir>/_merge_report.json`（完整清单 + 计数，机器可读，用于排波）；
    `mm_repair_apply.py` 的 `open_verdict_gate` 读**同一份**报告，脏则拒绝写回（检测趟与修复趟共用一个谓词）。
    另：`--base` 指向输出文件本身也是 `exit 1`。
  - **报告**：分片之间重复裁决 = COLLISIONS；base 判决（`corrections` **与 `ok` 都算**）落在「分片复核过的页」却没被点名
    = `MODE-B VERDICTS ON RE-REVIEWED PAGES, NEVER RULED`；base 判决在**任何分片都没去过的页** = `... ON PAGES NO AGENT VISITED`。
    两者都不是"沉默即确认"：`ok` 只证明「内嵌文本层与流水线 OCR 一致」，**文本层本身是老 OCR 时两边同源同错**，必须有视觉判决才算落账。
  - 判据测试：`data/repairs/tests/test_repairs_merge.py`。
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
