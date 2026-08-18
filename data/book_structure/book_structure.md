# `book_structure.json`（全书结构骨架 / 中间产物）

> 🔴 **本文件是该 JSON 数据结构的唯一权威说明（SSOT）**。模型类见同目录 `book_structure.py`；生成入口见 `flows/extract/structure/script/build_structure.py`；契约语义（章节→条目递归、写作契约+verify 基准合一）见 `flows/extract/structure/structure.md`。

## 1. 设计要点（2026-08-12 用户最终确认）

- **单一文件** `<extract_dir>/book_structure.json`（全书结构骨架，不按章拆分）。
- **顶层是一个「书」对象（不是数组）**：`key=-1, type=-1, name=<书名>, page_start/page_end=<全书起止页>, sub_sec=[章节对象...]`。
- 章节 / 条目节点递归嵌套在 `sub_sec` 中，复用 `structure.md` 的节点 schema（`key/type/name/page_start/page_end/sub_sec`）。定理/定义/例等叶节点 `sub_sec=[]`。
- `sub_sec` 顺序即书中实际顺序（章 → 节 → 条目）。
- 这是结构 JSON 的**唯一权威模型**：所有读写 / 遍历 / 回填都经 `book_structure.py` 的 `BookStructure` / `StructureNode`，脚本不再裸操作 json 字典。

## 2. 顶层书对象

```jsonc
{
  "key": -1,                       // 书根占位 key（非真实章/条目）
  "type": -1,                      // 书根占位 type
  "name": "Evans — Partial Differential Equations",  // 书名
  "page_start": 1,                 // 全书起始页（容器取末代子孙页，保存时重算）
  "page_end": 749,                 // 全书终止页
  "sub_sec": [ /* 章节节点，按章顺序 */ ]
}
```

书根与章节 / 条目用**同一套节点 schema**（`StructureNode`），仅 `key/type` 取值不同：
书根是 `-1 / -1`；章节是 `chapter` / `section`；编号项是 `definition` / `theorem` / … / `exercise` / `remark` / `uncat`。`StructureNode.is_container()` 对书根 / `chapter` / `section` 均返回 `True`。

## 3. 节点 Schema（递归）

```jsonc
{
  "key": "1.1-1",        // 书原生编号（语言无关）：三级 "1.1-1" / en "定义 1.2" /
                        //   vakil "1.2.1" / 练习 "1.2.A" / 章节 "1.1" / 章 "1" / 书根 -1
  "type": "definition", // chapter | section | definition | theorem | lemma |
                        //   corollary | proposition | example | exercise | remark | uncat | -1(书根)
  "name": "1.1-1 Definition (Metric space, metric).",  // 带序标的纯标题，不含正文
  "page_start": 18,
  "page_end": 18,       // 叶子 == page_start；容器取末代子孙页
  "sub_sec": [ /* 仅 chapter / section / 书根含此键，递归同结构；叶节点为 [] */ ]
}
```

- **`name` 带序标**：序标位置随书（前/后皆可），与原文一致；只含标题不含正文内容。
- **练习全量纳入** `type:"exercise"`（verify 展平取 key 集时过滤掉即可，不强制写作落地）。
- **`page_end`**：叶子 `== page_start`；容器（chapter/section/书根）取**末代子孙页**。`BookStructure.save()` 会递归重算容器页码。

## 4. 模型类 API（`book_structure.py`）

### `StructureNode`
- `__slots__ = (key, type, name, page_start, page_end, sub_sec)`。
- `to_dict()` / `from_dict(cls, d)`：序列化 / 反序列化（容错缺字段，默认回退根占位）。
- `is_container()`：书根 / `chapter` / `section` → `True`。
- `is_exercise()`：`type == "exercise"`。
- `iter_items(include_exercise=False)`：深度优先 yield 非容器编号项节点。
- `find_chapter(ch)`：按章号（字符串/整数均可）在 `sub_sec` 定位章节节点。
- `replace_chapter(node)`：用 `node` 替换同 `key` 章节；不存在则追加；返回是否替换。
- `recompute_pages()`：递归重算容器 `page_start/page_end`（容器取末代子孙页），返回自身 `page_end`。

### `BookStructure`
- `JSON_NAME = "book_structure.json"`。
- `new_book(name, book_dir=None)`：构造空书对象（根 `key=-1, type=-1, name=书名`）。
- `load(ext_dir, book_dir=None)`：读 `<ext_dir>/book_structure.json`；缺失/解析失败返回 `None`；否则返回 `BookStructure`（根经 `StructureNode.from_dict`）。
- `save(ext_dir=None)`：保存前 `root.recompute_pages()`，写回 `book_structure.json`，返回路径。
- `dump_dict()`：返回根 `to_dict()`。
- 属性 `name`（`root.name`）、`chapters`（`root.sub_sec`）。
- `find_chapter(ch)` / `chapter_items(ch, include_exercise=False)`：便捷查询。

> 注意：本模型类**未继承** `data/lib/json_data.py`（`data/data_schema.md` 描述的 `JsonData` 基类当前未实现），序列化契约以本模块 `to_dict()/from_dict()/dump()/load()` 为准。其字段与方法签名与 `JsonData` 约定（`to_dict/dump/load/from_dict`）一致，后续若实现基类可直接挂接。

## 5. 消费者（只读，不裸操作 json）

- `verify/script/structure_io.py`：`read_structure_items(ext_dir, ch)` → 经 `BookStructure.load` + `chapter_items` 返回编号项列表（被 `data_provider` 消费）。
- `verify/verbose_gates/script/verbose_gates.py`：`_load_contract` 经 `BookStructure.load` + `find_chapter` 取契约。
- `verify/script/check_structure_completeness.py`：`check_chapter` 经 `BookStructure.load` + `find_chapter` 取章节节点做查漏——章节漏用 `section_continuity`（D 层 `check_d_layer`）检、条目漏用 `item_numbering_integrity`（B 层）检，回填后 `root.replace_chapter(tree)` + `save()` 写回，并以「完整 + 连续」闸门收尾。
- `verify/script/report.py`：P-LAYER 提示串已指向 `book_structure.json`。

## 6. 构建 / 回填约定

- 生成：`build_structure <extract_dir> [ch ...]`，增量合并（按 `key` 替换或追加章节），章序按数字排；全程只产出/更新这一个文件。
- 回填：`check_structure_completeness.py <extract_dir> [ch ...] --backfill` 写回同一 `book_structure.json`（先备份）。
- 消费方只读单文件 `book_structure.json`；旧版每章结构文件不再被读取。若某书仍是旧版多文件结构，**对该书重跑 `build_structure`** 生成单文件 `book_structure.json`（`structure_io` 缺失时返回空，由 B 层如实报缺项，不静默通过）。
