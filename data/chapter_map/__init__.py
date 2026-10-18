"""`chapter_map` 包口：与同名模块 `chapter_map.py` **同一视图**。

🔴 为什么要 star re-export：`lib/boot.py` 会把 `data/` 与 `data/` 的每个直接子目录
都注入 `sys.path`，于是 `import chapter_map` 有两种解析结果——按 `data/` 命中**本包**、
按 `data/chapter_map/` 命中**模块 `chapter_map.py`**。只在本包 re-export
`ChapterMap, Chapter` 时，走包口的那条路会缺 `KIND_APPENDIX` 一类的模块级常量
（`from chapter_map import KIND_APPENDIX` → ImportError）。单跑某个测试文件时命中
模块、全量测试里被别的测试先把包塞进 `sys.modules` 就崩 —— 同一份代码两种结果，
属**导入遮蔽**假崩。这里把模块的公开名字全部转发，两条解析路径等价，遮蔽无害。
"""
from . import chapter_map as _m
from .chapter_map import *  # noqa: F401,F403
from .chapter_map import ChapterMap, Chapter

__all__ = sorted(n for n in dir(_m) if not n.startswith("_"))
