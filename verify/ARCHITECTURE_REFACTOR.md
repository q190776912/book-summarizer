# 校验层解耦重构 — 系统架构设计（ADR-VERIFY-001）

**状态:** Done — Phase 1（facade/门面）与 Phase 2（函数体搬入 layers/）均已完成；原两个巨型层实现模块已删除，17 层全部自包含于 `verify/layers/*.py`，由 `register_all.py` 经 `pkgutil` 自动发现注册。
**作者:** architect（系统架构师）
**日期:** 2025-07-30
**适用范围:** `verify/` 包（book-summarizer skill）

---

## 1. 背景（Background）

重构前，校验逻辑耦合在两个大文件里：

- `verify_chapter.py`（36KB）：编排器 `verify_one()` 直接返回一个硬编码的约 25+ 键 `dict`，
  每个键 = 直接调用一个 imported 检查函数（`check_g_quote_continuity(md)` / `check_d_layer(...)` 等）。
  **D 层逻辑内联在此文件**（`check_d_layer` 约 60 行正则 + 扫 JSON）。`main()` 处理 CLI；`--fix` 调
  `fix_all_layers()`（现仅作兼容 shim 保留）。
- 原两个巨型模块（合计 57KB+，承载 G/H/I/J/K/L/M/N/O 与 E/F 检查 + 对应 `fix_*` 函数，全是模块级函数、
  **无统一接口 / 注册表**）：Phase 2 已将这些实现搬入 `verify/layers/*.py` 并删除原文件。

| 层 | 性质 | 数据来源 | auto-fix | 稳定代号 |
|----|------|----------|----------|----------|
| D | section 缺失 / tail ordinal | 扫 raw `_extract` JSON，独立于 extract_items | ❌ | D |
| A | 完整性（truly missing / mentioned-only / extra） | `extract_items` | ❌ | A |
| B | 抽取完整性（blocking gap） | `extract_items` 内部 rescan | ❌ | B |
| C | KaTeX 校验 | `subprocess` 调 `format/check_katex.py` | ❌ | C |
| E | 图完整性 | E 层（无 `figure_index.json` 时 skip） | ❌ | E |
| F | 图有效性 | F 层（cv2 guard） | ❌ | F |
| G | `>` 块引用连续 / nested / example-proof gap | 扫 `.md` | ✅（仅 quote_gaps；nested/ex_proof 不修） | G |
| H | 结构标签顶层（含 3 扩展：stmt-in-bq / unlabeled-bq / missing-bq） | 扫 `.md` | ✅（4 个 fix） | H |
| I | 条目间分隔线 | 扫 `.md` | ✅ | I |
| J | 条目块内无 `---` | 扫 `.md` | ✅ | J |
| K | 列表后证明空行 | 扫 `.md` | ✅ | K |
| L | 分隔线上下空行 | 扫 `.md` | ✅ | L |
| M | 显示公式块内无 `>` | 扫 `.md` | ✅ | M |
| N | 块引用空 `>` 行过多 | 扫 `.md` | ✅ | N |
| O | 序号子项断号（仅警告 / 部分阻塞） | 扫 `.md` + OCR cross-ref | ❌ | O |

**核心约束（不可破坏）：**

1. CLI 不变：`verify_chapter.py <ch> <start> <end> <md> <ext> [--manual --ignore --ignore-figure --scheme --fix]` 以及 `--all <ext> <book_dir> [...]`
2. `--fix` 行为不变：自动修 G/H/I/J/K/L/M/N（含 H 三扩展），O 仅警告不修
3. `print_result` 输出格式不变（下游 agent 在 Step 4 解析 PASS/FAIL）
4. exit 0 条件不变：无 truly-missing ∧ 无 B-block ∧ 无 KaTeX error ∧ 无 missing-figure ∧ 无 invalid-figure ∧ 无 G gap
5. 层字母代号（G/H/...）在 SKILL.md 与大量 per-book 记忆/笔记中被引用，须作为**稳定标识符**保留
6. 不破坏已在 10+ 本书上跑通的流水线（幂等、中文 UTF-8）

> **关键洞察（决定整个方案走向）：** 约束 #3 要求 `print_result` 原样不变，而 `print_result` 通过**硬编码的约 30 个 dict 键**来渲染输出。因此最稳妥的迁移策略是：
> **让新的 `VerifyManager` 产出一个与旧 `verify_one` 返回结构字节级兼容的 `dict`**，把 `print_result`、退出码逻辑、下游解析全部原样保留。结构化 `Finding` 模型作为**增量能力**在后期（Phase 4）再接管渲染。这样每一阶段都是零行为风险。

---

## 2. 高层设计（High-Level Design）

```
                          ┌─────────────────────────────┐
 CLI (main)  ──args──▶    │  VerifyManager               │
                          │   • __init__(registry, config)│
                          │   • from_registry(registry, cfg) │
                          │   • verify_one(ch,start,end,md,ext) -> dict │
                          │   • fix(md_file) -> dict      │
                          └──────────────┬──────────────┘
                                         │  iterates
                                         ▼
                          ┌─────────────────────────────┐
                          │  LayerRegistry (LAYER_REGISTRY)│
                          │   D A B C E F G H I J K L   │
                          │   M N O  + EXTRACT           │
                          └──────────────┬──────────────┘
                                         │  each layer.run(ctx)
                                         ▼
                          ┌─────────────────────────────┐
                          │  VerifyContext (ctx)         │
                          │  md_file, ext_dir, ch, ...   │
                          │  items, entry_keys, fig_idx  │  ◀── 无全局状态
                          └─────────────────────────────┘
```

每个层 = 一个 `VerifyLayer` 实例，`run(ctx) -> LayerResult`（其 `.legacy` / `.metadata` 片段并入总 dict），
`fix(ctx) -> LayerFixResult`（仅 auto-fixable 层实现）。`verify_one` 返回的 dict 即旧 `verify_one` 返回值（字节级兼容）。

---

## 3. 关键接口签名（Python）

### 3.1 核心类型（`verify/registry.py`）

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

class Severity(str, Enum):
    BLOCKING = "blocking"   # 会导致 FAIL（Phase 1-3 仅作文档/未来 reporter 用，FAIL 判定仍由 print_result 负责）
    WARNING  = "warning"    # 非阻塞
    INFO     = "info"       # 信息

@dataclass
class Finding:
    level: Severity
    code: str               # 子代号，如 'truly_missing' / 'd_missing_section'
    message: str
    data: object = None

@dataclass
class LayerResult:
    code: str
    legacy: Any = None      # 并入 verify_one dict 的片段（给 print_result 用）
    metadata: Dict[str, Any] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)   # 增量：Phase 4 用

@dataclass
class LayerFixResult:
    fix_dict: Dict[str, int] = field(default_factory=dict)   # 仅一个字段；合并键序钉死，见 §8.1②

class VerifyLayer:
    code: str = 'X'
    order: int = 0          # run 运行顺序
    fix_order: int = 999    # fix 运行顺序（仅 auto_fixable 有意义）
    auto_fixable: bool = False
    depends_on: List[str] = []   # 注：任何子类都不设置，manager 也不强制（见 §7）

    def run(self, ctx: "VerifyContext") -> LayerResult: ...
    def fix(self, ctx: "VerifyContext") -> Optional[LayerFixResult]:
        return None         # 默认无操作
```

> **真实子类只设置** `code`、`order`、`auto_fixable`；仅当 `auto_fixable=True` 时设置 `fix_order`。
> 具体层的方法去掉类型注解：`run` 返回 `LayerResult(...)`；auto-fixable 层再实现 `fix` 返回
> `LayerFixResult(fix_dict={...})`。`depends_on` 事实上从不被任何子类设置。

### 3.2 注册表（`verify/registry.py`）

```python
class LayerRegistry:
    def __init__(self): self._layers: dict[str, VerifyLayer] = {}
    def register(self, layer: VerifyLayer) -> VerifyLayer: ...
    def get(self, code: str) -> VerifyLayer: ...
    def all_ordered(self) -> list[VerifyLayer]: ...       # 按 order 排序
    def fixable_ordered(self) -> list[VerifyLayer]: ...   # 按 (fix_order, order) 排序
    def by_code(self) -> dict[str, VerifyLayer]: ...

DEFAULT_RESULT: Dict[str, Any]   # 模块级常量：为每一个 legacy 键注入正确类型的占位值，
                                 # 使被禁用的层不会破坏字节契约（见 §3.3）
```

### 3.3 管理器（`verify/registry.py`）

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
    def __init__(self, registry: LayerRegistry, config: Optional[ManagerConfig] = None): ...
    @classmethod
    def from_registry(cls, registry, config=None) -> "VerifyManager": ...
    def verify_one(self, ch, start, end, md_file, ext_dir) -> Dict[str, Any]: ...
    def fix(self, md_file) -> Dict[str, int]: ...
    # _build_context 为私有方法，外部勿直接调用
```

> **合并规则（实现护栏，code-reviewer 审计）：**
> - `fix()` 遍历 `fixable_ordered()`（按 `(fix_order, order)` 排序），对 `result.update(fr.fix_dict)`，
>   得到键插入序钉死的 change-dict：`h,h_stmt,h_ul,h_mbq,g,i,j,k,l,m,n`。
> - `verify_one()` 对 `all_ordered()` 中每层的 `res.metadata` 做 `merged.update(res.metadata)`（last-writer-wins），
>   再 `final = dict(DEFAULT_RESULT)`；`final.update({ch, md, status, extract_dir, items})`；`final.update(merged)`。
> - `DEFAULT_RESULT` 为每个 legacy 键预置正确类型，被禁用的层因此保持字节安全。
>
> **注意：** `print_result` **不是** manager 的方法，它来自 `from verify.report import print_result`。
> `verify_chapter.verify_one` 先构建 `ManagerConfig`，再 `VerifyManager(LAYER_REGISTRY, cfg).verify_one(...)`；
> `fix_all_layers` shim 调用 `VerifyManager(LAYER_REGISTRY, ManagerConfig(disabled=...)).fix(md)`。

### 3.4 校验上下文（`verify/context.py`）

```python
_UNSET = object()

class VerifyContext:
    def __init__(self, ch, start, end, md_file, ext_dir, manual_path=None,
                 ignore_keys=None, ignore_fig=None, scheme='three-level'):
        self.ch, self.start, self.end = ch, start, end
        self.md_file, self.ext_dir = md_file, ext_dir
        self.manual_path = manual_path
        self.ignore_keys = ignore_keys or set()     # 规范化的 dash-form
        self.ignore_fig  = ignore_fig or set()
        self.scheme = scheme
        # 派生字段（由 EXTRACT 层 / 惰性加载填充）
        self.items = None
        self.entry_keys = None; self.all_keys = None
        self.ignored_hit = None
        self.extraction_blocking = None; self.extraction_warnings = None
        self.label_warns = None
        self._figure_index = _UNSET
        self.provided = set(); self.skipped = set()

    def read_md_lines(self) -> list[str]:
        with open(self.md_file, encoding='utf-8') as f:
            return f.read().split('\n')

    @property
    def figure_index(self):
        if self._figure_index is _UNSET:
            self._figure_index = load_figure_index(self.ext_dir)  # 无则 None
        return self._figure_index
```

> **设计要点：** 所有层只读 `ctx` 字段、只读盘（`read_md_lines` 每次重读），**无任何模块级全局可变状态**。
> `--fix` 先改盘（`mgr.fix(md_file)`），再 `verify_one(...)` 重读，因此幂等性与现有行为一致。

---

## 4. 解耦后的模块布局

```
verify/
├── __init__.py
├── context.py            # VerifyContext（§3.4）
├── registry.py           # Severity / Finding / LayerResult / LayerFixResult
│                         #   VerifyLayer / LayerRegistry / ManagerConfig / VerifyManager
│                         #   DEFAULT_RESULT（模块级常量）
├── register_all.py       # 导入时经 pkgutil 自动发现 verify/layers/ 下所有层并注册进 LAYER_REGISTRY
│                         #   （无需手动维护注册列表）
├── layers/
│   ├── __init__.py
│   ├── extract_layer.py  # EXTRACT：填 ctx.items/entry_keys/all_keys/
│   │                     #   extraction_blocking/extraction_warnings/label_warns；
│   │                     #   仅算 ignored_hit 第一段（stage1）写入 ctx；最终 ignored_hit 由 B 层回写（见 §4.1）。
│   │                     #   legacy 片段含 items/entry_keys（all_keys 为新增键，不进旧契约）。
│   │                     #   非 pass/fail 层，但 mandatory —— manager 特判 code != 'EXTRACT'，永不可禁用。
│   ├── d_layer.py        # D：搬运 verify_chapter.check_d_layer 逻辑
│   ├── a_layer.py        # A：读 ctx.items + ctx.all_keys/entry_keys → truly_missing/mentioned_only/extra/label_warns
│   ├── b_layer.py        # B：读 ctx.extraction_blocking/warnings
│   ├── c_layer.py        # C：subprocess 调 format/check_katex.py
│   ├── e_layer.py        # E：图完整性（无 figure_index 则 skip）
│   ├── f_layer.py        # F：图有效性（cv2 guard）
│   ├── g_layer.py        # G：quote_gaps（fixable）+ nested_bq + ex_proof_gaps（只读）
│   ├── h_layer.py        # H：4 个子检查 + 4 个 fix（fix() 返回含 h/h_stmt/h_ul/h_mbq 的 fix_dict）
│   ├── i_layer.py        # I
│   ├── j_layer.py        # J
│   ├── k_layer.py        # K
│   ├── l_layer.py        # L
│   ├── m_layer.py        # M
│   ├── n_layer.py        # N
│   ├── o_layer.py        # O：仅警告/部分阻塞（不 fix）
│   ├── _fig_common.py    # 内部 helper（'_' 前缀，自动发现跳过）
│   └── _template_layer.py# 复制起点（'_' 前缀，自动发现跳过）
├── verify_chapter.py     # 保留：main() / verify_one()(薄壳) / verify_all()(薄壳)，调用 manager
├── key_parse.py          # 不变
├── report.py             # print_result 来自本模块；Phase 1-3 不变
├── manage_ignore.py      # 不变
└── review_tool.py        # 不变
```

### 各层 → legacy dict 键 的映射（决定 print_result 不变）

| 层 code | legacy 键（并入总 dict） | auto_fixable | order | fix_order |
|---------|--------------------------|--------------|-------|-----------|
| EXTRACT | `items`, `entry_keys`, `all_keys`（新增键，不影响输出）,（EXTRACT 层；**不**直接产出 `ignored_hit`，见 B/§4.1） | ❌ | 0 | – |
| D | `d_layer`(missing_sections/tail_gaps/suspect) | ❌ | 1 | – |
| A | `truly_missing`, `mentioned_only`, `extra`, `label_warns` | ❌ | 2 | – |
| B | `blocking`, `warnings`, `ignored_hit`（**最终值**；两段式，见 §4.1） | ❌ | 3 | – |
| C | `katex_errors`, `katex_lines` | ❌ | 4 | – |
| E | `fig_missing`, `fig_extra`（legacy 外，`metadata['skipped']` = `e_layer is None` 完整语义：文件缺失 **或** 本章无图条目） | ❌ | 5 | – |
| F | `fig_invalid`, `fig_invalid_warn` | ❌ | 6 | – |
| G | `quote_gaps`, `nested_bq`, `ex_proof_gaps` | ✅ | 7 | 5 |
| H | `h_structural_bq`, `h_stmt_bq`, `h_ul_bq`, `h_mbq` | ✅ | 8 | 1 |
| I | `i_sep_gaps` | ✅ | 9 | 6 |
| J | `j_header_dash` | ✅ | 10 | 7 |
| K | `k_proof_list` | ✅ | 11 | 8 |
| L | `l_sep_blanks` | ✅ | 12 | 9 |
| M | `m_dm_gt` | ✅ | 13 | 10 |
| N | `n_bq_empty` | ✅ | 14 | 11 |
| O | `o_subitem_gaps` | ❌ | 15 | – |

> 管理器额外注入顶层键：`ch`, `md`, `status`, `extract_dir`, `items`, `fig_skipped`。
> **`fig_skipped` 必须 == `e_layer is None` 的完整语义**（文件缺失 **或** 本章自身无图条目，两种情况都 SKIP）。
> 实现上由 **E 层**在其 `LayerResult.metadata['skipped']` 中携带该布尔，管理器据此注入 `fig_skipped`，
> **禁止**窄化为 `ctx.figure_index is None`（否则「文件在但本章无图条目」的章节会丢失 SKIP 注记 → 破字节级 gate，见 §8.1 约束①）。

### 注册顺序即“稳定代号 + 运行顺序”

字母代号（D/A/B/C/E/F/G/H/I/J/K/L/M/N/O）作为 `VerifyLayer.code` 永久保留——SKILL.md 与 per-book 内存
引用它们时不会失效。H 的 3 个扩展（stmt-in-bq / unlabeled-bq / missing-bq）仍归属 `code="H"` 这一个层，
内部 4 个子检查/子 fix 不变，`fix()` 返回的 `fix_dict` 仍为 `{'h':..,'h_stmt':..,'h_ul':..,'h_mbq':..}`，
**与现有 `fix_all_layers` 的 change-dict 键完全一致**。

**自动发现机制：** `register_all.py` 在导入时遍历 `pkgutil.iter_modules(verify.layers.__path__)`，跳过头为
`_` 的模块（`_fig_common.py`、`_template_layer.py`、`__init__.py`），导入其余每个模块并把其中**所有**
`VerifyLayer` 子类（不含 `VerifyLayer` 自身）注册进全局 `LAYER_REGISTRY`。**新增一层 = 丢一个 `X_layer.py` 进
`verify/layers/`，无需改动 `register_all.py`。**

---

### 4.1 EXTRACT 层的两条关键逻辑（Phase 1 字节级 gate 的关键）

**(a) `scheme='en'` 分支必须原样 port。** 旧 `verify_one`（verify_chapter.py:342-361、395-397）对英文书有专门路径：调 `extract_items_en`、按章过滤前向引用（`chpart != ch` 的条目丢弃）、把 key 规范化成中文形式；并在 md 侧把 `entry_keys`/`all_keys` 限制到当前章（`_first_num(k) == ch`）。EXTRACT 层必须**完整搬运**这段逻辑（含 three-level / two-level / en 三套），否则 EN 书整体漂移。

**(b) `ignored_hit` 两段式，第二段归 B 层。** 旧逻辑分两段：
- 第一段（EXTRACT 阶段）：`ignored_hit = sorted(extracted & ignore_keys)`。
- 第二段（在 B 层产出 `blocking` 之后执行，verify_chapter.py:377-389）：遍历 `blocking` 消息，若某条阻塞引用的键全部 ∈ `ignore_keys`，则把这些 `bkeys` 并入 `ignored_hit` 并从 `blocking` 中剔除该条。

→ 设计落地：**EXTRACT 算第一段并写入 `ctx.ignored_hit`（stage1）**；**B 层在产出 `blocking` 后做第二段 regex 抑制、把 `bkeys` 并入 `ctx.ignored_hit`，并在自己的 legacy 片段中回写最终 `ignored_hit`**（因 manager 按 order 合并、后写覆盖，B 的 `ignored_hit` 会覆盖 EXTRACT 的 stage1，得到与旧完全一致的最终值）。禁止把 `ignored_hit` 只放在 EXTRACT 一次性算完（那样第二段 augmentation 会丢失）。

**(c) E/F 在 check 返回 None 时必须显式 emit 空列表。** 旧 `verify_one`（verify_chapter.py:419-422）用 `e_layer['missing'] if e_layer else []` 守卫，保证 `fig_missing/fig_extra/fig_invalid/fig_invalid_warn` 永远存在于 dict。E/F 层包底层实现时，若底层返回 None，必须 emit `fig_missing: [], fig_extra: []`（E）与 `fig_invalid: [], fig_invalid_warn: []`（F），**不得**直接 `legacy={... e['missing'] ...}`（会崩）。这与 `fig_skipped` 由 E 的 `metadata['skipped']` 统一守卫互不冲突，只是双保险。

**EN 书回归要求：** 10+ 本书验收语料中**至少包含 1 本 EN 书**，否则 `scheme='en'` 分支的回归盲区会让字节级 gate 形同虚设。

---

## 5. Registry / Manager 用法示例

### 5.1 定义一个层（复制 `_template_layer.py`）

```python
# verify/layers/x_layer.py  —— 由 _template_layer.py 复制而来
from verify.registry import VerifyLayer, LayerResult, LayerFixResult
from verify.register_all import LAYER_REGISTRY   # 全局注册表，自动发现，无需手动注册

class XLayer(VerifyLayer):
    code = 'X'            # 新大写字母，不与现有 16 个重复（EXTRACT/D/A/B/C/E/F/G/H/I/J/K/L/M/N/O）
    order = 16            # 运行顺序；现有 0..15 已占用，新层用 16+
    auto_fixable = False  # 若支持 --fix，改为 True 并实现 fix()，并设 fix_order

    def run(self, ctx):
        # 只贡献 DEFAULT_RESULT 中已存在的键（否则破字节契约）
        count = 0
        return LayerResult(code=self.code, legacy=None, metadata={'xxxx': count})

    # 仅当 auto_fixable=True 时实现：
    # def fix(self, ctx):
    #     changes = 0
    #     return LayerFixResult(fix_dict={'xxxx': changes})
```

要点（与 §4 自动发现一致）：
- 复制 `_template_layer.py` → `X_layer.py`；类名 `XLayer(VerifyLayer)`。
- 设置 `code`（新大写、不与现有 16 个重复）、`order`（16+）、`auto_fixable`；若可修再加 `fix_order`。
- `run(self, ctx)` 返回 `LayerResult(code=self.code, metadata={...})`，**只贡献 `DEFAULT_RESULT` 中已有的键**。
- 若 `auto_fixable`，`fix(self, ctx)` 返回 `LayerFixResult(fix_dict={'xxxx': 变更数})`。
- **新增结果键**必须同步更新 `verify/registry.py` 的 `DEFAULT_RESULT` **和** `verify/report.py` 的
  `print_result`，否则字节契约破裂。
- 用全局注册表 `from verify.register_all import LAYER_REGISTRY`，无需手动 `register`。

### 5.2 注册与运行（全局注册表，自动发现）

```python
# register_all.py 在导入时已完成自动发现；直接使用全局 LAYER_REGISTRY
from verify.register_all import LAYER_REGISTRY
from verify.registry import VerifyManager, ManagerConfig
from verify.report import print_result

cfg = ManagerConfig(manual_path=mp, ignore_keys=ik, ignore_fig=ifig, scheme=scheme)
mgr = VerifyManager(LAYER_REGISTRY, cfg)          # 或 VerifyManager.from_registry(LAYER_REGISTRY, cfg)
legacy_dict = mgr.verify_one(ch, start, end, md_file, ext_dir)
status = print_result(legacy_dict)                # print_result 来自 verify.report；manager 不含此方法
```

### 5.3 `--fix` 流程（与现有行为一致）

```python
from verify.register_all import LAYER_REGISTRY
from verify.registry import VerifyManager, ManagerConfig
from verify.report import print_result

mgr = VerifyManager(LAYER_REGISTRY,
                    ManagerConfig(manual_path=mp, ignore_keys=ik, ignore_fig=ifig, scheme=scheme))
changes = mgr.fix(md_file)        # 按 fix_order 跑 H→G→I→J→K→L→M→N
                                  # change-dict 键插入序钉死：h,h_stmt,h_ul,h_mbq,g,i,j,k,l,m,n
                                  # （H.fix 的 fix_dict 必须按此序构建，mgr.fix 合并时不得对键排序）
parts = [f"{k}={v}" for k, v in changes.items() if v > 0]
# 注：--all 模式必须【逐章】调用 mgr.fix(md_file)+mgr.verify_one(...)（旧 main 即 per-chapter），
#     不可一次性 fix 全部；且字节级 diff 范围应包含完整 --fix stdout（含 [FIX] Applied: 行）。
if parts: print(f"[FIX] Applied: {', '.join(parts)}")
else:    print("[FIX] No changes needed")
legacy_dict = mgr.verify_one(ch, start, end, md_file, ext_dir)   # fix 改盘后重读，复验所有 check
status = print_result(legacy_dict)
sys.exit(0 if status == 'PASS' else 1)
```

### 5.4 Per-book 启用/禁用

```python
cfg = ManagerConfig.load_book_config(book_dir)   # 读 verify_config.json {"disable":["O"]}，大写化进 cfg.disabled
mgr = VerifyManager(LAYER_REGISTRY, cfg)
# O 层被跳过：o_subitem_gaps 不出现、不计入；其余完全不变
# 注意：EXTRACT 永不可禁用（manager 特判 code != 'EXTRACT'）；其余层可按书 disable。
```

> A/B 与 EXTRACT **不存在依赖关系**（无 `depends_on` 机制，manager 也不强制）：禁用 EXTRACT 不会级联跳过 A/B。
> EXTRACT 由 manager 特判为 mandatory，根本不在 `disabled` 的可选范围内。

---

## 6. 迁移计划（分步、每步可回滚、每步字节级兼容）

### Phase 0 — 勘察（✅ 已完成）
读 `verify_chapter.py` / `key_parse.py` / `report.py` 及原层实现，完成 §4 的“层 → legacy 键”映射，
确认 `print_result` 是唯一契约权威。

### Phase 1 — 适配器/门面（低风险，~1–2 天）★ 不破坏任何现有行为
- 新增 `context.py`、`registry.py`（`VerifyLayer` / `LayerRegistry` / `ManagerConfig` / `VerifyManager` /
  `LayerResult` / `LayerFixResult` / `Severity` / `Finding` / `DEFAULT_RESULT`）。
- 新增 `layers/` 包：每个层模块**只做薄包裹**（import 现有函数并调用），实现逻辑仍留在
  原层实现模块（D 内联逻辑搬到 `d_layer.py`，不改语义）。
- 新增 `register_all.py`，导入时经 `pkgutil` 自动发现 `verify/layers/` 下所有层、按 `order` 注册进 `LAYER_REGISTRY`。
- 改写 `verify_chapter.py`：`verify_one()` 变为薄壳（`mgr.verify_one(...)`）；`verify_all()` 薄壳；
  `main()` 的 `--fix` 改为 `mgr.fix(md_file)` + `mgr.verify_one(...)`；保留 `fix_all_layers` 作兼容 shim。
- **`print_result` / `report.py` 原样不动。**
- **验收硬门禁：** 对 10+ 本书（**含 ≥1 本 EN 书**）跑新旧两版，对 **完整 stdout**（`print_result` 输出 **+ `[FIX] Applied:` 行**）做 `diff`，必须字节级一致。EN 书缺失则 `scheme='en'` 分支回归盲区。

### Phase 2 — 实现抽取（中风险，~2–3 天）
- 将每个 `check_*` / `fix_*` 函数体**搬入**对应 `layers/*.py`，删除原实现模块中的对应函数（仅留兼容 re-export）。
- 层模块自包含，去掉交叉 import。
- **验收：** 同 Phase 1 的字节级 diff；每层加单测（输入 `.md` → legacy 片段）。

### Phase 3 — Per-book 配置与 enable/disable（低风险，~0.5 天）
- `ManagerConfig.load_book_config` + `<book_dir>/verify_config.json`（`{"disable":["O"]}`）。
- CLI 不变，内部 enable/disable 可用。
- **验收：** 对某书禁用 O → `o_subitem_gaps` 缺失且不计入；其余不变。

### Phase 4 — 新 reporter（可选，稳定后，~2 天）
- 改写/新增 `report.py` 使其遍历 `LayerResult.findings` 渲染，不再硬编码键；可选输出 JSON 供下游 agent
  （比解析 PASS/FAIL 文本更稳）。
- **验收：** PASS/FAIL 判定与 Phase 1-3 完全一致；JSON 模式可选开启。

### Phase 5 — 扩展 P/Q 验证零侵入（~0.5 天）
- 新增 `layers/p_layer.py`（复制 `_template_layer.py`），自动发现即生效；**无需改 `register_all.py` / manager / CLI**。
- **验收：** 无需改 manager / CLI / report 即可加入新层。

> **时间盒与硬门禁：** 每阶段结束必须先在 10+ 本书语料上通过“字节级 diff”再进入下一阶段。
> Phase 1 & 2 目标是**零差异**；Phase 3 仅影响被禁用的层；Phase 4 改变输出形态但保留 PASS/FAIL；
> Phase 5 纯增量。任何阶段出问题，`git revert` 该阶段即可，因为 Phase 1 之前 `verify_chapter.py` 未动。

---

## 7. 可扩展性要点

- **加 P/Q 层 = 新增一个模块，自动发现即生效**，管理器按 `order` 自动调度，无需改 `VerifyManager` / CLI / `register_all.py`。
- **Phase 1-3 下：** 新层会在 legacy dict 中新增一个键，`print_result` 需加一个渲染块（低侵入，1 处）；
  并须同步更新 `DEFAULT_RESULT`（registry.py）。
- **Phase 4 后（遍历 findings）：** 真正零侵入——reporter 通用渲染，新层无需任何改动即可出报告。
- `VerifyLayer.depends_on` 属性存在但**任何子类都不设置、manager 也不强制**：层间顺序完全由 `order` /
  `fix_order` 决定，不存在“数据准备层 → 消费层”的依赖机制。EXTRACT 由 manager 特判为 mandatory，
  永不可禁用；其余层可按书 `disable`。

---

## 8. 影响与风险（供 code-reviewer 协作）

**变容易：**
- 单测可针对单个层（输入 `.md` → legacy 片段），不再需要跑整章。
- 加新层、按书禁用层、调整 fix 顺序都变成“数据/注册”操作。
- 移除 36KB+57KB 两个巨型文件的耦合，review diff 变小。

**需要重新审视：**
- 现有 exit 0 条件（约束 #4）在代码里实际比描述更宽——`print_result` 把下列任一非空即判 FAIL：
  `d_layer.missing_sections`、 `truly_missing`、 `blocking`(B)、 `katex_errors`、 `fig_missing`、
  `fig_invalid`、 `quote_gaps`、 `nested_bq`、 `ex_proof_gaps`、 `h_structural_bq`、 `h_stmt_bq`、
  `h_ul_bq`、 `h_mbq`、 `i_sep_gaps`、 `j_header_dash`、 `k_proof_list`、 `l_sep_blanks`、
  `m_dm_gt`、 `n_bq_empty`、 以及 `o_subitem_gaps` 中以 `x` 开头的条目。
  **方案通过保留 `print_result` 不动，使该集合 100% 不变**——这是“零行为风险”的根本保证。
- G 层只有 `quote_gaps` 可修；`nested_bq` / `ex_proof_gaps` 无 fix，保持现有“只修 quote_gaps、其余仍阻塞”的行为。
- O 层混有阻塞(`x`)与警告(`~`)，保留原始字符串（含前缀）进入 `o_subitem_gaps`，由 `print_result` 切分。
- 中文 UTF-8：`read_md_lines` / `open(..., encoding='utf-8')` 全程保留；cv2 的 `np.fromfile` 路径保留（Windows 中文路径）。

**风险与缓解：**
| 风险 | 缓解 |
|------|------|
| Phase 2 搬函数时改到语义 | 先有 Phase 1 字节级基线；Phase 2 后再 diff 一次 |
| `fig_skipped` 语义变窄（文件在但本章无图条目时丢失 SKIP 注记） | 改为按 **E 层 `metadata['skipped']`（= `e_layer is None` 完整语义）** 注入，禁止 `ctx.figure_index is None`（见 §8.1 约束①） |
| EXTRACT 被误禁用 | manager 特判 `code != 'EXTRACT'`，EXTRACT 永不可禁用；其余层可按书 disable |
| `--fix` 旧代码直接调 `fix_all_layers` | 保留 shim；新路径走 `mgr.fix(md_file)` |

---

### 8.1 字节级 gate 的 5 条硬约束（经 code-reviewer 审计追加）

1. **`fig_skipped` 必须 == `e_layer is None`**（含「文件在但本章无图条目」两种情况都 SKIP）。禁止窄化为 `ctx.figure_index is None`。
2. **H 层 `fix()` 内部子 fix 顺序钉死 `h→h_stmt→h_ul→h_mbq`**；`mgr.fix` 产出的 change-dict 键插入序钉死 `h,h_stmt,h_ul,h_mbq,g,i,j,k,l,m,n`；字节级 diff 范围包含**完整 `--fix` stdout**（含 `[FIX] Applied:` 行）。
3. **`ignored_hit` 第二段（在 B 层产出 blocking 之后执行的 bkeys 合并）必须归属 B 层或 post-step**，禁止只由 EXTRACT 算第一段。
4. **EXTRACT 层必须原样 port `scheme=='en'` 分支**；10+ 书语料须含 ≥1 本 EN 书。
5. **`extract_dir` 作顶层键名**（勿用 `ext`）；`all_keys` 为**新增键、不进入旧契约、不影响输出**（避免将来 dict 级相等比对时误判差异）。

### 8.2 次要记录（不破 print_result 输出）

- **F6**：`--all --fix` 必须逐章 `fix(md_file)+verify_one(...)`（旧 `main` 即 per-chapter），勿一次性 fix 全部章节。
- **F7**：dict 顶层键务必用 `extract_dir`（`report.py` 用 `r.get('extract_dir','')`）——已确认 doc 采用 `extract_dir`，仅提醒别手滑。

### 8.3 实现期护栏（code-reviewer 追加，非文档缺陷）

- **合并语义 = last-writer-wins**：`verify_one()` 合并各层 metadata 时必须按 `order` 用 `dict.update`，
  **同键后写覆盖**。这是 §8.1③（F2）正确性的硬依赖——EXTRACT(order 0) 写 `ignored_hit=stage1`，B(order 3) 写最终值，
  必须 B 覆盖 EXTRACT；若反过来（或去重合并）F2 修复会悄悄失效。`§3.3` 的 `verify_one` 注释已注明此语义。
- **E/F 的 None→空列表**：E 层包底层图完整性检查、F 层包底层图有效性检查时，底层返回 None 必须 emit
  `fig_missing:[]`/`fig_extra:[]`（E）与 `fig_invalid:[]`/`fig_invalid_warn:[]`（F），镜像旧 `e_layer['missing'] if e_layer else []` 守卫，
  既对称又防「直接读键」的代码路径崩溃（§4.1(c)）。

---

## 9. 结论

本方案以 **“产出字节级兼容的 legacy dict”** 为核心策略，把 16 个校验层（含 H×4、G×3）解耦为
`layers/` 包下独立模块 + `LAYER_REGISTRY` 自动发现注册 + `VerifyManager` 统一调度，同时**完整保留 CLI、
`--fix` 行为、`print_result` 格式、exit 0 条件、字母代号与 10+ 本书流水线**。分阶段迁移每步可回滚、
每步有字节级 diff 硬门禁，未来加 P/Q 层零侵入。
