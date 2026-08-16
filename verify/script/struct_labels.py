"""struct_labels.py — 共享「结构标签」正则常量（Phase-1 verbatim 抽取）。

本模块位于 verify/script/，是共享 helper，非校验层（register_all 仅扫描
verify/<snake>/script/<snake>.py 形式的层包，故不会被当作层注册），可安全地被各 layer 显式 import 复用。

本模块只搬位置、不改字符：所有 re.compile(...) 的文本与原始文件逐字符一致，
包括 H_STRUCT_BQ_RE 的注释。Phase-2（归一化、补「式」、合并发散正则）不在本次范围。
"""
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()


import re

# ── 顶层（top-level）结构标签： ^\*\*label ──────────────────────────────

# h_layer._H_EXT_HEADER 与 j_layer._J_HEADER_RE 逐字符相同 → 共享同一常量。
# 形态：顶层、带「式」、中英标签、无 \b、无负向断言。
TOP_LEVEL_HEADER_RE = re.compile(
    r'^\*\*(?:定义|定理|引理|推论|命题|断言|公理|式'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Axiom)'
)

# i_layer._I_ITEM_RE_STRUCT 与 i_layer.fix 内局部 _I_STRUCT 相同 → 共享。
# 形态：顶层、缺「式」、中英标签、无 \b。
I_ITEM_STRUCT_RE = re.compile(
    r'^\*\*(?:定义|定理|引理|推论|命题|断言|公理'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Axiom)'
)

# n_layer 内联（L31 / L72）。形态：顶层、缺「式」、仅中文标签、无 \b。
N_ITEM_RE = re.compile(
    r'^\*\*(?:定义|定理|引理|推论|命题|断言|公理)'
)

# g_layer 内联（L124）。形态：顶层、缺「式」、仅中文标签、带 \b。
# 注意：\b 是真实行为分叉点（CJK 后接数字不构成词边界，故不匹配 `**定义1.1**`），
# 必须原样保留，不可并入其它常量。
G_TOPLEVEL_BREAK_RE = re.compile(
    r'^\*\*(?:定义|定理|引理|推论|命题|断言)\b'
)

# ── 块引用内（ > **label ）结构标签 ─────────────────────────────────────

# Shared: name-prefixed structural label, e.g. `斯捷克洛夫定理 4.11-4`,
# `魏尔斯特拉斯逼近定理 4.11-5`, `Steklov's Theorem 4.11-4`.
# The structural keyword (定理/Theorem/...) is EMBEDDED in the name rather
# than at the start, so the OLD `**定理`-anchored regexes silently missed
# them when they appeared inside a blockquote — producing a false-green PASS.
# A dotted item number (or a heading delimiter) MUST follow the keyword so
# incidental theorem mentions inside proofs (e.g. `> **由 斯捷克洛夫定理 可知**`)
# are NOT mis-flagged.
_STRUCT_NAME = r"[\u4e00-\u9fffA-Za-z·.'-]+"
_STRUCT_KW = (r'(?:定理|定义|引理|推论|命题|断言|公理'
             r'|Theorem|Lemma|Corollary|Proposition|Axiom|Definition)')
_STRUCT_NAME_FORM = (
    _STRUCT_NAME + r'\s*' + _STRUCT_KW +
    r'(?=\s*\d{1,3}(?:[.．\-－]\d{1,3}){1,2}|[（(\[.\:;])'
)

# h_layer.H_STRUCT_BQ（check）。形态：块引用、缺「式」、中英标签、带负向断言。
H_STRUCT_BQ_RE = re.compile(
    r'^\s*>\s+\*\*'
    r'(?:'
    r'(?:定义|定理|引理|推论|命题|断言|公理'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Axiom)'
    r'|' + _STRUCT_NAME_FORM +
    r')'
    # A label followed by `的证明…` (e.g. `定理3.66的证明思路`,
    # `斯捷克洛夫定理 4.11-4 的证明`) is a *proof sketch*, NOT a structural
    # theorem — it legitimately lives inside a `>` blockquote, so don't flag
    # it as a structural-label-in-blockquote violation. The class spans the
    # item number (digits / `.` / `-` / `．` / `－` / space) so the lookahead
    # can reach `的证明` even when a hyphenated number sits between.
    r'(?![\d.\-－．\s]*的证明)'
)

# h_layer.fix 内局部 H_BQ_FIX。形态：块引用、带「式」、中英标签、带负向断言。
# 与 H_STRUCT_BQ_RE 仅差一个「式」——Phase-1 必须保留为独立常量，不可合并。
H_STRUCT_BQ_FIX_RE = re.compile(
    r'^\s*>\s+\*\*'
    r'(?:'
    r'(?:定义|定理|引理|推论|命题|断言|公理|式'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Axiom)'
    r'|' + _STRUCT_NAME_FORM +
    r')'
    r'(?![\d.\-－．\s]*的证明)'
)

# h_layer 内联。形态：块引用、带「式」、中英标签、无负向断言（用于 unlabeled
# 检查跳过——结构性标签不应被误判为「未标注块引用」）。
H_INLINE_STRUCT_BQ_RE = re.compile(
    r'^\s*>\s+\*\*'
    r'(?:定义|定理|引理|推论|命题|断言|公理|式'
    r'|' + _STRUCT_NAME_FORM +
    r')'
)

# ── 例 / 证明 等块引用标签（非 定义 家族，但属「加粗标签」，本次一并抽取） ──

# i_layer._I_ITEM_RE_EXAMPLE 与 fix 内局部 _I_EXAMPLE 相同 → 共享。
# 同时识别「编号在前」体例：> **N.M-K 例（…）**（Kreyszig 等书把例印成编号在前）。
I_ITEM_EXAMPLE_RE = re.compile(
    r'^> \*\*(?:例|Example|\d{1,3}(?:[.．-]\d{1,3}){1,2}\s*(?:例|Example))'
)

# i_layer：编号在前体例（Kreyszig 等把编号印在标签前，如
#   **4.2-1 汉恩-巴拿赫定理（…）** / **4.1-5 例（…）** / > **4.1-8 应用（…）**）。
# 同时覆盖「顶层」与「块引用」两种位置（(?\:\s*>\s*)? 使 > 前缀可选）。
# 标签可位于「编号+名称」之后（如「汉恩-巴拿赫定理」末字才是「定理」），故用 .*? 透传中间名称。
# 证明思路/证明等内部块不含下列结构性标签，不会被误判为 item。
I_ITEM_NUMFIRST_RE = re.compile(
    r'^(?:\s*>\s*)?\*\*\d{1,3}(?:[.．\-]\d{1,3}){1,2}\s'
    r'.*?'
    r'(?:定义|定理|引理|推论|命题|断言|公理|应用|例|注|'
    r'Definition|Theorem|Lemma|Corollary|Proposition|Axiom|Example|Application|Remark)'
)

# i_layer：鲁棒条目检测器（覆盖 关键词开头 / 编号在前 / 名称+关键词+尾随编号 三种体例，
# 含多词英文名如 `Polya Convergence Theorem 4.11-3`、`Weierstrass Approximation Theorem 4.11-5`）。
# 用于 check_i_separators 与 fix_i_separators，使分隔线校验不再对名称前缀定理假绿
# （旧 I_ITEM_STRUCT_RE / I_ITEM_NUMFIRST_RE 只认关键词开头与编号在前尾词为结构关键词，
#  漏掉「名称+定理」与「编号在前+非关键词尾词(Requirement)」体例）。
I_ITEM_RE = re.compile(
    r'^\*\*(?:'
    r'(?:定义|定理|引理|推论|命题|断言|公理'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Axiom)'
    r'|\d{1,3}(?:[.．\-－]\d{1,3}){1,2}\s'
    r'|[\u4e00-\u9fffA-Za-z·.\'\- ]+?\s*'
      r'(?:定理|定义|引理|推论|命题|断言|公理'
      r'|Theorem|Lemma|Corollary|Proposition|Axiom|Definition)'
      r'(?=\s*\d{1,3}(?:[.．\-－]\d{1,3}){1,2})'
    r')'
)

# g_layer._EX_RE。
# 同时识别「编号在前」体例：> **N.M-K 例（…）**。
G_EX_RE = re.compile(
    r'> \*\*(?:例\b(?:\d[\d.]*-[0-9]+|\d+)?\*\*'
    r'|Example\b(?:\s*\d+)?\*\*'
    r'|\d{1,3}(?:[.．-]\d{1,3}){1,2}\s*例)'
)

# g_layer._PF_RE。
G_PF_RE = re.compile(r'> \*\*(?:证明思路|证明|证明梗概|证明概要)\*\*')
