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
from page_json import PageJson

import os, sys

import json, re
from lib.regexlib import SEP_TIGHT
from item_dedup import dedup_items

# ---------------------------------------------------------------------------
# ENGLISH three-level extraction (LABEL-FIRST dots):  Label C.S.N
# For English textbooks that number entries as `Remark 1.1.1`,
# `Definition 2.3.4`, `Theorem 3.2.1`, ...  (three numeric components, the
# label word precedes the number).  Differs from the CN three-level path
# (extract_items, type 3) in TWO critical ways:
#   1. The label word is REQUIRED immediately before the number, so bare
#      figure captions (`FIGURE 1.1.1`) and parenthesised formula refs
#      (`(1.1.1)`) are NEVER captured as items — they share the same C.S.N
#      numbering space as the entries in books like Lasota & Mackey, and the
#      CN path's bare-number regex collides with them (key `1.1-1` overlaps
#      both `Remark 1.1.1` and `FIGURE 1.1.1`).
#   2. Keys are emitted WITH the label and DOTS (`Remark 1.1.1`), matching the
#      written `**Remark 1.1.1**` heading, so the B-layer / data_provider match
#      by (comps, label) separator-agnostically.
# ---------------------------------------------------------------------------
EN3_LABELS = ["Definition", "Theorem", "Lemma", "Proposition", "Corollary",
              "Example", "Remark", "Exercise", "Assertion", "Conjecture", "Fact"]
# OCR 易错变体归一：Definition 在本OCR中常被识为 `Defnition`（漏 i，全书 22 处 /
# 20 页），必须识别并归一为 Definition，否则这些定义条目整条漏抽（见
# §2.2 的 Definition 2.2.3 / 2.2.4 被识为 Defnition 而漏网）。Definition 还可能
# 被识为 Defintion（i/n 转置），一并覆盖。
EN3_LABEL_CANON = {
    'definition': 'Definition', 'defnition': 'Definition', 'defintion': 'Definition',
    'theorem': 'Theorem', 'lemma': 'Lemma', 'proposition': 'Proposition',
    'proposltlon': 'Proposition',
    'corollary': 'Corollary', 'example': 'Example', 'remark': 'Remark',
    'exercise': 'Exercise', 'assertion': 'Assertion', 'conjecture': 'Conjecture',
    'fact': 'Fact',
    # OCR 变体与 Leinster 体例扩展（2026-08-30）：Deinition=Definition 漏 i；
    # Construction/Warning/Notation/Note 归并为评注（本 skill 复合键空间只认
    # 8 类规范标签，非规范标签会导致契约/源侧复合键永不相交、A 层 md 键不匹配）。
    'deinition': 'Definition',
    'construction': 'Remark', 'warning': 'Remark', 'notation': 'Remark',
    'note': 'Remark',
    # 🔴 Weibel 等书 OCR 把英文标签词咬成「尾部碎片」（漏掉首部、只留尾 4+ 字母）：
    #   cise     = Exercise（"Exer▢cise" 首部丢失，留 cise）
    #   orem     = Theorem（"The▢orem"）
    #   emma     = Lemma（"Le▢mma"）
    #   llary    = Corollary（"Coro▢llary"）
    #   mple     = Example（"Exa▢mple"）；ples/xample/examp 同理（Examples/例截断）
    #   mark     = Remark（"Re▢mark"）；remak/remarl 同理
    #   tion     = Definition（"Defini▢tion" 尾 4 字母；Proposition 也截成 tion，
    #             本书 §1 中 tion 多为 Definition，故归一 Definition，个别 Proposition
    #             由 step5 agent 据 OCR 正文校正）
    #   sition   = Proposition（"Proposi▢tion" 尾 6 字母，区别于 Definition 的 tion）
    # 均带 \b 词边界（EN3_LAB_RE 外层 \b 首界 + (?![A-Za-z]) 尾界），不会命中
    # exercise/lemma 等中词（mid-word 无边界），故不加错。
    'cise': 'Exercise', 'orem': 'Theorem', 'emma': 'Lemma', 'llary': 'Corollary',
    'mple': 'Example', 'ples': 'Example', 'xample': 'Example', 'examp': 'Example',
    'mark': 'Remark', 'remak': 'Remark', 'remarl': 'Remark',
    'tion': 'Definition', 'sition': 'Proposition', 'oposition': 'Proposition',
}
EN3_LABEL_ALT = '|'.join([
    '(?:Definition|Defnition|Defintion|Deinition|tion)', 'Theorem', 'Lemma',
    # OCR 常把 i 误读为 l（PROPOslTloN），加模糊分支容忍
    '(?:Proposition|Propos[l1]t[l1]on|sition|oposition)',
    'Corollary', 'Example', 'Remark',
    'Exercise', 'Assertion', 'Conjecture', 'Fact',
    # Leinster 体例：Construction/Warning/Notation 是真实印刷条头（canon 到
    # Remark）；Notation 必须排在 Note 之前（正则交替按序匹配，长词优先）。
    'Construction', 'Warning', 'Notation', 'Note',
    # 🔴 Weibel OCR 尾截变体（见 EN3_LABEL_CANON 注释）；rick/exes/ions 不在此列
    # —— 它们分别是 Sign Trick / Total Complexes / Truncations 的尾部碎片，属
    # 「无标准 skill 类型的命名结果」，易与 Remark/Exercise 混淆，改由
    # manual_overrides_chN.json 显式回填（标签取标准类型 Remark），不污染共享正则。
    '(?:cise)', '(?:orem)', '(?:emma)', '(?:llary)',
    '(?:mple|ples|xample|examp)', '(?:mark|remak|remarl)',
])
EN3_LAB_RE = re.compile(
    # 🔴 尾界用 `(?![A-Za-z])` 而非 `\b`：OCR 常把标签与编号粘连成
    # `PROPOsITiON2.7.2`（无空格），而 `\b` 在「字母→数字」之间永不成立
    # （两者都是 \w），粘连形态整条漏抽；负向前瞻既容忍粘连又排除
    # `Propositional` 这类单词延伸。
    r'\b(' + EN3_LABEL_ALT + r')s?(?![A-Za-z])\s*(?:\([^)]*\))?\s*'
    r'(\d+)\s*' + SEP_TIGHT + r'\s*(\d+)\s*' + SEP_TIGHT + r'\s*(\d+)',
    re.IGNORECASE,
)


def _EN3_REST_OK(txt, m):
    """统一条头判别（2026-08-30）：编号后允许①空②句点③括号标题
    （可连续多组，如 "Examples 1.1.8 (Categories...)(a) ..."）④大写开头正文
    （Leinster 体例无标点直接接正文）。拒绝：纯标点尾（断行引用尾
    "Example 1.2.8."）、括号包裹引用（"Definition 5.1.1)"）、括号后小写延续
    （"Remark 5.1.2(a) that they..." 式行首引用）。"""
    rest = txt[m.end():].lstrip()
    if rest and not re.search(r"[A-Za-z]", rest):
        return False
    while True:
        m2 = re.match(r"\(([^)]*)\)\s*", rest)
        if not m2:
            break
        rest = rest[m2.end():]
    if rest and not (rest[0] == "." or rest[0] == "\u3002" or rest[0].isupper()):
        return False
    return True


# 章级两级条头（chapter==0 的 Introduction，如 Leinster "Example 0.1"）：三级书
# 的第 0 章条目只有两个数字分量。负向前瞻排除三级号（"1.1.3" 不被当作 "1.1"）。
EN3_TWO_RE = re.compile(
    r'\b(' + EN3_LABEL_ALT + r')s?(?![A-Za-z])\s*(?:\([^)]*\))?\s*'
    r'([0Oo])\s*' + SEP_TIGHT + r'\s*(\d+)(?!\s*' + SEP_TIGHT + r'\s*\d)',
    re.IGNORECASE)

# 附录字母条头（如 Leinster 附录 "Lemma A.1"）：首分量为字母。仅在块首锚定下
# 发射（与主正则同锚定纪律），字母位过滤只认 A（附录 A）。
# 🔴 第三级可选（2026-09-01 修复 Weibel 附录全漏）：Weibel Appendix A 的条目印成
# 三级 letter 号 "Exercise A.1.1" / "Definition A.4.2" / "Example A.1.8"（A.N.M），
# 旧正则的 (?![.\d]) 尾界对 "A.1.1" 直接拒绝 → 附录含练习在内的全部条目漏抽。
# 改为「可选第三级」：两级 "Lemma A.1"（Leinster）仍命中（group(4)=None），
# 三级 "A.1.1" 新增命中；_emit_app 据 group(4) 是否为 None 决定键形 A.N / A.N.M。
EN3_APP_RE = re.compile(
    r'\b(' + EN3_LABEL_ALT + r')s?(?![A-Za-z])\s*'
    r'([A-Za-z])\s*' + SEP_TIGHT + r'\s*(\d+)'
    r'(?:\s*' + SEP_TIGHT + r'\s*(\d+))?',
    re.IGNORECASE)
# 🔴 Weibel 附录「无标签定义」（印成 "A.1.4 Small categories" / "A.1.5 A
# morphism…"：粗体号 + 词目，省略 Definition 词）。块首锚定 + 号后须接大写标题
# 词（排除 "(see A.1.5)" 之类交叉引用），label 统归 Definition。仅字母位 A 生效。
EN3_APP_BARE_RE = re.compile(
    r'\b([A-Za-z])\s*' + SEP_TIGHT + r'\s*(\d+)\s*' + SEP_TIGHT + r'\s*(\d+)'
    r'(?=\s+[A-Z])',
    re.IGNORECASE)
# 标题在前、号在中间的的无标签定义（Weibel 附录主体体例，如
# "Opposite Category A.1.7 Every category…" / "Hom and Tensor Product A.2.1 Let R…"
# / "Faithful Functors A.2.3 A functor…" / "Small categories A.1.4 A category…"）：
# 1–5 个词目（首词大写、排除标签词与散文起手词 In/See/Section/Chapter/The/We/This）
# + 空白 + A.N.M + 空白 + 大写（定义正文）。块首锚定（^）天然排除 "(see A.N.M)"
# 之类交叉引用；号在中间（后接大写正文）而非块尾。
EN3_APP_BARE_MID_RE = re.compile(
    r'^(?!(?:Definition|Theorem|Lemma|Corollary|Proposition|Example|Examples|'
    r'Remark|Exercise|Assertion|Conjecture|Fact|Construction|Warning|Notation|'
    r'Note|In|See|Section|Chapter|The|We|This)\b)'
    r'(?:[A-Z][a-zA-Z]*(?:\s+[a-zA-Z]+){0,4})\s+'
    r'([A-Za-z])\s*' + SEP_TIGHT + r'\s*(\d+)\s*' + SEP_TIGHT + r'\s*(\d+)'
    r'(?=\s+[A-Z])',
    re.IGNORECASE)


def extract_items_en3(extract_dir, chapter, start, end, want_examples=True):
    """Extract EN three-level `Label C.S.N` entries for one chapter.

    `chapter` filters by the FIRST numeric component (the chapter number), so a
    stray `Remark 2.3.4` inside chapter 1 is dropped.  Returns items shaped like
    the other extractors: {key, label, page, text}.
    """
    # 块首装饰字符（Brin & Stuck 用 * 标记难题："*Exercise 1.2.4 ..."），
    # 不剥离会被「块首判定」整条漏抽；括号 ( 不在白名单——"(Exercise 2.1.3)"
    # 是交叉引用，必须保持拒绝。
    _DECOR = "*\u00b7\u2022\u2192'\u201d\u201c\""

    def _emit(txt, m, p):
        # 标题判别：真条目头在 C.S.N 后是句点（或「(定理名/人名)」括注再句点）。
        # OCR 断行会把 'by Proposition' 留在上块，使行首引用伪装成条目头
        # （实测：'PROPOSITION 2.1.2, Zorn's lemma...' / 'LEMMA 6.1.1 are
        # satisfied...' / 'PROPOSITION 9.2.1(6), H(...'）——按后随标点拒绝。
        if not _EN3_REST_OK(txt, m):
            return
        label = EN3_LABEL_CANON.get(m.group(1).lower(), m.group(1).title())
        if label == "Example" and not want_examples:
            return
        c, s, n = int(m.group(2)), int(m.group(3)), int(m.group(4))
        if c != chapter:
            return
        # Sanity bounds (avoid OCR garbage like 1.99.1).
        if s > 20 or n > 60:
            return
        key = f"{label} {c}.{s}.{n}"
        snippet = txt[max(0, m.start() - 5):m.end() + 90].replace("\n", " ")
        items.append({"key": key, "label": label, "page": p, "text": snippet})

    def _rest_ok(txt, m):
        return _EN3_REST_OK(txt, m)

    def _emit_two(txt, m, p):
        # chapter 0（Introduction）两级条目："Example 0.1"。仅 chapter==0 时启用。
        if not _rest_ok(txt, m):
            return
        label = EN3_LABEL_CANON.get(m.group(1).lower(), m.group(1).title())
        if label == "Example" and not want_examples:
            return
        c = 0 if m.group(2) in ('O', 'o') else int(m.group(2))
        n = int(m.group(3))
        if chapter != 0 or c != 0 or n > 60:
            return
        key = f"{label} {c}.{n}"
        snippet = txt[max(0, m.start() - 5):m.end() + 90].replace("\n", " ")
        items.append({"key": key, "label": label, "page": p, "text": snippet})

    def _emit_app(txt, m, p):
        # 附录字母条目："Lemma A.1" / "Exercise A.1.1"（三级可选，Weibel）。
        # 字母位只认 A（附录 A 体例）。
        if not _rest_ok(txt, m):
            return
        if (m.group(2) or "").upper() != "A":
            return
        label = EN3_LABEL_CANON.get(m.group(1).lower(), m.group(1).title())
        if label == "Example" and not want_examples:
            return
        letter = m.group(2).upper()
        n = m.group(3)
        mpart = m.group(4)
        key = f"{label} {letter}.{n}" + (f".{mpart}" if mpart else "")
        snippet = txt[max(0, m.start() - 5):m.end() + 90].replace("\n", " ")
        items.append({"key": key, "label": label, "page": p, "text": snippet})

    def _emit_app_bare(txt, m, p, tail=False):
        # 附录无标签定义（"A.1.4 Small categories" / "Small categories A.1.4"）：
        # 粗体号 + 词目、省略 Definition 词，Weibel 附录惯例归 Definition。仅 A 生效。
        letter = (m.group(1) or "").upper()
        if letter != "A":
            return
        n = m.group(2)
        mpart = m.group(3)
        if not tail:
            # 号后须接大写标题词（_EN3_REST_OK 的 rest 起点判定）：
            if not _EN3_REST_OK(txt, m):
                return
        label = "Definition"
        key = f"{label} {letter}.{n}.{mpart}"
        snippet = txt[max(0, m.start() - 5):m.end() + 90].replace("\n", " ")
        items.append({"key": key, "label": label, "page": p, "text": snippet})

    items = []
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as f:
            data = PageJson.load(os.path.join(extract_dir, f"page_{p:03d}.json")).data
        blocks = [t.get("text", "") for t in data.get("text", [])]
        prev = ""
        for txt in blocks:
            if not txt:
                continue
            for m in EN3_LAB_RE.finditer(txt):
                # Heading vs prose reference: a real entry heading starts the
                # text block (e.g. "REMARK 1.1.1. Map (1.1.1) ...").  A
                # cross-reference like "by Lemma 11.26" / "satisfy Theorem 2.3"
                # sits mid-block and is skipped.
                if txt[:m.start()].strip(_DECOR + " \t"):
                    continue
                _emit(txt, m, p)
            # 章级两级（chapter 0）与附录字母（A.N）扫描：同一块首锚定纪律。
            if chapter == 0:
                for m in EN3_TWO_RE.finditer(txt):
                    if txt[:m.start()].strip(_DECOR + " \t"):
                        continue
                    _emit_two(txt, m, p)
            for m in EN3_APP_RE.finditer(txt):
                if txt[:m.start()].strip(_DECOR + " \t"):
                    continue
                _emit_app(txt, m, p)
            # 🔴 Weibel 附录无标签定义（三级 letter 号，省略 Definition 词）：
            # 仅在附录章（字母位 A）生效，避免误伤正文章（其首分量为数字）。
            if chapter == "A":
                for m in EN3_APP_BARE_RE.finditer(txt):
                    if txt[:m.start()].strip(_DECOR + " \t"):
                        continue
                    _emit_app_bare(txt, m, p, tail=False)
                for m in EN3_APP_BARE_MID_RE.finditer(txt):
                    # 块首锚定（^）已由正则保证；号后接大写正文，走 rest 判别。
                    _emit_app_bare(txt, m, p, tail=False)
            # 跨块连字标签：OCR 把 "Proposi-" 留在上块末尾、下块以
            # "tion 4.10.3." 开头（实测 p112→p113 Proposition 4.10.3 整条漏抽）。
            # 取上块尾部字母段与下块拼接（有连字则去连字直拼）后锚定重试。
            tailm = re.search(r"([A-Za-z]{2,})([-\u00ad])?\s*$", prev)
            if tailm:
                frag = tailm.group(1)
                # 2026-08-30 Leinster 实测：裸号习题块（"4.2.3  One way..."）的上一块
                # 恰以 "...Yoneda lemma" 结尾时，拼接出 "lemma 4.2.3" 幻影条头。
                # 真印刷条头标签词首字母大写（或全大写）；纯小写 fragment 拒绝。
                if frag[0].isupper() or frag.isupper():
                    joined = (frag + txt.lstrip()) if tailm.group(2) \
                        else (frag + " " + txt.lstrip())
                    jm = EN3_LAB_RE.match(joined)
                    if jm:
                        _emit(joined, jm, p)
            prev = txt or prev
    # Collapse reference mentions but KEEP two genuinely different items that
    # share a (label, number) — e.g. a source book printing the same number
    # twice (a printing off-by-one, like Lasota & Mackey's Proposition 12.8.3
    # appearing on two pages).  Genuine headings are already pre-filtered above
    # (only block-start matches survive), so any same-key collision with a
    # different heading text is a distinct item.
    out = dedup_items(items)
    return out


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description="Extract EN three-level Label C.S.N items.")
    ap.add_argument("pos", nargs="*", help="<ch> <start> <end> <extract_dir>")
    ns = ap.parse_args()
    if len(ns.pos) < 4:
        ap.error("needs: <ch> <start> <end> <extract_dir>")
    ch, start, end, extract_dir = int(ns.pos[0]), int(ns.pos[1]), int(ns.pos[2]), ns.pos[3]
    items = extract_items_en3(extract_dir, ch, start, end)
    print(f"=== Ch{ch} EN3 ITEMS ({len(items)}) ===")
    for it in items:
        print(f"{it['key']:18s} p{it['page']:3d}  {it['text'][:80]}")
