# kreyszig_map

Kreyszig 专属的公式**重编号 / 对账**产物：`renumber_map.json`、`recon_chN.json`、`recon_all.json`。属于书级专用、非通用建模产物，因此只放一层**边界适配**：`kreyszig_map.py` 提供 `KreyszigMap.load(path)` / `.dump(path)`，`raw dict` 原样存于 `.data`。

> 规则：`../../flows`、`../../verify` 里读写这些 map 一律走 `KreyszigMap`，不得出现裸 `json.load` / `json.dump`。

## 示例（renumber_map.json）

```json
{
  "1": {"2.1-1": "2.1-1", "2.1-2": "2.1-2"},
  "2": {"2.2-3": "2.3-1"}
}
```
