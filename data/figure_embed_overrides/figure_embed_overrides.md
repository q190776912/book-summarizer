# `figure_embed_overrides.json` 配置说明

> 可选配置文件。位于本书 `_extract/figure_embed_overrides.json`。`embed_figures.py` 在图注→条目启发式匹配失败或图注无明确条目号时，读取本文件做**精确锚点覆盖**；文件缺失则纯靠启发式。

## 结构

顶层为 **文件名 → 覆盖对象** 的字典；每个对象含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `anchors` | `List[str]` | 必填。该图应归属的条目标签（如 `"**定义1.4**"`、`"**例1.5-9**"`）列表。脚本按**出现顺序取匹配到的第一个**作为嵌入锚点。 |
| `is_proof` | `bool` | 可选。该图是否落在「证明 / 例」引用块内（`>` 块）。`true` 时嵌入为块内 `> <img ...>`；缺省按图注语义判定。 |

## JSON 示例

```json
{
  "ch01_fig1.1.png": {"anchors": ["**定义1.4**", "**定义1.5**"], "is_proof": false},
  "ch01_fig1.2.png": {"anchors": ["**定义1.5**"]}
}
```

## 生成与维护

- `build_precise_anchors.py`：按页纵坐标定位「图上方最近条目」，**调用 `figure_embed_overrides.py` 的 `write_figure_embed_overrides(overrides, path)` 写出**骨架 `figure_embed_overrides.json`（`figure_index.json` 保持不动）；锚点计算留在本脚本，JSON 实例化归 `..`（流程脚本无裸 `json.dump`）。
- `../figure_index/figure_index.py`：在生成 `figure_index.json` 时一并写出本文件骨架。
- 两者均可后续手填 / 手改；重嵌前可用 `../../flows/script/figure/strip_figure_embeds.py` 剥离旧嵌入再据本文件重嵌。
