"""extract_items_gm.py — Gelfand-Manin《Methods of Homological Algebra》结构抽取器.

config_setting 规则5 增量扩展。本书体例（全书实测，见项目记忆）：

  - 章:   Roman I..V（chapter_map 存阿拉伯数字 1..5；文件级 # Chapter N）
  - 节:   每章内 "N. Title" 章局部重排（章局局部单序标），原书印 "§N. Title"，
          § 常 OCR 成 "$"/"S"/"8"/丢失。节头与节内条目头同为 "N. 大写词" 形态，
          纯靠 OCR 正则无法区分（与 descriptive 子块 "1. Main Definitions" 冲突），
          故本节锚点取自印刷 TOC（_extract/gm_sections.json 权威清单），
          按【预期节号 + 标题前缀】顺序匹配正文块——单调游标保证只认下一节，
          短章名 running head（"I. Simplicial Sets"）因不匹配"数字+下一节标题"被拒。
  - 条目: 节内【共享一条计数器】的裸整数头，数字在前、标签/标题在后：
          "3. Theorem ..." / "5. Definition. A morphism ..." / "2. Examples"
          （描述性子块也占同一计数器槽位）。交叉引用写作 "Theorem III.1.3"
          = 章.节.条（印刷裸号 N 即末位条号）。
          键取标准三级 "C.S-N"（与 vakil/type3 同形）→ 下游 B/D/Q/key_parse/backfill 全兼容。
  - 习题: 每节末 "Exercises" 标题块 + 其下裸编号题 → 进入习题闩锁，直到下一节头；
          闩锁内块不进 ITEM 合同（按 writing-rules 习题收录规则另行处理）。

用法（被 build_structure 依 config 标志 gm_bare_numbered 调用，亦可单跑调试）：
  python extract_items_gm.py <extract_dir> <ch> <start> <end>
  -> 打印 (sec_rows, items)
"""
import os
import re
import sys
import json
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

# 条目/子块共享计数器的标签词（数字在前，标签紧跟其后）。
LABEL_RE = re.compile(
    r'^(Theorem|Lemma|Proposition|Corollary|Definition|Remark|Example|Examples|'
    r'Commentary|Note|Notes|Axiom|Construction|Notation|Conjecture|Problem|Q\.E\.D)\b',
    re.I)
# 节内条目头：裸整数 + 句点 + 大写词/标签（margin 左对齐另判）。
# 🔴 句点后空格可有可无：原书大量条目头排作 '13.Corollary' / '3.Presheaves'
# / '4.Remarks'（数字紧贴标签，无空格），\s+ 会漏。放宽为 \s*；误吃由后续
# 守卫兜底（首词大写排除 '3.5'/'2. e.g.'，本节内单调排除正文裸号/交叉引用）。
HEAD_RE = re.compile(r'^(\d{1,2})\s*[.\u3002]\s*(\S.*)$')
# 节头候选：纯「数字 + 句点 + 标题」。§-前缀（OCR 成 $/S/€ 等非数字符号）在
# 代码里先行剥除，**不放进正则前缀类**——否则 '8'/'s' 作可选前缀会在数字串上
# 灾难性回溯、把 '$8. Sheaf' 反手吃成失配。裸 'N.' 直接命中本正则。
SEC_HEAD_RE = re.compile(r'^(\d{1,2})\s*[.\u3002]?\s*(.*)$')
EXER_RE = re.compile(r'^\s*exercises?\b', re.I)
# running-header 特征：块内粘连印刷页码（"22 1. Simplicial Sets"）或全大写章名头。
_HDR_PAGE = re.compile(r'^\s*\d{1,4}\s')
# 页眉/页脚带：真条目头左对齐 (x<_ITEM_X)；running head「61. Simplicial Sets」
# (x≈150-240) 与「$4. …」(x≈100+) 需靠 x 同带区分——running head 通常粘连页码
# 或被 _HDR_PAGE 先拦，且其 rest 不匹配 TOC 标题。
_ITEM_X = 300
# 章首页眉带（y）：真节头一律 y>150；running head 全在页顶 y<=150。
_HDR_BAND = 150
# 单节条目号合理上界（跳号过大视作页码粘连噪声）。
_ITEM_MAX = 60


def _norm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def load_gm_sections(extract_dir):
    fp = os.path.join(extract_dir, 'gm_sections.json')
    with open(fp, encoding='utf-8-sig') as fh:
        return json.load(fh).get('sections', {})


def _ordered_blocks(extract_dir, p):
    fp = os.path.join(extract_dir, f'page_{p:03d}.json')
    if not os.path.exists(fp):
        return []
    d = PageJson.load(fp)
    blocks = []
    for b in d.text_blocks:
        poly = b.get('poly') or [0, 0, 0, 0, 0, 0, 0, 0]
        y = min(poly[1], poly[3], poly[5], poly[7]) if len(poly) >= 8 else poly[1]
        x = poly[0]
        for ln in (b.get('text') or '').split('\n'):
            ln = ln.strip()
            if ln:
                blocks.append((round(y, 1), x, ln))
    blocks.sort(key=lambda t: (t[0], t[1]))
    return blocks


_STOP = {'a', 'an', 'the', 'of', 'and', 'to', 'in', 'on', 'or', 'for',
         'by', 'with', 'as', 'at', 'be', 'is', 'are'}


def _sigwords(s):
    return [w for w in re.findall(r'[a-z0-9]+', (s or '').lower())
            if w not in _STOP]


from difflib import SequenceMatcher


def _wmatch(a, b):
    """Fuzzy per-significant-word equality, tolerating OCR char corruption
    ('Categoris'≈'Categories', 'Eract'≈'Exact')."""
    if a == b or (len(a) >= 5 and (a.startswith(b) or b.startswith(a))):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.72


def _title_prefix(rest, exp, nwords):
    """Do the first `nwords` significant words of the TOC title appear (in
    order, allowing one leading slip word) at the head of `rest`'s significant
    words? Fuzzy per word."""
    e, head = _sigwords(exp), _sigwords(rest)[:6]
    if not e or not head:
        return False
    k = min(nwords, len(e))
    idx = 0
    for w in e[:k]:
        if idx < len(head) and _wmatch(head[idx], w):
            idx += 1
        elif idx + 1 < len(head) and _wmatch(head[idx + 1], w):   # one slip
            idx += 2
        else:
            return False
    return True


def scan_gm(extract_dir, ch, start, end):
    """返回 (sec_rows, items)。sec_rows=[(page,'SEC',C.S,title,None)]，
    items=[{'key','label','page','text'}]，键形如 'C.S-N'。

    判据（全书实测）：
      * 页眉噪声（running header / 粘连页码 OCR，如 '61. Simplicial Sets'）全在
        页顶带 y<=_HDR_BAND；正文块 y 起点 >=160，故带内一律跳过。
      * 真节头：带内以外、数字==下一 TOC 节号、标题前缀命中 TOC。§-标记（$/§/S
        等）是强信号（只需首词命中）；裸 'N. Title' 是弱信号（需两词命中且打断
        当前节条目计数器），以排除同节 descriptive item 撞标题（§3.6 'Derived…'）。
      * 真条目头：进入某节后、左对齐(x<_ITEM_X) 的 'N. 大写…'，N 在**本节内**严格
        递增（每节从 1 重排 → last_item_num 随节头归零，杜绝跨节大数页码噪声）。
    """
    titles = load_gm_sections(extract_dir).get(str(ch), [])
    sec_rows, items = [], []
    cur_sec = None            # 当前节号（int），None=章首未进节
    sec_pointer = 0           # 下一个待匹配的 TOC 节索引
    in_exer = False           # 习题闩锁
    last_item_num = 0         # **本节内**已见最大条目号（每节头归零）

    def match_section(num_str, rest, strong):
        if sec_pointer >= len(titles):
            return False
        if int(num_str) != sec_pointer + 1:
            return False
        exp = titles[sec_pointer]
        if strong:
            return _title_prefix(rest, exp, 1)
        seq_break = cur_sec is None or int(num_str) <= last_item_num
        return seq_break and _title_prefix(rest, exp, 2)

    def sec_candidates(ls):
        """产出 (num, rest, strong) 候选：先试剥 §-标记的强轨，再试裸轨。"""
        out = []
        stripped = ls.lstrip('$§Ss€\u00a7 ')
        if stripped is not ls and stripped[:1].isdigit():
            m = SEC_HEAD_RE.match(stripped)
            if m:
                out.append((m.group(1), m.group(2), True))
        m = SEC_HEAD_RE.match(ls)
        if m:
            out.append((m.group(1), m.group(2), False))
        return out

    for p in range(start, end + 1):
        for y, x, ln in _ordered_blocks(extract_dir, p):
            if y <= _HDR_BAND:       # 页眉/页脚带：整带丢弃
                continue
            ln = ln.strip("'\"\u2018\u2019\u201c\u201d` ")  # 去 OCR 首尾引号噪声
            if _HDR_PAGE.match(ln):
                continue
            if x < _ITEM_X:
                hit = None
                for num, rest, strong in sec_candidates(ln.lstrip()):
                    if match_section(num, rest, strong):
                        hit = (num, rest, strong)
                        break
                if hit:
                    snum = sec_pointer + 1
                    sec_rows.append((p, 'SEC', f'{ch}.{snum}',
                                     titles[sec_pointer], None))
                    cur_sec = snum
                    sec_pointer += 1
                    in_exer = False
                    last_item_num = 0    # 🔴 每节计数器归零
                    continue
            if EXER_RE.match(ln) and x < _ITEM_X and len(ln) < 24:
                in_exer = True
                continue
            if cur_sec is None:
                continue  # 章首未进节：交给章级 desc，不作条目
            hm = HEAD_RE.match(ln)
            if not hm or x >= _ITEM_X:
                continue
            n = int(hm.group(1))
            rest = hm.group(2).strip()
            # 本节内单调 + 合理上界：跳号过大（页码粘连残留/交叉引用）视为噪声。
            if n <= last_item_num or n > _ITEM_MAX:
                continue
            # 真条目头首词需「大写标题」形态，排除 "2 conditions hold" 类小写续句；
            # 例外：OCR 把希腊字母标签读成 't-Exact' / '$-Complex' 这类「小写字母+
            # 连字符+大写」复合标题（本节内单调守卫已足以挡住裸数字续句）。
            if not re.match(r'^(?:[A-Z$§\[]|[a-zA-Z]-[A-Z])', rest):
                continue
            lm = LABEL_RE.match(rest)
            label = lm.group(1).capitalize() if lm else 'uncat'
            key = f'{ch}.{cur_sec}-{n}'
            items.append({'key': key, 'label': label, 'page': p,
                          'text': ln[:120], '_in_exer': in_exer})
            last_item_num = n
    real_items = [it for it in items if not it.pop('_in_exer', False)]
    real_items.sort(key=lambda t: (t['page'], _natkey(t['key'])))
    return sec_rows, real_items


def _natkey(k):
    return [int(x) if x.isdigit() else x for x in re.split(r'[.\-]', k)]


# 兼容 build_structure 的 extract_items_* 调用签名：只回条目。
def extract_items_gm(extract_dir, ch, start, end, **kw):
    _, items = scan_gm(extract_dir, ch, start, end)
    return items


if __name__ == '__main__':
    ext = sys.argv[1]
    ch, s, e = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    secs, its = scan_gm(ext, ch, s, e)
    print('== SECTIONS ==')
    for r in secs:
        print('  ', r)
    print(f'== ITEMS ({len(its)}) ==')
    for it in its:
        print(f"  p{it['page']:03d} {it['key']:8s} [{it['label']:12s}] {it['text'][:60]!r}")
