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


class ComprehensionScope(unittest.TestCase):
    """🔴 2026-11-09 审计：Python 3 推导式目标不外泄到所在函数。

    旧实现把推导式目标算进函数绑定集，于是同函数里 A 推导式的目标 `c`
    会遮蔽 B 推导式误引用的自由名 `c` —— `resync_figure_refs.py:895`
    的 NameError 曾全库零报。用 `check_source` 直接判内存源码，无需临时文件。
    """

    def test_target_does_not_leak_into_function(self):
        src = ("def f():\n"
               "    cur = [c for c, _t in [(1, 2)]]\n"
               "    out = [c if i else t for i, t in enumerate([1, 2])]\n"
               "    return cur, out\n")
        probs = chk.check_source(src)
        self.assertTrue(any(p[0] == "c" and p[1] == 3 for p in probs), probs)

    def test_legal_target_not_reported(self):
        self.assertEqual(
            chk.check_source("def f(items):\n"
                             "    return [x * 2 for x in items if x]\n"), [])

    def test_nested_comprehension_targets(self):
        self.assertEqual(
            chk.check_source("def f(rows):\n"
                             "    return [[y for y in row] for row in rows]\n"), [])

    def test_generator_expression_free_name(self):
        probs = chk.check_source("def f():\n    return sum(c for t in [1])\n")
        self.assertTrue(any(p[0] == "c" for p in probs), probs)

    def test_module_level_free_name_still_caught(self):
        probs = chk.check_source("x = [z for t in [1]]\n")
        self.assertTrue(any(p[0] == "z" for p in probs), probs)

    def test_module_binding_visible_inside_comprehension(self):
        self.assertEqual(
            chk.check_source("K = 3\n"
                             "def f(items):\n"
                             "    return [x + K for x in items]\n"), [])


    def test_module_level_cross_comprehension_shadow(self):
        """🔴 二轮负向锁：模块级 A 推导式的目标不得遮蔽 B 推导式的自由名。

        旧 `_module_bindings` 用 `ast.walk` 把 A 的 `c` 收成模块级绑定，
        B 里误引用的 `c` 于是全库零报。
        """
        src = ("A = [c for c in [1]]\n"
               "B = (c for t in [1])\n")
        probs = chk.check_source(src)
        self.assertTrue(any(p[0] == "c" and p[1] == 2 for p in probs), probs)

    def test_class_body_cross_comprehension_shadow(self):
        src = ("class A:\n"
               "    X = [c for c in [1]]\n"
               "    Y = (c for t in [1])\n")
        probs = chk.check_source(src)
        self.assertTrue(any(p[0] == "c" for p in probs), probs)

    def test_module_level_legal_target_no_false_positive(self):
        """正向：合法推导式目标在模块级 / 类体都不得误报。"""
        self.assertEqual(chk.check_source("A = [c for c in [1]]\n"), [])
        self.assertEqual(
            chk.check_source("class B:\n    X = [y * 2 for y in range(3)]\n"), [])

    def test_for_loop_target_still_bound_in_module_scope(self):
        """正向：`for` 目标不是推导式目标，仍须按本作用域先绑定后使用放行。"""
        src = ("for _i in range(3):\n"
               "    print(_i)\n")
        self.assertEqual(chk.check_source(src), [])


if __name__ == "__main__":
    unittest.main()
