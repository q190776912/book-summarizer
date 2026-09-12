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
  ``sub_sec`` 顺序即书中实际顺序。整书单文件 ``book_structure.json`` 不是合法
  产物，不被读取（无兼容回退）。

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

from chapter_map import KIND_APPENDIX, KIND_CHAPTER, KIND_SUPPLEMENT

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
# 整书单文件 book_structure.json 不是合法产物：不做任何读取兼容，
# BookStructure.load 只认分章文件。
LEGACY_JSON_NAME = "book_structure.json"      # 仅用于报错提示（不读取）


_KIND_PREFIX = {KIND_CHAPTER: "ch", KIND_APPENDIX: "appendix",
                KIND_SUPPLEMENT: "supplement"}


def chapter_prefix(kind: Any = None) -> str:
    """kind → 名称前缀（``ch`` / ``appendix`` / ``supplement``）。

    🔴 2026-09-08 起 Supplement（补篇）不再被称作 appendix：Katok 书的
    Supplement（S.x.y 编号）是补篇而非附录。判据改为显式 ``kind``，
    只在缺失时回退「非数字 → appendix」（旧书零回归）。
    """
    try:
        k = int(kind)
    except (TypeError, ValueError):
        k = KIND_CHAPTER
    return _KIND_PREFIX.get(k, "appendix")


def chapter_kind(key: Any, kind: Any = None) -> int:
    """解析章的 kind（KIND_*）——与 :func:`chapter_label` 同一判据的唯一出口。"""
    return _resolve_kind(key, kind)


def _resolve_kind(key: Any, kind: Any) -> int:
    """``kind`` 显式优先 > 进程级 kind 注册表（由 chapter_map 灌注）
    > 形态回退（数字 → 章 / 非数字 → 附录）。"""
    if kind is not None:
        try:
            k = int(kind)
            if k in _KIND_PREFIX:
                return k
        except (TypeError, ValueError):
            pass
    k = _PRIMED_KINDS.get(str(key).strip())
    if k is not None:
        return k
    s = str(key).strip()
    return KIND_CHAPTER if (s[:1].isdigit() if s else False) else KIND_APPENDIX


def chapter_json_name(key: Any, kind: Any = None) -> str:
    """章 → 分章契约文件名：``ch{N}.json`` / ``appendix{X}.json`` /
    ``supplement{S}.json``。"""
    return f"{chapter_prefix(_resolve_kind(key, kind))}{key}.json"


def unit_dir_name(key: Any, kind: Any = None) -> str:
    """章 → 单元子目录名：``ch{N}`` / ``appendix{X}`` / ``supplement{S}``。"""
    return f"{chapter_prefix(_resolve_kind(key, kind))}{key}"


def chapter_label(key: Any, kind: Any = None) -> str:
    """章的显示标签 / 侧车文件名段：``ch{N}`` / ``appendix{X}`` / ``supplement{S}``。

    与 :func:`chapter_json_name` / :func:`unit_dir_name` 同一判据（见
    :func:`_resolve_kind`）。打印章号、拼接随章侧车文件名（ignore_* /
    manual_overrides_* / figure 文件基名等）一律经此函数——
    "ch" 只属于章，附录 appendix、补篇 supplement 各有其名。
    """
    return f"{chapter_prefix(_resolve_kind(key, kind))}{key}"


# ── 进程级 kind 注册表（由 chapter_map.json 灌注） ─────────────────────────
# 🔴 背景：kind 是 chapter_map 的属性，但 ``chapter_label`` 等 SSOT 的调用方
# （25 个文件 / 77 处）历来只传章号。逐处改签名风险远大于灌注一张表：入口脚本
# 启动时调用 :func:`prime_chapter_kinds` 一次， thereafter 全部调用点自动得到
# 正确前缀；未灌注时静默回退旧形态判据（零回归）。
_PRIMED_KINDS: Dict[str, int] = {}


def prime_chapter_kinds(extract_dir: Optional[str] = None) -> Dict[str, int]:
    """读 ``chapter_map.json`` 把 ``{num_str: kind}`` 灌进进程级注册表并返回它。

    幂等（重复调用只是重读）。文件缺失 / 损坏时返回既有内容（不抛）。
    """
    if not extract_dir:
        return dict(_PRIMED_KINDS)
    p = os.path.join(extract_dir, "chapter_map.json")
    if not os.path.isfile(p):
        return dict(_PRIMED_KINDS)
    try:
        from chapter_map import load_chapter_map_raw, iter_chapter_records
        for rec in iter_chapter_records(load_chapter_map_raw(p)):
            _PRIMED_KINDS[str(rec.get("num")).strip()] = int(rec.get("kind"))
    except Exception:
        pass
    return dict(_PRIMED_KINDS)


def chapter_json_path(ext_dir: str, key: Any) -> str:
    return os.path.join(ext_dir, OUT_SUBDIR, chapter_json_name(key))


def norm_chapter_key(key: Any) -> Any:
    """CLI / 字典键归一：数字章号（含 ``"11"``）→ ``int``；字母章号（附录 ``A/B…``）
    → 原串。与 :func:`_build_rng` 的键型对齐（数字章 ``int``、附录 ``str``），使
    附录章（如 ``A``）不会被误当成数字章 11、也不会被 ``int()`` 转换时崩溃。"""
    s = str(key).strip()
    try:
        return int(s)
    except (TypeError, ValueError):
        return s


def chapter_sort_key(key: Any):
    """章号排序键（与 :func:`_build_rng` 键型一致）：数字章 ``(0, int)``，字母/其它
    ``(1, str)``（附录排末尾）。供全量构建时 `sorted(rng, key=chapter_sort_key)`。"""
    try:
        return (0, int(str(key)))
    except (TypeError, ValueError):
        return (1, str(key))


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
            elif fn.startswith("supplement") and len(fn) > len("supplement.json"):
                keys.append(((1, 0, fn[10:-5]), fn[10:-5]))
            elif fn.startswith("appendix") and len(fn) > len("appendix.json"):
                keys.append(((1, 0, fn[8:-5]), fn[8:-5]))
    return [k for _, k in sorted(keys)]


def chapter_tag_map(root: Dict[str, Any]) -> Dict[str, List[str]]:
    """契约 → {条目/描述 key: [公式序标 tag, ...]}（单元级 tag 对账的真值源）。

    遍历分章契约树：容器（chapter / section）递归；带 key 的叶子节点
    （编号项 / exercise / description）收集其 `sub_sec` 内全部 `formula.tag`
    （含 proof 子节点内的公式），tag 按文档序排列；章/节直属的散落公式块
    归入章/节自身的 key。供 `gate_units` / flow 落账复核做单元级
    「缺失 / 编造」对账（Q 层是章级末步，单元粒度须提前拦）。
    """
    out: Dict[str, List[str]] = {}

    def _collect(n: Dict[str, Any], acc: List[str]) -> None:
        for c in n.get("sub_sec") or []:
            if not isinstance(c, dict):
                continue
            if c.get("tag"):
                acc.append(str(c["tag"]))
            elif "sub_sec" in c and (c.get("type") == "proof" or "key" not in c):
                _collect(c, acc)

    def _walk(n: Dict[str, Any]) -> None:
        # 章/节直属的散落公式块（不在任何条目内）归入容器自身 key
        acc = [str(c["tag"]) for c in (n.get("sub_sec") or [])
               if isinstance(c, dict) and c.get("tag")]
        if acc and n.get("key") is not None:
            out.setdefault(str(n["key"]), []).extend(acc)
        for c in n.get("sub_sec") or []:
            if not isinstance(c, dict):
                continue
            t = c.get("type")
            if t in _CONTAINER_TYPES:
                _walk(c)
            elif c.get("key") and t != "proof":
                acc2: List[str] = []
                _collect(c, acc2)
                if acc2:
                    out.setdefault(str(c["key"]), []).extend(acc2)

    _walk(root)
    return out


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
                 "consolidated", "letter_subs", "raw")

    # 内容块判定：attach_content 挂进 sub_sec 的 {"text"| "formula" | "image"}
    # 裸字典（无 key/type）。from_dict 遇到含内容块的子树时保留整个原始 dict
    # 到 node.raw，to_dict 原样吐回——否则内容块会被当默认节点解析、读写一轮
    # 即静默丢内容（Koopman 书实测）。
    _BLOCK_SIG = ("text", "formula", "image")

    def __init__(self, key: Any = ROOT_KEY, type: Any = ROOT_TYPE, name: str = "",
                  page_start: int = 0, page_end: int = 0,
                  sub_sec: Optional[List["StructureNode"]] = None,
                  consolidated: bool = False,
                  letter_subs: Optional[List[Dict[str, Any]]] = None,
                  raw: Optional[Dict[str, Any]] = None):
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
        # 原始 JSON 保真（含内容块/派生节点布局）。**只读语义**：一旦节点树被
        # 原地修改（回填条目 / 重排），调用方必须先 clear_raw_recursive() 丢弃
        # raw 并重建内容，再落盘——否则 raw 是过期视图。
        self.raw: Optional[Dict[str, Any]] = raw

    @classmethod
    def _has_blocks(cls, d: Dict[str, Any]) -> bool:
        sub = d.get("sub_sec") if isinstance(d, dict) else None
        if not isinstance(sub, list):
            return False
        for el in sub:
            if isinstance(el, dict) and not ("key" in el or "type" in el) \
                    and any(k in el for k in cls._BLOCK_SIG):
                return True
        return False

    # ---- 序列化 ----------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        if self.raw is not None:
            # 保真出口：完整契约（骨架+内容块）原样吐回，零信息损失。
            import copy as _copy
            return _copy.deepcopy(self.raw)
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
        raw = dict(d) if cls._has_blocks(d) else None
        node = cls(
            key=d.get("key", ROOT_KEY),
            type=d.get("type", ROOT_TYPE),
            name=d.get("name", ""),
            page_start=d.get("page_start", 0),
            page_end=d.get("page_end", 0),
            sub_sec=[cls.from_dict(x) for x in d.get("sub_sec", []) or []
                     if not (isinstance(x, dict) and not ("key" in x or "type" in x)
                             and any(k in x for k in cls._BLOCK_SIG))],
            consolidated=bool(d.get("consolidated", False)),
            letter_subs=list(d.get("letter_subs") or []) or None,
            raw=raw,
        )
        return node

    def clear_raw_recursive(self) -> None:
        """丢弃本节点及全部子孙的 raw 保真视图（原地修改节点树前必须调用，
        否则 to_dict 会吐回修改前的过期完整契约）。"""
        self.raw = None
        for c in self.sub_sec:
            c.clear_raw_recursive()

    # ---- 类型判定 --------------------------------------------------------
    def is_container(self) -> bool:
        """容器节点：递归 sub_sec，本身不作为编号项。书根 / chapter / section。"""
        return self.type in _CONTAINER_TYPES or self.key == ROOT_KEY or self.type == ROOT_TYPE

    def is_exercise(self) -> bool:
        return self.type == "exercise"

    def is_problem(self) -> bool:
        """问题节点（Lee 2e 章末 Problem；独立 problem 类型，2026-09-12）。"""
        return self.type == "problem"

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
            elif child.is_problem():
                # 🔴 问题节点一等公民（2026-09-12）：默认产出、纳入编号项校验
                # （A 层 truly_missing / B 层连续性），仅 consolidated 省略——
                # 与练习的 include_exercise 门控不同。
                if not child.consolidated:
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
    ``save`` 拆分写回各分章文件。无分章文件时 load 返回 None——整书单
    文件 ``book_structure.json`` 不被读取（无兼容回退）。
    """

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
        """聚合加载分章契约（唯一格式，2026-08-29 起不再回退旧单文件）。"""
        keys = list_chapter_keys(ext_dir)
        if not keys:
            return None
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

    def save(self, ext_dir: Optional[str] = None) -> List[str]:
        """拆分写回各分章文件（保存前重算书根页码）。返回写出的路径列表。"""
        out_dir = ext_dir or (self.book_dir if self.book_dir else None)
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
