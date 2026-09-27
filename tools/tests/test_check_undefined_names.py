"""test_check_undefined_names.py — 静态检查器必须覆盖**模块级 / 类体**自由名。

缺陷根因（Apostol IANT 2026-09-28 实测）：`check_undefined_names.py` 旧实现只递归
`def` 体，模块级语句里的 `Name` 读取从不检查，于是
`check_structure_completeness.py` 在模块级用未 import 的 `_LABEL_CANON` 派生
`_LABEL_RE` 这类「一加载即 NameError」的缺陷静默通过——而该脚本正是拆单元前的
完整性硬闸。判据双向钉死：

正向（必须报）：模块级 / 类体语句里用了未绑定的名字。
负向（不得报）：同一语句内**先绑定后使用**的合法写法——`for x in …: use(x)`、
      `except Exception as e: f"{e!r}"`、列表推导式变量、`with … as f:`。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
sys.path.insert(0, _ROOT)

import importlib.util  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "check_undefined_names", os.path.join(_ROOT, "tools", "check_undefined_names.py"))
chk = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(chk)


def _scan(src):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write(src)
        path = f.name
    try:
        return chk.check_file(path)
    finally:
        os.unlink(path)


class ReportsModuleLevelNames(unittest.TestCase):
    def test_module_level_genexp_uses_unimported_name(self):
        """缺陷原形：模块级推导式引用未导入的名字。"""
        probs = _scan(
            "import re\n"
            "RE = re.compile('|'.join(x for x in _LABEL_CANON))\n")
        self.assertIn("_LABEL_CANON", {p[0] for p in probs})

    def test_class_body_statement_uses_unbound_name(self):
        probs = _scan(
            "class A:\n"
            "    X = [MISSING for i in range(3)]\n")
        self.assertIn("MISSING", {p[0] for p in probs})

    def test_still_catches_function_body_name_error(self):
        """原有能力零回归：函数体引用签名里没有的名字。"""
        probs = _scan("def f(a):\n    return page_dir\n")
        self.assertIn("page_dir", {p[0] for p in probs})


class NoFalsePositives(unittest.TestCase):
    def test_for_loop_variable(self):
        src = (
            "LABELS = {}\n"
            "for _lbl, _cn in LABELS.items():\n"
            "    print(_lbl, _cn)\n")
        self.assertEqual(_scan(src), [])

    def test_except_as_name_used_in_f_string(self):
        src = (
            "import warnings\n"
            "try:\n"
            "    1\n"
            "except Exception as _e:\n"
            "    warnings.warn(f'failed: {_e!r}')\n")
        self.assertEqual(_scan(src), [])

    def test_comprehension_and_with_targets(self):
        src = (
            "import io\n"
            "YS = [y * 2 for y in range(3)]\n"
            "with io.StringIO() as buf:\n"
            "    buf.write('x')\n")
        self.assertEqual(_scan(src), [])

    def test_later_module_assignment_is_not_use_before_bind(self):
        """函数体引用后定义的模块级名 = 合法（调用时才解析）。"""
        src = "def f():\n    return HELPER\nHELPER = 1\n"
        self.assertEqual(_scan(src), [])


if __name__ == "__main__":
    unittest.main()
