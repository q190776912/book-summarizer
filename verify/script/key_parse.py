"""key_parse.py — 转发 shim → verify.common.key_parse。

真实实现已迁入 verify/common/key_parse.py（该文件为 SSOT）。本文件仅作向后兼容转发，
避免遗漏的引用点断裂（如 verify/script/ignore_files.py）。请勿在此新增任何逻辑。
"""
from verify.common.key_parse import *  # noqa: F401,F403
# `import *` 不转发下划线前缀名；显式转发被 flows 抽取器（extract_items_gm 等）引用的私有名。
from verify.common.key_parse import _canon_label  # noqa: F401
