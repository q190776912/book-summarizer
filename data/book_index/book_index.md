# book_index

`make_summary.py` 维护的**跨书总结索引**，形态为 `{"books": {<book_name>: <summary>}}`。属于流水线内部产物，只放一层**边界适配**：`book_index.py` 提供 `BookIndex.load(path)` / `.dump(path)`，`raw dict` 原样存于 `.data`。

> 规则：`../../flows`、`../../verify` 里读写该索引一律走 `BookIndex`，不得出现裸 `json.load` / `json.dump`。

## 示例

```json
{
  "books": {
    "do_carmo": {"chapters": 14, "status": "done"},
    "kreyszig": {"chapters": 11, "status": "done"}
  }
}
```
