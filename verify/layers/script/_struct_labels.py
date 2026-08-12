"""_struct_labels.py — 转发 shim → verify.common.struct_labels。

真实实现已迁入 verify/common/struct_labels.py（该文件为 SSOT）。本文件仅作向后兼容转发，
避免遗漏的引用点断裂。请勿在此新增任何逻辑——所有改动去 common/struct_labels.py。
"""
from verify.common.struct_labels import *  # noqa: F401,F403
