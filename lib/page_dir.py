"""page_dir.py — 解析某章的 ``page_*.json`` 实际存放目录（多册书关键）。

单册书：page 文件就在 ``extract_dir`` 下，一切照旧。
多册书：各册的 page 文件放在各自子目录（``_extract/上册/``、``_extract/下册/``），
且**页码通常重新从 1 开始**（上册 1..516 与下册 1..455 并存）——同一个
``page_015.json`` 在两册里都存在。因此"读 extract_dir 下的 page_NNN.json"
在多册书上是**歧义动作**，默认会命中某一册（实测命中上册），把该册内容静默
挂到别的册的章上，且不报错。

所以：**凡是要读某章页原文的地方，都必须先按章解析出 page_dir**，不得直接用
``extract_dir``。本模块是该解析的唯一真源，供 extract / structure / verify
各流程共用。

契约侧配套：分章契约 ``ch{N}.json`` 顶层携带 ``page_dir`` 字段（相对
extract_dir 的子目录名，如 ``"上册"``；单册书为空字符串/缺省），由
``build_structure`` 写入。下游拿到契约节点即可用 :func:`node_page_dir`
还原目录，无需再查 chapter_map。
"""

import json
import os
import re

__all__ = [
    "PAGE_FILE_RE",
    "volume_dirs",
    "chapter_map_has_chapter",
    "chapter_map_spans",
    "resolve_page_dir",
    "rel_page_dir",
    "node_page_dir",
    "page_path",
]

PAGE_FILE_RE = re.compile(r"^page_(\d+)\.json$")


def volume_dirs(ext):
    """``ext`` 下所有「直接含 page_*.json」的子目录（按名称排序）。

    判据是「目录里真的有 page 文件」，不硬编码 ``上册``/``下册`` 这类名字——
    册数、命名均不限。单册书没有这类子目录，返回空列表。
    """
    if not os.path.isdir(ext):
        return []
    out = []
    for name in sorted(os.listdir(ext)):
        d = os.path.join(ext, name)
        if not os.path.isdir(d):
            continue
        try:
            if any(PAGE_FILE_RE.match(f) for f in os.listdir(d)):
                out.append(d)
        except OSError:
            continue
    return out


def chapter_map_has_chapter(cm_path, ch):
    """chapter_map.json 是否含指定章（兼容两种落盘格式）。

    格式 A（扁平）：``{"1": {"start": …}, "2": …}``
    格式 B（模型）：``{"chapters": [{"ch": 1, …}, …]}``
    任一格式命中即 True；文件缺失 / 不可解析返回 False。
    """
    if not os.path.exists(cm_path):
        return False
    try:
        with open(cm_path, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        return False
    if not isinstance(d, dict):
        return False
    key = str(ch)
    if key in d:
        return True
    for e in (d.get("chapters") or []):
        if isinstance(e, dict) and str(e.get("ch")) == key:
            return True
    return False


def chapter_map_spans(cm_path):
    """读 chapter_map 得 ``[(ch, start, end), ...]``（按章序）；两格式通吃。"""
    if not os.path.exists(cm_path):
        return []
    try:
        with open(cm_path, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        return []
    if not isinstance(d, dict):
        return []
    rows = []
    if isinstance(d.get("chapters"), list):
        for e in d["chapters"]:
            if isinstance(e, dict) and e.get("ch") is not None:
                rows.append((e.get("ch"), e.get("start"), e.get("end")))
    else:
        for k, v in d.items():
            if isinstance(v, dict) and "start" in v:
                rows.append((k, v.get("start"), v.get("end")))

    def _ord(r):
        try:
            return (0, int(r[0]), "")
        except (TypeError, ValueError):
            return (1, 0, str(r[0]))

    rows.sort(key=_ord)
    return rows


def resolve_page_dir(ext, ch=None):
    """解析章 ``ch`` 的 page_*.json 所在目录（绝对路径）。

    单册书：直接返回 ``ext``（等价于历史行为，零回归）。
    多册书：按证据优先级递减判定，任一步无法定论就落到下一步，全部无解才返回
    ``ext``（宁可退回旧行为，也不猜）：

      1. **分册自带 chapter_map** 声明的章集合（精确，首选）——每册的
         chapter_map 只列本册的章（实测上册 1-9 / 下册 10-18）；
      2. **页码回退边界**：按章序遍历顶层 chapter_map，某章 start 页小于上一章
         start 页 ⇒ 该章开启新的一册；
      3. **页区间包含**：本章 [start, end] 与各册实际页范围重叠最多者；
         重叠并列（无法区分）时判为不定，返回 ``ext``。

    🔴 不得用「章号阈值」之类魔数判分册：那是从单本书反推的过拟合，换一本分册点
    不同的书就静默选错分册，且不会报错。
    """
    vols = volume_dirs(ext)
    if not vols:
        return ext
    if len(vols) == 1:
        return vols[0]
    if ch is None:
        return ext

    # 1) 分册自带 chapter_map 的章集合（精确）
    for v in vols:
        if chapter_map_has_chapter(os.path.join(v, "chapter_map.json"), ch):
            return v

    key = str(ch)
    seq = chapter_map_spans(os.path.join(ext, "chapter_map.json"))

    # 2) 页码回退边界：章序下 start 变小 ⇒ 进入下一册
    vol_of = {}
    cur = 0
    prev = None
    for c, s, _e in seq:
        try:
            s_int = int(s)
        except (TypeError, ValueError):
            s_int = None
        if prev is not None and s_int is not None and s_int < prev:
            cur += 1
        vol_of[str(c)] = cur
        if s_int is not None:
            prev = s_int
    if key in vol_of and vol_of[key] < len(vols):
        return vols[vol_of[key]]

    # 3) 页区间包含：取与本章 [start, end] 重叠最多的分册（并列判不定）
    span = None
    for c, s, e in seq:
        if str(c) == key:
            try:
                span = (int(s), int(e))
            except (TypeError, ValueError):
                span = None
            break
    if span is not None:
        scored = []
        for v in vols:
            pages = []
            try:
                for f in os.listdir(v):
                    m = PAGE_FILE_RE.match(f)
                    if m:
                        pages.append(int(m.group(1)))
            except OSError:
                continue
            if not pages:
                continue
            lo, hi = min(pages), max(pages)
            ov = min(hi, span[1]) - max(lo, span[0]) + 1
            if ov > 0:
                scored.append((ov, v))
        if scored:
            scored.sort(key=lambda t: (-t[0], t[1]))
            if len(scored) == 1 or scored[0][0] > scored[1][0]:
                return scored[0][1]
    return ext


def rel_page_dir(ext, page_dir):
    """绝对 page 目录 → 相对 ``ext`` 的子目录名（写进契约的形态）。

    等于 ``ext`` 本身（单册书）时返回 ``""``——契约侧空串表示"就在 extract_dir"。
    """
    if not page_dir:
        return ""
    a = os.path.normpath(os.path.abspath(ext))
    b = os.path.normpath(os.path.abspath(page_dir))
    if a == b:
        return ""
    try:
        rel = os.path.relpath(b, a)
    except ValueError:
        return ""
    return rel if not rel.startswith("..") else ""


def node_page_dir(ext, node, ch=None):
    """由契约节点还原其 page 目录（绝对路径）。

    优先读节点自带的 ``page_dir`` 字段（build_structure 写入的相对子目录名）；
    缺失时按章号回退 :func:`resolve_page_dir`；再不行返回 ``ext``。
    因此老契约（无该字段）行为不变，新契约自描述。
    """
    rel = ""
    if isinstance(node, dict):
        rel = node.get("page_dir") or ""
        if ch is None:
            ch = node.get("key")
    if rel:
        d = os.path.join(ext, rel)
        if os.path.isdir(d):
            return d
    return resolve_page_dir(ext, ch)


def page_path(ext, page, ch=None, page_dir=None):
    """``page_*.json`` 的绝对路径（读页原文的统一入口）。

    ``page_dir`` 显式给出时直接用它（调用方已解析）；否则按 ``ch`` 解析。
    调用方应从契约字段取得目录后传入，避免多册书里的歧义读取。
    """
    d = page_dir or resolve_page_dir(ext, ch)
    return os.path.join(d, "page_%03d.json" % int(page))
