# 校验关卡与架构总览（Verification & Architecture）

> 🔴 **本文件是校验系统的「注册表 + 全局架构」单一入口。**
> - **每层的全部细节（语义 / 阈值 / `--fix` 范围 / 字节契约键 / 实现）只写在 [`layers/<code>.md`](layers/) 各自文件中**，本文件不重复描述。
> - `SKILL.md` Step 4 只链接本文件的注册表，不内联任何规则。
>
> **新增 / 修改一层 = 新建 `layers/X.md` + 在本文件注册表加一行 + 改必要代码**，不要在其他文档重复描述层级语义。

---

## 1. 层级注册表（Registry）

统一强制关卡由 `verify/verify_chapter.py` 驱动；层级由 `verify/layers/*.py` 经 `register_all.py` **自动发现**，运行顺序 = 各层 `order` 属性。下表为当前全部层级的唯一索引，每行链接到该层的专属文档与代码模块。

| # | 层 code | 名称 | 一句话目的 | 阻断? | 可 `--fix`? | 层文档 | 代码模块 |
|---|---------|------|-----------|-------|------------|--------|----------|
| 0 | EXTRACT | 数据 provider | 提供原始 JSON 数据；必跑、永不可禁用 | 数据缺失→FAIL | 否 | [layers/extract.md](layers/extract.md) | [extract_layer.py](../verify/layers/extract_layer.py) |
| 1 | D | MISSING SECTION / TAIL ORDINAL | 整节缺失 / 尾部缺口 | 整节缺失阻断 | 否 | [layers/d.md](layers/d.md) | [d_layer.py](../verify/layers/d_layer.py) |
| 2 | A | TRULY MISSING | 提取到但 `.md` 无 | 阻断 | 否 | [layers/a.md](layers/a.md) | [a_layer.py](../verify/layers/a_layer.py) |
| 3 | B | BLOCKING | 边界复查候选项 | 阻断 | 否 | [layers/b.md](layers/b.md) | [b_layer.py](../verify/layers/b_layer.py) |
| 4 | C | KATEX ERRORS | KaTeX 渲染失败 | 阻断 | 部分 | [layers/c.md](layers/c.md) | [c_layer.py](../verify/layers/c_layer.py) |
| 5 | E | FIGURE COMPLETENESS | 图缺失 | 有图时阻断 | 否 | [layers/e.md](layers/e.md) | [e_layer.py](../verify/layers/e_layer.py) |
| 6 | F | FIGURE VALIDITY | 图无效 | 有图时阻断 | 否 | [layers/f.md](layers/f.md) | [f_layer.py](../verify/layers/f_layer.py) |
| 7 | G | QUOTE CONTINUITY | 引用块连续性（+ G扩展/EG） | 阻断 | 是 | [layers/g.md](layers/g.md) | [g_layer.py](../verify/layers/g_layer.py) |
| 8 | H | STRUCTURAL LABEL IN BQ | 结构标签被块引用吞（+ H扩展） | 阻断 | 是 | [layers/h.md](layers/h.md) | [h_layer.py](../verify/layers/h_layer.py) |
| 9 | I | MISSING SEPARATOR | 条目间缺 `---` | 阻断 | 是 | [layers/i.md](layers/i.md) | [i_layer.py](../verify/layers/i_layer.py) |
| 10 | J | ITEM-HEADER DASH | 条目块内多余 `---` | 阻断 | 是 | [layers/j.md](layers/j.md) | [j_layer.py](../verify/layers/j_layer.py) |
| 11 | K | PROOF-LIST BLANK | 编号列表后证明块缺空行 | 阻断 | 是 | [layers/k.md](layers/k.md) | [k_layer.py](../verify/layers/k_layer.py) |
| 12 | L | SEP BLANKS | `---` 上下缺空行 | 阻断 | 是 | [layers/l.md](layers/l.md) | [l_layer.py](../verify/layers/l_layer.py) |
| 13 | M | DISPLAY-MATH `>` | 显示公式内 `>` 前缀 | 阻断 | 是 | [layers/m.md](layers/m.md) | [m_layer.py](../verify/layers/m_layer.py) |
| 14 | N | BQ EMPTY LINES | 块内空 `>` 行 >1 | 阻断 | 是 | [layers/n.md](layers/n.md) | [n_layer.py](../verify/layers/n_layer.py) |
| 15 | O | SUBITEM GAP | 编号子项缺口 | 部分阻断 | 否 | [layers/o.md](layers/o.md) | [o_layer.py](../verify/layers/o_layer.py) |
| 16 | P | VERBOSE 闸门 | 反回归 7 闸门 | 阻断 | 否 | [layers/p.md](layers/p.md) | [p_layer.py](../verify/layers/p_layer.py) |

> G 层内含 **G扩展**（嵌套块引用）与 **EG 层**（例–证明空隙）子检查，非独立层；H 的 3 个扩展（stmt-in-bq / unlabeled-bq / missing-bq）仍归属 `code="H"` 单层。

## 2. 字节契约键集合（代码侧 SSOT）

`verify/registry.py` 的 `DEFAULT_RESULT` 与 `verify/report.py` 的 `print_result` 必须共同覆盖一组 legacy dict 键。**每个层拥有哪些键，由各层专属文档 [`layers/<code>.md`](layers/) 里的 ```` ```contract-keys ```` 代码块声明**——本文件不再硬编码完整清单。

- **聚合与防遗漏**：[`verify/tests/test_key_contract.py`](../verify/tests/test_key_contract.py) 扫描 `layers/*.md` 的所有 `contract-keys` 块，断言其并集（加上下方管理器注入键）**完全等于** `DEFAULT_RESULT` 的键集，且 `report.py` 只读取已知键。三者不一致直接 FAIL，杜绝"加层漏改键导致静默漏检"。
- **管理器注入、不归属任何层的键**（稳定基础设施，加层时不受影响）：`ch`, `md`, `status`, `extract_dir`。

## 3. 新增 / 修改一层同步清单（只改这几处）

1. **`verify/layers/X_layer.py`**：复制 `_template_layer.py` 新建层，定义 `code/order/fix_order/auto_fixable` + `run()`（+`fix()`）。自动注册，无需改 `register_all.py`。若引入新 legacy 结果键，在 `metadata` 中返回。
2. **`references/layers/x.md`**（新建）：写该层的**全部**内容——一句话目的、语义与检查内容、阻断性/可修复、```` ```contract-keys ```` 声明的字节契约键、实现（code/order/fixable/数据源/关键逻辑）。
3. **本文件注册表（第 1 节）**：追加一行（code + 名称 + 一句话目的 + 阻断/可fix + 两个链接）。
4. **`verify/registry.py` 的 `DEFAULT_RESULT`**：追加新键及中性默认值（类型须匹配该层正常 emission）。
5. **`verify/report.py` 的 `print_result`**：若新键需展示，增加对应读取与输出；否则确保不读取不存在的键。
6. **护栏**：运行 `python -m pytest verify/tests/ -q`，键集不一致会立即 FAIL，无需手工核对。

> `SKILL.md` Step 4 只链接本注册表，层级增减**无需改 SKILL.md**。

---

## 4. 全局架构（原 ADR-VERIFY-001，已合并）

**状态：** Done — 全部层级自包含于 `verify/layers/*.py`，由 `register_all.py` 经 `pkgutil` 自动发现注册（当前层列表见上方 §1 注册表，不在此写死数量）。
**核心约束（不可破坏）：**

1. CLI 不变：`verify_chapter.py <ch> <start> <end> <md> <ext> [--manual --ignore --ignore-figure --scheme --fix]` 以及 `--all <ext> <book_dir> [...]`
2. `--fix` 行为不变：自动修 G/H/I/J/K/L/M/N（含 H 三扩展），O 仅警告不修
3. `print_result` 输出格式不变（下游 agent 在 Step 4 解析 PASS/FAIL）
4. exit 0 条件不变（见 §5.2）
5. 层字母代号（G/H/...）作为**稳定标识符**保留（被 SKILL.md 与 per-book 记忆引用）
6. 不破坏已在 10+ 本书上跑通的流水线（幂等、中文 UTF-8）

> **关键洞察：** 约束 #3 要求 `print_result` 原样不变，而它靠硬编码的约 30 个 dict 键渲染输出。因此最稳妥策略是**让 `VerifyManager` 产出一个与旧 `verify_one` 返回结构字节级兼容的 `dict`**，把 `print_result`、退出码逻辑、下游解析全部原样保留。

### 4.1 高层设计

```
                          ┌─────────────────────────────┐
 CLI (main)  ──args──▶    │  VerifyManager               │
                          │   • verify_one(ch,start,end,md,ext) -> dict │
                          │   • fix(md_file) -> dict      │
                          └──────────────┬──────────────┘
                                         │  iterates
                                         ▼
                          ┌─────────────────────────────┐
                          │  LayerRegistry (LAYER_REGISTRY)│
                          │   D A B C E F G H I J K L M N O + EXTRACT │
                          └──────────────┬──────────────┘
                                         │  each layer.run(ctx)
                                         ▼
                          ┌─────────────────────────────┐
                          │  VerifyContext (ctx)         │
                          │  md_file, ext_dir, ch, ...   │
                          │  items, entry_keys, fig_idx  │  ◀── 无全局状态
                          └─────────────────────────────┘
```

每个层 = 一个 `VerifyLayer` 实例，`run(ctx) -> LayerResult`（其 `.legacy` / `.metadata` 片段并入总 dict），`fix(ctx) -> LayerFixResult`（仅 auto-fixable 层实现）。`verify_one` 返回的 dict 即旧 `verify_one` 返回值（字节级兼容）。

### 4.2 关键接口签名（`verify/registry.py`）

```python
class VerifyLayer:
    code: str = 'X'
    order: int = 0          # run 运行顺序
    fix_order: int = 999    # fix 运行顺序（仅 auto_fixable 有意义）
    auto_fixable: bool = False
    def run(self, ctx) -> LayerResult: ...
    def fix(self, ctx) -> Optional[LayerFixResult]:
        return None         # 默认无操作

class LayerRegistry:
    def register(self, layer) -> VerifyLayer: ...
    def get(self, code) -> Optional[VerifyLayer]: ...
    def all_ordered(self) -> list[VerifyLayer]: ...        # 按 order 排序
    def fixable_ordered(self) -> list[VerifyLayer]: ...    # 按 (fix_order, order) 排序
    def by_code(self) -> dict[str, VerifyLayer]: ...

DEFAULT_RESULT: Dict[str, Any]   # 模块级常量：为每一个 legacy 键注入正确类型的占位值，
                                 # 使被禁用的层不会破坏字节契约
```

> **真实子类只设置** `code`、`order`、`auto_fixable`；仅当 `auto_fixable=True` 时设置 `fix_order`。`depends_on` 事实上从不被任何子类设置（层间顺序完全由 `order`/`fix_order` 决定）。

### 4.3 管理器（`verify/registry.py`）

```python
@dataclass
class ManagerConfig:
    scheme: str = 'three-level'
    ignore_keys: Set[str] = set()
    ignore_fig: Set[str] = set()
    manual_path: Optional[str] = None
    disabled: Set[str] = set()
    @classmethod
    def load_book_config(cls, book_dir: str) -> "ManagerConfig":
        """读 <book_dir>/verify_config.json {"disable":[...]}，把 code 大写化进 disabled。"""

class VerifyManager:
    def verify_one(self, ch, start, end, md_file, ext_dir) -> Dict[str, Any]: ...
    def fix(self, md_file) -> Dict[str, int]: ...
```

> **合并规则（实现护栏）：**
> - `fix()` 遍历 `fixable_ordered()`（按 `(fix_order, order)` 排序），`result.update(fr.fix_dict)`，得到键插入序钉死的 change-dict：`h,h_stmt,h_ul,h_mbq,g,i,j,k,l,m,n`。
> - `verify_one()` 对 `all_ordered()` 中每层的 `res.metadata` 做 `merged.update(res.metadata)`（last-writer-wins），再 `final = dict(DEFAULT_RESULT)`；`final.update({ch, md, status, extract_dir, items})`；`final.update(merged)`。
> - `DEFAULT_RESULT` 为每个 legacy 键预置正确类型，被禁用的层因此保持字节安全。
> - `print_result` **不是** manager 的方法，来自 `verify.report`；`verify_chapter.verify_one` 先构建 `ManagerConfig` 再 `VerifyManager(LAYER_REGISTRY, cfg).verify_one(...)`。

### 4.4 模块布局

```
verify/
├── context.py            # VerifyContext
├── registry.py           # Severity / Finding / LayerResult / LayerFixResult
│                         #   VerifyLayer / LayerRegistry / ManagerConfig / VerifyManager
│                         #   DEFAULT_RESULT（模块级常量）
├── register_all.py       # 导入时经 pkgutil 自动发现 verify/layers/ 下所有层并注册进 LAYER_REGISTRY
├── layers/
│   ├── extract_layer.py  # EXTRACT：填 ctx.items/entry_keys/all_keys；算 ignored_hit stage1；mandatory
│   ├── d_layer.py  a_layer.py  b_layer.py  c_layer.py
│   ├── e_layer.py  f_layer.py
│   ├── g_layer.py  h_layer.py  i_layer.py  j_layer.py  k_layer.py  l_layer.py  m_layer.py  n_layer.py  o_layer.py  p_layer.py
│   ├── _fig_common.py    # 内部 helper（'_' 前缀，自动发现跳过）
│   └── _template_layer.py# 复制起点（'_' 前缀，自动发现跳过）
├── verify_chapter.py     # main() / verify_one()(薄壳) / verify_all()(薄壳)
├── key_parse.py  report.py  manage_ignore.py  review_tool.py
```

> **自动发现机制：** `register_all.py` 遍历 `pkgutil.iter_modules(verify.layers.__path__)`，跳过头为 `_` 的模块，导入其余每个模块并把其中**所有** `VerifyLayer` 子类注册进全局 `LAYER_REGISTRY`。**新增一层 = 丢一个 `X_layer.py` 进 `verify/layers/`，无需改动 `register_all.py`。**

### 4.5 EXTRACT 层关键逻辑（字节级 gate 的关键）

- **(a) `scheme='en'` 分支必须原样 port。** 英文书专用路径（调 `extract_items_en`、按章过滤前向引用、key 规范化成中文形式、md 侧 `entry_keys`/`all_keys` 限制到当前章）必须完整搬运，否则 EN 书整体漂移。
- **(b) `ignored_hit` 两段式，第二段归 B 层。** EXTRACT 算第一段写入 `ctx.ignored_hit`（stage1）；B 层在产出 `blocking` 后做第二段 regex 抑制、把 `bkeys` 并入 `ctx.ignored_hit` 并在自己的 legacy 片段中回写最终 `ignored_hit`（manager 按 order 合并、B 覆盖 EXTRACT）。禁止只由 EXTRACT 一次性算完。
- **(c) E/F 在底层返回 None 时必须显式 emit 空列表**（`fig_missing:[]`/`fig_extra:[]` 与 `fig_invalid:[]`/`fig_invalid_warn:[]`），镜像旧 `e_layer['missing'] if e_layer else []` 守卫，防崩溃。

> **EN 书回归要求：** 10+ 本书验收语料中**至少包含 1 本 EN 书**，否则 `scheme='en'` 分支回归盲区。

### 4.6 用法示例

定义一个层（复制 `_template_layer.py`）：

```python
# verify/layers/x_layer.py  —— 由 _template_layer.py 复制而来
from verify.registry import VerifyLayer, LayerResult, LayerFixResult
from verify.register_all import LAYER_REGISTRY   # 全局注册表，自动发现，无需手动注册

class XLayer(VerifyLayer):
    code = 'X'            # 新大写字母，不与现有层重复（完整列表见本文件第 1 节注册表）
    order = 17            # 运行顺序；取当前最大 +1
    auto_fixable = False  # 若支持 --fix，改为 True 并实现 fix()，并设 fix_order

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={'xxxx': 0})  # 只贡献 DEFAULT_RESULT 中已有键

# 仅当 auto_fixable=True 时实现：
#     def fix(self, ctx):
#         return LayerFixResult(fix_dict={'xxxx': changes})
```

注册与运行：

```python
from verify.register_all import LAYER_REGISTRY
from verify.registry import VerifyManager, ManagerConfig
from verify.report import print_result

cfg = ManagerConfig(manual_path=mp, ignore_keys=ik, ignore_fig=ifig, scheme=scheme)
mgr = VerifyManager(LAYER_REGISTRY, cfg)
legacy_dict = mgr.verify_one(ch, start, end, md_file, ext_dir)
status = print_result(legacy_dict)
```

`--fix` 流程（与现有行为一致）：

```python
mgr = VerifyManager(LAYER_REGISTRY, ManagerConfig(manual_path=mp, ignore_keys=ik, ignore_fig=ifig, scheme=scheme))
changes = mgr.fix(md_file)        # 按 fix_order 跑 H→G→I→J→K→L→M→N
                                  # change-dict 键插入序钉死：h,h_stmt,h_ul,h_mbq,g,i,j,k,l,m,n
parts = [f"{k}={v}" for k, v in changes.items() if v > 0]
print("[FIX] Applied: " + ", ".join(parts) if parts else "[FIX] No changes needed")
legacy_dict = mgr.verify_one(ch, start, end, md_file, ext_dir)   # fix 改盘后重读，复验
```

### 4.7 Per-book 启用/禁用

```python
cfg = ManagerConfig.load_book_config(book_dir)   # 读 verify_config.json {"disable":["O"]}
mgr = VerifyManager(LAYER_REGISTRY, cfg)
# O 层被跳过：o_subitem_gaps 不出现、不计入；其余完全不变
# 注意：EXTRACT 永不可禁用（manager 特判 code != 'EXTRACT'）；其余层可按书 disable。
```

> A/B 与 EXTRACT **不存在依赖关系**（无 `depends_on` 机制）。EXTRACT 由 manager 特判为 mandatory，根本不在 `disabled` 的可选范围内。

### 4.8 可扩展性要点

- **加新层 = 新增一个模块，自动发现即生效**，管理器按 `order` 自动调度，无需改 `VerifyManager` / CLI / `register_all.py`。
- **新增结果键**必须同步更新 `DEFAULT_RESULT`（registry.py）**和** `print_result`（report.py），否则字节契约破裂（由 §2 的护栏测试拦截）。
- `VerifyLayer.depends_on` 属性存在但**任何子类都不设置、manager 也不强制**：层间顺序完全由 `order`/`fix_order` 决定。

### 4.9 影响与风险

- **变容易：** 单测可针对单个层（输入 `.md` → legacy 片段）；加新层/按书禁用/调整 fix 顺序变成"数据/注册"操作；移除巨型文件耦合，review diff 变小。
- **需重新审视：** 现有 exit 0 条件在代码里实际比描述更宽——`print_result` 把下列任一非空即判 FAIL：`d_layer.missing_sections`、`truly_missing`、`blocking`(B)、`katex_errors`、`fig_missing`、`fig_invalid`、`quote_gaps`、`nested_bq`、`ex_proof_gaps`、`h_structural_bq`、`h_stmt_bq`、`h_ul_bq`、`h_mbq`、`i_sep_gaps`、`j_header_dash`、`k_proof_list`、`l_sep_blanks`、`m_dm_gt`、`n_bq_empty`、以及 `o_subitem_gaps` 中以 `x` 开头的条目。**方案通过保留 `print_result` 不动，使该集合 100% 不变。**
- **风险与缓解：**

| 风险 | 缓解 |
|------|------|
| 搬函数时改到语义 | 先有字节级基线再 diff |
| `fig_skipped` 语义变窄 | 改为按 E 层 `metadata['skipped']`（= `e_layer is None` 完整语义）注入，禁止 `ctx.figure_index is None` |
| EXTRACT 被误禁用 | manager 特判 `code != 'EXTRACT'` |
| `--fix` 旧代码直接调 `fix_all_layers` | 保留 shim；新路径走 `mgr.fix(md_file)` |

### 4.10 字节级 gate 的 5 条硬约束

1. **`fig_skipped` 必须 == `e_layer is None`**（含「文件在但本章无图条目」两种情况都 SKIP）。禁止窄化为 `ctx.figure_index is None`。
2. **H 层 `fix()` 内部子 fix 顺序钉死 `h→h_stmt→h_ul→h_mbq`**；`mgr.fix` 产出的 change-dict 键插入序钉死 `h,h_stmt,h_ul,h_mbq,g,i,j,k,l,m,n`；字节级 diff 范围包含**完整 `--fix` stdout**（含 `[FIX] Applied:` 行）。
3. **`ignored_hit` 第二段必须归属 B 层或 post-step**，禁止只由 EXTRACT 算第一段。
4. **EXTRACT 层必须原样 port `scheme=='en'` 分支**；10+ 书语料须含 ≥1 本 EN 书。
5. **`extract_dir` 作顶层键名**（勿用 `ext`）；`all_keys` 为**新增键、不进入旧契约、不影响输出**。

### 4.11 迁移计划（历史，已 Done）

- **Phase 1**（门面）：新增 `context.py`/`registry.py`/`register_all.py`，`verify_chapter.py` 变薄壳，`print_result` 不动。字节级 diff 验收。
- **Phase 2**（实现抽取）：函数体搬入 `layers/*.py`，删原巨型模块。
- **Phase 3**（per-book 配置）：`ManagerConfig.load_book_config` + `verify_config.json {"disable":[...]}`。
- **Phase 4**（可选）：新 reporter 遍历 `findings` 渲染，输出可选 JSON。
- **Phase 5**（零侵入扩展）：新增 `p_layer.py` 自动发现即生效。

### 4.12 结论

本方案以**"产出字节级兼容的 legacy dict"** 为核心策略，把全部校验层解耦为 `layers/` 包下独立模块 + `LAYER_REGISTRY` 自动发现注册 + `VerifyManager` 统一调度，同时**完整保留 CLI、`--fix` 行为、`print_result` 格式、exit 0 条件、字母代号与 10+ 本书流水线**。

---

## 5. 校验用法与命令

### 5.1 用法（`verify/verify_chapter.py`）

`verify/verify_chapter.py` 是**统一强制关卡**（各层顺序见第 1 节注册表）。**`<extract_dir>` 为必填参数**（该书 `_extract` 目录，无写死默认值，换书必须显式传入）。

> **⚠️ 前置依赖**：图片嵌入正确与 G 层「引用块连续」由 Step 3.5 的 `figure/embed_figures.py` 生成——**必须先嵌图、再跑本校验**。未嵌图时图完整性必 FAIL，含 `> **证明/例**` 块却未跑连续性扫描时 G 层必 FAIL。

```bash
# 单章
python verify/verify_chapter.py <ch> <start> <end> <md_file> <extract_dir> \
  [--manual overrides.json] [--ignore ignore.json] [--ignore-figure fig_noise.json]

# 整书
python verify/verify_chapter.py --all <extract_dir> <book_dir> \
  [--ignore ignore.json] [--ignore-figure fig_noise.json]
```

### 5.2 exit 0 的唯一条件（全部阻断层通过）

无 EXTRACT 数据缺失、无 D 层整节缺失、无 A 层 TRULY MISSING、无 B 层 BLOCKING、无 C 层 KATEX ERRORS、无 E 层图缺失、无 F 层图无效、无 G 层引用块断裂（含 G扩展嵌套、EG 例证空隙）、无 H 层结构标签包裹在块引用内、**无 H 层扩展（陈述进块引用）**、无 I 层条目间缺失分隔线、**无 J 层条目块内多余 `---`**、无 K 层证明–编号列表缺空行、无 L 层分隔线缺上下空行、无 M 层显示公式内 `>` 前缀、无 N 层块引用内空 `>` 行 >1、无 O 层 HEAD/INTERNAL 子项缺口、无 P 层 verbose 闸门（练习归拢/页眉噪声/裸编号/缺节/编造条目/长散文/长证明）。**O 层的 TAIL/OCR 缺口（`~` 行）仅告警不阻断；EXTRACT 为数据 provider，永不可禁用。**

### 5.3 常用校验命令

```bash
# 单章校验（最常用）
"<python>" verify/verify_chapter.py <ch> <start> <end> <md_file> <extract_dir>

# 整书校验
"<python>" verify/verify_chapter.py --all <extract_dir> <book_dir>

# 单独跑 KaTeX 校验定位行号
"<python>" format/check_katex.py "<file_path>"

# 两级书完整性扫描（独立于 verify）
"<python>" extract/scan_items.py <ch> <start> <end> <extract_dir>

# 格式后处理（verify PASS 后美化；自动修复 I 层缺失分隔线 + 拆分同行例证明）
"<python>" format/fmt_proofs.py <book_dir>
"<python>" format/fmt_proofs.py <book_dir> --number  # + 证明步骤编号
"<python>" format/fmt_proofs.py <book_dir> --check   # 仅检测标题下分隔线，不改
```

---

## 6. 编号体系（三级 vs 两级）

`extract/extract_items.py` 与 `verify/verify_chapter.py` 默认按**三级**编号 `章.节-号`（N.S-N）工作。**但部分中文教材用两级编号 + 双计数器**，默认三级正则会把公式碎片/集合枚举误读成幻影键，导致虚假 `TRULY MISSING`。

### 两级编号典型：周民强《实变函数论》第三版
- 定义：独立每章计数（`定义1.1`…`定义1.33`）
- 定理/引理/推论/命题：**共用一个连续计数器**（`定理1.1`、`引理1.2`…`命题`…，1.1–1.27 连续）
- 例：按节各自重编（`> **例1**：`）

### 启用方式
- 在 `chapter_map.json` 每章加 `"scheme": "two-level"`，`verify --all` 自动启用
- 或单章显式 `extract/extract_items.py ... --scheme two-level` / `verify/verify_chapter.py ... --scheme two-level`

### 判定与处理
详见 `references/book_patterns.md`（含 OCR 对 `§` 漏识为 `S`/`8` 的现象、`--ignore` 噪声键登记规范、判定树）。遇到新书先对照判定树选对 scheme。

> 两级书的**例完整性**不进 `extract_items`/`verify` 的 A/B 层（例按节重编、跨节重复），统一用 `extract/scan_items.py` 做独立连续性核验（权威）。

---

## 7. `--ignore` 登记规则

`--ignore <extract_dir>/ignore_ch{N}.json` 用于登记**已确认**不必阻断校验的键。该文件**放在本书 `_extract` 目录下**，不进 skill 目录。

1. **作用域：每章一个文件**。`ignore_ch{N}.json`（JSON 字符串数组，如 `["1.7-0"]`），随章传入 `--ignore`。**禁止全局单一文件**。
2. **仅允许忽略两类键**：
   - **(a) OCR 乱码**：提取自破碎/无意义文本块，且全书无对应真实条目
   - **(b) 残留交叉引用**：书中对某条目的引用（"见3.3-1"之类），提取误判为条目
3. **禁止忽略真实条目**：书里确有、应独立成条的编号项，**绝不可进 ignore**。
4. **举证责任**：每条 ignore 必须能在 raw 页面文本中定位到来源块并确认是乱码/交叉引用。
5. **暂定性质**：ignore 非永久删除。若后续发现该键实为真实项，必须从 ignore 移除并补写。
6. **B 层 BLOCKING 解决优先级**：先尝试补真实项；仅当确认是 (a)/(b) 时才进 ignore。

### `--ignore-figure` 图片豁免

`--ignore-figure fig_noise.json`（JSON 数组 `["6.7.9"]` 或字典）登记 OCR 噪声图豁免。脚本会自动合并 `_extract/ignore_ch{N}.json` 与 `_extract/ignore_fig_ch{N}.json`（存在即读）。
