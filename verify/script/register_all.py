"""
register_all.py - 通过 AUTO-DISCOVERY 构建全局 LayerRegistry。

机制：扫描 verify/ 下每个 <snake>/script/<snake>.py（每个校验层目录的 script/
子目录），按裸名 import（boot.setup() 已将 **/script 注入 sys.path），收集其中定义的
VerifyLayer 子类并注册。层文档 <snake>.md 位于 verify/<snake>/ 目录内（与 script/ 并列）。
共享 helper（base.py、fig_common.py、struct_labels.py、_template_layer.py、
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
import warnings

from verify.script.base import LayerRegistry, VerifyLayer

LAYER_REGISTRY = LayerRegistry()

# 发现机制：每个校验层是一个目录 verify/<snake>/，脚本在 verify/<snake>/script/<snake>.py。
# 层文档 <snake>.md 位于 verify/<snake>/ 目录内（与 script/ 并列）。共享 helper 留在 verify/script/。
# boot.setup() 已将所有 **/script 注入 sys.path，故层脚本可按裸名 import。
# 注意：verify/ 本身无 __init__.py（命名空间包），故层根目录必须基于本文件的
# 绝对位置推导（register_all.py 位于 verify/script/，故 parents[1] 即 verify/），
# 不可依赖 verify.__file__。层目录须含与本目录同名的 <snake>.py 才被当作层，
# 以此排除 formula-manifest/script 等非层 script/ 目录（其内部是工具脚本、非 VerifyLayer）。
_LAYERS_ROOT = Path(__file__).resolve().parents[1]  # .../verify
for _snake_dir in sorted(_LAYERS_ROOT.iterdir()):
    if not _snake_dir.is_dir() or _snake_dir.name.startswith('_'):
        continue
    _script_dir = _snake_dir / 'script'
    if not _script_dir.is_dir():
        continue
    # 层目录必须含 <snake>.py，否则不是校验层（如 formula-manifest/script 仅含工具脚本）。
    if not (_script_dir / (_snake_dir.name + '.py')).exists():
        continue
    for _py in sorted(_script_dir.glob('*.py')):
        _name = _py.stem
        if _name.startswith('_'):
            continue
        try:
            _module = importlib.import_module(_name)
        except Exception as _e:
            warnings.warn(f"[register_all] module '{_name}' failed to import, skipping: {_e!r}")
            continue
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
                except Exception as _e:
                    warnings.warn(f"[register_all] layer in module '{_name}' failed to register, skipping: {_e!r}")
                    continue
