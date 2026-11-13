"""
register_all.py - 通过 AUTO-DISCOVERY 构建全局 LayerRegistry。

机制：扫描 verify/ 下每个 <snake>/script/<snake>.py（每个校验层目录的 script/
子目录），按裸名 import（boot.setup() 已将 **/script 注入 sys.path），收集其中定义的
VerifyLayer 子类并注册。层文档 <snake>.md 位于 verify/<snake>/ 目录内（与 script/ 并列）。
共享 helper（base.py、fig_common.py、struct_labels.py、
_reconcile_book_formulas.py）放在 verify/script/，不会被当作层。运行顺序完全由各层
的 order / fix_order 属性决定，与发现顺序无关。
"""
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

import importlib
import importlib.util

from verify.script.base import LayerRegistry, VerifyLayer

LAYER_REGISTRY = LayerRegistry()


def _load_layer_module(name, path):
    """加载层模块；仅当裸名解析到**别的文件**时才按显式路径加载（2026-11-12）。

    🔴 旧实现 ``importlib.import_module(_name)`` 依赖 sys.path 顺序解析裸名。
    `verify/unit_order/script/unit_order.py`（定义 ULayer）与
    `lib/unit_order.py`（纯 helper，无 VerifyLayer）同名；全量 pytest 下裸名
    先解析到后者，U 层被静默剔除而报告仍全绿，单独跑又正常 —— 环境相关的假绿。
    但**无冲突时必须走裸名导入**：B 层判据测试直接 patch 裸名模块的全局开关，
    无差别按别名加载会让那些测试（及线上同类 patch）改到另一个模块副本上。
    """
    import importlib
    expected = os.path.abspath(str(path))
    cached = sys.modules.get(name)
    if cached is not None:
        got = os.path.abspath(getattr(cached, "__file__", "") or "")
        if got == expected:
            return cached
    else:
        spec0 = importlib.util.find_spec(name)
        origin = os.path.abspath(spec0.origin) if (spec0 and spec0.origin) else ""
        if origin == expected:
            return importlib.import_module(name)
    # 裸名已被同名 helper 占用 / 会解析到别处 → 用唯一别名按文件 spec 加载，
    # 不覆盖 sys.modules 里的裸名条目，避免影响其它消费者。
    alias = "_verify_layer_%s_%s" % (path.parent.parent.name, name)
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("[register_all] 无法为层模块构造 spec: %s" % path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(alias, None)
        raise
    return mod

# 发现机制：每个校验层是一个目录 verify/<snake>/，脚本在 verify/<snake>/script/<snake>.py。
# 层文档 <snake>.md 位于 verify/<snake>/ 目录内（与 script/ 并列）。共享 helper 留在 verify/script/。
# boot.setup() 已将所有 **/script 注入 sys.path，故层脚本可按裸名 import。
# 注意：verify/ 本身无 __init__.py（命名空间包），故层根目录必须基于本文件的
# 绝对位置推导（register_all.py 位于 verify/script/，故 parents[1] 即 verify/），
# 不可依赖 verify.__file__。层目录须含与本目录同名的 <snake>.py 才被当作层，
# 以此排除仅含工具脚本的非层 script/ 目录（其内部非 VerifyLayer）。
_LAYERS_ROOT = Path(__file__).resolve().parents[1]  # .../verify
_discovered_layer_dirs = []
for _snake_dir in sorted(_LAYERS_ROOT.iterdir()):
    if not _snake_dir.is_dir() or _snake_dir.name.startswith('_'):
        continue
    _script_dir = _snake_dir / 'script'
    if not _script_dir.is_dir():
        continue
    # 层目录必须含 <snake>.py，否则不是校验层（仅含工具脚本的目录）。
    if not (_script_dir / (_snake_dir.name + '.py')).exists():
        continue
    _discovered_layer_dirs.append(_snake_dir.name)
    for _py in sorted(_script_dir.glob('*.py')):
        _name = _py.stem
        if _name.startswith('_'):
            continue
        try:
            _module = _load_layer_module(_name, _py)
        except Exception as _e:
            raise RuntimeError(
                f"[register_all] 校验层模块 '{_name}' 导入失败，拒绝静默剔除该层"
                f"（否则其全部判据消失而结论仍 PASS）: {_e!r}") from _e
        _found_here = 0
        for _attr in vars(_module).values():
            if (isinstance(_attr, type)
                    and issubclass(_attr, VerifyLayer)
                    and _attr is not VerifyLayer):
                _code = _attr.code
                if LAYER_REGISTRY.get(_code) is not None:
                    raise ValueError(
                        f"Duplicate layer code '{_code}' declared by module '{_name}' "
                        f"(already registered by '{LAYER_REGISTRY.get(_code).__class__.__module__}.{LAYER_REGISTRY.get(_code).__class__.__name__}')")
                try:
                    LAYER_REGISTRY.register(_attr())
                    _found_here += 1
                except Exception as _e:
                    raise RuntimeError(
                        f"[register_all] 校验层 '{_name}' 注册失败，拒绝静默剔除: {_e!r}") from _e
        if _name == _snake_dir.name and _found_here == 0:
            raise RuntimeError(
                f"[register_all] 层主模块 '{_name}' 未注册任何 VerifyLayer 子类，"
                f"拒绝以残缺注册表出结论（疑似裸名解析到同名 helper）")


# 🔴 完整性闸：注册的层数必须覆盖本次发现的全部层目录，缺一层就炸。
# 结论 PASS 只在全部判据都在场时才有意义（verify.md 层表为 SSOT）。
if len(set(LAYER_REGISTRY.by_code())) < len(_discovered_layer_dirs):
    raise RuntimeError(
        "[register_all] 注册层数 %d < 发现的层目录 %d（%s），拒绝静默缺层"
        % (len(set(LAYER_REGISTRY.by_code())), len(_discovered_layer_dirs),
           sorted(_discovered_layer_dirs)))
