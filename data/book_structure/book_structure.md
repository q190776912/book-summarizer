# 书结构契约（内容化分章契约 `ch{N}.json` / `appendix{X}.json`）

> 🔴 **本文件是该 JSON 数据结构的唯一权威说明（SSOT）**。模型类见同目录 `book_structure.py`；
> 骨架生成 `flows/write-source/structure/script/build_structure.py`；正文内容化
> `flows/write-source/structure/script/attach_content.py`（structure 子流程第 5 步）；草稿渲染
> `flows/write-source/script/render_draft.py`（write-source 步骤 4）。契约语义
> （步骤 / 命令 / 已知近似）的流程侧 SSOT 见 `flows/write-source/structure/structure.md`。

## 1. 格式总览（2026-08-29 用户最终确认：**分章契约是唯一真源，全书单文件已废弃**）

| 产物 | 位置 | 承载 | 消费方 |
|------|------|------|--------|
| **内容化分章契约（唯一格式）** | `<extract_dir>/book_structure/ch{N}.json`（数字章）/ `appendix{X}.json`（附录章） | 该章完整树 + **全部正文内容**：`text` / `formula` / `image` 内容块、`description` 描述节点、`proof` 证明子节点 | `render_draft`（write-source 步骤 4）→ 基本总结草稿 `draft_ch{N}.md`；verify 经 `BookStructure.load` **聚合读取**为编号项基准 |

- **两阶段写同一文件**：`build_structure` 产出**纯骨架**（叶子 `sub_sec=[]`，无 description / proof / 内容块）→ structure 完整性闸门 → `attach_content` 挂入正文内容写回同一文件。
- **无单独的全书文件**：verify 全部消费方经 `BookStructure.load` 聚合读取分章文件；旧单文件 `book_structure.json` 仅作历史书**只读兼容回退**（且对其 `save` 拒绝——须重跑 build + attach 迁移）。
- 命名单点：`chapter_json_name` / `chapter_json_path` / `list_chapter_keys`（`book_structure.py`）——数字章按数值排序在前、附录字母章按字母排后。

## 2. 结构节点 Schema

```jsonc
{
  "key": "1.1-1",        // 书原生编号（语言无关，形态随书 ordinal）：三级 dash "1.1-1" /
                        //   两级 canon "定义1.1" / vakil 三级点分 "1.1.12" /
                        //   练习 "1.2.A" / 章节 "1.1" / 章 "1"（附录为字母 "A"）/
                        //   合成键：无序号标节 "U{n}"、描述节点 "D{n}"、证明 "{条目key}-P{n}"
  "type": "definition", // chapter | section | definition | theorem | lemma |
                        //   corollary | proposition | example | exercise | remark | uncat |
                        //   axiom(Ross) | algorithm | property | table | figure |
                        //   description（描述信息）| proof（证明，条目子节点）| -1(书根)
  "name": "1.1-1 Definition (Metric space, metric).",  // 带序标的纯标题，不含正文
                        //   description 恒为 ""（无序标）；proof 为证明标记原文
  "page_start": 18,
  "page_end": 18,       // 叶子 == page_start；容器 / description / proof 取所辖块的页区间
  "consolidated": false, // 全节点均有（save 序列化必写）；true 仅「章末集中习题块」内的练习
  "sub_sec": [ /* 混合列表，见 §3 / §4 / §5；结构基线中条目叶子为 [] */ ],
  "letter_subs": [ /* 可选：仅个别 section 携带且非空时才写出（见 2.3） */ ]
}
```

- **`name` 带序标**：序标位置随书（前/后皆可），与原文一致；只含标题不含正文内容。
- **练习全量纳入** `type:"exercise"`（verify 展平取 key 集时过滤掉即可，不强制写作落地）。
- **`page_end`**：结构基线中叶子 `== page_start`；容器取**末代子孙页**（`BookStructure.save()` 递归重算）。分章契约中 `description` / `proof` 节点的页码 = 所含内容块的最小/最大页。

### 2.1 完整迷你示例（`ch2.json`，顶层即该章节点；无书根包装）

```jsonc
// 纯骨架阶段（build_structure 产出）：叶子 sub_sec=[]、无 description / proof /
// 内容块；attach_content 后即下方完整形态
{
  "key": "2", "type": "chapter", "name": "2 A Crash Course in Basic Probability Theory",
  "page_start": 7, "page_end": 32,
  "sub_sec": [
    // ── 章首序言：大段无序标散文 → description 节点（与定理同级，置于最前）──
    { "type": "description", "key": "D1", "name": "",
      "page_start": 7, "page_end": 7,
      "sub_sec": [
        { "text": "This chapter is a very rapid introduction to the measure theoretic foundations of probability theory." }
      ]},
    // ── 无序号标小节（sections_unnumbered 书）：key 为合成键 "U{n}"，name 为纯印刷标题 ──
    { "key": "U1", "type": "section", "name": "A. BASIC DEFINITIONS",
      "page_start": 7, "page_end": 12,
      "sub_sec": [
        // 节导语散文 → description 节点（置于节 sub_sec 最前）
        { "type": "description", "key": "D2", "name": "", "page_start": 7, "page_end": 7,
          "sub_sec": [ { "text": "Let us begin with a puzzle: Bertrand's paradox." } ]},
        // 编号项叶子：sub_sec = 陈述内容块 + proof 子节点（保序）
        { "key": "2.1-1", "type": "definition",
          "name": "2.1-1 Definition (Metric space, metric).",
          "page_start": 9, "page_end": 9,
          "sub_sec": [
            { "text": "A metric on a set X is a map" },
            { "formula": "d: X\\times X\\to R", "display": false },          // 行内公式
            { "text": "satisfying positivity and symmetry." },
            { "formula": "d(x,y)\\ge 0", "display": true },                  // 行间公式
            // 证明子节点：标记原文为 name；内容块含 QED 收尾块
            { "type": "proof", "key": "2.1-1-P1", "name": "PROOF",
              "page_start": 9, "page_end": 9,
              "sub_sec": [
                { "text": "Immediate from the definitions." },
                { "text": "口" }
              ]}
          ]},
        // 条目证明之后的尾随散文 → description 节点（插在该条目之后，与条目同级）
        { "type": "description", "key": "D3", "name": "", "page_start": 10, "page_end": 10,
          "sub_sec": [ { "text": "We now turn to another class of examples." } ]},
        // 练习节点同样携带题面内容块（全量纳入；写作时按习题收录规则取舍）
        { "key": "2.1.A", "type": "exercise", "name": "2.1.A",
          "page_start": 12, "page_end": 12,
          "sub_sec": [ { "text": "Show that d is continuous." } ]},
        // 章末「集中习题块」内的练习：consolidated=true（verify 不校验、总结省略）
        { "key": "2.1.B", "type": "exercise", "name": "2.1.B",
          "page_start": 12, "page_end": 12, "consolidated": true, "sub_sec": [] }
      ]}
  ]
}
```

### 2.2 节点 type ↔ key/name 实书样例对照

`key` 的形态由该书 `verify_config.json` 的 `ordinal`（编号模式）决定，**不统一改写**（"不允许统一风格"）。下表 key/name 样例均取自语料实书产物：

| type | 语义 | key 形态 | 实书样例（key → name 摘录） |
|------|------|----------|------------------------------|
| `chapter` | 章 | 数字 `"2"`；附录字母 `"A"` | `"2"` → `2 A Crash Course…`；`"A"` → `A Appendix A: Notation` |
| `section` | 节 | `"N.M"`；无序号标书 `"U{n}"` | `"1.1"` → `1.1 Categories`；`"U1"` → `A. MOTIVATION` |
| `definition` | 定义 | 三级 dash `"1.1-1"` / 两级 canon `"定义1.1"` | `"定义1.1"` → `定义1.1 f is a finite map if k[X] is…` |
| `theorem` | 定理 | 同上 | `"定理1.1"` → `定理1.1 At any nonsingular point…` |
| `lemma` / `corollary` / `proposition` | 引理 / 推论 / 命题 | 同上 | `"引理1.1"` / `"推论1.1"` / `"命题1.1"` |
| `example` | 例 | 两级 canon `"例1.1"` / vakil 三级点分 `"1.1.12"` | `"例1.1"` → `例1.1 The whole affine space…`；`"1.1.12"` → `Find three examples…` |
| `exercise` | 练习 | `"0.10"` / `"1.2.A"` / 节内字母 `"4.A"` | `"0.10"` → `0.10 Let S be a set…`；`"4.A"` → `Appendix: Fourier integrals…` |
| `remark` | 评注 / 注 | `"评注1.1"` | `"评注1.1"` → `评注1.1 According to Proposition A.7…` |
| `axiom` | 公理（Ross 体例） | `"Axiom 1"` | `"Axiom 1"` |
| `algorithm` | 算法 | `"算法1"` | `"算法1"` → `算法1 列主元素消去法）设Ax=b…` |
| `property` | 性质 | `"性质1"` | `"性质1"` → `性质1 傅里叶变换是线性变换…` |
| `table` / `figure` | 表 / 图注条目（节内共享计数器书，Fraleigh 型） | `"Table1.20"` / `"Figure3.10"` | `"Table1.20"` → `Table1.20 1.20 Table` |
| `uncat` | 无法归类标签的编号项（兜底） | `"3.21-3"` | `"3.21-3"` → `3.21-3 22` |
| `description` | **描述信息**（大段无序标散文，与定理同级；仅分章契约） | 合成 `"D{n}"`（章内文档序）；name 恒空 | `"D2"`，`sub_sec` 承载散文内容块 |
| `proof` | **证明**（条目子节点；仅分章契约） | 合成 `"{条目key}-P{n}"`；name = 证明标记原文 | `"2.1-1-P1"` → `PROOF` |

### 2.3 特殊字段与遗留形态

- **`consolidated`**（全节点序列化必写）：`true` 仅出现在章末「Exercises / 练习」集中块内的练习节点——verify 展平**恒不产出**（不参与编号项校验），总结按习题收录规则省略；`false` 为普通节点（穿插练习保持 `false`，`iter_items(include_exercise=True)` 时纳入校验）。
- **`letter_subs`**（仅个别 `section` 节点携带，非空才写出）：Arnold《数学方法》体例的**裸字母子块头**元数据（`"letter_subs": [{"key": "A", "name": "A 空间与时间", "page_start": 18}, …]`，按书中出现顺序）；**子块的条目仍平铺在该 section 的 `sub_sec` 下**，不引入第三层容器。
- **遗留形态**：个别历史书 JSON 中可见 `type:"subsection"` 节点（`consolidated=true`、页码可能为 `0`）——**非规范契约类型**，现行抽取器不再产出，verify 与写作均不消费；仅作读取兼容，不必修复。

## 3. 内容块 Schema（仅内容化分章契约）

内容块是 `sub_sec` 中**无 `key`/`type` 键**的元素（与结构节点天然可区分，`attach_content._is_block` 判定）：

```jsonc
{ "text": "设 X 是度量空间，则对任意两点 x 与 y，距离 d(x,y) 非负。", "line_start": true, "indent": 2.0 }
{ "text": "且当 x 等于 y 时距离为零。", "line_start": true }                    // 新行顶格（续段或新段由消费方判断）
{ "text": "由对称性还有 d(y,x) 等于 d(x,y)。", "line_start": true, "indent": 16.7 }  // 居中行也如实写缩进
{ "formula": "d(x,y) \\le d(x,z)+d(z,y)", "display": false }          // 行内公式
{ "image": "_extract/figure/ch01_unnamed_01.png" }              // 图片（裁剪图路径，相对书根：最终 md 落书根可直接渲染）
{ "formula": "\\begin{aligned} … \\end{aligned}", "display": true }   // 行间公式（独立占一行或多行）
```

- **顺序即文档顺序**（OCR 阅读序，行内公式已按 x 位置拼回宿主文本行）。
- **`line_start` / `indent`（text 块的几何事实字段，尽力而为）**：`line_start: true` = 本块从新的一行开始（与前一文本块无 y 重叠；页首块恒为新行）；`indent: <字高倍数>` = 新行左缘相对本页正文左边界的缩进（≥0.3 字高才写出，如 `2.0` ≈ 中文两字符缩进；居中公式行的较大缩进也如实写出）。**两键都没有 = 续前一句**（同行 OCR 碎片 / 行内公式拼接段的中段）。是否新段落由消费方判断（渲染器：`line_start` 且 `indent` ∈ `[0.8, 3.5]` 另起一段），agent 调整时亦据此校对段落归属。
- **`image`（图片块，仅 text/formula 之外的第三种内容块）**：内容即裁剪图路径（**相对书根**，`_extract/` 前缀 + `figure_index.json` 的 `file`；最终 md 落书根可直接渲染），按其 `page`/`bbox` 并入阅读序（图随所在页/节/条目归位）；无图管线（书无图 / 未跑图检测）则为零图片块。渲染时按**原嵌图格式**输出：flex div（`display:flex; gap:6px; …`）包裹 `<img src=… alt=「图号+短说明」 width=「bbox 占页宽比」 height=auto>`（复用 `flows/script/embed_figures.py` 的 `short_caption` / `page_px_width` / 图号标签逻辑），例块内整体 `>` 前缀——最终 md 无需单独嵌图步骤。
- **`display` 语义**：`true` = 行间公式（MFD `cls=1`，渲染为 `$$...$$`）；`false` = 行内公式（`cls=0`，渲染为 `$...$`）。
- 内容块只承载**原文内容**（`page_*.json` 的文字块与公式框），不带页码/坐标等元数据；归属节点的页码由节点的 `page_start..page_end` 承担。
- **已知近似（调整步骤兜底）**：无证明条目之后的游离段落仍留在该条目正文内（无边界信号不做切分）；OCR 文本行与其行内公式的校正 latex 天然并存（内容重复，调整时保留公式、清理乱码）；图注文字 / 证明结尾框等残余噪声由调整清理。

## 4. description 节点（描述信息，与定理同级）

- **语义**：书中大段**不属于任何定义/定理、没有序标**的描述性散文——章首序言、节导语、条目之间/证明之后的独立段落。
- **产生规则**（`attach_content`）：① 章首序言块 → 章 `sub_sec` 最前的 description 节点；② 节首散文块 → 节 `sub_sec` 最前的 description 节点；③ 条目末个 `proof` 之后的尾随正文块 → 与该条目**同级**的 description 节点（插在该条目之后）。
- **字段**：合成 `key="D{n}"`（章内按文档顺序递增）；`name=""`（无序标）；`page_start/page_end` = 所含块的页区间；`sub_sec` = 文字/公式内容块。
- **verify 不消费**：description 仅存在于分章内容契约，结构基线不含，编号项基准 / B·D 层均不受影响（结构指纹亦排除）。
- **渲染**：`render_draft` 输出为**无标题纯段落**（公式照常 `$`/`$$`），agent 调整时按 Tier 2 描述性内容规则压缩。

## 5. proof 节点（证明，条目子节点）

- **语义**：定理/定义/例/练习等条目正文中的**证明（或解答）过程**，作为条目的子节点挂在条目 `sub_sec` 内（statement 内容块 → proof 子节点，保序）。
- **产生规则**（`attach_content._split_proofs`）：正文块流中出现**证明标记**（`PROOF` / `Proof` / `SOLUTION` / `Solution` / `证明` / `证：` / `解：`…，块首匹配）即开启 proof 节点；至 **QED 收尾**（`口` / `□` / `∎` / `证毕` / `Q.E.D.` / 纯 `\square` / `\blacksquare` / `\qed` 型公式，独立短块或行内切分）或块流末尾收束；QED 块归入 proof 内容；中文「证」与陈述同行被 OCR 合并时按句末标点 + 「证」边界内联拆分。**练习（exercise）不拆 proof**——其「证明：…」属题干任务，题面即正文。
- **字段**：合成 `key="{条目key}-P{n}"`（同条目多证明依次 P1、P2…）；`name` = 证明标记原文（如 `PROOF` / `证明`）；`page_start/page_end` = 证明块的页区间；`sub_sec` = 证明内容块。
- **宁整不碎**：标记 / QED 识别失败时不拆分（正文整体留在条目内）；不依据 y 空隙等弱信号切分。
- **verify 不消费**（同 description，仅分章契约中存在）。
- **渲染**：`render_draft` 输出 `**{name}**` 标记头 + 证明内容块；agent 调整时按 writing-rules 改写为 `> **证明思路**：1. 2. …` 块引用（OCR 公式逐条重写校正）。

## 6. 模型类 API（`book_structure.py`）

> 模型服务分章契约的聚合读写：`load` 把各分章文件聚合成内存书对象（root = 书根包装），
> `save` 把书根下的章节点拆分写回各自 `ch{N}.json` / `appendix{X}.json`；
> `attach_content` / `render_draft` / checker 直接按章读写单文件（经
> `chapter_json_path` 命名单点）。

### `StructureNode`
- `__slots__ = (key, type, name, page_start, page_end, sub_sec, consolidated, letter_subs)`。
- `to_dict()` / `from_dict(cls, d)`：序列化 / 反序列化（容错缺字段，默认回退根占位）。
- `is_container()`：书根 / `chapter` / `section` → `True`。
- `is_exercise()`：`type == "exercise"`。
- `is_derived()`：`type ∈ {description, proof}` → True（非编号项，verify 展平时排除）。
- `iter_items(include_exercise=False)`：深度优先 yield 非容器编号项节点（跳过派生节点）。
- `find_chapter(ch)` / `replace_chapter(node)` / `recompute_pages()`：同前。

### `BookStructure`
- `load(ext_dir, book_dir=None)`：**聚合** `book_structure/ch{N}.json` + `appendix{X}.json`
  为内存书对象（root.name = 书目录名；root 页码 = 各章 min/max）；无分章文件时回退读
  旧单文件 `book_structure.json`（`legacy=True`，只读）。
- `save(ext_dir=None)`：把 root 下各章节点**拆分写回** `ch{N}.json` / `appendix{X}.json`
  （保存前 `recompute_pages`）；`legacy=True` 且书根无分章文件时拒绝（旧书须先迁移）。
- 其余（`new_book` / `dump_dict` / `name` / `chapters` / `find_chapter` /
  `chapter_items`）同前。

### 分章命名单点（模块级函数）
- `chapter_json_name(key)`：数字章 `ch{N}.json` / 附录 `appendix{X}.json`。
- `chapter_json_path(ext_dir, key)`：分章契约完整路径。
- `list_chapter_keys(ext_dir)`：列出章号（数字章按数值在前、附录按字母在后）。

> 注意：本模型类**未继承** `data/lib/json_data.py`（`JsonData` 基类未实现），序列化契约
> 以本模块 `to_dict()/from_dict()/dump()/load()` 为准。

## 7. 消费者（只读，不裸操作 json）

全部经 `BookStructure.load` **聚合读取分章契约**（历史书回退旧单文件）：

- `verify/script/structure_io.py`：`read_structure_items(ext_dir, ch)` → `chapter_items` 返回编号项列表（被 `data_provider` 消费；派生节点 description / proof 已在 `iter_items` 排除）。
- `verify/verbose_gates/script/verbose_gates.py`：`_load_contract` 取契约。
- `verify/script/check_structure_completeness.py`：章节 / 条目查漏回填（`replace_chapter` + `save` 拆分写回）。
- `verify/script/audit_ignore.py`：编号 ignore 审计。
- `tools/restructure_by_ocr.py`：B 层 ORDERING 修复（聚合读、写回 md）。
- `flows/write-source/script/render_draft.py`：按章直读单文件（`chapter_json_path`）渲染草稿；内容完整性闸门 `verify/script/check_content_completeness.py` 同。

## 8. 构建 / 回填 / 内容化 / 渲染约定

1. **骨架生成**（write-source 步骤 3 前半）：`build_structure <extract_dir> [ch ...]`
   → 按章写 `book_structure/ch{N}.json`（纯骨架）。每章文件独立，重跑只覆盖指定章
   **并清除其已挂内容**——重跑后必须随后执行第 4 步 attach。
2. **查漏回填 + 闸门**（structure 第 2–4 步）：`check_structure_completeness.py
   <extract_dir> [ch ...] --backfill` 经聚合 load 定位章节点、`replace_chapter` +
   `save` 拆分写回（先备份）；闸门 `gate.passed == true` 后放行。
3. **正文内容化**（structure 第 5 步）：`attach_content <extract_dir> [ch ...]` 读入
   骨架、挂 description / proof / 内容块后**写回同一文件**（幂等可重跑）。
4. **草稿渲染**（write-source 步骤 4）：`render_draft <extract_dir> [ch ...]` →
   `draft_ch{N}.md`。
5. **内容完整性闸门**：`verify/script/check_content_completeness.py`（确定性复算 +
   图片真值 + 证明覆盖审计），FAIL 严禁渲染。
