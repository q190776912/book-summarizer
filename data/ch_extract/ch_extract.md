# ch<N>_extract.json（章提取中间产物）

## 性质
提取阶段每章的抽取结果 JSON 序列化，是 verify 与 write-source 的**输入源**之一。

## 生成脚本
- `flows/write-source/script/extract/extract_items*.py` 的 `write_outputs(extract_dir, ch, data)`
  （如 `extract_items_kt.py` 写 `ch<N>_extract.json`）。
- 该构造逻辑属于 **extract 编排流程**的一部分，按用户约定**留 `../../flows`**，未抽入 `..`
  （其"构造方法"即各 `extract_items*.py` 的 `write_outputs`）。

## 落盘位置
- `<book>/_extract/ch<N>_extract.json`（`<N>` 为章号）。

## 数据结构（要点）
该章抽取结果的 JSON 序列化，核心含：
- `sections`：段落结构（`SEC` 节 / `SUB` 子节），按出现顺序；
- `statements`：条目（定义 / 定理 / 例题 / 证明 等）列表；
- 以及各 `extract_items_*` 变体附加的书特定字段（如 K&T 方案的 `skeleton` 契约）。

> 具体字段随所用 `extract_items_*` 变体而异；本文件记录其作为中间产物的角色与位置，
> 字段细节由各提取器实现与 verify 层契约决定。

## JSON 示例

```json
{
  "sections": [
    ["1", "Review of Basic Terminology and Properties of Random", 18, "SEC"],
    ["1.A", "JOINT DISTRIBUTION FUNCTIONS", 20, "SUB"]
  ],
  "statements": [
    ["Example", "1", 38, "A very important example is the celebrated Brownian motion."],
    ["Definition", "1.2", 41, "A stochastic process X_t is said to be ..."]
  ]
}
```

- `sections`：段落结构数组，每项为 `[编号, 标题, 起始页, 类型]`，类型 `"SEC"`=节 / `"SUB"`=子节；
- `statements`：条目数组，每项为 `[标签, 编号, 页, 文本片段]`，标签如 `Definition` / `Theorem` / `Example` / `Proof`。
（不同 `extract_items_*` 变体可能追加书特定字段，但 `sections` / `statements` 两键是通用骨架。）

## 消费方
- verify 各层（条目 / 键集 / 结构）；
- write-source 阶段读取以生成章节 `.md`。

## 相关
- 原始输入：`page_*.json`（见 [page_json.md](../page_json/page_json.md)）；
- 章节映射：`chapter_map.json`（见 [data/chapter_map/chapter_map.md](../chapter_map/chapter_map.md)）。
