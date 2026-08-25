"""book_structure.json — 全书结构骨架的类型化数据模型（中间产物）。

设计（2026-08-12 用户最终确认）
------------------------------
- 单文件 ``<extract_dir>/book_structure.json``，顶层是一个「书」对象（**不是数组**）。
- 书对象：``key=-1, type=-1, name=<书名>, page_start/page_end=<全书起止页>,
  sub_sec=[章节对象...]``。
- 章节 / 条目节点复用 ``flows/extract/structure/structure.md`` 的 schema：
  ``key / type / name / page_start / page_end / sub_sec``（递归）；
  定理 / 定义 / 例等叶节点 ``sub_sec=[]``。``sub_sec`` 顺序即书中实际顺序。

本模块是结构 JSON 的**唯一权威模型**：所有读写 / 遍历 / 回填都经本类，
脚本不再裸操作 json 字典（见 ``verify/script/structure_io.py``、
``verify/verbose_gates``、``verify/script/check_structure_completeness.py``）。

序列化契约（对齐 data/data_schema.md 描述的 JsonData 基类）：
``to_dict()`` / ``from_dict()`` / ``dump()`` / ``load()``。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

# 书根节点的占位 key / type（非真实章节/条目）
ROOT_KEY = -1
ROOT_TYPE = -1

# 容器节点类型（递归 sub_sec，本身不作为编号项）
_CONTAINER_TYPES = ("chapter", "section")


class StructureNode:
    """结构树节点（书 / 章 / 节 / 条目）。避免脚本裸操作 json。"""

    __slots__ = ("key", "type", "name", "page_start", "page_end", "sub_sec",
                 "consolidated", "letter_subs")

    def __init__(self, key: Any = ROOT_KEY, type: Any = ROOT_TYPE, name: str = "",
                  page_start: int = 0, page_end: int = 0,
                  sub_sec: Optional[List["StructureNode"]] = None,
                  consolidated: bool = False,
                  letter_subs: Optional[List[Dict[str, Any]]] = None):
        self.key = key
        self.type = type
        self.name = name
        self.page_start = page_start
        self.page_end = page_end
        self.sub_sec: List["StructureNode"] = sub_sec if sub_sec is not None else []
        # True only for exercise nodes that belong to a consolidated
        # "Exercises/练习" block — these are omitted from the summary and must
        # NOT be verified.  Preserved (interleaved) exercises stay False and
        # ARE verified when the caller opts in via include_exercise=True.
        self.consolidated = consolidated
        # 裸字母子块头（Arnold《数学方法》体例：节内印 "A. 变分"，父节靠位置
        # 确定）。仅 section 节点携带；元素形如 {"key": "A", "name": "A 变分",
        # "page_start": 59}，按书中出现顺序排列。None/[] 表示本书节无字母子块
        # （to_dict 仅在非空时写出 → 其他书 JSON 零变化）。字母子块的**条目**
        # 仍平铺挂在 section.sub_sec 下（不引入第三层容器，_place 归并逻辑不动）。
        self.letter_subs: Optional[List[Dict[str, Any]]] = letter_subs or None

    # ---- 序列化 ----------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "key": self.key,
            "type": self.type,
            "name": self.name,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "consolidated": self.consolidated,
            "sub_sec": [c.to_dict() for c in self.sub_sec],
        }
        if self.letter_subs:
            d["letter_subs"] = [dict(x) for x in self.letter_subs]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StructureNode":
        if not isinstance(d, dict):
            raise TypeError("StructureNode.from_dict expects a dict")
        return cls(
            key=d.get("key", ROOT_KEY),
            type=d.get("type", ROOT_TYPE),
            name=d.get("name", ""),
            page_start=d.get("page_start", 0),
            page_end=d.get("page_end", 0),
            sub_sec=[cls.from_dict(x) for x in d.get("sub_sec", []) or []],
            consolidated=bool(d.get("consolidated", False)),
            letter_subs=list(d.get("letter_subs") or []) or None,
        )

    # ---- 类型判定 --------------------------------------------------------
    def is_container(self) -> bool:
        """容器节点：递归 sub_sec，本身不作为编号项。书根 / chapter / section。"""
        return self.type in _CONTAINER_TYPES or self.key == ROOT_KEY or self.type == ROOT_TYPE

    def is_exercise(self) -> bool:
        return self.type == "exercise"

    # ---- 遍历 / 查询 -----------------------------------------------------
    def iter_items(self, include_exercise: bool = False):
        """深度优先遍历，yield 非容器的编号项节点。

        校验（verify）口径：集中习题块的练习节点（consolidated=True）恒不产出；
        被保留的练习节点（consolidated=False）仅在 include_exercise=True 时产出、
        纳入编号项校验。默认 include_exercise=False → 排除全部练习（保持旧行为，
        待 extract 打 consolidated 标记后由 read_structure_items 切到 True）。
        """
        for child in self.sub_sec:
            if child.is_container():
                yield from child.iter_items(include_exercise=include_exercise)
            elif child.is_exercise():
                if include_exercise and not child.consolidated:
                    yield child
            else:
                yield child

    def find_chapter(self, ch: Any) -> Optional["StructureNode"]:
        """按章号（字符串/整数均可）在本书根下定位章节节点。"""
        target = str(ch)
        for c in self.sub_sec:
            if str(c.key) == target:
                return c
        return None

    def replace_chapter(self, node: "StructureNode") -> bool:
        """用 node 替换本书根下同 key 的章节；若不存在则追加。返回是否发生替换。"""
        target = str(node.key)
        for i, c in enumerate(self.sub_sec):
            if str(c.key) == target:
                self.sub_sec[i] = node
                return True
        self.sub_sec.append(node)
        return False

    def recompute_pages(self) -> int:
        """递归重算容器节点的 page_start/page_end（容器取末代子孙页）。

        先递归子节点（让子容器先定稿其页码），再用**已重算**的子节点
        page_start/page_end 取 min/max，使容器始终等于其全部末代子孙的页码跨度
        （起点 = 最小子孙页，终点 = 最大子孙页）。叶子节点返回自身 page_end。
        """
        if not self.sub_sec:
            return int(self.page_end)
        for c in self.sub_sec:
            c.recompute_pages()
        if self.type == "chapter":
            # 章级区间已按 chapter_map 权威值回填（build_chapter 末尾），不从子节点重算，
            # 否则无编号条目 / 空 section 的章会被塌缩回 page_start（实测 Ch14: 377→377，
            # 应为 375–398）。章节内部子区间仍由递归决定。书根（type=-1）继续在此聚合章区间。
            return int(self.page_end)
        self.page_start = min(c.page_start for c in self.sub_sec)
        self.page_end = max(c.page_end for c in self.sub_sec)
        return int(self.page_end)


class BookStructure:
    """book_structure.json 的加载 / 保存 / 查询门面。"""

    JSON_NAME = "book_structure.json"

    def __init__(self, root: StructureNode, book_dir: Optional[str] = None,
                 source_path: Optional[str] = None):
        self.root = root
        self.book_dir = book_dir
        self.source_path = source_path

    # ---- 构造辅助 --------------------------------------------------------
    @classmethod
    def new_book(cls, name: str, book_dir: Optional[str] = None) -> "BookStructure":
        """构造一个空书对象（根节点 key=-1, type=-1, name=书名）。"""
        root = StructureNode(key=ROOT_KEY, type=ROOT_TYPE, name=name,
                             page_start=0, page_end=0, sub_sec=[])
        return cls(root=root, book_dir=book_dir)

    # ---- 加载 / 保存 -----------------------------------------------------
    @classmethod
    def load(cls, ext_dir: str, book_dir: Optional[str] = None) -> Optional["BookStructure"]:
        p = os.path.join(ext_dir, cls.JSON_NAME)
        if not os.path.exists(p):
            return None
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return None
        if not isinstance(d, dict):
            return None
        root = StructureNode.from_dict(d)
        return cls(root=root, book_dir=book_dir, source_path=p)

    def save(self, ext_dir: Optional[str] = None) -> str:
        """写回 book_structure.json（保存前重算书根页码）。返回写出路径。"""
        out_dir = ext_dir or (os.path.dirname(self.source_path) if self.source_path else None)
        if not out_dir:
            raise ValueError("save() requires ext_dir or a prior source_path")
        # 保存前重算书根页码（容器取末代子孙页）
        self.root.recompute_pages()
        p = os.path.join(out_dir, self.JSON_NAME)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.root.to_dict(), f, ensure_ascii=False, indent=2)
        self.source_path = p
        return p

    def dump_dict(self) -> Dict[str, Any]:
        return self.root.to_dict()

    # ---- 便捷查询 --------------------------------------------------------
    @property
    def name(self) -> str:
        return self.root.name

    @property
    def chapters(self) -> List[StructureNode]:
        return self.root.sub_sec

    def find_chapter(self, ch: Any) -> Optional[StructureNode]:
        return self.root.find_chapter(ch)

    def chapter_items(self, ch: Any, include_exercise: bool = False) -> List[StructureNode]:
        """返回某章下的编号项节点（StructureNode 列表）。"""
        node = self.find_chapter(ch)
        if node is None:
            return []
        return list(node.iter_items(include_exercise=include_exercise))
