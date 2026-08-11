# mm_repair_manifest

`manifest.json` 是 **mm_repair 流水线的运行态文件**（apply / text_compare / audit 三阶段共享），记录每一页、每个条目的修复状态。

本目录只放一层**边界适配（Anti-Corruption Layer）**：`mm_repair_manifest.py` 提供 `MmRepairManifest.load(path)` / `.dump(path)`，`raw dict` 原样存于 `.data`，不建模其字段。

> 规则：`../../flows`、`../../verify` 里读写 `manifest.json` 一律走 `MmRepairManifest`，不得出现裸 `json.load` / `json.dump`。

## 示例

```json
{
  "pages": {
    "12": {
      "entries": [
        {"key": "text:I", "resolved": false, "action": "repair"},
        {"key": "formula:3", "resolved": true, "action": "ok"}
      ]
    }
  },
  "applied": 3,
  "reviewed": 1,
  "converted": 0,
  "converted_text": 0,
  "status": "applied"
}
```
