"""check_unit_quality.py — 单元级「写对」质量校验（write-source 步骤 5 门控的一部分）

全部复用 verify 流程已有检测脚本，按 verify F 层校验顺序执行，不重新造轮子：
  F 层（按 verify 顺序）：
    1. 裸 Unicode 箭头：`katex_heuristics.find_raw_arrow_errors`
    2. 裸 LaTeX 命令：`katex_heuristics.find_naked_command_errors`
    3. `$` 吞噬前缀：`katex_heuristics.find_swallowed_prefix_errors`
    4. 裸数学/裸函数调用：`katex_heuristics.find_bare_math_errors`
    5. `$` 奇偶配对：内联计算
    6. `$$` 闭合：`check_katex.check_display_math_closure`
    7. 围栏形态（`_fence_issues`，移植 check_katex.py Pass 1 口径）：单行
       `$$...$$` 块（真实 Markdown 预览器不认，而 katex_validate.js 支持、
       closure 只查 EOF——两道渲染检查都看不见）/ `$$` 附着内容 / blockquote
       内 `> $$` 前缺空 `>` 行 / 顶层 `$$` 前缺空行 / `\tag` 在数学模式外
  P 层：
    7. 证明过长：`verbose_gates.check_verbose_proofs`
  H/G 层：
    8. 结构标签：`struct_labels.TOP_LEVEL_HEADER_RE`
    9. example blockquote：`format_verify.check_example_blockquote_lines`
    9b. 块引用/例/证明/列表结构（`_run_format_verify_unit_checks`，临时 .md
        复用 format_verify 原函数，不复制逻辑）：nested_bq / ex_proof_gaps /
        g_quote_continuity（blockquote内 bare blank line 打断连续性）/
        h_structural_bq / h_stmt_bq / h_ul_bq / h_mbq / k_proof_list /
        n_bq_empty / m_dm_gt；文档级专属（`---` 分隔线 / 标题上下文类：
        i_sep / j_header / l_sep / heading_* / quote_gaps）不搬——孤立单元
        无 `---`、标题即首行，搬了必误报。
  补充：
    10. OCR 残留模式（verify 不覆盖的 OCR 特有命令 / garbled / 编码损坏）
    11. 内容审阅类残留（「没审阅改好」的典型痕迹，writing-rules 明确须剔除）：
        QED 结尾框「口/□」独立行、OCR 乱码重复片段、单元内私造 `#` 标题行
    12. 单元级公式序标对账（`expected_tags` 提供时）：以内容化契约
        （`chapter_tag_map`）要求该单元携带的 `formula.tag` 为真值，缺失（漏写
        编号公式）与编造（多出编号）均判不通过——Q 层是章级末步，单元粒度提前拦
    13. 单元级图片对账（`expected_images` 提供时）：契约节点 image 块为真值，
        按 basename 比对 `<img src>`；缺图（内容丢失）与多图（编造/错位）均不通过
    14. 空正文闸（`content_blocks` > 0 提供时）：契约节点有内容块而单元正文仅剩
        标头 = 整体清空，不通过（desc/item 的幻影节点 content_blocks == 0 允许空；
        exercise 的 0 块节点由第 16 项直接判不通过）
    15. 假省略声明闸：正文写「consolidated problem set / omitted here / 此处省略 /
        综合习题集」等措辞即不通过——有单元的习题节点必为 consolidated=false，
        该措辞既虚假又掩盖题面缺失；豁免两条：① 命中措辞原样见于该单元契约节点
        书源原文（``source_text``，Tier 1 忠实引用）；② **非** exercise/item 单元
        且声明处局部上下文无「习题/证明/整节」内容指向词（``_OMISSION_ANCHOR_RE``）
        = 「omit」的数学用法而非省略声明。无 source_text 不享豁免 ①
    16. 幻影习题条目闸（契约切片缺陷，`utype == "exercise"`）：标题去序标后起于
        句中 / 契约节点零内容块 / 节点携带**别的小节**的编号公式或插图 = OCR 把
        跨条目续行切成独立条目、或把后续小节正文整段吞进习题节点；不通过，须契约
        + 单元同步修（并回碎片、按书源复原题面），改措辞无效
    17. 行内公式边界粘连闸（`math_glue_problems`）：散文（EN 字母/数字/`)`、CN
        汉字）紧贴 `$...$` 任一侧 = OCR 粘连未清理；标点/引号紧贴豁免
  🔴 本模块只做静态/启发式检测；**真实 KaTeX 渲染**（`katex_render.run_render_check`，
    katex_validate.js 按章批量跑、错误映射回单元）由 `gate_units.gate_chapter` 承担。
  🔴 调用方（gate_units / flow_runner 证据复核）必须 **fail-closed**：本函数抛异常时
    该单元按「质量未达标」处理，绝不放行。

用法：``check_unit_quality.check_body(utype, name, body) -> (ok, problems)``
译文语言残留：``check_unit_quality.english_residues(body) -> problems``（仅
units-translate 单元调用，由 gate_units 翻译分支与 check_translate_parity 共用）
"""
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "verify", "format_verify", "script"),
           os.path.join(_ROOT, "verify", "verbose_gates", "script"),
           os.path.join(_ROOT, "verify", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

# ── 复用 verify 已有检测（全部 import，不重新实现）────────────────────────
from check_katex import check_display_math_closure   # F 层：$$ 闭合
from katex_heuristics import (                        # F 层：裸数学检测
    find_bare_math_errors,
    find_raw_arrow_errors,
    find_naked_command_errors,
    find_swallowed_prefix_errors,
    find_display_fence_damage_errors,
)
from verbose_gates import check_verbose_proofs        # P 层：证明过长
from struct_labels import TOP_LEVEL_HEADER_RE         # H 层：结构标签
from format_verify import check_example_blockquote_lines  # G 层：example blockquote

# ── 复用 format_verify 文档级检查（块引用/例/证明/列表结构），单元级化 ──
# 这些检查在 verify 里以文件为输入；单元门控把单元正文写到临时 .md 后复用原函数，
# **不复制逻辑**（保持单一真相源，避免已踩过的「三份分叉」坑）。文档级专属的
# `---` 分隔线 / 标题上下文类检查（i_sep / j_header / l_sep / heading_* /
# quote_gaps）不搬——孤立单元里无 `---`、标题即首行，搬了会误报。
# 🔴 块引用内 bare blank line（blockquote内无 `>` 前缀的空行）检查已加入——
# 这在单元级别也是正确的，因为单元中也可能有blockquote内的bare blank line
# 打断块引用连续性。
from format_verify import (
    check_nested_blockquotes,          # G: > > ** 嵌套块引用
    check_example_proof_gap,           # G: 例与证明间断裂 / 同行
    check_g_quote_continuity,          # G: blockquote内 bare blank line 打断连续性
    check_h_structural_blockquote,     # H: 结构标签误入 `>` / 孤儿空 `>`
    check_h_statement_in_blockquote,   # H: 陈述内容误包 `>`
    check_unlabeled_blockquotes,       # H: `>` 块无标签
    check_labels_missing_blockquote,   # H: 标签在顶层未包 `>`
    check_proof_after_list,            # K: 列表末项后直接接新块无空行
    check_excessive_bq_empty_lines,    # N: 连续空 `>` 行
    check_displaymath_gt,              # M: `$$` 块内泄 `>`
)

# ── 本模块专有：OCR 公式残留（verify 不覆盖）──────────────────────────────
_OCR_FORMULA_PATTERNS = [
    (r"\\ensuremath\s*\{", "OCR 残留 \\ensuremath（应改为直接 KaTeX）"),
    (r"\\pmb\s*\{", "OCR 残留 \\pmb（应改为 \\mathbf 或 \\boldsymbol）"),
    (r"\\boldsymbol\s*\{[^}]*\}\s*[A-Za-z]", "OCR 残留 \\boldsymbol 在数学模式外"),
    (r"[\u00e0-\u00ff]{3,}", "garbled Unicode 片段（OCR 编码错误）"),
    (r"\\sun\b", "OCR 残留 \\sun（应改为具体数学符号）"),
    (r"\\b\s*\{", "OCR 残留 \\b 命令"),
    (r"\\E\s*\{", "OCR 残留 \\E（应改为 \\operatorname{E} 或具体符号）"),
    (r"\ufffd", "replacement character（U+FFFD）残留（编码损坏，须回源修正）"),
]

# ── 本模块专有：内容审阅类残留（「没审阅改好」的典型痕迹）─────────────────
# QED 结尾框独立行（writing-rules「内容清理与保真」明确须剔除；∎ 同属裸 Unicode
# 数学字形，也不该以独立行形式出现）。
_QED_BOX_LINE_RE = re.compile(r"^[口□■◻◼∎]$")
# 单元内出现 ATX 标题行 = 自造层级 / 把标题并进条目（标题是独立 section 单元；
# writing-rules：不得自创层级、不得无中生有）。
_HEADING_LINE_RE = re.compile(r"\s{0,3}#{1,6}\s")
# 🔴 「假省略声明」：把没写的习题谎称「原书把它们收进了综合习题集，此处省略」。
# 拆分期（split_draft_units）对契约 `consolidated=true` 的章末集中习题块**根本不
# 生成单元**——因此凡是存在单元的习题节点一律 consolidated=false（穿插/逐节习题，
# 收录规则要求题面完整在位）。正文里出现下列措辞即等于对读者作虚假声明，且实际
# 掩盖了整节题面缺失（曾在 Katok ch20 一次掩盖 22 道题）。
_OMISSION_CLAIM_RE = re.compile(
    r"consolidated\s+problem\s+set|omitted\s+here|not\s+reproduced\s+here"
    r"|collected\s+as\s+a\s+consolidated"
    r"|此处省略|此处从略|不再收录|未予收录|省略未收"
    r"|归入综合习题|综合习题集", re.I)
# 🔴 措辞指向**被省掉的总结内容**（习题 / 证明 / 整节）才算掩盖缺失。习题与编号项
# 单元正文必须完整，一律直接判（不看措辞语境）；desc / section 等散文单元里
# 「omit」常是**数学用法**（Katok ch5 D21：「a second chart … covers the vertically
# downward vectors omitted here」= 第一张图不覆盖竖直向下向量，是正文内容本身），
# 无内容指向即不构成虚假声明，否则门控对忠实转写的散文假阳。
_OMISSION_ANCHOR_RE = re.compile(
    r"exercise|problem|习题|综合题|题面|证明|proof|本节|该节|全节|末节|本章"
    r"|this\s+section|these\s+sections|that\s+section|section\s*[§]?\d"
    r"|all\s+the\s+exercises", re.I)
# 判「内容指向」只看声明处**局部上下文**（±字符），不做全篇搜索：散文单元正文长，
# 全篇搜「proof / 节」几乎必命中，等于没豁免。
_OMISSION_CTX = 160
# 🔴 「幻影习题条目」= OCR 把**跨条目续行**切成独立条目。抽取器按「序标 + 句号」
# 认条目，而正文里 `…Theorem | 20.1.3. Let Per(t,ε)…`、`…(Definition | 20.2.5). In
# analogy…` 这类断行同样形如序标，于是后半段被登记成一条「习题」。三种可机械判定
# 的痕迹（曾在 Katok 全书命中 24 处，最严重一例让 ch20 20 道题被谎称省略）：
#   (a) 条目标题起于**句中**（去掉序标残留后以小写字母 / `)` / `,` 开头）；
#   (b) 节点**零内容块**——真习题不可能一块都没有；
#   (c) 节点携带的编号公式 / 插图的**小节号 ≠ 该习题自己的小节号** = 把后续小节
#       正文整段吞进习题节点（Katok ch9 的 9.1.5 吞了 §9.2 全节 684 块 4 图）。
# 判据只到「该单元对应的契约节点有幻影痕迹」为止：修法是把碎片并回上一条目、
# 按书源复原题面（契约 + 单元同步），不是把单元改措辞。
# 两条按**单元正文形态**豁免（Leinster 全书 37 处误伤回归）：
#   ① 标题去残留后以 `a)` / `b.` 等**子题标号**起头 = 原书分小题习题的合法
#      条目（题面本身就是 "(a) Show that…"），不是句中续行；
#   ② content_blocks==0 但题面其实**已落地单元正文**（name 非句中起头时）：
#      契约 name 自带完整题面（≥6 个词元，如组标题 "Interactions between
#      adjoint functors and limits"）；或正文**加粗标签**里写出本条目编号
#      （"Exercises 4.3.15 Prove Lemma 4.3.8" 这类短题面，正文 `**4.3.15**`
#      即落地证明；Katok 残渣 "for fows." 句中起头 → 两条均不适用，照旧拦）。
#      两条豁免都要求正文非空（空正文照常 FAIL，防措辞掩盖）。
_LABEL_RESIDUE_RE = re.compile(r"^[\s)\],;.0-9*†\-(/]+")
_FIG_CHAPTER_RE = re.compile(r"(?:ch0*|appendix)(\d+|[A-Za-z])[_/]fig", re.I)
# 图号「章.节.序」形态（≥3 段数字）才携带小节信息，可据图号反推所属小节；
# 「章.序」（2 段，Vakil/Katok/Weibel 章级计数器 Figure 5.2）不含小节信息，绝不反推。
_FIG_NUM_RE = re.compile(r"fig(\d+(?:[.\-]\d+){2,})", re.I)
# 子题标号形态：单个/双/三个字母 + `)` 或 `.`（"(a)" 去残留后剩 "a) …"）
_PART_LABEL_RE = re.compile(r"^[a-z]{1,3}[.)]\s")
# 结构性条目标签关键词：正文 own-key 粗体头含之 = 真·自洽条目（非裸序标残渣）。
_LABEL_KEYWORD_RE = re.compile(
    r"(Exercise|Example|Theorem|Definition|Lemma|Corollary|Proposition|Problem|"
    r"Solution|Remark|Note|Algorithm|Proof|"
    r"习题|练习|例题|例|定理|定义|引理|推论|命题|问题|注|算法|证明|证)")
# 词元（字母词，含中日韩），用于判 name 是否「自带题面」而非两三词残渣
_WORD_TOKEN_RE = re.compile(r"[^\W\d_]+")
_NAME_STATEMENT_MIN_WORDS = 6


def _name_carries_statement(name):
    """契约 name 是否自带完整题面（≥6 个词元的实质文字而非切片残渣）。"""
    return len(_WORD_TOKEN_RE.findall(str(name or ""))) >= _NAME_STATEMENT_MIN_WORDS


def _key_ordinal(key):
    """``4.3-15`` / ``4.3.15`` -> ``4.3.15``；无分段序标（如 ``6_3``）返回 None。"""
    parts = [p for p in re.split(r"[.\-]", str(key or "")) if p != ""]
    return ".".join(parts) if len(parts) >= 2 else None


def _bold_carries_ordinal(body, ordinal):
    """正文任一 ``**加粗**`` 标签含本条目编号 = 题面已落地该单元。"""
    if not ordinal:
        return False
    return any(ordinal in seg for seg in re.findall(r"\*\*([^*]+)\*\*", body))


def _sec_prefix(token):
    """``9.1.5`` -> ``9.1``；不足三段（无小节可判）返回 None。"""
    parts = [p for p in re.split(r"[.\-]", str(token or "")) if p != ""]
    return ".".join(parts[:-1]) if len(parts) >= 3 else None


def phantom_exercise_problems(name, content_blocks, expected_tags, expected_images,
                              key, body=""):
    """习题单元的「幻影条目」判据（见 ``_LABEL_RESIDUE_RE`` 注释）。返回问题列表。

    ``body``：单元正文（供两条形态豁免判定，见注释①②；缺省空 = 不豁免）。
    """
    out = []
    has_body = bool(str(body or "").strip())
    residue = _LABEL_RESIDUE_RE.sub("", str(name or "")).strip()
    # 正文自带与本题 key 一致、且**含结构性关键词**（Exercise/定理/例…）的粗体头 =
    # 完整自洽条目，绝非 OCR 续行碎片——即便契约 name 字段带 OCR 噪声前缀（如星标
    # `⋆`→`*x` 粘在标题前）使其看起来「起于句中」，仍据此豁免误判。豁免条件收紧为
    # 「own-key 粗体头里同时有关键词」：真条目形如 `**Exercise 11.1.K …**`；Katok 残渣
    # 的正文粗体头只是**裸序标** `**20.1.5.**`（无关键词），据以判句中的豁免不成立，照旧拦。
    own_ord = _key_ordinal(key)
    self_keyed = (has_body and bool(own_ord)
                  and any(own_ord in seg and _LABEL_KEYWORD_RE.search(seg)
                          for seg in re.findall(r"\*\*([^*]+)\*\*", str(body))))
    mid_sentence = (residue[:1].islower() and residue[:1].isalpha()
                    and not (has_body and _PART_LABEL_RE.match(residue))
                    and not self_keyed)
    if mid_sentence:
        out.append(
            "契约习题条目「%s…」标题起于句中——OCR 把跨条目续行错切成独立条目"
            "（幻影习题）；须把该碎片并回上一条目、按书源复原本题题面（契约与单元同步）"
            % residue[:24])
    if content_blocks == 0 and not (
            has_body and not mid_sentence
            and (_name_carries_statement(name)
                 or _bold_carries_ordinal(str(body), _key_ordinal(key)))):
        out.append(
            "契约习题节点不含任何内容块（text/formula/image 全空）——真习题不可能"
            "零内容，本单元对应的是 OCR 切片残渣；须在契约层并回上一条目后重拆")
    own = _sec_prefix(key)
    if own:
        cross = [t for t in (expected_tags or []) if _sec_prefix(t) and _sec_prefix(t) != own]
        if cross:
            out.append(
                "习题条目 %s（属 §%s）的契约节点携带后续小节 §%s 的编号公式 %s——"
                "该节点吞并了别的小节的正文，须把这些内容块并回所属小节（契约层）"
                % (key, own, "、§".join(sorted(set(_sec_prefix(t) for t in cross))),
                   "、".join(map(str, cross[:6]))))
        # 插图归属判据（两级）：
        #   ① 跨章：文件名 ``ch{NN}`` 前缀（assign_figures 按章命名 = 权威）≠ 本条目章
        #      → 吞并别章正文；
        #   ② 跨小节：**仅当**图号是「章.节.序」≥3 段（携带小节信息）时，取其前两段的
        #      小节号与本条目小节号比对；「章.序」2 段（Vakil/Katok/Weibel 章级计数器
        #      Figure 5.2）不含小节信息，绝不据第二段反推小节——否则 §5.5 的 Exercise
        #      5.5.G 正常携带的 Figure 5.2 会被误判成「§5.2 的图」。
        img_cross = []
        own_segs = [s for s in re.split(r"[.\-]", str(key)) if s != ""]
        own_ch = own_segs[0].lstrip("0").upper() if own_segs else ""

        def _num_prefix2(segs):
            try:
                return ".".join(str(int(x)) for x in segs[:2])
            except (ValueError, TypeError):
                return ".".join(segs[:2])

        own_sec = _num_prefix2(own_segs) if len(own_segs) >= 2 else None
        for p in (expected_images or []):
            sp = str(p)
            fm = _FIG_CHAPTER_RE.search(sp)
            if fm and fm.group(1).lstrip("0").upper() != own_ch:
                img_cross.append("%s(第%s章)" % (sp.split("/")[-1], fm.group(1)))
                continue
            nm = _FIG_NUM_RE.search(sp)
            if nm and own_sec:
                fsegs = [s for s in re.split(r"[.\-]", nm.group(1)) if s != ""]
                if len(fsegs) >= 3 and _num_prefix2(fsegs) != own_sec:
                    img_cross.append("%s(§%s)" % (sp.split("/")[-1], _num_prefix2(fsegs)))
        if img_cross:
            out.append(
                "习题条目 %s（属第%s章%s）的契约节点携带别的小节 / 别章插图 %s——该节点"
                "吞并了后续正文，须在契约层把图块并回所属小节 / 章"
                % (key, own_ch, ("§" + own_sec if own_sec else ""),
                   "、".join(img_cross[:6])))
    return out


def _prose_text(line_list):
    """剥掉数学模式，只留散文段（OCR 残留模式只对数学模式外文本有意义）。

    按 `$` 配对剥除：
      - 先剥 blockquote 前缀 `>`（否则 `> $$` 围栏识别不到，块内公式被当散文）；
      - `$$` 围栏内的行整行跳过（含围栏行本身）；
      - 其余行按单个 `$` 分段，偶数段（数学外）保留。
    """
    out = []
    in_display = False
    for ln in line_list:
        content = re.sub(r"^\s*>\s?", "", ln)  # 剥一层 blockquote 前缀
        s = content.strip()
        if s == "$$" or (s.startswith("$$") and not s.endswith("$$")):
            in_display = not in_display
            continue
        if s.startswith("$$") and s.endswith("$$") and len(s) > 4:
            continue  # 单行 $$...$$ 整行是数学
        if in_display:
            continue
        parts = content.split("$")
        out.append("".join(parts[0::2]))  # 偶数段 = 数学外
    return "\n".join(out)


def _count_inline_dollars(line_list):
    """计算数学模式外的 `$` 总数，奇数 = 未配对。"""
    in_display = False
    count = 0
    for ln in line_list:
        s = ln.strip()
        if s == "$$" or (s.startswith("$$") and not s.endswith("$$")):
            in_display = not in_display
            continue
        if s.startswith("$$") and s.endswith("$$") and len(s) > 4:
            continue
        if in_display:
            continue
        # 剥掉转义的 \$
        content = re.sub(r"\\\$", "", ln)
        # 按 $ 分段，统计 $ 数量 = 段数 - 1
        count += content.count("$")
    return count


# ── F 层围栏形态（移植 check_katex.py Pass 1 的单元化轻量版）──────────────
# katex_validate.js 的状态机**显式支持单行 `$$...$$` 块**（渲染 OK 不报错），
# check_display_math_closure 只查 EOF 闭合——两者都看不见「一对 $$ 挤在一行」
# 这类形态违规，而真实 Markdown 预览器多数不认单行块（显示原文/渲染失败）。
# 故单元门控必须用与 F 层一致的 heuristic 把形态查住。

def _fence_issues(line_list):
    """`$$` 围栏形态检测（F 层口径）。返回问题列表。

    检测（与 verify F 层 check_katex.py Pass 1 同口径）：
      F7a) single-line display math：`$$...$$` 挤在一行（剥 `>` 后）——须拆行；
      F7b) $$ 附着内容：开围栏 `$$xxx` / 闭围栏 `xxx$$`（同行还有内容）——须拆行；
      F7c) blockquote 内 `> $$` 开围栏的上一非空行不是空 `>` 行（如紧接
           `> **证明**：` 文字）——须插一个空 `>` 行；
      F7d) 顶层开 `$$` 的上一非空行是普通文本（缺空行）；
      F7e) `\tag{` 出现在数学模式外（tag 必须在 `$$` 块内）。
    """
    problems = []
    in_math = False        # 顶层 $$ 块
    in_bq_math = False     # > $$ 块
    prev_raw = None        # 紧邻上一非空行（lstrip 原文；空行清空）
    for raw in line_list:
        is_bq = raw.lstrip().startswith(">")
        content = re.sub(r"^\s*>\s?", "", raw) if is_bq else raw
        s = content.strip().replace("\\$", "")
        if s == "$$":
            if is_bq:
                if in_bq_math:
                    in_bq_math = False
                else:
                    if in_math:  # 跨层错位：> $$ 关掉了顶层块
                        in_math = False
                    # F7c：上一非空行必须是空 `>` 行（`>` / `> `）
                    if prev_raw is not None:
                        prev_is_empty_bq = (
                            prev_raw.startswith(">")
                            and re.sub(r"^\s*>\s?", "", prev_raw).strip() == "")
                        if not prev_is_empty_bq:
                            problems.append(
                                "missing empty > line before > $$（blockquote 内 "
                                "`> $$` 前须插一个空 `>` 行，上一行：%s）"
                                % prev_raw.strip()[:30])
                    in_bq_math = True
            else:
                if in_math:
                    in_math = False
                elif in_bq_math:
                    in_bq_math = False
                else:  # F7d：顶层开围栏前须空行（上一非空行不能是普通文本）
                    if prev_raw is not None and not prev_raw.startswith(">"):
                        problems.append(
                            "missing blank line before opening $$（$$ 前须空行，"
                            "上一行：%s）" % prev_raw.strip()[:30])
                    in_math = True
            prev_raw = None
            continue
        if not in_math and not in_bq_math:
            # F7a / F7b：文本模式下的含 $$ 行（纯围栏行已在上面 continue）
            core = s
            if core.startswith("$$") and not core.endswith("$$") and len(core) > 2:
                problems.append(
                    "opening $$ attached to formula content — split onto its own "
                    "lines（%s）" % core[:40])
            elif core.endswith("$$") and not core.startswith("$$") and len(core) > 2 \
                    and "$$" not in core[:-2]:
                problems.append(
                    "closing $$ attached to formula content — split onto its own "
                    "lines（%s）" % core[:40])
            elif core.count("$$") >= 2:
                problems.append(
                    "single-line display math — split $$ onto separate lines（%s）"
                    % core[:40])
        if s:
            prev_raw = raw.lstrip()
        else:
            prev_raw = None  # 空行（含空 `>` 行）= 与上一非空行不再紧邻
    return problems


# ── 复用 format_verify 的单元级可查检查（块引用/例/证明/列表结构）────────────
# 这些检查在 verify 里以「文件」为输入；单元门控把单元正文写临时 .md 后复用原函数，
# 行号相对于单元正文（临时文件即 body 内容），与单元内行一致。文档级专属
# （`---` 分隔线 / 标题上下文）检查不入此列，避免孤立单元误报。
# 🔴 fail-closed：本函数内不吞掉子检查异常——任一子检查抛错会冒泡到 check_body，
#   由 gate_units 统一按「质量未达标」fail-closed 处理（绝不静默放行）。
_FV_UNIT_CHECKS = (
    check_nested_blockquotes,          # G: > > ** 嵌套
    check_example_proof_gap,           # G: 例与证明间断裂 / 同行（返回 (errors, warns)）
    check_g_quote_continuity,          # G: blockquote内 bare blank line 打断连续性
    check_h_structural_blockquote,     # H: 结构标签误入 `>` / 孤儿空 `>`
    check_h_statement_in_blockquote,   # H: 陈述内容误包 `>`
    check_unlabeled_blockquotes,       # H: `>` 块无标签
    check_labels_missing_blockquote,   # H: 标签在顶层未包 `>`
    check_proof_after_list,            # K: 列表末项后直接接新块无空行
    check_excessive_bq_empty_lines,    # N: 连续空 `>` 行
    check_displaymath_gt,              # M: `$$` 块内泄 `>`
)


def _run_format_verify_unit_checks(line_list):
    """把单元正文写临时 .md，复用 format_verify 的单元级检查，返回问题字符串列表。

    复用而非复制：与 verify FLayer 同一份逻辑，杜绝「三份分叉」。行号即单元内行号。
    """
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md",
                                     encoding="utf-8", delete=False) as f:
        f.write("\n".join(line_list))
        tmp = f.name
    try:
        problems = []
        for fn in _FV_UNIT_CHECKS:
            res = fn(tmp)              # 任一异常向外冒泡 → fail-closed
            if isinstance(res, tuple):
                msgs = res[0] if res else []
            else:
                msgs = res or []
            for m in msgs:
                problems.append("[F/H-unit] " + m.strip())
        return problems
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ── 翻译语言残留检测（仅译文单元调用；gate_units units-translate 分支 / parity 共用）──
# 2026-09-24 real-analysis-for-graduate-students ch21/22 教训：parity 旧判据
# 「译文哈希 == 源文哈希」只抓逐字未动；把 `> **证明**：` 译掉、标签与证明散文
# 仍整段英文的**半截翻译**因哈希一变即逃逸。本函数给出不看哈希、只看语言的机械判据。
_CJK_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_EN_ITEM_LABEL_RE = re.compile(
    r"\*\*\s*(Theorem|Proposition|Lemma|Corollary|Definition|Remark|Example|Exercise|"
    r"Problem|Solution|Answer|Proof|Notation|Claim)\b[^*\n]*\*\*")
_EN_PROSE_MIN_RUN = 8     # 连续英文词 ≥8 = 成句散文，不可能是术语/人名豁免情形
_EN_PROSE_MIN_CHARS = 40  # 行短于此按专名/括注处理，不判散文残留


def _en_word_run(text):
    """最长连续英文词数（数字/符号/非 ASCII 连字符词均打断）。"""
    best = cur = 0
    for tok in re.split(r"\s+|[,;:.!?()\[\]\"'“”‘’]+", text):
        if not tok:
            continue
        if re.fullmatch(r"[A-Za-z][A-Za-z'-]*", tok):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def english_residues(body):
    """译文单元语言残留检测 → 问题列表（空 = 干净）。

    规则 1（标签）：粗体标签以英文条目/证明词开头（``**Theorem 21.10**`` /
    ``**Proof**``）= 标签未翻译；中英并写 ``**定理 21.10（Theorem 21.10）**``
    因 bold 首词是中文不触发。
    规则 2（散文）：剥掉公式 / HTML / LaTeX 命令后**不含任何 CJK**、长度
    ≥40 且含 ≥8 连续英文词的行 = 未翻译英文散文。含 CJK 的行（中文句内嵌
    Lebesgue 等专名）、纯公式行、纯图行天然豁免。
    """
    problems = []
    m = _EN_ITEM_LABEL_RE.search(body)
    if m:
        problems.append("英文条目/证明标签未翻译：%s" % m.group(0)[:50])
    s = re.sub(r"\$\$[\s\S]*?\$\$", " ", body)
    s = re.sub(r"\$[^$\n]*\$", " ", s)
    s = re.sub(r"<!--[\s\S]*?-->", " ", s)
    hits = []
    for ln in s.split("\n"):
        t = ln.strip().lstrip(">").strip()
        if not t or _CJK_CHAR_RE.search(t):
            continue
        t = re.sub(r"<[^>]+>", " ", t)
        t = re.sub(r"\*\*[^*\n]*\*\*", " ", t)   # bold 标签交由规则 1 判定
        t = re.sub(r"\\[A-Za-z]+\*?", " ", t)
        t = re.sub(r"[{}&\\$_]+", " ", t)
        t = t.strip()
        if len(t) >= _EN_PROSE_MIN_CHARS and _en_word_run(t) >= _EN_PROSE_MIN_RUN:
            hits.append(t[:60])
    if hits:
        problems.append("%d 行未翻译英文散文（例：%r）" % (len(hits), hits[0]))
    return problems


# ── 主入口 ────────────────────────────────────────────────────────────────
def reconcile_images(want, got):
    """(期望图片 basename 集合, 观测集合) → (missing, extra)。

    别名豁免：契约 image 块若为**未标号占位图**（``chNN_unnamed_K.png``），它是
    书源某图的备用裁剪——assign/figure_index 重跑后契约路径可能滞后（图被重新
    命名为标号文件）。故 missing 中的 unnamed 项与 extra 中的标号图一一配对销账，
    配对成功不报缺图/编造（契约是派生物，重建即自愈）；配不上的仍照报。
    """
    missing = sorted(want - got)
    extra = sorted(got - want)
    pool = list(extra)
    kept_missing = []
    for m in missing:
        paired = False
        if "unnamed" in m.lower():
            mtag = m.split("_")[0]  # 章前缀 chNN：只与**同章**标号图配对
            for i, e in enumerate(pool):
                if e.split("_")[0] == mtag:
                    pool.pop(i)
                    paired = True
                    break
        if not paired:
            kept_missing.append(m)
    return kept_missing, pool


_BOLD_LABEL_LINE_RE = re.compile(r"^\*\*([^*\n]+)\*\*")   # 行首条目/习题粗体标签


# ── 第 17 项：行内公式边界粘连（math glue）────────────────────────────────
# Weibel 全书实战（2026-09-24）：单元正文按 OCR 原样留下「散文紧贴 $...$」的
# 粘连（`maps$C_n \to C_{n-1}$are`、`couple$\varepsilon$&`），门控与 verify 都
# 不查，一路流入合并 md。按 `$` 奇偶分段（偶数段=散文）判两侧：EN 散文以字母/
# 数字/`)` 紧贴公式开界或公式闭界紧贴字母/`(`，CN（units-translate）汉字紧贴任一
# 侧，均判粘连。豁免三类：
#   ① 紧贴标点/引号（`$R$-module`、`$X$;`、`“$n$-胞腔”` 的起引号）；
#   ② 序数后缀（`$n$th`、`$(n-1)$st` = 书排 "nth syzygy" 的合法 LaTeX 写法）；
#   ③ 函数式记法（散文词 + 紧跟 `(` 开界的公式：`cone$(f)$`、`Sheaves$(X)$`，
#      Weibel ch1 通篇如此排版）；`$` 奇数行与 `$$` 围栏行不判（另有判据）。
_GLUE_EN_BEFORE = re.compile(r"[A-Za-z0-9\)]$")
_GLUE_EN_AFTER = re.compile(r"[A-Za-z(]")
_GLUE_HAN_BEFORE = re.compile(r"[\u4e00-\u9fff]$")
_GLUE_HAN_AFTER = re.compile(r"[\u4e00-\u9fff]")
_GLUE_ORDINAL = re.compile(r"(?:th|st|nd|rd|Th|St|Nd|Rd)\b")


def math_glue_problems(body, limit=4):
    """行内公式与散文粘连检测 → 问题列表（按行判，行内 `$` 须成对）。"""
    hits = []
    for ln in str(body or "").split("\n"):
        s = ln.strip()
        if not s or "$$" in ln or s.startswith("<!--") or "\\$" in ln:
            continue
        if ln.count("$") % 2:
            continue
        parts = ln.split("$")          # 偶数段=散文，奇数段=数学
        for k in range(0, len(parts) - 1, 2):
            before, math = parts[k], parts[k + 1]
            after = parts[k + 2] if k + 2 < len(parts) else ""
            if math.startswith("("):
                before = ""            # 豁免③ 函数式：coker$(f_n)$
            if _GLUE_ORDINAL.match(after):
                after = ""             # 豁免② 序数：$n$th、$(n-1)$st
            if _GLUE_EN_BEFORE.search(before) or _GLUE_HAN_BEFORE.search(before):
                hits.append((ln, before[-18:] + "|" + math[:14]))
            elif _GLUE_EN_AFTER.match(after) or _GLUE_HAN_AFTER.match(after):
                hits.append((ln, math[-10:] + "|" + after[:18]))
    if not hits:
        return []
    out = ["行内公式与正文粘连（`$...$` 两侧须有空格，标点/引号/序数/函数式紧贴除外）"]
    out += ["  %s" % frag for _, frag in hits[:limit]]
    if len(hits) > limit:
        out.append("  …共 %d 处" % len(hits))
    return ["\n".join(out)]

def label_key_problems(body, ord_keys, ch_num):
    """第 23 项：单元行首**粗体条目/习题标签**里的三级序标必须是本章契约登记的编号。

    现场（Katok ch2 / ch13 / ch17，2026-09-23）：OCR 把上一节末尾的习题接在下一节
    开头散文前面，``build_structure`` 整段挂成 description 节点——契约里既无该习题
    节点，agent 又把题面照书写进单元，于是单元里凭空出现 ``**2.4.3.**`` /
    ``**Exercise 13.3.3\\***`` / ``**习题 13.3.3**``。这类「标签有、契约无」过去只有
    步骤 8 verify 的 P 层看得见，且 P 层只认裸编号（标签式形态漏检，见
    ``verify/verbose_gates``），故在单元门控提前拦住，判据两侧共用
    ``data.book_structure.chapter_ordinals`` 真值。

    只认**行首**粗体标签（条目头的书写形态），且只认首分量等于本章章号的序标：
    正文中间的 ``**Definition 9.6.1**`` 式跨章粗体引用因此不会被误报。
    """
    from lib.util import sec_ordinals
    out = []
    for ln in str(body or "").replace("\r", "").split("\n"):
        m = _BOLD_LABEL_LINE_RE.match(ln.strip())
        if not m:
            continue
        for ordn in sec_ordinals(m.group(1)):
            if ordn.split(".")[0] != str(ch_num) or ordn in (ord_keys or set()):
                continue
            out.append("单元标签 %r 的编号 %s 在本章契约中无对应条目节点——契约漏抽"
                       "（多为跨节被吞的习题），须在分章契约补建条目并同步拆分单元"
                       % (m.group(1).strip(), ordn))
    return out


def unit_source_map(contract):
    """契约 key → 该节点子树全部 text/formula 块的拼接原文（供「假省略声明」闸
    的忠实引用豁免：命中措辞原样见于书源原文 = Tier 1 忠实保留，非掩盖缺失）。
    内容块 = 无 ``key`` 的 dict（同 attach_content 判据）；结构子节点的块同时记在
    其自身 key 与祖先 key 下（父级散文不误伤）。"""
    import collections
    parts = collections.defaultdict(list)

    def _subtree_blocks(node):
        out = []

        def _w(n):
            for blk in n.get("sub_sec") or []:
                if not isinstance(blk, dict):
                    continue
                if "key" in blk:
                    _w(blk)
                elif "text" in blk:
                    out.append(str(blk.get("text") or ""))
                elif "formula" in blk:
                    out.append(str(blk.get("formula") or ""))
        _w(node)
        return out

    def _walk(node, ancestor_texts):
        key = str(node.get("key"))
        mine = list(ancestor_texts)
        for blk in node.get("sub_sec") or []:
            if not isinstance(blk, dict):
                continue
            if "key" in blk:
                _walk(blk, mine)
                mine.extend(_subtree_blocks(blk))
            elif "text" in blk:
                mine.append(str(blk.get("text") or ""))
            elif "formula" in blk:
                mine.append(str(blk.get("formula") or ""))
        parts[key].extend(mine)

    if isinstance(contract, dict):
        _walk(contract, [])
    return {k: " ".join(v) for k, v in parts.items()}


def check_body(utype, name, body, expected_tags=None, allow_extra=None,
               expected_images=None, content_blocks=None, source_text=None,
               key=None):
    """对单个单元正文做「写对」质量校验。返回 (ok, problems)。

    按 verify F 层校验顺序执行全部检测，报告所有错误（不只第一个）。
    ``expected_tags``：契约要求该单元携带的公式编号集合（裸编号字符串列表，
    来自内容化契约 formula.tag）——提供时做**单元级 tag 对账**：缺失（漏写
    编号公式）与多出（编造编号）均判不通过；None = 跳过（调用方无契约上下文）。
    ``expected_images``：契约要求该单元嵌入的图片路径列表（节点 image 块，
    来自 manifest 的 ``images``）——提供时做**单元级图片对账**：缺失（agent
    清噪时把图删掉 = 内容丢失）与多出（编造 / 错位到别的单元）均判不通过；
    None = 跳过。按 basename 比对，容忍相对路径前缀差异。
    ``content_blocks``：契约节点子树内容块数（manifest 的 ``content``）——
    >0 而单元正文为空（只剩标头）= 整体清空，判不通过；0 = 幻影节点允许空；
    None = 跳过。
    ``allow_extra``：可豁免「编造编号」判定的**真实书源编号**集合（裸编号字符串，
    通常来自 ``verify_config.json`` 的 ``formula.known_book``）。契约抽取器只认
    **独立成块**的右缘编号，若某编号在源页与公式**同行内联粘连**（如 ``…dx.(5.15)``）
    则会被契约漏挂 → 单元按 verify（独立源扫描）补写的 ``\\tag`` 会被误判「编造」。
    登记进 known_book 的编号即视为真实、不再判编造（缺失判定不受影响）。
    ``source_text``：该单元所属契约节点的内容块原文（OCR 源文，调用方从分章
    契约拼接）。仅用于「假省略声明」闸的**忠实引用豁免**：命中措辞若本就出现
    在书源原文里（Tier 1 逐句保留的原书措辞，如 Leinster 6.3.11 "a little
    cardinal arithmetic, omitted here"），不算掩盖缺失；None / 未命中 → 照常
    判 FAIL（fail-closed：无契约上下文时不放行）。
    ``key``：该单元的契约条目键（如 ``9.1.5``）。仅用于「幻影习题条目」闸判定
    编号公式 / 插图是否属于**别的小节**；None = 该子判据跳过（句中起始与零内容块
    两项不依赖 key，仍生效）。
    """
    if utype not in ("item", "desc", "exercise"):
        return True, []
    lines = body.splitlines(keepends=True)
    while lines and lines[0].startswith("<!--"):
        lines.pop(0)
    body_clean = "".join(lines)

    all_problems = []
    line_list = body_clean.splitlines()

    # ── F 层：按 verify 校验顺序 ──────────────────────────────────────

    # exercise 单元的 $...$ 分隔符序列因 OCR 交错常有破损，
    # _strip_math_and_code 无法正确判断内外，跳过依赖它的 F 层检查
    if utype != "exercise":
        # F1) 裸 Unicode 箭头（→ ⇒ ↔ 等在 $...$ 外）
        errs = find_raw_arrow_errors(line_list)
        if errs:
            all_problems.extend(e.strip() for e in errs)

        # F2) 裸 LaTeX 命令（\mathbf \delta 等在 $...$ 外）
        errs = find_naked_command_errors(line_list)
        if errs:
            all_problems.extend(e.strip() for e in errs)

        # F3) $ 吞噬结构性前缀（blockquote/list 标记被吃进公式）
        errs = find_swallowed_prefix_errors(line_list)
        if errs:
            all_problems.extend(e.strip() for e in errs)

        # F4) 裸数学 / 裸函数调用（希腊字母 α β ε、函数 F(X) D(A) 等在 $...$ 外）
        errs = find_bare_math_errors(line_list)
        if errs:
            all_problems.extend(e.strip() for e in errs)

        # F5) $ 奇偶配对（奇数 = 未闭合，破坏后续所有公式）
        dollar_count = _count_inline_dollars(line_list)
        if dollar_count % 2 != 0:
            all_problems.append(f"inline $ 数量为奇数（{dollar_count}）——存在未配对的 $，破坏后续所有公式")

        # F6) $$ 闭合（display math 未关闭）
        errs = check_display_math_closure(line_list)
        if errs:
            all_problems.extend(errs)

    # F7) 围栏形态（单行 $$ 块 / $$ 附着内容 / 缺空行或缺空 > 行）
    # —— 对 exercise 单元同样执行：这些是纯行形态检测，不依赖 $ 内外判断
    errs = _fence_issues(line_list)
    if errs:
        all_problems.extend(errs)

    # F7e) \tag 在数学模式外：对全单元散文视图查（_prose_text 按跨行状态跳过
    # $$ 块内行，单行逐条看会漏块上下文误报）
    joined = _prose_text(line_list)  # 散文视图——F7e 与 OCR 残留检测共用
    if re.search(r"\\tag\s*\{", joined):
        all_problems.append(
            "\\tag 出现在 $$ 块外（编号必须随公式写在 $$ 块内，不得散落正文）")

    # F8) 展示围栏损伤（转义 `\$\$` / 围栏重复 / `$$` 块内 body 被 `$...$` 包裹）
    # —— 纯行形态检测，对 exercise 单元同样执行；三类都非法 KaTeX，
    # 且都由 verify format_verify Pattern 11 机械修复
    errs = find_display_fence_damage_errors(line_list)
    if errs:
        all_problems.extend(e.strip() for e in errs)

    # ── P 层 ──────────────────────────────────────────────────────────

    # P1) 证明过长（>700 字符无步骤枚举）
    errs = check_verbose_proofs(line_list)
    if errs:
        all_problems.extend(e.strip() for e in errs)

    # ── H/G 层 ────────────────────────────────────────────────────────

    # H1) 结构标签 + G1) example blockquote
    if utype == "item":
        has_bold = bool(TOP_LEVEL_HEADER_RE.search(body_clean)) or bool(re.search(r"\*\*", body_clean))
        if not has_bold:
            all_problems.append("编号项单元缺粗体标签（**name** 或 **定义/定理/…**）")
        if re.match(r"^例", (name or "")) or re.match(r"^Example", (name or ""), re.I):
            errs = check_example_blockquote_lines(line_list)
            if errs:
                all_problems.extend(e.strip() for e in errs)

    # ── 补充：OCR 残留模式 ────────────────────────────────────────────
    # 只对数学模式外的散文段匹配（joined 已由 _prose_text 剥除 $...$ / $$ 块），
    # 否则 `\boldsymbol{\Gamma} f` 这类合法显示公式被误报。
    for pat, msg in _OCR_FORMULA_PATTERNS:
        if re.search(pat, joined):
            all_problems.append(msg)

    # ── 补充：内容审阅类残留（writing-rules「内容清理与保真」的机械落实）──
    # 11a) QED 结尾框「口/□」独立行（数学模式外逐行查，先剥 `>` 前缀再判围栏）
    in_display = False
    for ln in line_list:
        content = re.sub(r"^\s*>\s?", "", ln)
        s = content.strip()
        if s == "$$" or (s.startswith("$$") and not s.endswith("$$")):
            in_display = not in_display
            continue
        if s.startswith("$$") and s.endswith("$$") and len(s) > 4:
            continue
        if in_display:
            continue
        if _QED_BOX_LINE_RE.match(s):
            all_problems.append(
                "QED 结尾框「%s」残留（OCR 噪声，证明结尾须剔除）" % s)
            break

    # 11b) OCR 乱码重复片段（同一 ≥12 字符片段同行连续重复 = OCR 抽风复制）
    # 注意：必须在**原始行**（math 未剥除）上查。若先剥 $...$ 再查，合法并列句式
    # （如 "For n=2 … is a solution; note … / For n≥3 … is a solution; note …"）会坍缩成
    # 相同散文残桩被误报为重复。原始行里两段夹着不同数学，不会形成连续 12+ 字符重复，
    # 故改用 line_list（保留 math），既保留对真实 OCR 抽风复制的捕获，又避免误报。
    # 🔴 **数学感知强化（2026-09-09）**：PDE 文本里大量「合法数学重复」会被
    #   `(.{12,}?)\1+` 误伤，例如乘积空间 `\Omega\times\mathbb R\times\mathbb R^n`、
    #   不等式链 `w(x_0)\leq … \leq w(x_0)\leq …`、双侧估计
    #   `\varphi(x_0)…\leq \varphi(x)\leq \varphi(x_0)…`。这些重复单元都含 LaTeX
    #   命令（反斜杠）。故：**重复单元含 `\` 一律视为合法数学重复跳过**；仅对非数学
    #   的普通文本/乱码重复报警。本数据集全树 11b 命中仅 6 处，全部是此类合法数学，
    #   该强化后 6 处均放行，真实（无反斜杠的）OCR 乱码仍会被捕获。
    # 🔴 **标题豁免（2026-09-24）**：行首 `**…**` 粗体 run-in 标签是契约照搬的
    #   印刷标题，Vakil 等书常见「并列同义词」标题（如 "General fibers, generic
    #   fibers, generically finite morphisms"）会形成合法的连续重复，非 OCR 抽风。
    #   故扫描前先剥离开头的粗体标签，仅对标签之后的正文散文查重（同行正文里的
    #   真·重复仍能捕获）。
    for pl in line_list:
        pl_scan = re.sub(r"^\s*(?:>\s*)?\*\*.*?\*\*", "", pl)
        m_dup = re.search(r"(.{12,}?)\1+", pl_scan)
        if not m_dup:
            continue
        unit = m_dup.group(1)
        # 重复单元含 LaTeX 命令（反斜杠）→ 数学符号的合法重复，跳过
        if "\\" in unit:
            continue
        # 重复单元含数学定界符（()|{}^_[]<>=）→ 合法公式片段（如
        # |P(0)|+|DP(0)|+|D^2P(0)|、Ω×ℝ×ℝⁿ、不等式链），非 OCR 抽风，跳过
        if any(c in unit for c in "()|{}^_[]<>"):
            continue
        all_problems.append(
            "疑似 OCR 乱码重复片段：「%s…」连续重复（须清理）"
            % unit[:20])
        break

    # 11c) 单元内私造标题行（标题应为独立 section 单元）
    if utype in ("item", "desc", "exercise"):
        for ln in line_list:
            if _HEADING_LINE_RE.match(ln):
                all_problems.append(
                    "单元内出现标题行（%r）——标题应为独立 section 单元，"
                    "不得并入条目（防自造层级）" % ln.strip()[:30])
                break

    # ── F/H 层：块引用 / 例 / 证明 / 列表结构（复用 format_verify，单元级左移）──
    # verify F 层原只在合并后的整章 md 才查这些 intra-unit 结构；现前移到单元门控，
    # 让「重修单元」时即暴露，而非漏到合并后才被 verify 抓（合并脚本不负责重排正文）。
    # 文档级专属（`---`/标题上下文）检查不在此列，孤立单元查会误报。
    errs = _run_format_verify_unit_checks(line_list)
    if errs:
        all_problems.extend(errs)

    # 12) 单元级公式序标对账（契约 tag 为唯一真值；Q 层是章级末步，单元门控
    #     必须提前拦「漏写编号公式」与「编造编号」）
    if expected_tags is not None:
        want = list(expected_tags)
        allow = set(str(x) for x in (allow_extra or []))
        got = re.findall(r"\\tag\{([^}]*)\}", body_clean)
        missing = [t for t in want if t not in got]
        extra = [t for t in got if t not in want and t not in allow]
        if missing:
            all_problems.append(
                "缺编号公式 \\tag{%s}（契约要求该单元携带；漏写 = 书源编号公式"
                "缺失）" % "}{".join(missing[:6])
                + (" 等共 %d 个" % len(missing) if len(missing) > 6 else ""))
        if extra:
            all_problems.append(
                "编造编号 \\tag{%s}（契约中不存在；书无此编号严禁编造）"
                % "}{".join(extra[:6])
                + (" 等共 %d 个" % len(extra) if len(extra) > 6 else ""))

    # 13) 单元级图片对账（契约节点 image 块为真值；按 basename 比对）——
    #     曾发生：步骤 5 agent 把带 OCR 噪声 alt 的图块连同习题正文一起删光，
    #     tag 有对账、图片没有 → 一路绿灯流入拼接。缺 = 内容丢失，多 = 编造/错位。
    if expected_images is not None:
        def _bn(p):
            return str(p).replace("\\", "/").rstrip("/").split("/")[-1]
        want = set(_bn(p) for p in expected_images if p)
        got = set(_bn(m) for m in
                  re.findall(r'<img[^>]+src="([^"]+)"', body_clean))
        missing, extra_imgs = reconcile_images(want, got)
        if missing:
            all_problems.append(
                "缺契约图片 %s（契约要求本单元嵌入；漏图 = 内容丢失，"
                "须按 V-E 规则以 <img> 块补回）" % "、".join(missing[:6])
                + (" 等共 %d 张" % len(missing) if len(missing) > 6 else ""))
        if extra_imgs:
            all_problems.append(
                "嵌入了契约本单元之外的图片 %s（文件名须来自契约 image 块；"
                "放错单元 = 按契约归属移到正确单元）" % "、".join(extra_imgs[:6]))

    # 14) 空正文闸：契约节点有内容块而单元正文为空 = 整体清空（习题/条目单元
    #     必须完整收录规则的死命令兜底；幻影节点 content_blocks==0 不受影响）
    if content_blocks and not body_clean.strip():
        all_problems.append(
            "单元正文为空但契约节点含 %d 个内容块（text/formula/image）——"
            "编号项/习题单元须完整收录，禁止清空正文" % content_blocks)

    # 15) 假省略声明闸（见 ``_OMISSION_CLAIM_RE`` 注释）：单元正文谎称习题被省略 /
    #     归入综合习题集 = 题面缺失被措辞掩盖，一律不通过。
    #     豁免两条：① 命中措辞原样出现在该单元契约节点的书源原文里 = Tier 1
    #        忠实保留的原书措辞（如 Leinster "cardinal arithmetic, omitted here"），
    #        不是 agent 掩盖缺失；无 source_text 上下文则不豁免（fail-closed）。
    #        ② 散文单元（desc/section/proof…）且该句不含内容指向词
    #        （``_OMISSION_ANCHOR_RE``）= 「omit」的数学用法而非省略声明；
    #        exercise / item 单元**不适用**此豁免（正文按规则必完整）。
    m_om = _OMISSION_CLAIM_RE.search(body_clean)
    if m_om:
        _norm = lambda s: " ".join(str(s).split()).casefold()
        _phrase = _norm(m_om.group(0))
        _src = _norm(source_text or "")
        _ctx = body_clean[max(0, m_om.start() - _OMISSION_CTX):
                          m_om.end() + _OMISSION_CTX]
        _prose = utype not in ("exercise", "item")
        if _phrase not in _src and not (
                _prose and not _OMISSION_ANCHOR_RE.search(_ctx)):
            all_problems.append(
                "正文出现假省略声明「%s」——能生成单元的习题节点契约里必为 "
                "consolidated=false（章末集中块不生成单元），题面须按契约 text/formula "
                "块完整复原，禁止用「省略」措辞掩盖缺失" % m_om.group(0))

    # 16) 幻影习题条目闸（契约切片缺陷，见 ``_LABEL_RESIDUE_RE`` 注释）：单元本身
    #     措辞再干净也不放行——题面/正文归属错在契约层，须契约 + 单元同步修。
    if utype == "exercise":
        all_problems.extend(phantom_exercise_problems(
            name, content_blocks, expected_tags, expected_images, key,
            body=body_clean))

    # 17) 行内公式边界粘连（Weibel ch8 2026-09-24：OCR 原样「maps$C_n\to C_{n-1}$are」
    #     式粘连逃过全部既有检测流入合并 md；纯行形态判据，exercise 单元同样执行）
    all_problems.extend(math_glue_problems(body_clean))

    return (len(all_problems) == 0, all_problems)
