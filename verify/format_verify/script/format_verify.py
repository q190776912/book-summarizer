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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见
# verify/format_verify/format_verify.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""format_verify.py — F-LAYER (order 6): unified format verification.

fixer 代号 H/G/I/J/K/L/M/N 对应的检测项：

    C  katex_validation        -> KaTeX render validation (subprocess)
    G  blockquote_continuity   -> quote-block continuity / nested / example-proof gap
    H  structural_label_guard  -> structural label in blockquote (4 sub-checks)
    I  item_separator          -> `---` between consecutive items
    J  intra_item_dash         -> no `---` inside an item block
    K  proof_list_spacing      -> blank line between a list's last item and a
                                  following new block (bq/$$/label/<div)
    L  separator_spacing       -> blank lines around `---` separators
    M  math_blockquote_leak    -> `>` lines inside display math blocks
    N  blockquote_spacing      -> excessive empty `>` lines inside blockquotes

所有检测逻辑内联于本文件（超长公式行检测独立于 `long_row_check.py`）；本层产出 19 个字节契约键（含 `heading_sep`/`heading_blank_above`/`long_formula_rows`）
（显示公式行过长 → `\tag` 重叠风险，WARN 非阻断；由 DEFAULT_RESULT 与契约测试的
动态 ALLOWED 集覆盖）——故 `report.py`、`verify_chapter.py` 与契约测试保持通过。

Auto-fix is NOT performed by this layer: it is implemented by the eight
`fix_*.py` modules in this same `script/` directory, which self-register via
`register_fixer` under the legacy fixer codes H/G/I/J/K/L/M/N (fix-dict keys
`h/h_stmt/h_ul/h_mbq/g/i/j/k/l/m/n`, byte-compatible unchanged).
"""
from verify.script.base import VerifyLayer, LayerResult

import re
import subprocess

from verify.script.struct_labels import (
    G_EX_RE, G_PF_RE, G_TOPLEVEL_BREAK_RE,
    G_ITEM_BQ_HEAD_RE,
    G_BQ_BOLD_HEAD_BOUNDARY_RE,
    N_ITEM_RE,
    H_STRUCT_BQ_RE, H_INLINE_STRUCT_BQ_RE, TOP_LEVEL_HEADER_RE,
    I_ITEM_RE, I_ITEM_EXAMPLE_RE,
)
from lib.regexlib import G_HEAD, FMT_HR_RE, FMT_SEC_RE
from long_row_check import check_long_formula_rows, LONG_FORMULA_CHECK_ENABLED  # 显示公式行过长（tag 重叠）WARN；受开关控制


# ===========================================================================
# C-LAYER: KaTeX validation (subprocess)
# ===========================================================================
def check_katex(md_file):
    """Run check_katex.py on the markdown file, return (has_errors, error_lines).

    The checker lives at `verify/format_verify/script/check_katex.py` (the
    whole katex detection subsystem — check_katex + katex_heuristics +
    katex_render + katex_validate.js). Resolve it from the skill root (`_ROOT`) so it always points
    at the live file.  The subprocess is guarded: any failure to launch
    (missing node / katex JS runtime) or a non-zero exit degrades to
    "(False, [])" — never crashes `verify_one`."""
    check_path = os.path.join(
        _ROOT, 'verify', 'format_verify', 'script', 'check_katex.py')
    try:
        r = subprocess.run([
            sys.executable, '-X', 'utf8', check_path, md_file
        ], capture_output=True, text=True, encoding='utf-8')
    except (OSError, FileNotFoundError):
        # node / check_katex.py unavailable in this environment — skip silently.
        return False, []
    lines = [l for l in r.stdout.strip().splitlines()
             if l.strip() and not l.strip().startswith('KATEX ERRORS') and not l.startswith('KATEX CHECK')]
    has_errors = bool(lines) and r.returncode != 0
    return has_errors, lines


# ===========================================================================
# G-LAYER: quote-block continuity (structural)
# ===========================================================================
# <div> figure blocks cannot live inside a blockquote (CommonMark); they
# naturally exit it, so treat a <div> as a block terminator. This avoids a
# false conflict with the C-layer, which requires a truly blank line before
# a <div> (a `> ` empty-quote line would itself fail C).
# ANY ATX heading level (`#`…`######`) terminates the blockquote context —
# not just `## `: a heading after a proof block ends it, and the blank line
# required above headings (heading_blank_above) is a legitimate inter-block
# separator.
G_TERM = re.compile(r'^(?:---+\s*$|#{1,6}\s|\*\*[^*]+\*\*|\$\$\s*$|<div|\s*\|)')
#     🔴 `\s*\|` = 顶级 markdown 表格行也是**块终止符**（Rosen 8e ch8 译单元实测，
#     2026-09-26）：原书常把示例的题面与其数据表/解答表分排，EN 源里 `**Example 1.**`
#     不被 G_HEAD 认出（G_HEAD 只认中文 证明/证/例），故该断裂只在**译单元**暴露；
#     表格既是一块的结束也是下块的开端，其前的空行是合法的分块空行，不判「bare blank」。

NESTED_BQ = re.compile(r'^>\s*>\s*\S')

# 顶层「非散文」块起始：这些块自带边界语义，item 块与其之间不要求 `---`。
_NON_PROSE_START = re.compile(r'^(?:---+\s*$|#{1,6}\s|\*\*[^*]+\*\*|\$\$|<div|\s*\||>)')


def check_g_quote_continuity(md_file):
    """G-LAYER: quote-block continuity.

    Returns a list of violation strings (with line numbers). Empty = pass.

    🔴 判据必须**语言无关**（Strogatz 3e 2026-09-27 根治）：旧版用只认中文
    「证明|证|例」的 `G_HEAD` 开块，导致同一结构 EN 源单元不开块、CN 译单元判
    断裂——译者为过关把合法分块空行改写成空 `>` 行或私加 `---`，源/译两版结构
    分叉。现统一用 `G_ITEM_BQ_HEAD_RE`（例/Example/证明/Proof/解答/Solution）。
    🔴 「下一个引用行是不是**新块**」还要认**任意粗体标签头**（`G_BQ_BOLD_HEAD_
    BOUNDARY_RE`，Shafarevich 代数几何 1 附录 2026-09-28）：本技能的另一判据
    `_H_MISSING_BQ` 要求 `注/Note/Remark` 也包成 `> **Remark** …`，而六词表不含
    它们，于是「证明块 + 合法空行 + `> **Remark**`」被本检测判断裂，写手只能
    把 Remark 挤进证明块（改结构）才过闸。实测放宽：corpus 全量 md 消 5 误报 /
    新增 0 报告（散文续行从不以粗体 run 起头，保护力度不降）。

    Flagged:
      (1) **真断裂**：item 块内出现裸空行（无 `>` 的纯空行），且下一个非空行仍以
          `>` 开头但不是新 item 的头——同一个 blockquote 被劈成两段。
      (2) **半包例子**（writing-rules V-F）：块头带 `>` 而正文留在顶层裸奔——即
          裸空行后接顶层散文，且该 `>` 组除头行外没有任何正文行。
    合法（不判）：裸空行后接新 item 头、或 `---`/标题/顶层 `**标签**`/`$$`/表格/
    `<div` 等自带边界的块；以及**正文完整的 item 块**结束后接顶层散文（该处缺的
    是 `---`，由 `check_i_prose_separator` 报，消息指向正确判据）。
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    n = len(lines)
    out = []
    in_block = False
    body_seen = False      # 头行之后是否出现过 `>` 正文行（判「半包」）
    for i in range(n):
        ln = lines[i]
        if G_ITEM_BQ_HEAD_RE.match(ln):
            in_block = True
            body_seen = False
            continue
        if G_TERM.match(ln) and not ln.lstrip().startswith('>'):
            in_block = False
            continue
        if ln.startswith('>'):
            if ln.strip() not in ('>', '> '):
                body_seen = True
            continue
        # Only flag truly bare blank lines (no `>` prefix), not empty blockquote
        # lines (`> ` or `>`) which keep the blockquote contiguous.
        if in_block and ln.strip() == '' and not ln.startswith('>'):
            j = i + 1
            while j < n and lines[j].strip() == '':
                j += 1
            if j >= n:
                continue  # trailing blank at EOF — nothing after to split, harmless
            nx = lines[j]
            is_newblock = bool(G_ITEM_BQ_HEAD_RE.match(nx) or G_HEAD.match(nx)
                               or G_BQ_BOLD_HEAD_BOUNDARY_RE.match(nx))
            is_term = bool(G_TERM.match(nx) and not nx.lstrip().startswith('>'))
            if is_newblock or is_term:
                in_block = bool(is_newblock and not is_term)
                continue  # legitimate inter-block separator
            if nx.startswith('>'):
                out.append(f"  x L{i+1}: bare blank line splits the `> **例/证明` block "
                           f"(quote resumes at L{j+1}: {nx.strip()[:40]})")
            elif not body_seen:
                out.append(f"  x L{i+1}: example/proof head is quoted but its body is "
                           f"bare top-level prose (half-wrapped block, L{j+1}: "
                           f"{nx.strip()[:40]})")
            # 正文完整 + 顶层散文：块到此确实结束，交给 I 层分隔线判据
            in_block = False
        # A top-level (non->) non-blank line closes the blockquote
        if in_block and ln.strip() and not ln.startswith('>'):
            in_block = False
    return out


def check_i_prose_separator(md_file):
    """I-LAYER: `---` required between a completed item block and prose.

    writing-rules V-F「item 上方或下方是描述性散文时必须加 `---`」的机械化。
    🔴 判据语言无关（同 `check_g_quote_continuity` 的根治口径）：旧版该结构只在
    CN 侧被 G_HEAD 开块后以「断裂」形式误报，EN 侧同位裸奔无人管，两版只能各自
    用不同手段规避。

    判：一个 `>` item 块（头行为 例/Example/证明/Proof/解答/Solution，且头外还有
    正文行）结束后的第一个非空行是**顶层散文**（既非 `---`/标题/顶层 `**标签**`/
    `$$`/表格/`<div`，也非新的 `>` 块）→ 缺 `---`。块尾的空 `>` 行（`>`/`> `）与
    其后的顶层散文之间同样缺 `---`——空 `>` 行是块**内**留白，不是块间分隔线。
    不判：文件结束、`---` 已在位、下块自带边界（标题/标签/公式/表格/图）。
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    n = len(lines)
    out = []
    i = 0
    while i < n:
        if not G_ITEM_BQ_HEAD_RE.match(lines[i]):
            i += 1
            continue
        j = i + 1
        body = False
        while j < n and lines[j].startswith('>'):
            if lines[j].strip() not in ('>', '> '):
                body = True
            j += 1
        if not body:
            i = j
            continue                      # 半包由 G 层报，不在此重复
        k = j
        while k < n and lines[k].strip() == '':
            k += 1
        if k < n and not _NON_PROSE_START.match(lines[k]) \
                and not G_ITEM_BQ_HEAD_RE.match(lines[k]):
            out.append(f"  x L{j}: missing `---` between the `> **例/证明**` block "
                       f"(ends L{j}) and the descriptive prose at L{k+1}: "
                       f"{lines[k].strip()[:50]}")
        i = j
    return out

# ===========================================================================
# 译本「结构继承源本」豁免谓词（SSOT：单元门控与文档级 verify 共用同一份判据）
# ===========================================================================
# 现象（Apostol《解析数论导引》ch2/ch4/ch9/ch11 实测 2026-09-29）：英文源顶层的复数集体
# 小标题 `**Examples.**` / `**Notes.**` 因 `_H_MISSING_BQ` 的 `Example(?![\w\-])` 负向前瞻
# **天然不命中**（复数尾 s），于是留在顶层并过源闸；中文没有复数形态，译者照结构写成顶层
# `**例。**` / `**注.**` 却命中必包表 → 同一结构「源过 / 译不过」。中文里 `例子` 是
# 2026-09-29 已裁的豁免词，但 `Notes` **没有任何豁免同位词**（注 / 注记 / 说明 全命中必包
# 表），于是闸门只剩两条坏出路：把印面结构改掉（塞进 `>`，与已过闸的源侧分叉）或自撰替代
# 词 = 「闸逼代理自撰」型判据缺口（与 2026-09-27/28 的 Note/Notes、Remark/评注 同族）。
# I 层同一族缺陷：英文「关键词不在首位」的证明头（`> **Alternate proof.**`）不被
# `G_ITEM_BQ_HEAD_RE` 认出 → 源侧不开块 → 不追分隔线，中文侧（`> **另一证明。**`）开块
# → 要求插入一条源里没有的 `---`，两版结构分叉。
# 根治口径 = **以源本为结构真值**（源先于译硬闸已保证源整体过闸）：
#   * 译文顶层粗体标签的**族多重集**与源本相等 ⇒ 译者逐位镜像了源侧「顶层 vs 包 `>`」的
#     选择 ⇒ 必包判据对译文放行；
#   * 「`>` 粗体标签块 → 顶层散文缺 `---`」的**处数**与源本相等 ⇒ 分隔线缺失是照抄源结构
#     ⇒ I 层该条对译文放行。
# 🔴 安全性关键：每条被报的必包违规行本身就是一个**已映射族**的顶层粗体标签（证明/例/注/
# 说明/解答/评注…），它必然进入译文多重集；源本若没有同族的顶层标签，两集必不相等 → 豁免
# 不成立。所以「译者凭空把附属块提到顶层」不可能被本豁免放过，盲区不扩大。
# 两条消费趟共用本节的谓词：单元级 = `flows/write-source/script/check_unit_quality`
# （按配对**源单元**逐单元比较，配对读 `paired_source_body`）；文档级 = 本文件 `FLayer.run`
# （按配对**源语言章 md** 整章比较，配对路径由 `verify_chapter.verify_all` 解析并经
# `ctx.src_pair_md` 带入；解析不出配对 = 不豁免，fail-closed）。

# 未映射词的族名桶（语言无关）。🔴 不能退回「用词本身作族名」：中英两侧的**主题式**顶层
# 粗体小标题（`**Goldbach's conjecture.**` ↔ `**哥德巴赫猜想。**`）必然用词不同，逐词作族名
# 会让任何译了主题头的章永远判「不等」→ 豁免对本章整体失效，复数 Examples 一类合法继承
# 又被逼改结构（Apostol ch8/ch14 实测）。主题头不属于必包表的附属块族，落进同一 'other'
# 桶后仍然要求**两侧处数相等**，保护力度不降。
_OTHER_FAMILY = 'other'

# `_H_MISSING_BQ` 实际会报出来的附属块族（证明/例/注/说明/注记/解答/评注 + 对应英文词）。
# 结构继承指纹只对**这些族**敏感，其余标签一律并入 'other' 桶，见 `_label_family`。
_REPORTABLE_FAMILIES = {'example', 'note', 'proof', 'solution', 'remark'}

_FAMILY_CN = {
    '例子': 'example', '例': 'example',
    '注记': 'note', '注': 'note', '说明': 'note',
    '证明思路': 'proof', '证明': 'proof', '证': 'proof',
    '解答': 'solution', '解': 'solution',
    '评注': 'remark',
    '练习': 'exercise', '习题': 'exercise',
    # 条目类标签（定义/定理/引理…）本身不会被 `_H_MISSING_BQ` 报，经 `_label_family`
    # 的「只保留可报族」过滤后与主题头同落 'other' 桶；此处仍登记，是因为中英**同一**
    # 标签必须映射到同一族（Apostol ch2/0077 实测：源 `**Definition.**`+`**Examples.**`
    # vs 译 `**定义.**`+`**例.**`），族名一致时桶位自然一致，处数比较才有意义。
    '定义': 'definition', '定理': 'theorem', '引理': 'lemma',
    '推论': 'corollary', '命题': 'proposition', '猜想': 'conjecture',
    '记号': 'notation', '问题': 'problem', '算法': 'algorithm',
    '答案': 'answer',
    # 🔴 后置中心词形（「导出模的定义」↔ `Definition of induced modulus`，Apostol ch8 实测；
    # 「定理 4.2 的证明」↔ `Proof of Theorem 4.2`）：中文习惯把限定语放前面、标签名词收尾，
    # 前缀查表必然落空 → 该族判定与英文分叉。中心词按**后缀**再查一次同一张表（值集合，
    # 非新表），中英同族。
}

_FAMILY_EN = {
    'example': 'example', 'examples': 'example',
    'note': 'note', 'notes': 'note', 'explanation': 'note',
    'proof': 'proof', 'proofs': 'proof',
    'solution': 'solution', 'solutions': 'solution',
    'remark': 'remark', 'remarks': 'remark',
    'exercise': 'exercise', 'exercises': 'exercise',
    'definition': 'definition', 'definitions': 'definition',
    'theorem': 'theorem', 'theorems': 'theorem',
    'lemma': 'lemma', 'lemmas': 'lemma',
    'corollary': 'corollary', 'corollaries': 'corollary',
    'proposition': 'proposition', 'propositions': 'proposition',
    'conjecture': 'conjecture', 'conjectures': 'conjecture',
    'notation': 'notation', 'notations': 'notation',
    'problem': 'problem', 'problems': 'problem',
    'algorithm': 'algorithm', 'algorithms': 'algorithm',
    'answer': 'answer', 'answers': 'answer',
}

_FAMILY_CN_HEAD_NOUNS = sorted({k for k, v in _FAMILY_CN.items() if len(k) >= 2},
                               key=len, reverse=True)

_INHERIT_TOKEN_RE = re.compile(r'^([一-鿿]+|[A-Za-z]+)')
_BQ_ANY_BOLD_HEAD_RE = re.compile(r'^\s*>\s*\*\*[^*]+\*\*')

MBQ_ERR_MARK = "should be inside `>`"
ISEP_ERR_MARK = "missing `---`"


def _label_family(token):
    """标签首词（或中文首/尾词）→ 语言无关族名；查不到 → `_OTHER_FAMILY` 桶。

    🔴 只有**必包表真会报的族**（`_REPORTABLE_FAMILIES`）才保留族名，其余一律落
    `_OTHER_FAMILY`。指纹的全部作用是「被报的违规行必然进指纹」，而 `**Definition.**` /
    `**定理 3.1**` 这类顶层标签永远不可能被 `_H_MISSING_BQ` 报出来——给它们单独族名
    只会引入中英不对称（`**Goldbach's conjecture.**` 首词是专名 → other，而中文
    `**哥德巴赫猜想。**` 走后缀支 → conjecture，Apostol ch14 实测），把该章整体豁免打掉。
    收进 other 桶后**处数依旧逐位相等**，保护力度不降。
    """
    fam = _label_family_raw(token)
    return fam if fam in _REPORTABLE_FAMILIES else _OTHER_FAMILY


def _label_family_raw(token):
    """标签首词（或中文首/尾词）→ 附属块族名；查不到 → `_OTHER_FAMILY`。"""
    if token.isascii():
        return _FAMILY_EN.get(token.lower(), _OTHER_FAMILY)
    for n in (3, 2, 1):
        if token[:n] in _FAMILY_CN:
            return _FAMILY_CN[token[:n]]
    for noun in _FAMILY_CN_HEAD_NOUNS:
        if token.endswith(noun):
            return _FAMILY_CN[noun]
    return _OTHER_FAMILY


def top_label_families(line_list):
    """顶层粗体标签行的**族多重集**（按标签首词映射，中英同族合并）。

    只数「顶层粗体标签行」：非 `>`、非标题、非显示式围栏内、以 `**…**` 粗体 run 起头。
    源/译两趟与检测/豁免两趟共用本函数，杜绝「三份分叉」。

    🔴 顶层 `{…}` 行单独计一族（`_H_MISSING_BQ_FOOTNOTE` 的必包形）：它不是粗体标签，
    若不进指纹，「豁免成立时凭空加一行顶层 `{`」就查不出来，安全论证（被报的违规行必然
    进入译文指纹）会留一个缺口。两侧都有 = 照抄源结构 = 该豁免；只有一侧有 = 不等 = 不豁免。
    """
    fams = []
    in_math = False
    for raw in line_list:
        s = raw.strip()
        if s in ('$$', '> $$'):
            in_math = not in_math
            continue
        if in_math or not s or s.startswith('>') or s.startswith('#'):
            continue
        if s.startswith('{'):
            fams.append('brace')
            continue
        if not s.startswith('**'):
            continue
        end = s.find('**', 2)
        if end < 2:
            continue
        m = _INHERIT_TOKEN_RE.match(s[2:end].lstrip())
        fams.append(_label_family(m.group(1)) if m else 'blank')
    return fams


def bq_label_block_then_prose(line_list):
    """数「`> **标签** …` 引用块结束后紧跟顶层散文（中间无 `---`）」的处数。

    与 `check_i_prose_separator` 同一份行走逻辑、同一份 `_NON_PROSE_START` 谓词，但块头
    按**任意粗体 run** 认（语言无关）：英文关键词后置的证明头在 I 层不开块，若指纹照抄
    I 层的开吻词表，源侧计数恒为 0，豁免就只剩「译文也必须不开块」一条坏出路。
    """
    n = len(line_list)
    cnt = 0
    i = 0
    while i < n:
        if not _BQ_ANY_BOLD_HEAD_RE.match(line_list[i]):
            i += 1
            continue
        j = i + 1
        body = False
        while j < n and line_list[j].startswith('>'):
            if line_list[j].strip() not in ('>', '> '):
                body = True
            j += 1
        if not body:
            i = j
            continue
        k = j
        while k < n and line_list[k].strip() == '':
            k += 1
        if k < n and not _NON_PROSE_START.match(line_list[k]):
            cnt += 1
        i = j
    return cnt


def inherited_structure_exemptions(md_lines, src_lines):
    """译文 md 相对**源语言 md** 的结构继承判据 → 可豁免的判据标记集合。

    `src_lines` 为 None（解析不出配对 / 本书无译本）→ 空集 = 一条都不豁免（fail-closed）。
    返回 {'h_mbq', 'i_prose_sep'} 的子集，由 `FLayer.run` 用来丢掉对应判据的报告。
    """
    out = set()
    if not src_lines:
        return out
    if sorted(top_label_families(src_lines)) == sorted(top_label_families(md_lines)):
        out.add('h_mbq')
    if bq_label_block_then_prose(src_lines) == bq_label_block_then_prose(md_lines):
        out.add('i_prose_sep')
    return out


def read_pair_lines(md_file):
    """配对源本 md 的行（读不到 = None，调用方据此不豁免）。"""
    if not md_file:
        return None
    try:
        with open(md_file, encoding='utf-8-sig') as f:
            return f.read().split('\n')
    except Exception:
        return None


def check_nested_blockquotes(md_file):
    """Detect nested blockquotes (> > **证明/例** or > > **例**) — the OLD format.
    Examples and their proofs must use the SAME single `>` level."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    for i, ln in enumerate(lines):
        if NESTED_BQ.match(ln):
            out.append(f"  x L{i+1}: nested blockquote `> > **` (use single `>` level): "
                       f"{ln.strip()[:60]}")
    return out

def check_example_proof_gap(md_file):
    """G-LAYER: detect gap between example (> **例**) and its proof (> **证明思路**).

    A bare empty line or non-blockquote content between them breaks
    the single blockquote — example and proof must be in the same
    contiguous `>` block. Also flags blank `>` lines (visual spacing
    within blockquote is allowed, but warnings are emitted).

    Also detects SAME-LINE example+proof: `> **例**：...**证明梗概**：...`
    which should be split onto two separate `>` lines.
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return [], []
    errors = []   # blocking — empty lines or non-bq content
    warns = []    # non-blocking — `>` gap lines
    # --- Same-line example+proof detection ---
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith('> **例') and '**证明' in s:
            # A `> **例` line containing `**证明` — they should be separate lines
            errors.append(f"  x L{i+1}: example and proof on same line — split into\n"
                          f"             `> **例…**` and `> **证明…**` on separate lines")
    # --- Gap detection (original logic) ---
    for i, ln in enumerate(lines):
        if not G_EX_RE.match(ln):
            continue
        for j in range(i + 1, min(i + 25, len(lines))):
            if not G_PF_RE.match(lines[j]):
                continue
            # Another example between → not the same pair
            if any(G_EX_RE.match(lines[k]) for k in range(i + 1, j)):
                break
            # Section header or structural interrupt → not the same pair
            if any(re.match(r'^#{1,6}\s', lines[k]) for k in range(i + 1, j)):
                break
            if any(re.match(r'^---\s*$', lines[k]) for k in range(i + 1, j)):
                break
            if any(G_TOPLEVEL_BREAK_RE.match(lines[k]) for k in range(i + 1, j)):
                break
            # Inspect gap lines
            for k in range(i + 1, j):
                t = lines[k].strip()
                if t == '':
                    errors.append(f"  x L{i+1}: empty line between example and proof (L{j+1})")
                    break
                elif not lines[k].startswith('>'):
                    errors.append(f"  x L{i+1}: non-blockquote content between example and proof "
                                  f"L{k+1}: {t[:60]}")
                    break
            break
    return errors, warns


# G-LAYER: example blockquote check (writing-rules V-F)
# Example blocks must be wrapped in `>` blockquotes.
_EX_NO_BQ_RE = re.compile(
    r'^\*\*(?:例\b(?:\d[\d.]*-[0-9]+|\d+)?\*\*'
    r'|Example\b(?:\s*\d+)?\*\*)'
)

def check_example_blockquote_lines(lines):
    """Check example blocks not wrapped in `>` blockquotes.

    Standalone function usable by both verify (file-level) and
    check_unit_quality (unit-level). Takes list of lines, returns
    list of error strings.
    """
    out = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith('>'):
            continue
        if _EX_NO_BQ_RE.match(s):
            out.append(f"  x L{i+1}: example block not wrapped in `>` blockquote "
                       f"(writing-rules V-F): {s[:60]}")
    return out

def check_example_blockquote(md_file):
    """G-LAYER: file-level wrapper for check_example_blockquote_lines."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    return check_example_blockquote_lines(lines)


# ===========================================================================
# H-LAYER: structural label / blockquote audit (4 sub-checks)
# ===========================================================================
# 🔴 开吻白名单新增 `答`（Arnold《经典力学的数学方法》ch7 实测 2026-09-29）：
#   该书题后**直接印 `答 …`**（PDF p.130「答 C；下面将给出一个基底.」、p.137
#   「答dx|(1,0)(ξ) = 0, dy|(1,0)(ξ) = 1.」），写手据印面写成 `> **答** …`。旧表只有
#   `解答?` → 整块判「unlabeled blockquote」，块内每一行 `> **答**` / `> $$` 连带重复
#   报错（ch7 四单元 12 处），逼出的两条坏出路都不可接受：把印面解答拆出 `>`（破坏
#   V-F 附属块规则），或删掉印面答案（= 制造缺失）。
#   本表**只放宽检测**（放行合法开吻），不进 `_H_MISSING_BQ`：印面顶层 `**答** …`
#   同样是本书合法形态（ch2 0034 的问题/答对），不得反过来逼作者包块。
#   修复趟 `fix_unlabeled_blockquotes` import 同一正则，检测/修复天然对称。
#   🔴 开吻白名单再补 `练习|习题`（Iwaniec–Kowalski《解析数论》ch18 0006 译单元实测
#   2026-09-29）：英文源印 `> **Exercise 1.** …` 且已过本闸（表内历来有 `Exercise`），
#   中文译版照印面写 `> **练习1。** …` 却被判「unlabeled blockquote」——同一结构
#   「源过 / 译不过」，译者只剩「把练习题头改成注/说明」或「拆出 `>`」两条自撰出路。
#   与 2026-09-27/28 的 Note/Notes、Remark/评注、Examples/例子 同族缺口。
#   **只**放宽本表：`_H_MISSING_BQ`（必包表）不含 Exercise，故也不含 练习/习题，
#   顶层 `**习题 3.**` 仍按印面留在顶层（不反向逼作者包块）。
_H_UL_OPENERS = re.compile(
    r'^\s*>\s*\*\*(?:'
    r'(?:\d{1,3}[.．]\s*)?(?:'
    r'(?:证明|证|解答?|答|例|评注|注|说明|算法|练习|习题'
    r'|Proof|Example|Solution|Note|Remark|Algorithm'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Exercise)'
    r')'
    # number-first form:  > **N.M-K 例  (some books print 编号在前, e.g. Kreyszig `8.1-6 例子`)
    r'|(?:\d{1,3}(?:[.．-]\d{1,3}){1,2})\s*'
    r'(?:例|Example|Solution|注|Note|Remark|证明|证|说明)'
    # bold-led catch-all: any `>**Label...**` is an intentional (English/number) label
    # block — e.g. Kreyszig `**Solution (core steps).**`, `**Crucial distinction.**`,
    # `**3.7-1 Legendre polynomials.**`. Avoids mis-flagging legit proof/example blocks.
    # 🔴 同分支补 CJK 首字（Apostol《解析数论导引》ch4/0010 + ch9/0038 译单元实测
    # 2026-09-29）：英文侧 `> **Alternate proof.**`、`> **Proof of the reciprocity
    # law.**` 这类「关键词不在首位」的证明头经本 catch-all 放行，而其中文同位写法
    # `> **另一证明。**`、`> **互反律的证明。**` 因首字是汉字既不入关键词表也不入
    # catch-all → 整块判「unlabeled blockquote」，块内每一行 `> $$` 连带重复报错
    # （ch4 一处标签引出 4 条 FAIL，ch9 同）。译者只剩「改词规避」或「拆掉 `>`」两条
    # 自撰出路，两版结构分叉——与 2026-09-29 的 答 / 练习|习题 / 评注 同族缺口。
    # **只放宽检测**：不进 `_H_MISSING_BQ`（必包表），故不会反过来逼作者包裹。
    # 散文续行从不以 `**` 粗体 run 起头（`_h_ext_is_legit_bq` 同款论证，跨 corpus
    # 标定 0 新增报告）。
    r'|[A-Z0-9一-鿿].*?\*\*'
    r')'
)

_H_UL_FOOTNOTE = re.compile(r'^\s*>\s*\^\{')

_H_MISSING_BQ = re.compile(
    r'^\s*\*\*(?:'
    # keyword-first label word, then content / punctuation / end-of-bold
    # (the OLD pattern required the keyword to be immediately followed by `**`,
    #  so it only matched a bare `**Example**` and never fired on real
    #  examples like `**Example 1.1-2**:` or `**证明：...` — fixed here).
    r'(?:证明|证|证明思路|证明概要|解答?|注记|说明'
    # `Remark` was long missing from this table while its CN counterpart `注`
    # (below) was present → same structure passed in the EN unit and FAILED in
    # the CN translation (Robinson ch2/ch7 实测 2026-09-27, 根治 2026-09-27).
    # SSOT = format_verify.md 第29/230 条「证明、例、注、说明等附属块一律 `>` 包裹」。
    r'|Proof|Example|Solution|Note|Remarks?)(?![\w\-])'
    # 🔴 `例` 后必须排除复数尾 `子`（Iwaniec–Kowalski 解析数论 ch4 0012 实测 2026-09-29）：
    # 英文侧 `Example(?![\w\-])` 使 `**Examples.**` **天然不命中**（跨书普查 69,403 个源单元
    # 里 22 处顶级粗体 Examples，分布于 8 本已收官书，全部按印面留在顶层并过闸），
    # 而中文同位写法 `**例子。**` 却命中 → 同一结构「源过 / 译不过」，译者只能把合法
    # 顶层标签塞进 `>` 或改词规避，两版结构分叉（与 2026-09-27/28 的 Note/Notes、
    # Remark/评注 同族）。带编号或单数的例子块照旧必包：`**例。**`/`**例 3.**`。
    r'|例(?!子)(?:\s*\d[\d.]*)?'      # 例 / 例1 / 例 1  (then content)
    r'|注(?:\s*\d[\d.]*)?'           # 注 / 注1
    # 评注 = `Remark` 的标准译名（Weibel / do Carmo 黎曼几何 全书用此形）。
    # 补 `Remarks?` 时必须同步补它，否则不对称只是换了个方向。
    r'|评注(?:\s*\d[\d.]*)?'
    # number-first form: N.S-N + label word
    # (e.g. Kreyszig `3.1-3 Example (...)`, `3.1-3 例子（...）`)
    r'|\d{1,3}(?:[.．\-－]\d{1,3}){1,2}\s*'
    r'(?:例|例子|Example|Solution|Proof|Note|Remarks?|证明|证|说明|注|评注)'
    r')'
)

_H_MISSING_BQ_FOOTNOTE = re.compile(r'^\s*\{')

# 🔴 「章末注记题头」豁免（Robinson 李代数书 ch3/ch6 译单元实测 2026-09-28）。
#   章末 `**Notes**` / `**注记 (Notes)**`（含 run-in 正文，如 `**Notes** On weight
#   spaces … see Lemire [1]`）是**节级**标题，不属 V-F 第 29 条所指的 item 附属块。
#   旧判据下英文 `**Notes**` 因 `Note(?![\w\-])` 的复数尾巴**天然不命中**，中文同位
#   写法 `**注记 …**` 却命中 → 同一结构「源过 / 译不过」，译者只能把标题塞进 `>` 或
#   改词规避，两版结构随之分叉（本书 ch3 0009/0034/0050、ch6 0008/0018 实测）。
#   豁免形态收得很窄，以免冲掉 2026-09-27/28「`评注`/`注记` 补入必包表」的决定
#   （见 `tests/test_h_mbq_bilingual_remark.py`）：**只**认「关键词 + 英文括注 +
#   粗体 run 即止」——括注正是「印面标题词被翻译」的机械信号（`**注记 (Notes)**`）。
#   仍必包：`**注记 3.1**：…`（带编号）、`**评注** 单独一个词。`（无括注）、
#   `**Note**: …` / `**Remarks 3.4.1** …`（英文侧同判）。
_H_NOTE_HEADING_RE = re.compile(
    r'^\s*\*\*\s*(?:注记|评注|说明)\s*[（(]\s*(?:Notes?|Remarks?|Comments?)\s*[)）]\s*\*\*')


def _h_ext_is_legit_bq(s):
    """A blockquote line that is LEGIT (proof/example/note/footnote) -> stop.

    Bilingual: recognizes both Chinese (证明/例/注) and English
    (Proof/Example/Note/Remark) openers so English summaries are not
    mis-scanned as a statement region (which would flag `> $$` as h_stmt_bq).
    """
    t = s.lstrip()
    if not t.startswith('>'):
        return False
    inner = t[1:].lstrip()
    if inner.startswith('^{'):
        return True
    # Chinese openers（解 = EN Solution 的对应标签，Rosen 8e 译单元实测 2026-09-26）
    # 🔴 评注 / 说明 必须与必包表 `_H_MISSING_BQ` 同步（Etingof 表示论 2026-09-28 实测）：
    # 必包表要求 `**评注 N.M**` 包进 `>`，但本判定只认 `**注`，`**评注` 开头认不出来，
    # 于是**已经正确包裹**的中文评注块被当作「陈述区」，其块内 `> $$` 误报 h_stmt_bq，
    # 而同结构的英文 `> **Remark 6.12**`（EN 分支在下方）却放行 → 「源过 / 译不过」。
    if (inner.startswith('**证明') or inner.startswith('**例')
            or inner.startswith('**注') or inner.startswith('**解')
            or inner.startswith('**评注') or inner.startswith('**说明')):
        return True
    # number-first form:  > **N.M-K 例  (book prints 编号在前)
    if re.match(r'^\*\*\d{1,3}(?:[.．-]\d{1,3}){1,2}\s*(?:例|Example|注|Note|Remark|证明|证|说明)', inner):
        return True
    # CN 「X的证明(思路)」 proof header (Leinster 实测：> **引理2.2.2的证明思路**：
    # 旧判定只认 `**证明` 开头 / EN `**Proof`，CN 标签前置的证明头不被承认，
    # 其块内 `> $$` 落入 statement 区被 h_stmt_bq 误报）。
    if re.match(r'^\*\*[^*\n]{0,15}?(的证明|证明思路|证毕)', inner):
        return True
    # English openers (bilingual support)
    if re.match(r'^\*\*(?:Proof|Example|Solution|Note|Remark|Exercise)\b', inner):
        return True
    # bold-led catch-all (English/number labels like `**Crucial distinction.**`,
    # `**3.7-1 Legendre polynomials.**`, `**Solution (core steps).**`)
    if re.match(r'^\*\*[A-Z0-9]', inner):
        return True
    return False

def _h_ext_is_structural_bq(s):
    """A blockquote line that is WRAPPED STATEMENT content (sub-point/formula)."""
    t = s.lstrip()
    if not t.startswith('>'):
        return False
    inner = t[1:].lstrip()
    if inner.startswith('$$'):
        return True
    if re.match(r'^（([0-9a-zA-Z]+)）', inner):
        return True
    if re.match(r'^\*\*\(([0-9a-zA-Z]+)\)\*\*', inner):
        return True
    if re.match(r'^- （([0-9a-zA-Z]+)）', inner):
        return True
    if re.match(r'^- \(([0-9a-zA-Z]+)\)', inner):
        return True
    return False

def _h_ext_items(md_file):
    """Yield (lines, h_idx, pen_idx) for each structural item in the file."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return
    n = len(lines)
    heads = [i for i in range(n) if TOP_LEVEL_HEADER_RE.match(lines[i])]
    for idx, h in enumerate(heads):
        nxt = heads[idx + 1] if idx + 1 < len(heads) else n
        pen_idx = nxt
        for k in range(h + 1, nxt):
            if _h_ext_is_legit_bq(lines[k]):
                pen_idx = k
                break
        yield lines, h, pen_idx

def check_h_structural_blockquote(md_file):
    """H-LAYER: scan the file for structural labels inside blockquotes.

    Returns a list of violation strings (with line numbers). Empty = pass.
    Each violation is a line matching `> **LABEL...` where LABEL is a
    structural label (definition/theorem/lemma/etc.)."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    for i, ln in enumerate(lines):
        if H_STRUCT_BQ_RE.match(ln):
            rest = ln.lstrip()
            label_end = rest.find('**', 2)
            label = rest[4:label_end] if label_end > 4 else rest[4:].split()[0]
            out.append(f"  x L{i+1}: structural label `{label.strip()}` inside blockquote "
                       f"(must be top-level): {ln.strip()[:70]}")
    # Sub-check: orphan bare `>` lines (empty blockquote not attached to content).
    # A bare `>` line is orphan only if it has no blockquote content either before or after.
    n = len(lines)
    for i, ln in enumerate(lines):
        if re.match(r'^\s*>\s*$', ln):
            # Check if preceded by blockquote content
            prev_bq = False
            for k in range(i - 1, -1, -1):
                s = lines[k].strip()
                if s:
                    prev_bq = lines[k].lstrip().startswith('>')
                    break
            # Check if followed by blockquote content
            next_bq = False
            for k in range(i + 1, n):
                s = lines[k].strip()
                if s:
                    next_bq = lines[k].lstrip().startswith('>')
                    break
            if not (prev_bq or next_bq):
                out.append(f"  x L{i+1}: bare `>` line not attached to any blockquote content "
                           f"(orphan empty blockquote — remove or merge)")
    return out

def check_h_statement_in_blockquote(md_file):
    """H-LAYER ext (BQ): flag statement content wrongly wrapped in `>`.
    Returns a list of violation strings (with line numbers). Empty = pass."""
    out = []
    for lines, h, pen_idx in _h_ext_items(md_file):
        for k in range(h + 1, pen_idx):
            if _h_ext_is_structural_bq(lines[k]):
                out.append(f"  x L{k+1}: statement content wrapped in `>` "
                           f"(unexpected blockquote): {lines[k].strip()[:70]}")
    return out


def check_unlabeled_blockquotes(md_file):
    """H-LAYER ext (unlabeled BQ): flag free-standing `>` blocks without a
    recognized label (证明/证/例/注/说明/脚注).

    Grouping: consecutive `>` lines form one "block".  A new legit opener
    (`> **证明**` / `> **例**` etc.) encountered mid-stream SPLITS the block,
    so that:

        > (unlabeled text)
        > **证明**：...   ← splits here, this line starts a fresh block

    Reports each content line within an unlabeled block individually.

    Returns a list of violation strings. Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    n = len(lines)
    out = []
    i = 0
    while i < n:
        if not lines[i].lstrip().startswith('>'):
            i += 1
            continue
        # Collect a blockquote block, splitting at new legit openers
        start = i
        i += 1
        while i < n and lines[i].lstrip().startswith('>'):
            # A legit opener mid-stream breaks the block so it starts fresh
            if _H_UL_OPENERS.match(lines[i]) or _H_UL_FOOTNOTE.match(lines[i]):
                break
            i += 1
        end = i
        # Find first content-bearing line in the block
        first = None
        for k in range(start, end):
            inner = lines[k].lstrip()
            if inner == '>' or inner == '':
                continue
            first = k
            break
        if first is None:
            continue  # block is all empty `>` lines
        ln = lines[first]
        if _H_UL_OPENERS.match(ln) or _H_UL_FOOTNOTE.match(ln):
            continue  # legit blockquote
        # Let H-layer handle structural labels inside blockquotes (double-flag avoidance)
        if H_INLINE_STRUCT_BQ_RE.match(ln):
            continue
        # Unlabeled blockquote — flag each content line
        for k in range(start, end):
            t = lines[k].strip()
            if t.startswith('>') and t != '>':
                inner2 = t[1:].lstrip()
                if inner2:
                    out.append(f"  x L{k+1}: unlabeled blockquote (only 证明/证/例/注/说明/脚注 "
                               f"allowed in `>`): {lines[k].strip()[:70]}")
    return out


def check_labels_missing_blockquote(md_file):
    """H-LAYER ext (missing BQ): flag labels (证明/证/例/注/说明/注记/脚注)
    found at TOP LEVEL — they MUST be inside `>`. Returns list of violation
    strings. Empty = pass.

    Display math ($$...$$ fences) is skipped: CD commutative-diagram rows
    like `{...} @>>> ...` legitimately start a line with `{` and are NOT
    blockquote labels, so scanning them here causes false positives."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    in_math = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        # Toggle display-math state on fences. A single-line `$$ ... $$`
        # block does not persist in_math across lines.
        if s == '$$':
            in_math = not in_math
            continue
        if s.startswith('$$') and s.endswith('$$'):
            continue
        if in_math:
            continue
        st = ln.strip()
        if st.startswith('>'):
            continue
        if re.match(r'^#{1,6}\s', ln):
            continue
        if _H_NOTE_HEADING_RE.match(st):
            continue    # 题式注记标签（两侧同口径豁免，见上方注释）
        if _H_MISSING_BQ.match(st) or _H_MISSING_BQ_FOOTNOTE.match(st):
            out.append(f"  x L{i+1}: label `{st[:40]}` should be inside `>` "
                       f"(add `> ` prefix)")
    return out


# ===========================================================================
# I-LAYER: item separator completeness
# ===========================================================================
def check_i_separators(md_file):
    """I-LAYER: check that consecutive items are separated by `---`.

    Items checked: definition, theorem, lemma, corollary, proposition,
    axiom, example. Internal blocks (proof, note) are NOT items and
    don't need separators. Section boundaries (##) reset the requirement.
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    # Collect all item-starting line numbers
    item_lines = []
    for i, ln in enumerate(lines):
        if (I_ITEM_RE.match(ln) or I_ITEM_EXAMPLE_RE.match(ln)):
            item_lines.append(i)
    item_lines = sorted(set(item_lines))
    # Check consecutive pairs
    for idx in range(len(item_lines) - 1):
        i = item_lines[idx]
        j = item_lines[idx + 1]
        # Skip if too far apart (likely across a section boundary with no ## mark)
        if j - i > 100:
            continue
        # Look for --- or section heading between i and j
        has_sep = False
        section_between = False
        for k in range(i + 1, j):
            t = lines[k].strip()
            if t == '---':
                has_sep = True
                break
            if re.match(r'^#{1,6}\s', lines[k]):
                section_between = True
                break
        if not has_sep and not section_between:
            si = lines[i].strip()[:70]
            sj = lines[j].strip()[:70]
            out.append(f"  x L{i+1}→L{j+1}: missing `---` between items: [{si}]...[{sj}]")
    return out


# ===========================================================================
# J-LAYER: no `---` inside an item block
# ===========================================================================
_J_SUBPOINT_RE = re.compile(r'^\*\*\(\d+\)\*\*')

_J_DASH_RE = re.compile(r'^---\s*$')

def check_item_header_dash(md_file):
    """J-LAYER: detect any `---` that sits INSIDE an item block.

    Returns a list of violation strings (with line numbers). Empty = pass.
    A top-level item (`**引理3.1**` ...) may have `**(N)**` numbered sub-points,
    but the block (header line through its last sub-point) must NOT contain any
    `---`. This includes BOTH:
      * header → `---` → `**(1)**`  (between header and first sub-point), and
      * `**(i)**` → `---` → `**(i+1)**`  (between two sub-points),
    even when a sub-point spans multiple lines (its continuation text / a `$$`
    formula sits directly above the `---` rather than the `**(i)**` label).

    Implementation: walk the file keeping an `in_item` flag.
      - Set in_item=ON when we see a `**LABEL**` header or a `**(N)**` sub-point.
      - Set in_item=OFF when we see a `## ` heading or a `>` blockquote line
        (these close the item block).
      - A top-level `---` is a violation when in_item is True AND its next
        non-blank, non-blockquote line is a `**(N)**` sub-point (so we never
        flag a legitimate `---` that separates two different top-level items).
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    n = len(lines)
    out = []
    in_item = False
    for i in range(n):
        s = lines[i]
        st = s.strip()
        if st == '':
            continue
        # blockquote line closes any open item block
        if st.startswith('>'):
            in_item = False
            continue
        # heading closes any open item block
        if re.match(r'^#{1,6}\s', s):
            in_item = False
            continue
        # item header or numbered sub-point opens the block
        if TOP_LEVEL_HEADER_RE.match(s) or _J_SUBPOINT_RE.match(s):
            in_item = True
            continue
        # a top-level `---`
        if _J_DASH_RE.match(s):
            ni = i + 1
            while ni < n and lines[ni].strip() == '':
                ni += 1
            if ni < n and not lines[ni].lstrip().startswith('>'):
                nxt = lines[ni]
                if in_item and _J_SUBPOINT_RE.match(nxt):
                    out.append(f"  x L{i+1}: `---` inside an item block "
                               f"(next: {nxt.strip()[:40]}) — remove it")
            continue
    return out


# ===========================================================================
# K-LAYER: blank line between a list's last item and a following new block
# ===========================================================================
# List item markers at ANY indentation: `1.` / `1)`, `(1)`, bullets `- + *`
# (a bullet-looking `*bold*:` emphasis has no whitespace after `*`, so it is
# never matched).
_K_LIST_RE = re.compile(r'^\s*(?:\d+[.)]|\(\d+\)|[-+*])\s')

_K_LABEL_RE = re.compile(r'^\*\*[^*]+\*\*')

def _k_next_is_new_block(item_line, nx):
    """True when `nx` (the line directly after a list item) is a NEW BLOCK
    that must be separated by a blank line.

    Not flagged (no blank needed):
      * blank line already present,
      * another list item (continuation of the same list),
      * deeper-indented (subordinate) content belonging to the item,
      * headings (owned by heading_blank_above),
      * plain wrapped prose (legal lazy continuation).
    Flagged (renderer absorbs them into the list item — right-shifted boxes):
      * `>` blockquote (proof/example/note),
      * `$$` display math,
      * top-level `**label**` statement,
      * `<div` figure container."""
    if nx.strip() == '':
        return False
    if len(nx) - len(nx.lstrip()) > len(item_line) - len(item_line.lstrip()):
        return False  # subordinate content of the item
    if _K_LIST_RE.match(nx):
        return False  # next item of the same list
    t = nx.strip()
    if re.match(r'^#{1,6}\s', t):
        return False  # heading_blank_above owns heading separation
    if t.startswith('>') or t.startswith('$$') or t.startswith('<div'):
        return True
    if _K_LABEL_RE.match(t):
        return True
    return False

def _k_display_mask(lines):
    """True at index i when lines[i] IS a `$$` fence or sits inside a display
    block (also for `> $$` in-block fences).

    Why: a display body may legitimately begin with a bullet-looking line
    (`$$` / `- n ( h ( T , \\zeta ) ) < ...` / `$$` — Robinson ch9 Cor 9.3.8).
    That is math content, not a list item, and inserting a blank line inside a
    `$$` block is itself a violation, so the K pair check must skip it."""
    mask = [False] * len(lines)
    in_disp = False
    for i, ln in enumerate(lines):
        t = ln.strip()
        if t.startswith('$$') or t.startswith('> $$'):
            mask[i] = True
            if t.count('$$') >= 2:      # single-line block: opens and closes
                continue
            in_disp = not in_disp
            continue
        mask[i] = in_disp
    return mask


def check_proof_after_list(md_file):
    """K-LAYER: ensure a blank line separates a list's last item from a
    following new block (proof blockquote, display math, structural label,
    figure container).

    Without the blank line the renderer lazy-continues the block INTO the
    last list item — the proof/math renders at the list's indentation
    instead of the outer level (real incident: Koopman ch12 Theorem 12.2,
    list item 2 directly followed by `> **Proof sketch**`).  Returns a list
    of violation strings (with line numbers). Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    n = len(lines)
    disp = _k_display_mask(lines)
    for i in range(n - 1):
        if disp[i]:
            continue  # the item-looking line is display-math content
        if _K_LIST_RE.match(lines[i]) and _k_next_is_new_block(lines[i], lines[i + 1]):
            out.append(f"  x L{i+2}: new block `{lines[i + 1].strip()[:50]}` directly follows "
                       f"list item L{i+1} without blank line — add one")
    return out


# ===========================================================================
# L-LAYER: blank lines around `---` separators
# ===========================================================================
def check_separator_blank_lines(md_file):
    """L-LAYER: every `---` separator line must have a blank line immediately
    above AND below it. Returns list of violation strings (with line numbers).
    Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    n = len(lines)
    for i, ln in enumerate(lines):
        if ln.strip() == '---':
            if i > 0 and lines[i - 1].strip() != '':
                out.append(f"  x L{i+1}: `---` missing blank line BEFORE "
                           f"(prev L{i}: {lines[i-1].strip()[:40]})")
            if i < n - 1 and lines[i + 1].strip() != '':
                out.append(f"  x L{i+1}: `---` missing blank line AFTER "
                           f"(next L{i+2}: {lines[i+1].strip()[:40]})")
    return out


# ===========================================================================
# L-EXT: `---` directly under a section heading
# ===========================================================================
def check_heading_separators(md_file):
    """Detect a `---` whose nearest preceding non-blank line is a section
    heading (## / ### / …).  Such a separator is NEVER legitimate per the
    format convention (legitimate separators live only below a lead-in
    paragraph or between adjacent items).  Returns a list of violation
    strings.  Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    for i, ln in enumerate(lines):
        if FMT_HR_RE.match(ln):
            j = i - 1
            while j >= 0 and lines[j].strip() == '':
                j -= 1
            if j >= 0 and FMT_SEC_RE.match(lines[j]):
                out.append(f"  x L{i+1}: `---` directly under a heading "
                           f"(remove it): {ln.strip()[:40]}")
    return out


# ===========================================================================
# L-EXT2: blank line above every section heading
# ===========================================================================
_FENCE_RE = re.compile(r'^\s*(?:```|~~~)')

_HEADING_ABOVE_RE = re.compile(r'^#{1,6}\s')

def check_heading_blank_above(md_file):
    """L-EXT2: every ATX heading (`#`…`######`) must be separated from the
    content above it by a blank line.

    A heading that directly follows an ordered-list item (e.g. `10. …`) or any
    paragraph line gets ABSORBED into that block by the renderer — the whole
    section below then renders indented instead of flush-left (real incident:
    Koopman ch12, list item 10 directly followed by `## §12.5`).  Returns a
    list of violation strings (with line numbers). Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    in_fence = False
    in_math = False
    for i, ln in enumerate(lines):
        if _FENCE_RE.match(ln):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        s = ln.strip()
        if s == '$$':
            in_math = not in_math
            continue
        if in_math:
            continue
        if _HEADING_ABOVE_RE.match(ln):
            if i > 0 and lines[i - 1].strip() != '':
                out.append(f"  x L{i+1}: heading has no blank line above "
                           f"(prev L{i}: {lines[i - 1].strip()[:40]}) — add one")
    return out


# ===========================================================================
# M-LAYER: `>` lines inside display math blocks
# ===========================================================================
def check_displaymath_gt(md_file):
    """M-LAYER: detect `>` lines inside `$$...$$` display math blocks.

    When a display math block is wrapped in a blockquote context, empty `>`
    lines can leak inside the `$$` fences. KaTeX rejects bare `>` inside math
    mode. Returns list of violation strings (with line numbers). Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    n = len(lines)
    i = 0
    while i < n:
        s = lines[i].strip()
        if s == '$$':
            j = i + 1
            while j < n and lines[j].strip() != '$$':
                j += 1
            if j < n:
                for k in range(i + 1, j):
                    ln = lines[k]
                    if ln.lstrip().startswith('>'):
                        out.append(f"  x L{k+1}: `>` inside display math ($$...$$) — "
                                   f"remove blockquote prefix: {ln.strip()[:60]}")
                i = j
        i += 1
    return out


# ===========================================================================
# N-LAYER: excessive empty `>` lines inside blockquotes
# ===========================================================================
def check_excessive_bq_empty_lines(md_file):
    """N-LAYER: detect excessive consecutive empty `>` lines inside blockquotes.

    Within a blockquote (> **证明** / > **例** ...), consecutive empty `>` lines
    should be limited to at most 1 between content-bearing lines."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    n = len(lines)
    in_bq = False
    i = 0
    while i < n:
        s = lines[i].strip()
        if s.startswith('> **') and ('证明' in s or '例' in s or '注' in s
                or re.search(r'\*\*(?:Proof|Example|Note|Remark)\b', s)):
            in_bq = True
            i += 1
            continue
        if in_bq:
            if (re.match(r'^---\s*$', s) or re.match(r'^#{1,6}\s', s) or
                N_ITEM_RE.match(s)):
                in_bq = False
                i += 1
                continue
            if s in ('>', '> '):
                j = i
                while j < n and lines[j].strip() in ('>', '> '):
                    j += 1
                count = j - i
                if count > 1:
                    out.append(f"  x L{i+1}–L{j}: {count} consecutive empty `>` lines "
                               f"in blockquote (max 1 allowed)")
                i = j
                continue
            # Skip regular blank lines (not >)
            if s == '':
                i += 1
                continue
        i += 1
    return out


class FLayer(VerifyLayer):
    code = 'F'
    name = 'format-verify'
    order = 6
    auto_fixable = False

    def run(self, ctx):
        katex_errors, katex_lines = check_katex(ctx.md_file)
        with open(ctx.md_file, encoding='utf-8-sig') as _f:
            _md_lines = _f.read().split('\n')
        h_mbq = check_labels_missing_blockquote(ctx.md_file)
        i_prose = check_i_prose_separator(ctx.md_file)
        # 🔴 译本结构继承豁免（只在调用方解析出**源语言配对 md** 时生效，见本节上方注释）：
        # 译文照抄源侧的「顶层 vs 包 `>`」与分隔线选择时，这两条对译文放行；解析不出配对
        # （中文原书 / 三语书歧义 / 文件缺失）→ 一条不豁免。
        if h_mbq or i_prose:
            _ex = inherited_structure_exemptions(
                _md_lines, read_pair_lines(getattr(ctx, 'src_pair_md', None)))
            if 'h_mbq' in _ex:
                h_mbq = []
            if 'i_prose_sep' in _ex:
                i_prose = []
        return LayerResult(code=self.code, metadata={
            'katex_errors': katex_errors,
            'katex_lines': katex_lines,
            'long_formula_rows': (check_long_formula_rows(_md_lines)
                                  if LONG_FORMULA_CHECK_ENABLED else []),  # 开关关闭时恒空（键仍在，WARN 非阻断）
            'quote_gaps': check_g_quote_continuity(ctx.md_file),
            'nested_bq': check_nested_blockquotes(ctx.md_file),
            'ex_proof_gaps': check_example_proof_gap(ctx.md_file),
            'ex_no_bq': check_example_blockquote(ctx.md_file),
            'h_structural_bq': check_h_structural_blockquote(ctx.md_file),
            'h_stmt_bq': check_h_statement_in_blockquote(ctx.md_file),
            'h_ul_bq': check_unlabeled_blockquotes(ctx.md_file),
            'h_mbq': h_mbq,
            'i_sep_gaps': check_i_separators(ctx.md_file),
            'i_prose_sep': i_prose,
            'j_header_dash': check_item_header_dash(ctx.md_file),
            'k_proof_list': check_proof_after_list(ctx.md_file),
            'l_sep_blanks': check_separator_blank_lines(ctx.md_file),
            'heading_sep': check_heading_separators(ctx.md_file),
            'heading_blank_above': check_heading_blank_above(ctx.md_file),
            'm_dm_gt': check_displaymath_gt(ctx.md_file),
            'n_bq_empty': check_excessive_bq_empty_lines(ctx.md_file),
        })
