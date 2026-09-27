"""test_structure_checker_label_vocab.py — 完整性闸门脚本必须**可导入**且标签词表单源。

缺陷根因（Apostol IANT 2026-09-28 实测）：`check_structure_completeness.py` 用
`_LABEL_CANON` 派生 `_LABEL_RE`，却只 import 了派生表 `LABEL_TO_TYPE`——模块一加载
即 `NameError: name '_LABEL_CANON' is not defined`，structure 第 2–4 步查漏闸门对
**任何书**都跑不起来（`tools/check_undefined_names.py` 也没抓到：模块级推导式
作用域里的自由名不在其扫描范围）。闸门是拆单元前的硬闸，它一崩整条流水线就
只剩「手工跳步」一条路，故把「能导入 + 词表齐备」做成机械判据。

正向：模块可导入；`_LABEL_RE` 认识 LABEL_TO_TYPE 的**全部**英文标签与
      TYPE_TO_LABEL_EN 的每个规范标签（长词优先，`Remark` 不被 `Re` 截走）。
负向：词表里新增标签而 `_LABEL_RE` 漏识 → 该标签的契约键无法归一 →
      `_canon_key` 返回 None（回填定位循环会整段跳过该节点 = 原缺陷形态）。
"""
import importlib.util
import os
import re
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot  # noqa: E402
_boot.setup()

from verify_config import LABEL_TO_TYPE, TYPE_TO_LABEL_EN, _LABEL_CANON  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "check_structure_completeness",
    os.path.join(_ROOT, "verify", "script", "check_structure_completeness.py"))


class CheckerImportable(unittest.TestCase):
    def test_module_loads_without_name_error(self):
        """模块级 `_LABEL_RE` 构造不得引用未导入的名字。"""
        mod = importlib.util.module_from_spec(_SPEC)
        try:
            _SPEC.loader.exec_module(mod)
        except NameError as e:                       # 缺陷原形
            self.fail("checker 模块导入即 NameError（词表单源名未导入）: %s" % e)
        self.assertTrue(hasattr(mod, "_LABEL_RE"))


class LabelRegexVocabulary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mod = importlib.util.module_from_spec(_SPEC)
        _SPEC.loader.exec_module(mod)
        cls.re_ = mod._LABEL_RE
        cls.canon_key = getattr(mod, "_canon_key", None)

    def _matches(self, label):
        return self.re_.match(label)

    def test_every_registered_english_label_is_recognised(self):
        for lbl in sorted({l for l in LABEL_TO_TYPE if re.fullmatch(r"[A-Za-z]+", l)}):
            m = self._matches(lbl)
            self.assertIsNotNone(m, "LABEL_TO_TYPE 有 %r 但 _LABEL_RE 漏识" % lbl)
            if m:
                self.assertEqual(m.group(0), lbl, "%r 被更短的词截走" % lbl)

    def test_every_canonical_en_surface_form_is_recognised(self):
        for cn, en in TYPE_TO_LABEL_EN.items():
            forms = en if isinstance(en, (list, tuple, set)) else [en]
            for f in forms:
                if not f or not re.fullmatch(r"[A-Za-z ]+", f):
                    continue
                for word in re.findall(r"[A-Za-z]+", f):
                    self.assertIsNotNone(self._matches(word),
                                         "TYPE_TO_LABEL_EN[%s] 的词 %r 漏识" % (cn, word))

    def test_longest_form_wins(self):
        """长词优先：`Corollary` 不得被 `Cor` 之类短词截成残段。"""
        for lbl in ("Corollary", "Proposition", "Definition", "Remark", "Example"):
            m = self._matches(lbl)
            self.assertIsNotNone(m)
            self.assertEqual(m.group(0), lbl)

    def test_unknown_label_is_not_matched(self):
        """负向：非标签词不匹配（否则正文词被当标签剥掉，键归一出错）。"""
        for word in ("The", "There", "For"):
            self.assertIsNone(self._matches(word))


if __name__ == "__main__":
    unittest.main()
