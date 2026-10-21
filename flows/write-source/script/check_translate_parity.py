"""check_translate_parity.py — 翻译单元「1:1 同构」闸门（write-source 步骤 7 门控之一）

背景（2026-09-03 翻译单元化：翻译并入 write-source，单元粒度 1:1）
------------------------------------------------------------------
翻译下沉到单元粒度后，需要一道**机械的同构闸门**来保证「翻译版没漏东西」——
单元级质量校验（``gate_units`` / ``check_unit_quality``）只管「写得对不对」，
管不了「翻得全不全」。本脚本补上后者：逐项比对源单元目录与翻译单元目录。

检查项（任一为 FAIL 即 exit 1）
----------------------------
1. **单元按 `file` 配对**：以 `file` 为键把源/译两侧的 manifest 记录配上（缺 / 多 = FAIL，
   两侧同名重复 = FAIL），再比对每对的 `id` / `type` / `key` / `name`。🔴 **不按 manifest
   下标 zip**：Kreyszig 泛函分析 ch4 实测两侧文件集合相同、仅 D-注与节标题先后差 26 位，
   zip 会把 26 对无关单元配成「字段不一致」假阳并跳过真正该比的一对。两侧顺序不同本身
   单列一条 FAIL（`merge_units` 按各自 manifest 顺序拼接 → 源/译阅读顺序分叉）。
2. **公式序标一致**：`\\tag{...}` 编号集合逐单元相同（漏公式 / 擅自改号 → FAIL）。
3. **图片一致**：`<img src="...">` 集合逐单元相同（漏图 → FAIL）。
4. **节号一致**：`section` 单元的 `§N.M` 编号集合相同（D 层靠 `§` 认节，错位即 FAIL）。
5. **编号项标签一致**：item 单元的条目编号（`**定理9.2**` / `**Theorem 9.2**` 中的 `9.2`）
   集合相同（漏条目 / 改号 → FAIL）。
6. **源单元漂移**：`manifest.units[].src_hash` ≠ 源单元当前哈希 → 源在派生后被改，
   须先同步翻译单元（单向修复：先修源 → 再同步译），FAIL。🔴 **快照缺失同样
   FAIL**（fail-closed）——manifest 缺 `src_hash` 时漂移检测即失效，等于给
   「源未定稿就翻译」留旁路；补齐须重跑 `init_translate_units`。
7. **未翻译残留（WARN 升 FAIL）**：item / desc 单元译文哈希 == 源文哈希，即整单元未翻译。
   仅对**含散文**的单元判定（`_has_prose` 先剥掉 `$$...$$` 与 `$...$`）——纯公式单元
   （如 `$y \\in \\Re$`）与纯图单元两侧本就应逐字一致，不算漏译。
8. **英文残留（半截翻译，2026-09-24 real-analysis ch21/22 教训）**：第 7 项只抓
   逐字全等——把 `> **证明**：` 译掉、条目标签与证明散文仍整段英文的单元因哈希
   一变即逃逸。本项不看哈希只看语言（复用 `check_unit_quality.english_residues`）：
   译文单元含英文条目/证明粗体标签（`**Theorem 21.10**` / `**Proof**`）或
   无 CJK 且 ≥8 连续英文词的散文行 → FAIL。
9. **显示公式内容丢失（2026-09-28 Etingof rep-theory ch1/0014 教训）**：翻译代理会
   「凭记忆」改写公式——第 2/3/5 项都是**集合**对账（tag / 图 / 条目编号），公式**内容**
   根本不在账上，于是把 `$f(xy) = f(x)f(y)$，并且 $f(1) = 1$` 整条截成 `$f(xy) = $`
   也能全绿通过。本项把两侧 `$$...$$` 块逐条归一（剥行首 `>` 包裹 + 去全部空白 +
   删 `\\text{}` 体 + 剥尾部标点：版式与**公式内散文**差异豁免、token 内容差异不豁免）
   后做**多重集**比对；精确配不上的再允许「整块搬进行内」兜底（源式完整内核作为子串
   出现在摊平译文里）。两者都失败 = 漏写/被改写 → FAIL。
   （逐字严格版在已收官的 real-analysis 假报 19 单元、Robinson 1、do Carmo 曲线曲面 2，
   全属上述豁免类；豁免后四书 2582 单元 0 假报，而截断样本仍被抓。）
10. **行内公式被截断**：译文行内式以**悬空关系/二元运算符**收尾（如
    `$f(xy) = $`、`$\\phi \\to$`）即数学内容被砍在半截 → FAIL。两处豁免（本书实测的假报源）：
    `\\cdots` / `\\ldots` 等省略号收尾是**完整**式，不列进悬空表；**源文自己就这么写**的
    悬空式（函子 `$V \\otimes$`、「包含关系 `$\\subseteq$`」）属照抄，按源行内式集合配对豁免。
11. **首行标记 ↔ 本侧 manifest 脱账**（2026-09-28 Etingof 步骤6 教训）：单元首行
    `<!-- book-summarizer DONE unit: id=… type=… key=… name=… -->` 四个字段必须与**该单元在
    自己那侧 `manifest.json` 里的记录**逐字相同。第 1 项只比两侧 manifest 的字段，代理改
    `.md` 首行的 `name=`（补全被拆分截断的标题、顺手多敲字符）两道闸都看不见，而首行正是
    「代理动没动这一行」的唯一证据（Etingof ch1/0063·0064、ch6/0021 实测被改）。跨书探针另在
    real-analysis 查出 2 文件（manifest `type=description` vs 全书 285 处 `desc`）、
    Robinson 动力学 18 文件（含**源侧**首行把 UTF-8 箭头存成 `cat -v` 字面文本、manifest 才是
    正确箭头）。复位工具 `tools/sync_translate_markers.py`——它按**契约**裁决该修哪一侧
    （Robinson `ch3/0051` 的 manifest name 是 `3.6 Substitutions2`，契约与首行都对，
    无脑照 manifest 复位会把对的改成错的）。

用法
----
    python flows/write-source/script/check_translate_parity.py <extract_dir> [ch ...]
    # 不传 <ch> 即全部章（中文书源整体跳过，无翻译目录）
输出
----
    通过 exit 0；不通过 exit 1 并打印逐章问题清单。
"""
import difflib
import hashlib
import json
import os
import re
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

sys.stdout.reconfigure(encoding="utf-8")

import attach_content as _ac
from data.book_structure.book_structure import (chapter_label, list_chapter_keys,
                                                prime_chapter_kinds, unit_dir_name)
import split_draft_units as _split
import gate_units as _gate
import check_unit_quality as _quality
from lib.unit_markers import marker_manifest_mismatch

SRC_SUB = "units"
TGT_SUB = "units-translate"

_TAG_RE = re.compile(r"\\tag\{([^}]*)\}")
_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"')
_SEC_RE = re.compile(r"§\s*([0-9]+(?:\.[0-9]+)*)")
# 条目编号：**定理9.2** / **Theorem 9.2** / **定义 9.2（名称）**
# 🔴 必须「先取粗体标签内部、再在内部找编号」——早期写法直接从 `**` 起惰性扫 40 字符，
# 会从闭合粗体的后半段一路扫到正文里的参考文献编号（源文 `**Remark 9.3**: … Sect.
# 9.4.1.1` 因英文冗长侥幸躲过，中文译文变短即命中）→ 假 FAIL。
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_NUM_IN_LABEL_RE = re.compile(r"([0-9]+(?:\.[0-9]+)+)")

# ── 公式内容对账（判据 9/10）────────────────────────────────────────────
_INLINE_RE = re.compile(r"\$[^$\n]*\$")
_DISPLAY_RE = re.compile(r"\$\$[\s\S]*?\$\$")
# 悬空收尾 = 公式被截断（`$f(xy) = $`）。只列**关系/二元运算符**，不含 `*` `/` `-`
# （`$X^*$`、`$n-1$`、`$A/B$` 都是完整式的合法收尾，列进来会假报），也不列
# `\cdots` / `\ldots` / `\dots`——省略号本身就是「以下省略」的**完整**收尾
# （`$1 + b_1 t + b_2 t^2 + \cdots$`、`$s_n\alpha, \ldots$` 实测均被误报过）。
_DANGLING_RE = re.compile(
    r"(?:[=<>]|\\(?:to|rightarrow|leftarrow|mapsto|Longrightarrow|in|notin"
    r"|subseteq|supseteq|times|otimes|oplus|cdot|cup|cap|circ|sim"
    r"|equiv|approx|neq?|leq?|geq?|pm|mp))$")
# 公式**内**的正文（`\\text{and}` / `\\mathrm{Hom}` 里的 `\\text{偶数}`）：翻译把词译成
# 中文是**正确**做法，不是内容差异 → 显示式对账时整段删掉（跨书实测：删体前 real-analysis
# 假报 19 单元，删体后 0）。`\\mathrm` / `\\operatorname` **不**删——它们是算子名，
# 被改动就是被改动。
# 🔴 必须**按花括号配平**取参数体：早先用一条正则 `\{(?:[^{}]|\\[^{}])*\}` 无法穿透嵌套，
# 遇 `\text{… \pmod{4} …}` 会从**第一个** `}` 截断，把残留的 `…}` 当成数学内容比 → 假阳。
# 全库普查（594 个 units-translate 章目录 / 32292 对配对单元，2026-10-21）今天 0 处踩中，
# 属**前瞻加固**（配平版与旧版实测**零差分**：转绿 0 / 新增 0）。
_TEXT_CMD_RE = re.compile(
    r"\\(?:text|textrm|textit|textbf|textsf|texttt|mbox)\s*\{")


def _text_group_end(s, start):
    """从 `\\text{` 左括号**之后**走到配平的右括号之后；不配平返回 None。"""
    depth, j = 1, start
    while j < len(s):
        c = s[j]
        if c == "\\" and j + 1 < len(s):
            j += 2                      # 跳过 \| \{ \} 等转义
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return None


def _strip_text_bodies(s):
    """删掉全部 `\\text{}` 散文体（含内层花括号）；参数不配平则原样保留。"""
    out, i = [], 0
    while True:
        m = _TEXT_CMD_RE.search(s, i)
        if m is None:
            out.append(s[i:])
            break
        out.append(s[i:m.start()])
        end = _text_group_end(s, m.end())
        if end is None:
            out.append(s[m.start():m.end()])
            i = m.end()
        else:
            i = end
    return "".join(out)


# 尾部标点：中文用 `。`、英文用 `.`，且 CN 版常在 `$$…$$` 内保留/删去句点 → 归一掉。
_TAIL_PUNCT_RE = re.compile(r"[.,;:!?。，；：！？]+$")
# 间距命令：`\quad` / `\qquad` / `\,` / `\;` / `\:` / `\\ ` / `~` **不携带数学内容**，
# 译文在 `\text{}` 散文两侧多打一个 `\quad` 当分隔（数论 ch34/0003 实测：源
# `x + yi \text{ is normalized if } x > 0`、译 `x + yi \text{是规范化的}\quad\text{若}\quad x>0`
# ——删散文后差的只是两个 `\quad`）→ 归一掉。此删除**单调安全**：两侧同删，原先相等的
# 不会变不等，只会让红转绿，不会凭空造红。
_SPACING_RE = re.compile(r"\\(?:q?quad|,|;|:>|!| )|~(?![a-zA-Z])")

# 🔴 带编号的显示式尾部是 `\tag{9.1}`，块尾锚定的 `_TAIL_PUNCT_RE` **永远剥不到**式子
# 自己的句末标点（`… = 0 . \tag{9.1}`），于是上面那条「句末标点习惯差异放行」的设计对
# 编号式失效——随机过程 ch5/0031、ch6/0051、ch9 四处实测全是这一形（`.` vs `,`）。
# 故同一豁免须显式覆盖「紧贴 `\tag{` 之前的标点」。
_PUNCT_BEFORE_TAG_RE = re.compile(r"[.,;:!?。，；：！？]+(?=\\tag\{)")


def _norm_inline_spans(body):
    """行内式清单（`$$…$$` 先剔除，避免把显示式内核当行内式），逐条去空白归一。"""
    return [re.sub(r"\s+", "", m.group(0))
            for m in _INLINE_RE.finditer(_DISPLAY_RE.sub(" ", body))]


def _norm_display_blocks(body):
    """显示式清单，逐条归一：剥行首 `>` 包裹与全部空白 + 删 `\\text{}` 体 + 删间距命令
    + 剥尾部标点。

    中英两版的 `$$` 块允许四类**排版/表述**差异（必包 `>` 的标签表是双语对称的，CN
    版可能比 EN 多一层 `>`；换行位置同理）：块内措辞的版式差异、`\\text{}` 里的散文被
    正确译成中文、句末标点习惯差异、散文两侧的间距命令多寡。除此之外剩下的 token 差异
    一律视为丢失/改写。
    """
    out = []
    for blk in _DISPLAY_RE.findall(body):
        lines = [re.sub(r"^\s*>?\s*", "", ln) for ln in blk.split("\n")]
        s = _SPACING_RE.sub("", _strip_text_bodies(
            re.sub(r"\s+", "", "".join(lines))))
        core = _TAIL_PUNCT_RE.sub("", s[:-2] if s.endswith("$$") else s)
        core = _PUNCT_BEFORE_TAG_RE.sub("", core)
        out.append(core + "$$" if s.endswith("$$") else core)
    return out


def _norm_display_pairs(body):
    """与 `_norm_display_blocks` **同序同数**，但每条附带逐字原文块。

    只给 FAIL 消息取证用：归一串把空白全删，`\\max_{1 \\le i \\le k_n}` 会被印成
    `\\max_{1\\lei\\lek_n}`——看着像 OCR 粘连没修（随机过程 ch5/0031 实测：因此误判分诊
    方向一轮）。消息必须给**磁盘上的真形**，否则闸门自己造假证据。
    """
    return list(zip(_norm_display_blocks(body),
                    [m.group(0) for m in _DISPLAY_RE.finditer(body)]))


def _lost_block_text(norm_blk, raw_src, tr_pairs):
    """一条「译文中丢失/被改写」的显示式 → 消息文本：源侧逐字 + 译侧最接近的一条。"""
    shown = " ".join(raw_src.split())[:90]
    best, best_r = None, 0.0
    for tnorm, traw in tr_pairs:
        r = difflib.SequenceMatcher(None, norm_blk, tnorm).ratio()
        if r > best_r:
            best, best_r = traw, r
    if best is not None and best_r >= 0.5:
        shown += " ｜ 译侧最近块: " + " ".join(best.split())[:90]
    return shown


def _flatten_math(body):
    """整篇正文摊平成「纯公式内容」串：去行首 `>`、去所有 `$` 定界符、去空白、删 `\\text{}
    体。用于显示式的**搬迁兜底**——EN 版独立成块、CN 版并进展望句子里写成行内式，内容一
    字未丢时仍应放行（real-analysis 实测 7 单元属此类）。截断/改写无法靠搬迁逃逸：
    要求源式**完整**内核作为子串出现。
    """
    s = "\n".join(re.sub(r"^\s*>?\s*", "", ln) for ln in body.split("\n"))
    s = _SPACING_RE.sub("", _strip_text_bodies(s))
    return re.sub(r"\$+", "", re.sub(r"\s+", "", s))


# 只有一个控制词的行内式（`$\circ$` / `$\times$` / `$\otimes$`）= 把**符号本身当名词**指代，
# 不是被砍半截的表达式：真截断必然连着剩下的操作数（`$f(xy) = $`、`$a \in$`）。
_OP_ONLY_RE = re.compile(r"^\$\\([A-Za-z]+)\$$")

# 运算符的**印面字形**：OCR 文字层常把 `\cdot` 打成裸 `·`、`\times` 打成 `×`，
# 「源侧数学里有 `\cdot`」这条豁免随之失效（abstract-algebra ch1/0007 实测：印面
# 「Our usual multiplication · is a different operation」进文字层是 U+00B7，全文
# 从未出现 `\cdot`）。故同一运算符还要认它的 Unicode 写法。
# 🔴 只在「整条行内式就一个运算符」时启用，且字形必须在源文里真实出现；凭空造一个
# 源文里连字形都没有的符号仍会被报。字形只列单码位字符，不做多字符拼接比较。
_OP_GLYPHS = {
    "cdot": "·⋅∙", "cdotp": "·", "bullet": "•",
    "times": "×", "rtimes": "⋉", "lefttimes": "⋊",
    "div": "÷", "ast": "∗", "star": "⋆", "circ": "∘",
    "oplus": "⊕", "ominus": "⊖", "oslash": "⊘", "otimes": "⊗",
    "pm": "±", "mp": "∓",
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥",
    "ne": "≠", "neq": "≠", "equiv": "≡", "cong": "≅",
    "sim": "∼~", "simeq": "≃", "approx": "≈", "asymp": "≍",
    "propto": "∝", "ll": "≪", "gg": "≫",
    "in": "∈", "notin": "∉", "ni": "∋", "mid": "∣|", "nmid": "∤",
    "subset": "⊂", "subseteq": "⊆", "supset": "⊃", "supseteq": "⊇",
    "sqsubset": "⊏", "sqsubseteq": "⊑",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔",
    "mapsto": "↦", "implies": "⇒", "iff": "⇔",
    "perp": "⊥", "parallel": "∥", "smile": "⌣", "frown": "⌢",
    "cup": "∪", "cap": "∩", "setminus": "∖",
    "wedge": "∧", "vee": "∨", "land": "∧", "lor": "∨",
}


def _op_named_in_source(span, flat_src):
    r"""「只有一个运算符」的行内式且该运算符在源文里在账 → 视为指代符号，不报。

    实测（abstract-algebra ch1/0017_desc_D8）：源书把复合运算印在散文列举里
    「$+,-,\cdot,$ and ∘」，OCR 文字层把它打坏成 `$^ \circ$` / `$^{\circ}$` → 判据 10 的
    「源文逐字有此式」豁免失效，而译文规范写的 `$\circ$` 被当成半截式（两处）。
    豁免收窄到「符号在源侧数学里在账（命令名或印面字形任一）」，故凭空造一个源文
    既无命令又无字形的符号仍会被报。
    """
    m = _OP_ONLY_RE.match(span)
    if not m:
        return False
    name = m.group(1)
    return ("\\" + name) in flat_src or any(
        g in flat_src for g in _OP_GLYPHS.get(name, ""))


def _math_content_problems(src_body, tr_body, fname):
    """判据 9/10：译文**公式内容**相对源文的丢失/截断，返回问题清单（纯函数）。

    动机（2026-09-28 Etingof《Introduction to representation theory》ch1/0014 实测）：
    翻译代理会凭「自己读到的」内容改写公式，而磁盘上的源其实是完整的——
    `$f(xy) = f(x)f(y)$ for all $x, y \\in A$` 被写成半截 `$f(xy) = $`，整条定义丢了
    一半。既有各判据全是**集合**对账（`\\tag` / 图片 / 条目编号 / 节号），公式**内容**
    不在账上，故此类静默截断一路绿灯到 merge。

    两条机械判据（都只**单向**判：译文多出公式不报，中文把代词显化为公式属正常）：
    9. 源侧每一条显示式（`_norm_display_blocks` 归一后）都必须在译文里在位——先按**多重集
       精确配对**，配不上再允许「整块搬进行内」的兜底（源式完整内核作为子串出现在
       `_flatten_math` 摊平后的译文里）；
    10. 译文行内 `$...$` 不得以悬空关系/二元运算符收尾（`$f(xy) = $` = 被截断）。
    """
    out = []

    # 9) 显示式内容丢失 / 被改写。精确配对失败 → 查摊平子串（块↔行内搬迁豁免），
    #    两者都失败才算真丢失/被改写。
    pool = list(_norm_display_blocks(tr_body))
    tr_pairs = _norm_display_pairs(tr_body)
    flat_tr = _flatten_math(tr_body)
    lost = []
    for blk, raw in _norm_display_pairs(src_body):
        if blk in pool:
            pool.remove(blk)
            continue
        core = blk[2:-2] if (blk.startswith("$$") and blk.endswith("$$")) else blk
        if core and core in flat_tr:
            continue
        lost.append(_lost_block_text(blk, raw, tr_pairs))
    if lost:
        out.append("单元 %s 显示公式在译文里丢失/被改写（须逐字节照抄源）：%s"
                   % (fname, "；".join(lost)))

    # 10) 行内式半截。**仅判译文新造**的悬空式：源书本就那样写的（`$V \otimes$` 指
    # 「张量函子」、`$\subseteq$` 指「包含关系」，本书实测两处）属印面照抄，不报；
    # 真正被砍半截的 `$f(xy) = $` 在源的行内式集合里无配对 → 报。
    attested = set(_norm_inline_spans(src_body))
    flat_src = _flatten_math(src_body)
    dang = [s[:40] for s in _norm_inline_spans(tr_body)
            if _DANGLING_RE.search(s[1:-1]) and s not in attested
            and not _op_named_in_source(s, flat_src)]
    if dang:
        out.append("单元 %s 行内公式被截断（以悬空运算符收尾且源文无此式）：%s"
                   % (fname, "；".join(dang[:4])))
    return out


def _labels(body):
    """粗体标签内部的条目编号集合（只认标签内，不认正文里的数字编号）。"""
    out = set()
    for m in _BOLD_RE.finditer(body):
        n = _NUM_IN_LABEL_RE.search(m.group(1))
        if n:
            out.add(n.group(1))
    return sorted(out)


def _has_prose(body):
    """True when the unit carries natural-language text worth translating.

    "未翻译" can only be judged on prose: a pure-formula unit (`$y \\in \\Re$`)
    or a pure-image unit is *correctly* byte-identical in both languages, so
    flagging it is a false positive.  All math ($$...$$ and $...$) is masked
    out first; whatever visible text remains decides.
    """
    s = re.sub(r"\$\$[\s\S]*?\$\$", " ", body)
    s = re.sub(r"\$[^$\n]*\$", " ", s)
    for ln in s.split("\n"):
        t = ln.strip()
        if not t:
            continue
        if "<img" in t or "<div" in t or "</div>" in t or t.startswith("<!--"):
            continue
        return True
    return False


def _hash_text(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _read_body(path):
    """读单元正文（去掉首行标记）——复用 ``gate_units._read_unit``，不重复实现。"""
    _mark, _uid, _utype, _key, body, _h = _gate._read_unit(path)
    return body or ""


def _collect(body, rx):
    return sorted(set(rx.findall(body)))


PAIR_FIELDS = ("id", "type", "key", "name")


def pair_units(su, tu):
    """把源/译两侧的 manifest 单元记录**按 `file` 配对**。返回 (problems, pairs)。

    🔴 判据本体（第 1 项）不住在 `check_chapter_parity` 里而先拆成纯函数，是因为
    「按下标 zip 配对」这个错法只有拿真实清单才能证伪——zip 版在 Kreyszig 泛函分析
    ch4 报出 26 行「字段不一致」全是假阳（该章两侧字段本就全等），而它跳过的正是
    该比的那一对。本函数还负责把三种真缺陷分开报清：**漏译**（源有译无）、**多余/改名**
    （译有源无）、**顺序分叉**（集合相同而次序不同：`merge_units` 各按自己那侧的
    `units` 次序拼接，源/译交付 md 的阅读顺序会不一样）。同名单元重复使配对失去唯一性，
    单独报出且**不再按位置猜测**。
    """
    problems = []
    if len(su) != len(tu):
        problems.append("单元数不一致：源 %d / 译 %d（漏译或多余单元）" % (len(su), len(tu)))
    su_files = [str(u.get("file") or "") for u in su]
    tu_files = [str(u.get("file") or "") for u in tu]

    def _by_file(units, side):
        by_file, dups = {}, []
        for u in units:
            fname = str(u.get("file") or "")
            if fname in by_file:
                dups.append(fname)
            else:
                by_file[fname] = u
        for fname in sorted(set(dups)):
            problems.append("%s侧 manifest 单元文件名重复：%s（同名下无法按文件配对）"
                            % (side, fname))
        return by_file

    src_by, tgt_by = _by_file(su, "源"), _by_file(tu, "译")
    only_src = sorted(set(src_by) - set(tgt_by))
    only_tgt = sorted(set(tgt_by) - set(src_by))
    if only_src:
        problems.append("源侧 %d 个单元无对应译文（漏译）：%s"
                        % (len(only_src), ", ".join(only_src[:8])
                           + (" …" if len(only_src) > 8 else "")))
    if only_tgt:
        problems.append("译侧 %d 个单元在源侧无据（多余 / 改名）：%s"
                        % (len(only_tgt), ", ".join(only_tgt[:8])
                           + (" …" if len(only_tgt) > 8 else "")))

    pairs = []
    for fname in su_files:                        # 按源侧登记顺序逐单元裁决
        a, b = src_by.get(fname), tgt_by.get(fname)
        if a is None or b is None:
            continue                               # 缺对已由上面两条报出
        for fld in PAIR_FIELDS:
            if str(a.get(fld) or "") != str(b.get(fld) or ""):
                problems.append("单元 %s %s 不一致：源 %r / 译 %r"
                                % (fname, fld, a.get(fld), b.get(fld)))
                break
        pairs.append((a, b))
    if not (only_src or only_tgt) \
            and len(set(su_files)) == len(su_files) and len(set(tu_files)) == len(tu_files) \
            and su_files != tu_files:
        _nd = sum(1 for x, y in zip(su_files, tu_files) if x != y)
        problems.append("两侧 manifest 的单元**顺序**不同（%d/%d 个位置的文件名不一致）——"
                        "`merge_units` 各按自己那侧的顺序拼接，源/译交付 md 的阅读顺序会分叉；"
                        "须把一侧的 `units` 数组次序改回另一侧（正文不动）"
                        % (_nd, len(su_files)))
    return problems, pairs


def check_chapter_parity(ext, ch_key):
    """比对单章源单元与翻译单元。返回 (ok, problems)。"""
    prime_chapter_kinds(ext)  # 被当库调用时同样保证补篇/附录目录名正确
    src_dir = os.path.join(ext, _ac.OUT_DIR_NAME, SRC_SUB, unit_dir_name(ch_key))
    tgt_dir = os.path.join(ext, _ac.OUT_DIR_NAME, TGT_SUB, unit_dir_name(ch_key))
    problems = []
    if not os.path.isdir(tgt_dir):
        return False, ["%s 缺 units-translate 目录（先跑 init_translate_units.py 初始化清单）。" % chapter_label(ch_key)]
    smp, tmp = (os.path.join(d, "manifest.json") for d in (src_dir, tgt_dir))
    if not (os.path.exists(smp) and os.path.exists(tmp)):
        return False, ["%s 源/译 manifest.json 缺失。" % chapter_label(ch_key)]
    with open(smp, encoding="utf-8") as f:
        src_m = json.load(f)
    with open(tmp, encoding="utf-8") as f:
        tgt_m = json.load(f)
    su, tu = src_m.get("units") or [], tgt_m.get("units") or []

    # 1) 单元配对 + 字段一致（判据本体 = `pair_units`，负向测试见其文档）
    _pair_problems, pairs = pair_units(su, tu)
    problems.extend(_pair_problems)

    for a, b in pairs:
        sp = os.path.join(src_dir, a["file"])
        tp = os.path.join(tgt_dir, b["file"])
        if not (os.path.exists(sp) and os.path.exists(tp)):
            problems.append("单元 %s 文件缺失（源/译之一不存在）" % a["file"])
            continue
        sb, tb = _read_body(sp), _read_body(tp)
        utype = a.get("type")

        # 12) 首行标记 ↔ 本侧 manifest 记录（两侧各判一次；判据理由见 marker_manifest_mismatch）
        for _rec, _p, _side in ((a, sp, "源"), (b, tp, "译")):
            _mm = marker_manifest_mismatch(_p, _rec, _side)
            if _mm:
                problems.append("单元 %s %s（可用 tools/sync_translate_markers.py 复位）"
                                % (a["file"], _mm))

        # 7) 未翻译残留（仅对该翻译的散文：纯公式 / 纯图单元译文与源文一致是正确的）
        if utype in ("item", "desc") and sb.strip() and tb.strip() \
                and _has_prose(sb) \
                and _hash_text(sb.rstrip("\n")) == _hash_text(tb.rstrip("\n")):
            problems.append("单元 %s 译文与源文完全相同（未翻译）" % a["file"])

        # 8) 英文残留（半截翻译：标签/证明散文仍是英文，哈希对账抓不住）
        if utype in ("item", "desc", "exercise") and tb.strip():
            for p in _quality.english_residues(tb):
                problems.append("单元 %s 未翻译：%s" % (a["file"], p))

        # 9) / 10) 公式内容对账（纯函数，判据与负向测试见 _math_content_problems）
        problems.extend(_math_content_problems(sb, tb, a["file"]))

        # 2) \tag 一致
        st, tt = _collect(sb, _TAG_RE), _collect(tb, _TAG_RE)
        if st != tt:
            miss = [x for x in st if x not in tt]
            extra = [x for x in tt if x not in st]
            problems.append("单元 %s 公式序标不一致：缺 %s / 多 %s"
                            % (a["file"], miss or "-", extra or "-"))
        # 3) 图片一致
        si, ti = _collect(sb, _IMG_RE), _collect(tb, _IMG_RE)
        if si != ti:
            problems.append("单元 %s 图片不一致：源 %s / 译 %s" % (a["file"], si, ti))
        # 4) 节号一致（section 单元）
        if utype == "section":
            ss, ts = _collect(sb, _SEC_RE), _collect(tb, _SEC_RE)
            if ss != ts:
                problems.append("单元 %s 节号不一致：源 %s / 译 %s" % (a["file"], ss, ts))
        # 5) 编号项标签编号一致（item / exercise 单元）
        if utype in ("item", "exercise"):
            sl, tl = _labels(sb), _labels(tb)
            if sl != tl:
                problems.append("单元 %s 条目编号不一致：源 %s / 译 %s" % (a["file"], sl, tl))
        # 6) 源单元漂移（派生后源又被改 → 译文与源已不同步）。
        # 🔴 fail-closed：manifest 缺 src_hash 快照同样判不通过——没有快照漂移
        # 检测即失效，等于给「源未定稿就翻译」留旁路。
        src_now = _hash_text(sb.rstrip("\n"))
        recorded = b.get("src_hash")
        if not recorded:
            problems.append("单元 %s manifest 缺 src_hash 快照（重跑 init_translate_units "
                            "补齐；无快照 = 漂移检测失效 = 旁路）" % a["file"])
        elif recorded != src_now:
            problems.append("单元 %s 源单元已被修改（派生后漂移）——须按单向修复规则"
                            "先定稿源单元，再重新派生/同步翻译单元" % a["file"])

    if problems:
        return False, problems
    return True, ["%s 翻译同构通过：%d 个单元（tag / 图 / 节号 / 条目号 / 无漂移）"
                  % (chapter_label(ch_key), len(su))]


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    ext = argv[0]
    # 🔴 kind 注册表必须先灌注：unit_dir_name / chapter_label 判据来自 chapter_map，
    # 未灌注时字母章一律回退成 appendixX → 补篇（supplementS）会被找成 appendixS，
    # 报「缺 units-translate 目录」假 FAIL，且该章同构校验形同虚设。
    prime_chapter_kinds(ext)
    try:
        chapters = [int(x) for x in argv[1:]]
    except ValueError:
        chapters = argv[1:]
    keys = [k for k in list_chapter_keys(ext)
            if not chapters or k in {str(c) for c in chapters}]
    if not keys:
        print("[check_translate_parity] 无章节可校验。")
        return 2
    all_ok = True
    for k in keys:
        ok, detail = check_chapter_parity(ext, k)
        if ok:
            print("[PASS] " + detail[0])
        else:
            all_ok = False
            print("[FAIL] %s 翻译同构未通过（%d 处）：" % (chapter_label(k), len(detail)))
            for d in detail[:40]:
                print("  - " + d)
            if len(detail) > 40:
                print("  … 另有 %d 处" % (len(detail) - 40))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
