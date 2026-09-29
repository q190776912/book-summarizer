"""附录 / 补篇**序标的印刷证据**判据（根治：无号附录不得伪造序标）。

背景（Shafarevich《Basic Algebraic Geometry 1》2026-09-29 实测）：本书附录印面标题
就是裸的 ``Algebraic Appendix``（目录页 / 标题页 / 页眉均无任何序标），但 chapter_map
把它顺着正文章号登记成了第 5 章，于是整条命名链长出伪造序标——契约
``appendix5.json``、单元目录 ``units/appendix5/``、成品 ``附录5_代数附录.md`` /
``Appendix5_Algebraic_Appendix.md``、H1 ``# Chapter 5: Algebraic Appendix``。
SKILL.md「附录命名总则」对此早有规定（无印刷序标 → chapter_map 键写裸 ``appendix``），
但**没有任何机械校验**：判据只写在文档里，靠人记得住。本模块把「序标必须有印面证据」
做成可机械判定的谓词，供 ``config/verify_config/make_config.py``（chapter_map 的最早
消费点）接成 fail-closed 硬闸。

判据（保守，宁漏报不误报；只对 **阿拉伯数字序标** 生效）：
* 序标为空（键 == kind 前缀词）→ 本就是裸名形态，无需证据，直接通过。
* 序标是字母/罗马字（A、B、S、I…）→ **不判**：跨书普查实测这类序标的印刷形态多样
  （Lee 只印 ``A. Point-Set Topology``、Arnold 中译本印 ``附录1`` 而登记成 A…P），
  要求「附录词 + 字母相邻」会打成一片假阳；伪造序标的成因本来也不在这里。
* 数字序标须在该章页窗 **+ 前置目录区**的 OCR 文字层里找到
  **「附录/补篇词 + 该数字」相邻共现**的证据：``Appendix 5`` / ``附录三`` /
  ``5. Appendix`` / ``Supplement 2``。命中 = 印面确实印了这个号。
* 词表按 kind 分流（附录 / appendices / 补篇 / supplement / 补编 / 增补），
  阿拉伯数字序标同时接受中文数目字（附录三 = 附录 3）。
* 取证面（页窗 + 前置目录）全无可读文字 → 同样不通过（无法自证即拦截）。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

# kind → 印面词（KIND_APPENDIX=2 / KIND_SUPPLEMENT=3）
_WORDS = {
    2: r"appendi(?:x|ces)|appendixes|附录|附\s*录",
    3: r"supplements?|补篇|补编|增补",
}

_CN_NUM = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
           6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}

_SEP = r"[\s\.\,::：、\-—\(\)]*"


def ordinal_forms(ordinal: str) -> List[str]:
    """序标的可接受印面写法（阿拉伯数字 ↔ 中文数目字）。"""
    s = str(ordinal or "").strip()
    out = [s] if s else []
    if s.isdigit() and int(s) in _CN_NUM:
        out.append(_CN_NUM[int(s)])
    return out


def evidence_pattern(ordinal: str, kind: int) -> Optional[re.Pattern]:
    """「kind 词与序标相邻」的正则（两个方向都认）。"""
    word = _WORDS.get(int(kind or 2))
    forms = ordinal_forms(ordinal)
    if not word or not forms:
        return None
    alt = "|".join(re.escape(f) for f in forms)
    rx = (r"(?:%s)\s*%s(?:%s)|(?:%s)%s\s*(?:%s)"
          % (word, _SEP, alt, alt, _SEP, word))
    return re.compile(rx, re.IGNORECASE)


def page_text(blob: Dict[str, Any]) -> str:
    """page_*.json → 纯文字层文本（公式 latex 不参与，序标印在标题/页眉里）。"""
    parts = []
    for blk in (blob.get("text") or []):
        if isinstance(blk, dict):
            parts.append(str(blk.get("text") or ""))
    return "\n".join(parts)


def window_text(extract_dir: str, start: Any, end: Any,
                page_dir: Optional[str] = None) -> str:
    """按页窗拼文字层（缺页静默跳过，由调用方按 has_text 判断能否裁定）。"""
    base = os.path.join(extract_dir, page_dir) if page_dir else extract_dir
    out = []
    try:
        lo, hi = int(start), int(end)
    except (TypeError, ValueError):
        return ""
    for p in range(lo, hi + 1):
        fp = os.path.join(base, "page_%03d.json" % p)
        if not os.path.isfile(fp):
            continue
        try:
            with open(fp, encoding="utf-8-sig") as f:
                out.append(page_text(json.load(f)))
        except Exception:
            continue
    return "\n".join(out)


def evidence_text(extract_dir: str, start: Any, end: Any,
                  page_dir: Optional[str] = None) -> str:
    """取证文本 = 该章页窗 **+ 前置目录区**（页 1..start-1，至多 30 页）。

    目录页常写 ``Appendix 5  …  283`` 而正文标题页只印裸标题（或反之），只查页窗
    会把「印面确实有序标」的书误判成伪造——取证面必须覆盖两个独立来源。
    """
    try:
        s = int(start)
    except (TypeError, ValueError):
        s = 1
    front = window_text(extract_dir, 1, max(1, min(s - 1, 30)), page_dir=page_dir)
    return front + "\n" + window_text(extract_dir, start, end, page_dir=page_dir)


def appendix_ordinal_problems(records: List[Dict[str, Any]],
                              extract_dir: str) -> List[str]:
    """纯函数判据：返回 chapter_map 记录里「附录/补篇**阿拉伯数字**序标无印面证据」的问题行。

    ``records`` = ``iter_chapter_records`` 的规范记录（含 num/kind/start/end）。

    🔴 判据只对 **数字序标** 生效（跨书普查实测后收窄，见
    ``_calib_appendix_ordinal_gate`` 记录）：伪造序标的真实成因就是「顺着正文章号
    往下编」（本书 ch5 / Rosen 14-16），而字母序标（A/B/S…）是操作者照印面抄的
    记法，其印刷形态多样（Lee《流形导论》正文标题只印 ``A. Point-Set Topology``、
    Arnold 中译本印 ``附录1`` 而登记成 A…P），一律要求「附录词 + 字母相邻」会把
    合法书打成假阳。数字序标仍然必须给出证据：「附录/补篇词 + 该数字」相邻共现，
    页窗与前置目录区两处取证；取不到 = FAIL。页窗完全没有文字层 → 也 FAIL
    （无法自证清白即拦截，fail-closed）。
    """
    from data.book_structure.book_structure import chapter_ordinal  # 延迟：避免环依赖

    problems: List[str] = []
    for rec in records:
        kind = int(rec.get("kind") or 1)
        if kind not in (2, 3):
            continue
        num = rec.get("num")
        if chapter_ordinal(num, kind) == "":       # 裸名形态：无需证据
            continue
        if not str(num).strip().isdigit():         # 字母/罗马序标：不判（见 docstring）
            continue
        rx = evidence_pattern(num, kind)
        if rx is None:
            continue
        txt = evidence_text(extract_dir, rec.get("start"), rec.get("end"),
                            page_dir=rec.get("page_dir"))
        if not txt.strip():
            problems.append(
                "章「%s」(kind=%s, 数字序标 %r) 页窗 %s-%s 及其前置目录区取不到任何文字层，"
                "无法证明该序标印在书里：请按印刷页眉/标题页/目录核实，"
                "确无序标则把 chapter_map 该章键写成裸 %r"
                % (rec.get("name") or "", kind, num, rec.get("start"),
                   rec.get("end"), "appendix" if kind == 2 else "supplement"))
            continue
        hits = [m.group(0).strip() for m in rx.finditer(txt)]
        if not hits:
            problems.append(
                "章「%s」(kind=%s, 数字序标 %r) 在页窗 %s-%s 与前置目录区的印刷文字层里"
                "**找不到该序标的任何印刷证据**（附录/补篇词与数字相邻共现）："
                "数字序标通常来自「顺着正文章号往下编」这种伪造（实测产出 "
                "附录5_*.md / Appendix5_*.md 整条假号链）。若印面确有此号请核对页窗"
                "是否覆盖标题页/目录页；否则 chapter_map 该章键须写成裸 %r"
                "（SKILL.md 附录命名总则），或改抄印面字母序标"
                % (rec.get("name") or "", kind, num, rec.get("start"), rec.get("end"),
                   "appendix" if kind == 2 else "supplement"))
    return problems
