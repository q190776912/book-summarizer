"""extract_items_ross.py — S. Ross《A First Course in Probability》编号项抽取器。

config_setting 规则5 增量扩展（ORDINAL_ROSS = 11）：本书条目为「标签在前 +
节内作用域编号」，且例题带小写字母序号——

    Example 2a          （§1.2 内第 1 道例题；字母序号 a..u，节内独立计数）
    Proposition 4.1     （§2.4 内第 1 个命题；节号.节内序号）
    Theorem 7.1         （§5.7 内第 1 个定理）
    Lemma 2.1 / Corollary 4.1
    Axiom 1             （§2.3 三公理；纯单数字）

键保留原书印刷形态（"Example 2a"），供 build_structure 契约与 md 侧
key_parse（规范中文标签 + 原编号，如 例2a / 命题4.1）对齐。

抽取约束：
* 块首锚定（txt[:m.start()] 仅空白）——正文交叉引用（"by Example 2a" /
  "of Chapter 7"）一律不进契约；
* 行内含异章限定词（Chapter N / Section N.M 引用形态）时跳过——真条目头
  从不提 Chapter；
* 无字母后缀的 "Example N" 一律拒绝（真例题恒带字母；无字母者要么是散文
  引用、要么 OCR 把字母读成了数字，宁缺勿滥，漏项交由
  check_structure_completeness 的源侧回填兜底）；
* OCR 大写化容错：字母位的大写混淆字符按 OCR_DIGIT 反查归一为小写
  （"Example 2B" → b；"EXAMPLE8C" 粘连形态同样支持）。

不进契约：Figure/Table（图管线管辖）、Remark/Definition（本书不带编号，
是散文评注）。
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
from lib.regexlib import SEP_TIGHT
from item_dedup import dedup_items

# 标签 → 类别词（label 字段，供 _type_of 映射节点 type）
ROSS_LABELS = ("Example", "Proposition", "Theorem", "Lemma", "Corollary", "Axiom")

_EN_OCR_LETTERS = ''.join(sorted(
    k for k in set("OoQDZzEeSsGgTtBbIl") if not k.isdigit()))
_NUM = r'[\d' + _EN_OCR_LETTERS + r']+'

# 例题：Example + 节号 + 单个小写字母（OCR 可能大写化）。(?![A-Za-z]) 挡
# 复数 "Examples"；字母后不允许再跟字母/数字（"2ab"/"2a1" 是噪声）。
_EX_RE = re.compile(
    r'\b(Examples?)(?![A-Za-z])\s*(?:\([^)]*\))?\s*(' + _NUM + r')\s*([A-Za-z])(?![A-Za-z0-9])',
    re.IGNORECASE)
# 定理族：Label + 节号.节内序号（SEP_TIGHT 兼容点号 OCR 变体）。
_TH_RE = re.compile(
    r'\b(Theorems?|Propositions?|Corollary|Corollaries|Lemmas?|Lemma)(?![A-Za-z])'
    r'\s*(?:\([^)]*\))?\s*(\d{1,2})\s*' + SEP_TIGHT + r'\s*(\d{1,3})(?!\d'
    + SEP_TIGHT + r'\d)',
    re.IGNORECASE)
# 公理：Axiom + 单数字（仅 §2.3 出现）。
_AX_RE = re.compile(
    r'\b(Axioms?)(?![A-Za-z])\s*(?:\([^)]*\))?\s*(\d{1,2})(?![\d.])',
    re.IGNORECASE)

# 异章限定词：真条目头绝不提 Chapter/Section；带者必是跨章引用。
_FOREIGN_REF = re.compile(r'\b(?:Chapters?|Sections?)\s+\d', re.IGNORECASE)

# OCR 把字母位读成大写混淆字符时的反查表（大写形态 → 印刷小写字母）。
_LETTER_FIX = {'O': 'o', 'Q': 'q', 'D': 'd', 'I': 'i', 'L': 'l', 'Z': 'z',
               'E': 'e', 'S': 's', 'G': 'g', 'T': 't', 'B': 'b'}
_DIGIT_AS_LETTER = {'0': 'o', '1': 'l', '5': 's', '8': 'b', '6': 'b', '2': 'z',
                    '7': 'z', '3': 'e', '4': 'a', '9': 'g'}


def _fix_letter(raw):
    """字母位归一：小写化 + OCR 大写混淆字符反查。返回单个小写字母或 None。"""
    c = (raw or '').strip()
    if not c:
        return None
    c = c[0]
    if c.isupper() and c in _LETTER_FIX:
        return _LETTER_FIX[c]
    if c.isdigit():
        # 数字位的字母误读只在「整行再无其它字母可锚」时才可疑；保守起见
        # 只接受高置信映射，其余拒绝（宁缺勿滥）。
        return _DIGIT_AS_LETTER.get(c)
    return c.lower() if c.isalpha() else None


def extract_items_ross(extract_dir, start, end):
    """扫描 [start, end] 页，返回 Ross 体例编号项列表。

    每项: {key, label, page, text}；key 为原书印刷编号（"Example 2a" /
    "Proposition 4.1" / "Axiom 1"），text 为含标题的块首片段。
    """
    items = []
    for p in range(int(start), int(end) + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        data = PageJson.load(fp).data
        for blk in data.get("text", []):
            txt = (blk.get("text") or "").strip()
            if not txt:
                continue
            hit = None      # (key, label, mend)
            for rgx, kind in ((_EX_RE, 'Example'), (_TH_RE, 'th'), (_AX_RE, 'Axiom')):
                for m in rgx.finditer(txt):
                    if txt[:m.start()].strip():
                        continue    # 非块首：引用/续行，不进契约
                    label = m.group(1)
                    label = {'Theorems': 'Theorem', 'Propositions': 'Proposition',
                             'Corollaries': 'Corollary', 'Lemmas': 'Lemma',
                             'Axioms': 'Axiom'}.get(label, label.rstrip('s'))
                    after = txt[m.end():m.end() + 1]
                    if after and after in ")]},;:":
                        continue    # 闭括号收尾 = 引用形态
                    if kind == 'Example':
                        letter = _fix_letter(m.group(3))
                        if letter is None:
                            continue
                        n1 = m.group(2)
                        if not n1.isdigit():
                            continue    # 节号位出现字母混淆 → 弃（宁缺勿滥）
                        key = f"{label} {int(n1)}{letter}"
                    elif kind == 'th':
                        key = f"{label} {int(m.group(2))}.{int(m.group(3))}"
                    else:
                        key = f"{label} {int(m.group(2))}"
                    hit = (key, label, m.end())
                    break
                if hit:
                    break
            if not hit:
                continue
            key, label, mend = hit
            tail = txt[mend:mend + 60]
            if _FOREIGN_REF.search(tail) or _FOREIGN_REF.search(txt[:mend]):
                continue
            snippet = txt[max(0, 0):mend + 90].replace("\n", " ")
            items.append({"key": key, "label": label,
                          "page": p, "text": snippet})
    return dedup_items(items)


if __name__ == '__main__':
    ext = sys.argv[1] if len(sys.argv) > 1 else '.'
    s = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    e = int(sys.argv[3]) if len(sys.argv) > 3 else 10 ** 6
    sys.stdout.reconfigure(encoding='utf-8')
    for it in extract_items_ross(ext, s, e):
        print('%-16s p%-4d %s' % (it['key'], it['page'], (it.get('text') or '')[:60]))
