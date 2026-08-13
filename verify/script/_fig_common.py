"""_fig_common.py — 转发 shim → verify.common.fig_common。

真实实现已迁入 verify/common/fig_common.py（该文件为 SSOT）。本文件仅作向后兼容转发，
避免遗漏的引用点断裂。请勿在此新增任何逻辑——所有改动去 common/fig_common.py。
"""
from verify.common.fig_common import *  # noqa: F401,F403
