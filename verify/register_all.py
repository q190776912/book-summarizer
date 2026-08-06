"""
register_all.py — 通过 AUTO-DISCOVERY 构建全局 LayerRegistry。

机制：扫描 verify.layers 包下所有**不以 '_' 开头**的模块，收集其中定义的
VerifyLayer 子类并注册。因此「新增一层 = 在 verify/layers/ 下新建一个 X_layer.py
并定义 VerifyLayer 子类」即可，本文件无需任何改动。以 '_' 开头的文件
（_fig_common.py 共用 helper、_template_layer.py 模板）被跳过。
运行顺序完全由各层的 order / fix_order 属性决定，与发现顺序无关。
"""
import importlib
import pkgutil
import warnings

from verify import layers as _layers_pkg
from verify.layers.base import LayerRegistry, VerifyLayer

LAYER_REGISTRY = LayerRegistry()

for _mod in pkgutil.iter_modules(_layers_pkg.__path__):
    _name = _mod.name
    if _name.startswith('_'):
        continue
    try:
        _module = importlib.import_module(f'verify.layers.{_name}')
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
