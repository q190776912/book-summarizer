"""extract_items_hum.py — Humphreys《Introduction to Lie Algebras and
Representation Theory》(GTM 9) 编号项抽取器。

config_setting 规则5 增量扩展（ORDINAL_HUM = 12）。本书体例（全书实测）：

  - 章:      Chapter I..VII（文件级，# 第N章）
  - 节:      全书全局单序标 §1..§27，原书印裸 "9. Axiomatics" / "12. Construction
             of root systems and automorphisms"（无 § 前缀）——节头由
             scan_skeleton.SEC_GLOBAL_PLAIN 分支进骨架，本抽取器只为条目定位
             跟踪当前节号。
  - 小节:    "7.2. Classification of irreducible modules"（N.M），不作契约层级。
  - 条目头:  两类——
             (a) 裸标签   "Lemma." / "Theorem." / "Corollary." /
                 "Theorem (Cartan's Criterion)." / "Remark."
             (b) 字母号   "Lemma A." / "Corollary A (Lie's Theorem)." /
                 "Proposition B." / "Lemma C.Let ..."（点后粘连）
             书中引用它们时写 "Lemma 7.2"（§7.2 的那条引理）/ "Lemma 10.2B"
             （§10.2 的引理 B）——编号=所在小节+字母，不在条目头上印数字。
  - 例:      仅 §22.4 有编号例 "Example 1." / "Example 2."。
  - 图表:    "Table 1." / "Table 2.Highest long and short roots" /
             "Figure 1. (m even)"——按小节重编（§9.4 与 §11.4 各有 Table 1），
             引用带节限定 "Table 1 (11.4)"。
  - 习题:    每节末 "Exercises" 标题 + 裸编号 "1." "2." …——集中习题块，
             按 writing-rules V-I 一律省略、不入契约；抽取器进入闩锁跳过。

键格式（唯一化 + 故意不可被 B 层数字解析，理由见 verify_config.ORDINAL_HUM）：
  字母号条目  "Lemma §10.2B"
  裸标签条目  "Lemma §7.2"        （= 书中引用形态的定位语义）
  编号例      "Example §22.4-1"
  表 / 图     "Table §11.4-1" / "Figure §9.3-1"

md 侧标签照原书印刷：**Lemma A** / **Lemma**（writing-rules 编号规范：
书真省号时不造号）。键与 md 标签不逐字相等属预期：两者都不可被 B 层解析，
配对审计由 D 层 + 源侧回填 + 计数审计兜底（与 Ross/Karlin 字母项同路径）。

用法:
  python extract_items_hum.py <extract_dir> <start> <end>
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
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from page_json import PageJson
import scan_skeleton as _ss

# 页眉带下限：本书页眉 y≈44-51（奇数页为「当前小节名+粘连页码」，偶数页为
# 章名词粘页码）；真实节/小节头若起始于新页顶，落在 y≈80-95（实测 81/83/84/
# 86/88/90），绝不下探到 70 以下。故阈值取 70：既滤净页眉，又不误杀页顶标题。
_HEADER_Y = 70.0

_LAB_SING = {
    'Theorems': 'Theorem', 'Theorem': 'Theorem',
    'Propositions': 'Proposition', 'Proposition': 'Proposition',
    'Corollaries': 'Corollary', 'Corollary': 'Corollary',
    'Lemmas': 'Lemma', 'Lemma': 'Lemma',
    'Examples': 'Example', 'Example': 'Example',
}

# 字母号条目头："Corollary A (Lie's Theorem). Let L be..." / "Lemma C.Let Φ..."
# 锚定行首；字母后必须紧跟可选名称括号再句点 —— "Lemma B of (15.2), H is..."
# 这类块首交叉引用因字母后是 " of" 不带句点而被拒绝。
_LETTERED_RE = re.compile(
    r'^(Theorems?|Propositions?|Corollar(?:y|ies)|Lemmas?|Examples?)(?![A-Za-z])'
    r'\s+\(?([A-Z])\)?\s*(?:\(([^)]{0,50})\))?\s*\.\s*(.*)$')

# 裸标签条目头："Lemma. If v e Va, then..." / "Theorem (Cartan's Criterion). Let L..."
# / "Theorem.LetVbeanirreduciblemodule..."（OCR 点后粘连）/ "Corollary'. Let..."
#（撇号变体，书中引用作 "Corollary' in (23.2)"）。
_BARE_RE = re.compile(
    r'^(Theorem|Proposition|Corollary|Lemma|Remark)(?![A-Za-z])(\')?'
    r'\s*(?:\(([^)]{0,55})\))?\s*\.\s*(.*)$')

# 编号例："Example 1. L = sI(3, F), ..."
_EXNUM_RE = re.compile(
    r'^Examples?(?![A-Za-z])\s+(\d{1,2})\s*[.:]\s*(.*)$')

# 表/图头："Table 1." / "Table 2.Highest long and short roots" / "Figure 1. (m even)"
# 号后只允许「点号 / 空白 / 行尾」——"(Figure 1, for type A2.)" 这类句中引用
# 碎片（逗号紧跟号）据此拒绝；"Table 1 (11.4)." 带节限定括号的行是交叉引用，
# 由 _CITE_PAREN 拒绝。同键重复题注（表格跨页重印表头）保留首现。
_GRAPH_RE = re.compile(
    r'^(Tables?|Figures?)(?![A-Za-z])\s+(\d{1,2})(?:[.:]\s*|\s+|\s*$)(.*)$')
_CITE_PAREN = re.compile(r'\(\d{1,2}\.\d{1,2}\)')

# 小节头："7.2. Classification of irreducible modules" / "1.4.AbstractLiealgebras"
# （OCR 粘连）/ "19.3. The algebra G2103"（页码粘尾）。行首 N.M 且标题大写起。
_SUBSEC_RE = re.compile(r'^(\d{1,2})\.(\d{1,2})[．.]\s*([A-Z][^\n]{2,68})$')
_SUBSEC_GLUE_RE = re.compile(r'^(\d{1,2})\.(\d{1,2})\.([A-Z][^\n]{2,68})$')

# 习题区闩锁头（集中习题块，V-I 规定省略）。
_EXER_HEAD_RE = re.compile(r'^Exercises?\s*[.:]?$', re.IGNORECASE)


# 块首交叉引用的余串停用词："Lemma B of (15.2), H is..." / "Corollary C of
# Theorem 17.3" 这类「字母号 + of/in/to…」散片。注意不能按「余串首字母小写」
# 拒绝——§24.2 的 Lemma B-E 陈述以数学对象开头，OCR 把希腊字母读成小写
# 拉丁字母（"Lemma B. oq = (-1)^..." 的 o=σ、"Lemma C. q * p * ..."）。
_CROSSREF_WORDS = re.compile(
    r'^(of|in|to|and|we|is|at|by|on|for|with|from|that|then|shows|says|gives)\b')


def _norm_label(raw):
    return _LAB_SING.get(raw, raw.rstrip('s') if raw.endswith('s') else raw)


class _State(object):
    def __init__(self):
        self.cur_sec = None       # int 当前全局节号 §N
        self.cur_sub = None       # (N, M) 当前小节
        self.in_appendix = False  # 章 VI 的两个无编号 Appendix 单元
        self.in_exercise = False
        self.dup_count = {}       # key -> 已出现次数（同键重复 → "-2"/"-3" 槽位）
        self.dup_warn = []


def _loc(st):
    if st.in_appendix and st.cur_sec is not None:
        return '%d.App' % st.cur_sec
    if st.cur_sub is not None:
        return '%d.%d' % st.cur_sub
    if st.cur_sec is not None:
        return '%d' % st.cur_sec
    return '?'


def _register(st, items, it):
    """同键重复（如 §10.2 三个连排 Corollary、附录内多条 Lemma）按出现顺序
    追加槽位后缀 "-2"/"-3"，保证契约键唯一；首个保持裸键。"""
    k = it['key']
    n = st.dup_count.get(k, 0) + 1
    st.dup_count[k] = n
    if n > 1:
        it['key'] = '%s-%d' % (k, n)
        st.dup_warn.append((it['key'], it['page']))
    items.append(it)


def _feed_line(ln, p, st, items):
    """处理单行；命中即 append 并返回 True（该行已消费）。"""
    # ---- 结构锚：节头（与 scan_skeleton 同正则同守卫，仅用于条目定位跟踪）----
    m = _ss.SEC_GLOBAL_PLAIN.match(ln)
    if (m and (st.cur_sec is None or int(m.group(1)) == st.cur_sec + 1)
            and not m.group(2).rstrip().endswith('.')):
        st.cur_sec = int(m.group(1))
        st.cur_sub = None
        st.in_appendix = False
        st.in_exercise = False
        return True

    # ---- 结构锚：小节头（含 OCR 粘连变体）----
    m = _SUBSEC_RE.match(ln) or _SUBSEC_GLUE_RE.match(ln)
    if (m and st.cur_sec is not None and int(m.group(1)) == st.cur_sec
            and int(m.group(2)) >= 1):
        st.cur_sub = (int(m.group(1)), int(m.group(2)))
        st.in_appendix = False
        st.in_exercise = False
        return True

    # ---- 结构锚：章 VI 的两个无编号 Appendix 单元 ----
    if re.match(r'^Appendix\.?\s*$', ln):
        st.in_appendix = True
        st.in_exercise = False
        return True

    # ---- 习题区闩锁 ----
    if _EXER_HEAD_RE.match(ln):
        st.in_exercise = True
        return True

    # ---- 图表头（短行；引用括号拒绝；跨页重印题注同键 → 槽位后缀）。
    # 置于习题闩锁 continue 之前：本书 §12.2 的 Table 2 物理上排在节末习题
    # 块之后，仍属正文图表；而习题题干从不以「Table N./Figure N.」起行。----
    m = _GRAPH_RE.match(ln)
    if m and len(ln) < 70 and not _CITE_PAREN.search(ln):
        kind = 'Table' if m.group(1).startswith('Tab') else 'Figure'
        title = (m.group(3) or '').strip().rstrip('.')
        name = ('%s %s. %s' % (kind, m.group(2), title)).strip(' .') if title \
            else '%s %s' % (kind, m.group(2))
        _register(st, items, {'key': '%s §%s-%s' % (kind, _loc(st), m.group(2)),
                              'label': kind, 'page': p, 'text': name[:90]})
        return True
    if st.in_exercise:
        return False

    # ---- 字母号条目头 ----
    m = _LETTERED_RE.match(ln)
    if m:
        lab = _norm_label(m.group(1))
        letter = m.group(2)
        rest = m.group(4) or ''
        # 点后接停用词（"of/in/..."）= 块首交叉引用散片，非条目头
        if rest and _CROSSREF_WORDS.match(rest):
            return False
        name = m.group(3)
        text = ('%s %s%s' % (lab, letter,
                             (' (%s)' % name.strip()) if name else '')).strip()
        _register(st, items, {'key': '%s §%s%s' % (lab, _loc(st), letter),
                              'label': lab, 'page': p,
                              'text': (text or ln)[:90]})
        return True

    # ---- 编号例 ----
    m = _EXNUM_RE.match(ln)
    if m:
        _register(st, items, {'key': 'Example §%s-%s' % (_loc(st), m.group(1)),
                              'label': 'Example', 'page': p,
                              'text': ('Example %s. %s' % (m.group(1), m.group(2)))[:90]})
        return True

    # ---- 裸标签条目头（余串为空/大写/开括号/数字，或非停用词小写——数学
    # 对象常以 OCR 小写字母开头，如 "Lemma. q = Σ σ(η)ε_σ."；而
    # "Theorem (Chevalley). θ is surjective." 的 θ 读作 'θ'/小写）----
    m = _BARE_RE.match(ln)
    if m:
        rest = m.group(4) or ''
        if rest and not (rest[0].isupper() or rest[0] in '(['
                         or rest[0].isdigit()
                         or not _CROSSREF_WORDS.match(rest)):
            return False
        lab = m.group(1) + (m.group(2) or '')
        name = m.group(3)
        text = '%s%s' % (lab, (' (%s)' % name.strip()) if name else '')
        _register(st, items, {'key': '%s §%s' % (lab, _loc(st)),
                              'label': lab, 'page': p,
                              'text': (text or ln)[:90]})
        return True

    return False


def extract_items_hum(extract_dir, start, end):
    """扫描 [start, end] 页，返回 ORDINAL_HUM 体例编号项列表。

    每项 {key, label, page, text}；key 形如 "Lemma §10.2B"，text 为含标签的
    块首片段（供契约节点 name 与人工核对）。
    """
    blocks = []
    for p in range(int(start), int(end) + 1):
        fp = os.path.join(extract_dir, 'page_%03d.json' % p)
        if not os.path.exists(fp):
            continue
        d = PageJson.load(fp).data
        for t in d.get('text', []):
            txt = (t.get('text') or '').strip()
            if not txt:
                continue
            poly = t.get('poly') or []
            try:
                y = float(poly[1]) if len(poly) >= 8 else 999.0
            except (TypeError, ValueError):
                y = 999.0
            blocks.append((p, y, txt))
    blocks.sort(key=lambda x: (x[0], x[1]))

    st = _State()
    items = []
    for p, y, txt in blocks:
        if y < _HEADER_Y:
            continue                      # 页眉带
        for ln in txt.split('\n'):
            ln = ln.strip()
            if not ln:
                continue
            _feed_line(ln, p, st, items)

    if st.dup_warn:
        for k, pg in st.dup_warn[:20]:
            sys.stderr.write('[extract_items_hum] slot-suffixed dup key %s @p%03d\n'
                             % (k, pg))
    # 保持捕获序（块已按 (page, y) 排序、行内按出现序）——同页条目的先后
    # 与原书阅读序一致（如 Proposition 在其 Corollary 之前），不做键序重排。
    return items


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) < 3:
        print(__doc__)
        return 2
    extract_dir, start, end = args[0], int(args[1]), int(args[2])
    items = extract_items_hum(extract_dir, start, end)
    for it in items:
        print('p%03d | %-14s | %-28s | %s'
              % (it['page'], it['label'], it['key'], it['text'][:60]))
    print('total:', len(items))
    return 0


if __name__ == '__main__':
    sys.exit(main())
