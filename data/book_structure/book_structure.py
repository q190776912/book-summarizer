"""book_structure — 书结构契约的类型化数据模型（中间产物）。

设计（2026-08-29 用户最终确认，替代 2026-08-12 的全书单文件方案）
------------------------------
- **按章分文件，是结构契约的唯一真源**：
  ``<extract_dir>/book_structure/ch{N}.json``（数字章，如 ``ch1.json``）与
  ``<extract_dir>/book_structure/appendix{X}.json``（附录章，如 ``appendixA.json``），
  顶层即该章 ``chapter`` 节点（**无书根包装**）。
- 两阶段写同一文件：``build_structure`` 产出**纯骨架**（叶子 ``sub_sec=[]``），
  ``attach_content`` 挂入正文内容（description / proof 派生节点与
  text / formula / image 内容块）后**写回同一文件**。
- 节点 schema：``key / type / name / page_start / page_end / sub_sec``（递归）；
  ``sub_sec`` 顺序即书中实际顺序。全书单文件 ``book_structure.json`` 已废弃
  （历史书由 :meth:`BookStructure.load` 只读兼容回退）。

本模块是结构 JSON 的**唯一权威模型**：所有读写 / 遍历 / 回填都经本类，
脚本不再裸操作 json 字典（见 ``verify/script/structure_io.py``、
``verify/verbose_gates``、``verify/script/check_structure_completeness.py``）。
``load()`` 聚合各分章文件为内存书对象（root = 书根包装，供逐章消费的
verify / 回填使用）；``save()`` 拆分写回各分章文件。

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

# 派生节点类型（attach_content 产出，仅存在于分章内容契约；非编号项，
# verify 展平编号项基准时必须排除）
_DERIVED_TYPES = ("description", "proof")

# 分章契约的落位子目录与命名（数字章 ch{N}.json / 附录章 appendix{X}.json）
OUT_SUBDIR = "book_structure"
LEGACY_JSON_NAME = "book_structure.json"      # 旧版全书单文件（只读兼容）


def chapter_json_name(key: Any) -> str:
    """章号 → 分章契约文件名：数字章 ``ch{N}.json`` / 附录章 ``appendix{X}.json``。"""
    k = str(key)
    return f"ch{k}.json" if k[:1].isdigit() else f"appendix{k}.json"


def chapter_json_path(ext_dir: str, key: Any) -> str:
    return os.path.join(ext_dir, OUT_SUBDIR, chapter_json_name(key))


def _chapter_sort_key_fn(key: str):
    return (0, int(key), "") if key.isdigit() else (1, 0, key)


def list_chapter_keys(ext_dir: str) -> List[str]:
    """列出分章契约的章号（数字章在前按数值、附录字母章在后按字母）。"""
    sub = os.path.join(ext_dir, OUT_SUBDIR)
    keys = []
    if os.path.isdir(sub):
        for fn in os.listdir(sub):
            if not fn.endswith(".json"):
                continue
            if fn.startswith("ch") and fn[2:-5].isdigit():
                keys.append(((0, int(fn[2:-5]), ""), fn[2:-5]))
            elif fn.startswith("appendix") and len(fn) > len("appendix.json"):
                keys.append(((1, 0, fn[8:-5]), fn[8:-5]))
    return [k for _, k in sorted(keys)]


def _default_book_dir(ext_dir: str) -> str:
    """由 extract_dir 推书根目录（多册书 ext=_extract/<册> 时上溯两级）。"""
    d = os.path.abspath(ext_dir)
    parent = os.path.dirname(d)
    if os.path.basename(parent) == "_extract":
        return os.path.dirname(parent)
    return parent


class StructureNode:
    """结构树节点（书 / 章 / 节 / 条目 / 派生节点）。避免脚本裸操作 json。"""

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

    def is_derived(self) -> bool:
        """派生节点（description / proof，attach_content 产出）——非编号项。"""
        return self.type in _DERIVED_TYPES

    # ---- 遍历 / 查询 -----------------------------------------------------
    def iter_items(self, include_exercise: bool = False):
        """深度优先遍历，yield 非容器的编号项节点。

        校验（verify）口径：集中习题块的练习节点（consolidated=True）恒不产出；
        被保留的练习节点（consolidated=False）仅在 include_exercise=True 时产出、
        纳入编号项校验。默认 include_exercise=False → 排除全部练习（保持旧行为，
        待 extract 打 consolidated 标记后由 read_structure_items 切到 True）。
        派生节点（description / proof，仅存在于分章内容契约）不是编号项，恒不产出。
        """
        for child in self.sub_sec:
            if child.is_derived():
                continue
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
        容器自身的 page_start（节头所在页）参与 min：仅有晚页子项的空节
        （谷超豪《数学物理方程》ch2 §1 等）若只取子项最小页，会把节头页
        推迟到子项页，节区间失真。
        """
        if not self.sub_sec:
            return int(self.page_end)
        for c in self.sub_sec:
            c.recompute_pages()
        if self.type == "chapter":
            # 章级区间已按 chapter_map 权威值回填（build_chapter 末尾），不从子节点重算，
            # 否则无编号条目 / 空 section 的章会被塌缩回 page_start（实测 Ch14: 377→377，
            # 应为 375–398）。章节内部子区间仍由递归决定。
            return int(self.page_end)
        if self.key == ROOT_KEY or self.type == ROOT_TYPE:
            # 书根：自身页码是占位值（0,0），不参与聚合——书根页码 = 章区间的 min/max。
            self.page_start = min(int(c.page_start) for c in self.sub_sec)
            self.page_end = max(int(c.page_end) for c in self.sub_sec)
            return int(self.page_end)
        self.page_start = min([int(self.page_start)]
                              + [int(c.page_start) for c in self.sub_sec])
        self.page_end = max(int(c.page_end) for c in self.sub_sec)
        return int(self.page_end)


class BookStructure:
    """书结构契约的加载 / 保存 / 查询门面。

    ``load`` 聚合分章文件 ``ch{N}.json`` / ``appendix{X}.json`` 为内存书对象；
    ``save`` 拆分写回各分章文件。历史书无分章文件时回退读旧单文件
    ``book_structure.json``（只读兼容；此时 save 会拒绝——旧书须先迁移，
    对其重跑 ``build_structure`` + ``attach_content`` 生成分章文件）。
    """

    def __init__(self, root: StructureNode, book_dir: Optional[str] = None,
                 source_path: Optional[str] = None, legacy: bool = False):
        self.root = root
        self.book_dir = book_dir
        self.source_path = source_path
        self.legacy = legacy          # True = 回退自旧单文件（save 拒绝）

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
        """聚合加载分章契约；无分章文件时回退旧单文件（legacy，只读）。"""
        keys = list_chapter_keys(ext_dir)
        if keys:
            bd = book_dir or _default_book_dir(ext_dir)
            chapters = []
            for k in keys:
                with open(chapter_json_path(ext_dir, k), encoding="utf-8") as f:
                    chapters.append(json.load(f))
            ps = min(int(c.get("page_start") or 0) for c in chapters)
            pe = max(int(c.get("page_end") or 0) for c in chapters)
            name = os.path.basename(os.path.normpath(bd)) if bd else ""
            root = StructureNode(key=ROOT_KEY, type=ROOT_TYPE, name=name,
                                 page_start=ps, page_end=pe,
                                 sub_sec=[StructureNode.from_dict(c) for c in chapters])
            return cls(root=root, book_dir=bd,
                       source_path=os.path.join(ext_dir, OUT_SUBDIR))
        return cls._load_legacy(ext_dir, book_dir)

    @classmethod
    def _load_legacy(cls, ext_dir: str, book_dir: Optional[str] = None) -> Optional["BookStructure"]:
        p = os.path.join(ext_dir, LEGACY_JSON_NAME)
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
        return cls(root=root, book_dir=book_dir, source_path=p, legacy=True)

    def save(self, ext_dir: Optional[str] = None) -> List[str]:
        """拆分写回各分章文件（保存前重算书根页码）。返回写出的路径列表。

        legacy（回退自旧单文件、且书根无分章文件）时拒绝保存——旧书须先对其
        重跑 ``build_structure`` + ``attach_content`` 迁移为分章格式。
        """
        out_dir = ext_dir or (self.book_dir if self.book_dir else None)
        if self.legacy and not list_chapter_keys(out_dir or ""):
            raise ValueError(
                "legacy book_structure.json（旧单文件）不可写回；"
                "请对其重跑 build_structure + attach_content 迁移为分章契约。")
        if not out_dir:
            raise ValueError("save() requires ext_dir or a prior source_path")
        # 保存前重算书根页码（容器取末代子孙页）
        self.root.recompute_pages()
        out_sub = os.path.join(out_dir, OUT_SUBDIR)
        os.makedirs(out_sub, exist_ok=True)
        written = []
        for c in self.root.sub_sec:
            p = chapter_json_path(out_dir, str(c.key))
            with open(p, "w", encoding="utf-8") as f:
                json.dump(c.to_dict(), f, ensure_ascii=False, indent=2)
            written.append(p)
        self.source_path = out_sub
        return written

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
