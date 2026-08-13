# `verify_config.json` 配置说明

> 书级配置文件，位于本书 `_extract/verify_config.json`。是 `verify_chapter.py` / `flows/extract/structure/script/scan_skeleton` 的**唯一配置源**（配置缺失时 verify 硬失败，见 `config_setting` 流程 规则1；scan 仅告警安全网）。半自动生成脚本见 [`./make_config.py`](./make_config.py)（**需人工核对**，不声称自动正确）。

## BookConfig 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `ordinal` | `List[GroupConfig]` | 必填。每个 group：`{type(1–7), name:[标签类别], depth(段数≥1), scope(1=book/2=chapter/3=section)}`。数组首元素 `type` 即 `primary_type`，自动反推编号模式与小节层级。 |
| `language` | `str` | `'cn'` / `'en'`（默认 `'cn'`）。 |
| `strict` | `bool` | 默认 `true`。 |
| `ignore` | `List[str]` | 章节忽略列表。 |
| `formula` | `object?` | **仅书含公式序标时存在**：`{type, depth, scope:2, ignore:[]}`（见 `config_setting` 流程 规则3）。 |
| `figure` | `object?`→🔴 **`config_setting` 流程强制必现** | 图序标体例 `{"labels": ["图", "Figure", "Fig"], "components": 2}`。列出**每本书自己的**图号前缀词（图 / Figure / Fig / Scheme / Illustration …）；驱动 `extract_figures.parse_fig_label`（检测阶段裁图是否带 caption）与 `assign_figures.gather_refs`（分配阶段扫 OCR 图号）。**不再写死**中英语词表——书的图号到底长什么样由这里决定。🔴 **两种语义严格区分**：`figure` 块/`labels` 键**缺失** → 回落 `FIGURE_LABELS_DEFAULT = ["图", "Figure", "Fig"]`（向后兼容）；`figure.labels` **显式为空数组 `[]`** → 这是"**无图序标**"的**标记号**，返回真正的零匹配集（不回落默认），避免无图号书被误匹配 `Figure`/`图` 等前缀。见 `lib/figure_io.load_fig_labels`。 |

`figure.components`（可选，默认 2）控制图号**段数**，解决不同编号体例：
- `1` = **全局整数序列**（如 Kreyszig "Fig. 1" / "Fig. 23" … 全书连续编号到 ~270）。**此类书必须声明 `"components": 1`**，否则 "Fig. 23" 因只有 1 段被正则 `{1,2}` 判为非图号，全部图沦为未命名。
- `2` = 章.图（"Fig. 3.1"），**历史默认行为**，不声明即此值，已有书不回归。
- `3` = 章.节.图（"Fig. 3.1.2"），更严格。

`lib/figure_io.build_fig_label_re(labels, components)` 据此生成对应段数的捕获组；`load_fig_label_re(out_dir)` 一次性读取 `labels`+`components`。OCR 鲁棒性：`fig_label_alt` 对含 `i` 的前缀额外生成 `[il]` 变体，容忍 "Fig."→"Flg."（i 误读为 l）这类扫描噪声。
| `section_types` / `section_depths` | `List[int]` | 多数由 `primary_type` 自动反推；仅四级子小节 `1.1.1.1` 需显式覆盖。 |

## GroupConfig 字段

- `type`：编号风格码 1–7。
- `name`：标签类别列表（如 `["定理","定义"]`；可含中英文，靠规范化匹配）。
- `depth`：编号阿拉伯数字段数（≥1）。
- `scope`：计数重置边界（1=book / 2=chapter / 3=section）。

## `from_dict` 严格校验

- 旧整型 `{"ordinal": int}` / 字符串 `ordinal` **直接拒绝**，提示重跑 `make_config --force`（`exit 2`）。
- 逐组校验：`type`∈1–7、`depth`≥1、`scope`∈{1,2,3}，否则 `exit 2`。
- 无 `uncat` 组不自动追加、不警告（`uncat` 是显式决策；无 `uncat` 时 `uncat_group()` 回退 `ordinal[0]`）。

## JSON 示例

CN 三级（含公式序标）：

```json
{
  "ordinal": [{"type": 3, "name": ["uncat"], "depth": 3, "scope": 2}],
  "strict": true,
  "language": "cn",
  "formula": {"type": 4, "depth": 2, "scope": 2, "ignore": []}
}
```

EN 两级：

```json
{
  "ordinal": [{"type": 4, "name": ["uncat"], "depth": 2, "scope": 2}],
  "strict": true,
  "language": "en"
}
```

指定图序标体例（本书图号用 "Fig." / "图"）：

```json
{
  "ordinal": [{"type": 3, "name": ["uncat"], "depth": 3, "scope": 2}],
  "language": "cn",
  "figure": {"labels": ["图", "Fig"], "components": 2}
}
```

全局整数图号书（如 Kreyszig，图号 "Fig. 1" … "Fig. 270" 连续）：

```json
{
  "ordinal": [{"type": 3, "name": ["uncat"], "depth": 3, "scope": 2}],
  "language": "en",
  "figure": {"labels": ["Fig", "Figure"], "components": 1}
}
```

无图序标（🔴 显式标记号，禁止回落默认）：

```json
{
  "ordinal": [{"type": 3, "name": ["uncat"], "depth": 3, "scope": 2}],
  "language": "cn",
  "figure": {"labels": []}
}
```

> 空数组 `[]` 是"本书确实没有任何图号前缀"的**标记号**：下游（`extract_figures` / `assign_figures` / E 层 `fig_cap_re`）据此返回真正的零匹配，而**不会**回落到默认 `["图","Figure","Fig"]` 去误匹配正文里碰巧出现的 `Figure`/`图` 等词。与"`figure` 字段缺失→回落默认"语义严格区分。
