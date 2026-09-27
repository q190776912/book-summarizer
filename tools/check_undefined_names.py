#!/usr/bin/env python3
"""check_undefined_names.py — 未定义名静态检查（pyflakes-lite）。

找出一类 `py_compile` **查不出**、只在特定代码路径触发时才爆炸的错误：
函数体里引用了既不是参数、也不是局部量、也不来自外层函数、也不是模块级绑定、
也不是内置名的标识符 —— 即 ``NameError: name 'X' is not defined``。
🔴 **模块级与类体的语句同样在检查范围内**（按语句顺序增量累积绑定，先绑定后用才
合法；`for`/`with`/推导式/`except … as` 的目标名在同一语句内视为已绑定），
否则「模块级推导式用了没 import 的名字」这种一加载即炸的缺陷会漏网
（2026-09-28 实测：`check_structure_completeness.py` 的 `_LABEL_CANON`）。

真实事故（2026-09-16）：``build_structure._recognized_sections`` 的函数体用了
``page_dir``，但签名没有该参数 → 对**任何**配了 ``_recognized_sections.json``
的书（如 Lee）一调用就 NameError；而没配该文件的书走不到这行，所以长期潜伏。

用法
----
    python tools/check_undefined_names.py                  # 扫技能自带源码
    python tools/check_undefined_names.py <file|dir> ...    # 扫指定路径

退出码：0 = 未发现可疑项；1 = 有可疑项（需人工确认是否真 bug）。
已知误报：模块级 ``global X`` 后在函数里赋值的全局量（如 extract_pipeline
的 ``LOG_FILE``）——它在首次使用前已被赋值，属可接受写法。
"""
import ast
import builtins
import os
import sys

BUILTINS = set(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__package__", "__spec__", "__loader__",
}

_SKIP_DIRS = {"__pycache__", ".git", "node_modules", "tests", ".pytest_cache"}


def _own_bindings(fn):
    """本函数直接引入的绑定（不含嵌套 def 的函数体）。"""
    names = set()
    for a in list(fn.args.posonlyargs) + list(fn.args.args) + \
            list(fn.args.kwonlyargs):
        names.add(a.arg)
    if fn.args.vararg:
        names.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        names.add(fn.args.kwarg.arg)

    stack = list(fn.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)          # 定义名本身算绑定，函数体交给递归
            continue
        if isinstance(n, ast.Lambda):
            continue                   # lambda 子树跳过（自身参数，风险低）
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, ast.Import):
            for a in n.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                names.add(a.asname or a.name)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            names.update(n.names)
        elif isinstance(n, ast.comprehension):
            for sub in ast.walk(n.target):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
        for child in ast.iter_child_nodes(n):
            stack.append(child)
    return names


def _loads_and_nested(fn):
    """本函数直接的 Name 读取，以及其嵌套 def/lambda。"""
    loads, nested = [], []
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nested.append(n)
            continue
        if isinstance(n, ast.Lambda):
            continue                   # lambda 子树跳过（自身参数，风险低）
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            loads.append((n.id, n.lineno))
        for child in ast.iter_child_nodes(n):
            stack.append(child)
    return loads, nested


def _module_bindings(tree):
    names = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                names.add(a.asname or a.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            names.add(n.id)
        elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.Try, ast.If,
                            ast.For, ast.While, ast.With)):
            for t in ast.walk(n):
                if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store):
                    names.add(t.id)
                elif isinstance(t, (ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef)):
                    names.add(t.name)
                elif isinstance(t, ast.Import):
                    for a in t.names:
                        names.add((a.asname or a.name).split(".")[0])
                elif isinstance(t, ast.ImportFrom):
                    for a in t.names:
                        names.add(a.asname or a.name)
    # 函数内 `global X` 声明的名字也属模块级绑定（如 extract_pipeline 的 LOG_FILE：
    # 在 main() 里赋值、在 log() 里使用，首用前已赋值，属可接受写法）。
    for n in ast.walk(tree):
        if isinstance(n, ast.Global):
            names.update(n.names)
    return names


def _walk_fn(fn, outer, mod, problems, seen):
    own = _own_bindings(fn)
    known = set(outer) | own | mod | BUILTINS
    loads, nested = _loads_and_nested(fn)
    for name, ln in loads:
        if name not in known and (name, ln) not in seen:
            seen.add((name, ln))
            problems.append((name, ln, fn.name))
    for sub in nested:
        _walk_fn(sub, known, mod, problems, seen)


# ── 模块级 / 类体语句的作用域扫描 ──────────────────────────────────────────
# 旧实现只进 `def` 体查自由名，**模块级语句里的 Name 读取从未检查**，于是
# 「模块级推导式用了没 import 的名字」这一类必炸缺陷静默通过（2026-09-28
# Apostol 实测：`check_structure_completeness.py` 在模块级用 `_LABEL_CANON`
# 派生 `_LABEL_RE` 却没 import，闸门脚本对任何书一加载即 NameError）。
# 判据：按语句顺序**增量**累积本作用域的绑定（先绑定后使用才合法），
# 嵌套 def/lambda 的子树交给 `_walk_fn`（其自由名另有一套作用域）。
def _loads_in_stmt(n):
    """本语句（不含嵌套 def/lambda 体）里的 Name 读取。"""
    loads = []
    stack = [n]
    while stack:
        x = stack.pop()
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            for d in getattr(x, "decorator_list", []):
                stack.append(d)          # 装饰器在本作用域求值
            continue
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load):
            loads.append((x.id, x.lineno))
        for c in ast.iter_child_nodes(x):
            stack.append(c)
    return loads


def _bindings_in_stmt(n):
    """本语句在本作用域引入的绑定名。"""
    names = set()
    for x in ast.walk(n):
        if isinstance(x, ast.Name) and isinstance(x.ctx, (ast.Store, ast.Del)):
            names.add(x.id)
        elif isinstance(x, ast.Import):
            for a in x.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(x, ast.ImportFrom):
            for a in x.names:
                names.add(a.asname or a.name)
        elif isinstance(x, ast.ExceptHandler) and x.name:
            names.add(x.name)
        elif isinstance(x, (ast.Global, ast.Nonlocal)):
            names.update(x.names)
    return names


def _header_bindings(n):
    """语句**求值前/体内必先**绑定的名字：循环变量、with 目标、推导式变量、
    `except E as X` 的 X。它们在同一语句内先绑定后使用，扫描本语句的读取时必须
    先计入已知集，否则 `for x in y: use(x)`、`except Exception as e: f"{e}"`
    这类合法写法被误报（register_all / _flow_contract 实测）。
    """
    names = set()
    for x in ast.walk(n):
        if isinstance(x, (ast.For, ast.AsyncFor)):
            targets = [x.target]
        elif isinstance(x, ast.comprehension):
            targets = [x.target]
        elif isinstance(x, (ast.With, ast.AsyncWith)):
            targets = [i.optional_vars for i in x.items if i.optional_vars]
        elif isinstance(x, ast.ExceptHandler):
            targets = []
            if x.name:
                names.add(x.name)
        else:
            continue
        for t in targets:
            if t is None:
                continue
            for sub in ast.walk(t):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    names.add(sub.id)
    return names


def _walk_scope(body, outer, mod, problems, seen, scope_name):
    known = set(outer)
    for n in body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _walk_fn(n, known | mod, mod, problems, seen)
            known.add(n.name)
        elif isinstance(n, ast.ClassDef):
            _walk_scope(n.body, known, mod, problems, seen, n.name)
            known.add(n.name)
        else:
            known |= _header_bindings(n)
            for name, ln in _loads_in_stmt(n):
                if name not in known | mod | BUILTINS and (name, ln) not in seen:
                    seen.add((name, ln))
                    problems.append((name, ln, scope_name))
            known |= _bindings_in_stmt(n)


def check_file(path):
    tree = ast.parse(open(path, encoding="utf-8-sig").read())
    mod = _module_bindings(tree)
    problems, seen = [], set()
    _walk_scope(tree.body, set(), mod, problems, seen, "<module>")
    return problems


def iter_py(paths):
    for p in paths:
        if os.path.isfile(p) and p.endswith(".py"):
            yield p
        elif os.path.isdir(p):
            for dp, dn, fn in os.walk(p):
                dn[:] = [d for d in dn if d not in _SKIP_DIRS]
                for f in sorted(fn):
                    if f.endswith(".py"):
                        yield os.path.join(dp, f)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        targets = argv
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        subdirs = ("flows", "verify", "lib", "tools", "config", "data")
        targets = [os.path.join(root, d) for d in subdirs
                   if os.path.isdir(os.path.join(root, d))]

    total = 0
    for path in iter_py(targets):
        try:
            probs = check_file(path)
        except SyntaxError as e:
            print("=== %s === SYNTAX ERROR: %s" % (path, e))
            total += 1
            continue
        if probs:
            print("=== %s ===" % path)
            for name, ln, fn in sorted(probs, key=lambda x: x[1]):
                print("  line %-5d %-24s in %s()" % (ln, name, fn))
            total += len(probs)
    print()
    print("suspicious undefined names: %d" % total)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
