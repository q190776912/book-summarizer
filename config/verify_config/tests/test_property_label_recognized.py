"""`Property` 类条目的 md 侧识别必须与契约侧键推导同源（2026-10-03 实测根因）。

根因（Lasota & Mackey《Chaos, Fractals and Noise》ch8 §8.5）：原书印面以
`Property 1.`–`Property 5.` 立目，交付 md 双侧照印面写成 `**Property 1.**` /
`**性质1.**`。分章契约侧一直认这类节点（`TYPE_TO_LABEL_CN['property']='性质'`、
`_LABEL_CANON['Property']='性质'`），唯独 md 侧的正则词表 `EN_LABEL_KINDS` 漏收
`Property`，于是同一批印面条目两头都堵：
  * 契约无槽位 → 中文版 B 层报 `EXTRA-ENTRY 性质1..性质5`；
  * 按处方登记零内容契约节点后 → 英文版 `**Property N.**` 条头解析不出键，
    5 条全部翻成 `TRULY MISSING`（PASS 24/24 → 23/24）。
即 `_LABEL_CANON` / `TYPE_TO_LABEL_CN` / `TYPE_TO_LABEL_EN` / `EN_LABEL_KINDS`
四张表之间的 SSOT 漂移。修法是补 `EN_LABEL_KINDS`，并由本文件的词表一致性测试
把「每个内容类型的中英文标签都必须在 md 词表里」钉成机械闸（今后再漏收即红）。

跨 50 书普查（`_census_property_label`，把 COMBINED 交替式换出净新增 match）：
净新增 49 处、落在 6 书，逐条核过全是印面 Property 条目或其交叉引用（do Carmo
§2-7 Property 1–3、ODE 书 Property 1–2 粗体条头、Strogatz §6.8 property n 回指），
无一处标题/散文误配。

负向口径同批固化：单号 `property 2` 这类**散文回指**在三级体例（type 3）下不得
产生键（该分支只有带 `**` 的条头正则与三段号散文正则走 COMBINED 词表），否则
写手转述句会伪装成条目。

Runs under stdlib unittest:
  python config/verify_config/tests/test_property_label_recognized.py
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for p in (_ROOT, os.path.join(_ROOT, "lib"),
          os.path.join(_ROOT, "verify", "script")):
    if p not in sys.path:
        sys.path.insert(0, p)
import lib.boot as _boot
_boot.setup()

from verify_config import (GroupConfig, TYPE_TO_LABEL_CN, TYPE_TO_LABEL_EN,
                          EN_LABEL_KINDS, _canon_label,
                          LABEL_TO_TYPE, ORDINAL_THREE_LEVEL, ORDINAL_TWO_LEVEL)
from key_parse import keys_in_md, CN_LABEL_KINDS
from structure_io import read_structure_items


def _write(tmp, name, text):
    p = os.path.join(tmp, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)
    return p

class LabelTableConsistency(unittest.TestCase):
    """每个内容类型的中/英标签都必须同时活在 md 词表里。"""

    CONTENT_TYPES = [t for t in TYPE_TO_LABEL_CN if t != 'uncat']

    def test_en_label_of_every_type_is_in_md_wordlist(self):
        for t in self.CONTENT_TYPES:
            en = TYPE_TO_LABEL_EN[t]
            self.assertIn(en, EN_LABEL_KINDS,
                          "type=%s 的英文标签 %r 不在 EN_LABEL_KINDS → md 侧 %s 条头"
                          "解析不出键（契约侧却出键），B 层必然假 MISSING/EXTRA"
                          % (t, en, en))

    def test_cn_label_of_every_type_is_in_md_wordlist(self):
        for t in self.CONTENT_TYPES:
            self.assertIn(TYPE_TO_LABEL_CN[t], CN_LABEL_KINDS,
                          "type=%s 的中文标签 %r 不在 CN_LABEL_KINDS" % (t, TYPE_TO_LABEL_CN[t]))

    def test_en_and_cn_label_share_one_canon_key(self):
        for t in self.CONTENT_TYPES:
            self.assertEqual(_canon_label(TYPE_TO_LABEL_EN[t]), TYPE_TO_LABEL_CN[t],
                             "type=%s: 英文标签正名 ≠ 中文规范标签" % t)

    def test_property_registration_present(self):
        self.assertEqual(_canon_label('Property'), '性质')
        self.assertEqual(LABEL_TO_TYPE.get('Property'), 'property')


class PropertyHeadRecognition(unittest.TestCase):
    """`**Property N.**` / `**性质N.**` 条头 → 规范键 `性质N`。

    体例照 chaos 书真实 config：三级组（定理/评注…）+ 一个二级组（练习）——
    章/节内起号的**单号**条头正是由二级组分支里的 `ENTRY_RE_EN_SINGLE_C` 解析的，
    所以词表漏收 `Property` 时，英文版这些条头一条键都出不来。
    """

    GROUPS = [GroupConfig(type=ORDINAL_THREE_LEVEL, name=['Theorem'], scope=3),
              GroupConfig(type=ORDINAL_TWO_LEVEL, name=['Exercise'], scope=2)]

    MD = '\n'.join([
        '## §8.5 Elementary Properties of the Solutions of the Linear Boltzmann Equation',
        '',
        '> **Property 1.** From inequality (7.4.7) we know that, given $f \\in L^{1}$, …',
        '',
        '> 图 6.8.6 shows the shrinking used in property 2, and the tangency behind property 4.',
        '',
        '于是由 (8.5.8) 与性质3 可知结论成立。',
        '',
        '> **性质5.** 若对某个 $f_{*} \\in L^{1}$ 有 $P f_{*} = f_{*}$，则也有 $\\hat{P}_{t} f_{*} = f_{*}$。',
        '',
    ])

    def test_en_and_cn_bold_heads_emit_same_key_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, 'ch8.md', self.MD)
            entries, allk = keys_in_md(p, groups=self.GROUPS, chapter=8)
        self.assertIn('性质1', entries)
        self.assertIn('性质5', entries)
        self.assertIn('性质1', allk)
        # 散文回指（小写 property 2 / 句中带号的「性质3」回指）不进条目桶
        self.assertNotIn('性质2', entries)
        self.assertNotIn('性质3', entries)

    def test_section_title_alone_produces_no_property_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, 't.md', '## §8.5 Elementary Properties of the Solutions\n'
                                    '本节考察 (8.3.7) 最重要的性质。\n')
            entries, allk = keys_in_md(p, groups=self.GROUPS, chapter=8)
        self.assertFalse([k for k in set(list(entries) + list(allk)) if '性质' in k])


class ContractSideKeyDerivation(unittest.TestCase):
    """契约里 `type='property'` 节点出的键必须与 md 条头键逐字相同（两侧 1:1 相交）。"""

    def _contract(self, tmp):
        d = os.path.join(tmp, 'book_structure')
        os.makedirs(d)
        root = {
            "key": "8", "type": "chapter",
            "name": "8 Discrete Time Processes",
            "page_start": 266, "page_end": 297, "consolidated": False,
            "sub_sec": [
                {"key": "8.5", "type": "section", "name": "8.5 Elementary Properties",
                 "page_start": 279, "page_end": 295, "consolidated": False,
                 "sub_sec": [
                     {"key": "性质1", "type": "property",
                      "name": "性质1 Property 1. From inequality (7.4.7)",
                      "page_start": 281, "page_end": 281, "consolidated": False,
                      "sub_sec": []},
                 ]},
            ],
        }
        with open(os.path.join(d, 'ch8.json'), 'w', encoding='utf-8') as f:
            json.dump(root, f, ensure_ascii=False)
        return tmp

    def test_property_node_key_matches_md_head_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            ext = self._contract(tmp)
            items = read_structure_items(ext, 8, primary_type=ORDINAL_THREE_LEVEL)
            p = _write(tmp, 'ch8.md', '> **Property 1.** From inequality (7.4.7) …\n')
            entries, _ = keys_in_md(p, groups=PropertyHeadRecognition.GROUPS,
                                    chapter=8)
        keys = {it['key'] for it in (items or [])}
        self.assertIn('性质1', keys)
        self.assertEqual([it for it in items if it['key'] == '性质1'][0]['label'], '性质')
        # 关键：契约键必须能在 md 侧找到同名条头键（旧行为是 md 侧啥也解析不出）
        self.assertTrue(keys & set(entries))


if __name__ == '__main__':
    unittest.main(verbosity=2)
