"""_struct_labels.py — 共享「结构标签」正则常量（Phase-1 verbatim 抽取）。

下划线前缀：被 register_all.py 的 pkgutil 自动发现跳过（if _name.startswith('_')），
因此本模块不会被当作 verify layer 注册，可安全地被各 layer 显式 import 复用。

本模块只搬位置、不改字符：所有 re.compile(...) 的文本与原始文件逐字符一致，
包括 H_STRUCT_BQ_RE 的注释。Phase-2（归一化、补「式」、合并发散正则）不在本次范围。
"""

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

# h_layer.H_STRUCT_BQ（check，L117）。形态：块引用、缺「式」、中英标签、带负向断言。
H_STRUCT_BQ_RE = re.compile(
    r'^\s*>\s+\*\*(?:'
    r'(?:定义|定理|引理|推论|命题|断言|公理'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Axiom)'
    # A label followed by `的证明…` (e.g. `定理3.66的证明思路`) is a *proof
    # sketch*, NOT a structural theorem — it legitimately lives inside a `>`
    # blockquote, so don't flag it as a structural-label-in-blockquote violation.
    r'(?![\d.]*的证明)'
    r')'
)

# h_layer.fix 内局部 H_BQ_FIX（L389）。形态：块引用、带「式」、中英标签、带负向断言。
# 与 H_STRUCT_BQ_RE 仅差一个「式」——Phase-1 必须保留为独立常量，不可合并。
H_STRUCT_BQ_FIX_RE = re.compile(
    r'^\s*>\s+\*\*(?:'
    r'(?:定义|定理|引理|推论|命题|断言|公理|式'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Axiom)'
    r'(?![\d.]*的证明)'
    r')'
)

# h_layer 内联（L261 / L309）。形态：块引用、带「式」、仅中文标签、无负向断言。
H_INLINE_STRUCT_BQ_RE = re.compile(
    r'^\s*>\s+\*\*(?:定义|定理|引理|推论|命题|断言|公理|式)'
)

# ── 例 / 证明 等块引用标签（非 定义 家族，但属「加粗标签」，本次一并抽取） ──

# i_layer._I_ITEM_RE_EXAMPLE 与 fix 内局部 _I_EXAMPLE 相同 → 共享。
# 同时识别「编号在前」体例：> **N.M-K 例（…）**（Kreyszig 等书把例印成编号在前）。
I_ITEM_EXAMPLE_RE = re.compile(
    r'^> \*\*(?:例|Example|\d{1,3}(?:[.．-]\d{1,3}){1,2}\s*(?:例|Example))'
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
