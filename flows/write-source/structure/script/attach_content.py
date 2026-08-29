"""attach_content.py — structure 子流程 Step 5：正文内容化 + 按章拆分契约

职责（2026-08-29 用户需求）
--------------------------
把「描述信息 + 每个定理/定义/练习等条目的文字与公式内容」按**文档顺序**挂进结构契约的
``sub_sec``，并**按章拆分**落盘，解决全书单文件内容化后过大的问题：

  * **分章契约 = 结构契约唯一真源**（2026-08-29 起：``ch{N}.json`` /
    ``appendix{X}.json``，全书单文件已废弃）：``build_structure`` 产出纯骨架后，
    本脚本读入骨架、挂入正文内容并**写回同一文件**——verify（data_provider / B/D
    层）经 ``BookStructure.load`` 聚合读取分章文件为编号项基准。
  * 分章契约 ``sub_sec`` 内按文档顺序混合三类元素——
      * 结构节点：与单文件同 schema（key/type/name/page_start/page_end/sub_sec）；
      * ``description`` 节点：**与定理同级的描述信息**——书中大段不属于定义/定理、
        没有序标的散文（章首序言 / 节导语 / 条目证明后的尾随段落），聚合为一个节点
        （合成 key ``D{n}``，章内文档序；name 为空；页码为所含块的页区间）；
      * ``proof`` 节点：条目内的**证明子节点**——正文块流中出现证明标记
        （PROOF / Proof / Solution / 证明 / 证： / 解：…）即开启，至 QED 收尾
        （□ / 口 / ∎ / 证毕 / Q.E.D. / \\square…）或块流末尾收束；
        合成 key ``{条目key}-P{n}``，name 为标记原文；statement 与 proof 保序；
      * 内容块：``{"text": "<段落文字>", "line_start": true, "indent": 2.0}``、
        ``{"formula": "<LaTeX>", "display": true|false}``
        （``display: true`` = 行间公式 / 独立占一行或多行；``false`` = 行内公式）、
        ``{"image": "<裁剪图路径>"}``（图检测产物，路径相对 ``<extract_dir>``；
        按 ``figure_index.json`` 的 page/bbox 并入阅读序，无图管线则为零图片块）。
    description / proof 为**派生节点**：非编号项，verify 展平编号项基准时
    排除（``StructureNode.iter_items`` / :func:`_structural_fp`）。

数据来源与门控
--------------
  * ``page_*.json``（MM Repair 写回后的版本）——``formulas[].cls`` 0=embedded（行内）
    / 1=isolated（行间），``latex`` 为公式内容；``text[].poly`` 定位阅读顺序。
  * 🔴 与 ``build_structure`` 同一硬闸：缺 ``_extraction_done.json``（MM Repair 未
    真完成）时拒绝运行——内容必须来自修复后的页面，否则 OCR 噪声直接污染写作草稿。
  * 结构节点锚点（item 用 ``build_structure._item_pos``、section 用
    ``build_structure._find_title_pos``）复用 build_chapter 同款定位逻辑，保证
    「内容块归到哪个节点」与骨架构建时的阅读顺序一致。

噪声过滤与结构化（尽力而为，草稿仍须 agent 调整）
--------------------------------------------------
  * 跨页边缘重复行（页眉 / 页脚 / 版权行）→ 丢弃；
  * 全章过半页面重复的行（running head 变体）→ 丢弃；
  * 页面极端边缘的纯数字短行（页码）→ 丢弃；
  * 行内公式（MFD ``cls=0``）按 x 位置拼回宿主文本行，恢复行内阅读顺序；
  * 条目 / 小节的首部文本块按序匹配契约 ``name`` 的归一化前缀时剥离印刷标题
    （宁重复不误删）；
  * 证明标记 / QED 识别失败时**不拆**（宁整不碎）——proof 聚合只在高置信匹配时发生。

新鲜度（供 render_draft 自动续挂）
----------------------------------
  * :func:`fingerprint_matches` 比较单文件与分章文件的**结构指纹**（全部结构节点
    的 type/key/page 序列，忽略内容块）；单文件因回填 / restructure 变化后指纹
    不再匹配 → render_draft 自动对过期章重跑 attach。
  * 任何回填（``check_structure_completeness --backfill``）或
    ``restructure_by_ocr --apply`` 之后**必须重跑本脚本**（或直接跑 render_draft，
    由其自动续挂），否则分章内容契约相对结构契约过期。

用法
----
    python flows/write-source/structure/script/attach_content.py <extract_dir> [ch ...] [--force]
    # 不传 <ch> 即全部章；--force 跳过指纹比对强制重挂
"""
import bisect
import json
import os
import re
import statistics
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

sys.stdout.reconfigure(encoding="utf-8")

from page_json import PageJson
from data.book_structure.book_structure import (chapter_json_path,
                                                list_chapter_keys,
                                                _DERIVED_TYPES)
import build_structure as _bs

OUT_DIR_NAME = "book_structure"

# 内容块判定：块 dict 只含这些键（无 key/type），与结构节点天然可区分
_BLOCK_KEYS = ("text", "formula", "display")


def _is_block(el):
    """sub_sec 元素是否为内容块（结构节点必有 key/type，内容块只有 text/formula/image）。"""
    return isinstance(el, dict) and ("text" in el or "formula" in el or "image" in el) \
        and "key" not in el and "type" not in el


def _norm(s):
    """归一化：小写 + 去全部非字母数字（OCR 标点/空格噪声不影响前缀比较）。"""
    return re.sub(r"[\W_]+", "", (s or "").lower())


# ---------------------------------------------------------------------------
# 内容块收集（page_*.json → 阅读序块流）
# ---------------------------------------------------------------------------
def _poly_box(poly):
    """8 值 poly → (x0, y0, x1, y1)；退化时返回 None。"""
    try:
        xs = [float(poly[i]) for i in (0, 2, 4, 6)]
        ys = [float(poly[i]) for i in (1, 3, 5, 7)]
    except (TypeError, ValueError, IndexError):
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _splice_inline(texts, formulas):
    """把行内公式（cls=0）按 x 位置拼接进其所属文本行，恢复行内阅读顺序。

    MFD 对行内公式独立裁剪 + MFR 识别 latex，而 OCR 同时整行读出（公式片段在
    文本行内呈乱码）——两者天然并存。若按 y 顶边全局排序，行内公式 bbox 稍高，
    会整体堆到所在文本行之前/之后，阅读顺序被打乱。此处对每个行内公式找
    「垂直重叠 ≥45% 且水平被包含（容差 40px）」的文本行，按 x 比例定位到该行
    文本的相应字符位置（非 CJK 文本吸附到最近词边界），把文本行拆成
    [前段, 公式, 中段, 公式, …, 后段]。找不到宿主行的公式保持独立块
    （宁重复不丢内容）；行间公式（display）不参与拼接、原样返回。
    """
    display_kept = []
    embedded = {}   # id(text_block) -> [(fx_center, latex), ...]
    inline = []
    for f in formulas:
        if f.get("display"):
            display_kept.append(f)
            continue
        fx0, fy0, fx1, fy1 = f["x"], f["y"], f["x1"], f["bottom"]
        fh = max(fy1 - fy0, 1.0)
        best, best_ov = None, 0.0
        for t in texts:
            ov = min(fy1, t["bottom"]) - max(fy0, t["y"])
            if ov < 0.45 * min(fh, max(t["bottom"] - t["y"], 1.0)):
                continue
            if fx0 < t["x"] - 40.0 or fx1 > t["x1"] + 40.0:
                continue
            if ov > best_ov:
                best, best_ov = t, ov
        if best is None:
            inline.append(f)
            continue
        embedded.setdefault(id(best), []).append(
            ((fx0 + fx1) / 2.0, f["latex"]))
    out = []
    for t in texts:
        ems = embedded.pop(id(t), None)
        if not ems:
            out.append(t)
            continue
        ems.sort(key=lambda e: e[0])
        txt = t["text"]
        width = max(t["x1"] - t["x"], 1.0)
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", txt))
        segs, prev = [], 0
        for fx, latex in ems:
            pos = int(round(min(max((fx - t["x"]) / width, 0.0), 1.0) * len(txt)))
            if not has_cjk:
                # 吸附到最近词边界（空格/标点），避免把英文单词切成两半
                radius = min(8, max(len(txt) // 6, 1))
                cands = [i for i in range(max(0, pos - radius),
                                          min(len(txt), pos + radius))
                         if i > prev and not _norm(txt[i])]
                if cands:
                    pos = min(cands, key=lambda i: abs(i - pos))
            pos = max(pos, prev)
            segs.append({"page": t["page"], "y": t["y"], "x": t["x"],
                         "bottom": t["bottom"], "kind": "text",
                         "text": txt[prev:pos].strip()})
            segs.append({"page": t["page"], "y": t["y"], "x": t["x"],
                         "bottom": t["bottom"], "kind": "formula",
                         "latex": latex, "display": False})
            prev = pos
        segs.append({"page": t["page"], "y": t["y"], "x": t["x"],
                     "bottom": t["bottom"], "kind": "text",
                     "text": txt[prev:].strip()})
        out.extend(s for s in segs if s.get("text") or "latex" in s)
    out.extend(inline)
    out.extend(display_kept)
    return out


_FIG_INDEX_CACHE = {}
_EXTRACT_REL_PREFIX = {}


def _extract_rel_prefix(ext):
    """<extract_dir> 相对书根目录的前缀（如 ``_extract`` / ``_extract/上册``）——
    图片路径写成书根相对，最终 md 落书根即可直接渲染。"""
    if ext not in _EXTRACT_REL_PREFIX:
        book_dir = os.path.dirname(os.path.abspath(ext.rstrip("/\\"))) or "."
        _EXTRACT_REL_PREFIX[ext] = os.path.relpath(
            os.path.abspath(ext), book_dir).replace("\\", "/")
    return _EXTRACT_REL_PREFIX[ext]


def _figure_blocks(ext, page):
    """page 上检测到的图片 → 内容块流元素（kind=image，内容即裁剪图路径）。

    来源 ``<extract_dir>/figure_index.json``（图检测 + 分配产物，extract Step 5）：
    ``file`` 为相对 ``<extract_dir>`` 的裁剪图路径，``bbox`` 定位阅读顺序。
    无图管线产物（书无图 / 未跑图检测）时返回空——分章契约零图片块。
    """
    cache = _FIG_INDEX_CACHE
    if ext not in cache:                 # 按 extract 目录缓存（同进程多书不串）
        fp = os.path.join(ext, "figure_index.json")
        try:
            with open(fp, encoding="utf-8") as f:
                idx = json.load(f)
        except Exception:
            idx = []
        cache[ext] = idx if isinstance(idx, list) else []
    out = []
    for fig in cache[ext]:
        if fig.get("page") != page:
            continue
        bbox = fig.get("bbox") or [0, 0, 0, 0]
        try:
            x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]),
                              float(bbox[2]), float(bbox[3]))
        except (TypeError, ValueError, IndexError):
            x0, y0, x1, y1 = 0.0, 0.0, 0.0, 0.0
        out.append({"page": page, "y": y0, "x": x0, "x1": x1, "bottom": y1,
                    "kind": "image",
                    "file": _extract_rel_prefix(ext) + "/" + (fig.get("file") or "")})
    return out


def _collect_blocks(ext, start, end):
    """收集 [start, end] 页全部内容块，页内按 (y, x) 稳定排序，跨页拼接。

    返回 (blocks, page_height)；page_height 为全书观测到的最大 bottom（同一本书
    扫描页高一致；用全书值而非单页值，避免稀疏页页高被低估、页眉页脚落不进
    边缘区）。行内公式先经 :func:`_splice_inline` 拼回宿主文本行。
    """
    blocks = []
    for p in range(int(start), int(end) + 1):
        fp = os.path.join(ext, "page_%03d.json" % p)
        if not os.path.exists(fp):
            continue
        try:
            pg = PageJson.load(fp)
        except Exception:
            continue
        texts, disp = [], []
        for b in pg.text_blocks:
            if not isinstance(b, dict):
                continue
            t = (b.get("text") or "").strip()
            if not t:
                continue
            box = _poly_box(b.get("poly") or [])
            x0, y0, x1, y1 = box if box else (0.0, 0.0, 0.0, 0.0)
            texts.append({"page": p, "y": y0, "x": x0, "x1": x1,
                          "bottom": y1, "kind": "text", "text": t})
        for f in pg.formulas:
            if not isinstance(f, dict):
                continue
            latex = (f.get("latex") or "").strip()
            if not latex:
                continue
            bbox = f.get("bbox") or [0, 0, 0, 0]
            try:
                fx0, fy0, fx1, fy1 = (float(bbox[0]), float(bbox[1]),
                                      float(bbox[2]), float(bbox[3]))
            except (TypeError, ValueError, IndexError):
                fx0, fy0, fx1, fy1 = 0.0, 0.0, 0.0, 0.0
            try:
                display = int(f.get("cls") or 0) == 1
            except (TypeError, ValueError):
                display = False
            blk = {"page": p, "y": fy0, "x": fx0, "x1": fx1,
                   "bottom": fy1, "kind": "formula",
                   "latex": latex, "display": display}
            disp.append(blk)
        page_blocks = _splice_inline(texts, disp)
        page_blocks.extend(_figure_blocks(ext, p))
        page_blocks.sort(key=lambda b: (b["y"], b["x"]))
        blocks.extend(page_blocks)
    page_height = max((b["bottom"] for b in blocks), default=0.0)
    return blocks, page_height


def _filter_noise(blocks, page_height, n_pages):
    """丢弃页眉 / 页脚 / 版权行 / 页码类噪声块（尽力而为；规则见模块 docstring）。"""

    def _edge(b):
        h = page_height
        if h <= 0:
            return False
        return b["y"] < 0.12 * h or b["bottom"] > 0.90 * h

    edge_pages, all_pages = {}, {}
    for b in blocks:
        if b["kind"] != "text":
            continue
        n = _norm(b["text"])
        if len(n) < 4:
            continue
        all_pages.setdefault(n, set()).add(b["page"])
        if _edge(b):
            edge_pages.setdefault(n, set()).add(b["page"])

    kept = []
    for b in blocks:
        if b["kind"] == "text":
            n = _norm(b["text"])
            if not n:
                continue
            if len(n) >= 4 and len(edge_pages.get(n, ())) >= 2:
                continue          # 页眉/页脚/版权行：跨页边缘重复
            if len(all_pages.get(n, ())) >= max(3, int(0.5 * n_pages)):
                continue          # running head 变体：全章过半页重复
            h = page_height
            if (h and n.isdigit() and len(n) <= 3
                    and (b["y"] < 0.06 * h or b["bottom"] > 0.94 * h)):
                continue          # 页码：极端边缘纯数字短行
        kept.append(b)
    return kept


# ---------------------------------------------------------------------------
# 锚点事件（结构节点 → (page, y)），复用 build_structure 的定位逻辑
# ---------------------------------------------------------------------------
_SEC_NO_PREFIX = re.compile(r'^[\dA-Z]+(?:\.[\dA-Z]+)*\s+(.*)$', re.DOTALL)


def _section_anchor(ext, node):
    page = int(node.get("page_start") or 0)
    name = (node.get("name") or "").strip()
    key = str(node.get("key") or "")
    title = name if key.startswith("U") else (_SEC_NO_PREFIX.match(name).group(1)
                                              if _SEC_NO_PREFIX.match(name) else name)
    if title:
        pos = _bs._find_title_pos(ext, title, page, page)
        if pos:
            return page, float(pos[1])
    return page, 0.0


def _item_anchor(ext, node):
    page = int(node.get("page_start") or 0)
    pos = _bs._item_pos(ext, {"key": node.get("key") or "",
                              "page": page,
                              "text": node.get("name") or ""})
    if pos and pos[0] == page:
        return page, float(pos[1])
    return page, 0.0


def _build_events(ext, ch_node):
    """深度优先收集 (pos, seq, node) 锚点事件；同位次以文档序（seq）稳定排序。"""
    events = []

    def add(node, page, y):
        events.append(((int(page), float(y)), len(events), node))

    def walk(node):
        for child in node.get("sub_sec") or []:
            if _is_block(child):
                continue
            t = child.get("type")
            if t == "section":
                add(child, *_section_anchor(ext, child))
                walk(child)
            elif t == "chapter":
                walk(child)
            else:
                add(child, *_item_anchor(ext, child))

    walk(ch_node)
    events.sort(key=lambda e: (e[0][0], e[0][1], e[1]))
    return events


# ---------------------------------------------------------------------------
# 标题剥离：条目/节正文开头的文本块若按序拼出契约 name（归一化前缀匹配）则剥去
# （防草稿正文重复印刷标题；行内公式保留——它们是校正内容；行间公式即停）
# ---------------------------------------------------------------------------
_STRIP_TAIL_PUNCT = " .:：．，,;；)）-–—"
# 标题的一部分可由行内公式承载（如 "Let $G$ be…"），文本段与 name 的对位允许
# 跳过少量归一化字符（被公式块"占用"的标题字）——上限防过度贪心错位。
_STRIP_MAX_SKIP = 12


def _strip_header(blocks, name):
    n_name = _norm(name)
    if len(n_name) < 4 or not blocks:
        return blocks
    pos = 0            # 已消耗的 name 归一化字符数
    out = []
    for b in blocks:
        if pos >= len(n_name):
            out.append(b)
            continue
        # 兼容两种块格式：内部流（kind="formula"+latex）与输出块（formula 键）
        is_fx = b.get("kind") == "formula" or "formula" in b
        if is_fx:
            if b.get("display"):
                out.append(b)       # 标题不会跨行间公式：保留该式并停止消耗
                pos = len(n_name)
            else:
                out.append(b)       # 行内公式保留（校正内容），标题消耗继续
            continue
        t = b.get("text") or ""
        n_t = _norm(t)
        if not n_t:
            out.append(b)
            continue
        # ① 完整匹配（块 ⊆ 剩余标题）：整段丢弃
        if n_name[pos:pos + len(n_t)] == n_t:
            pos += len(n_t)
            continue
        # ② 部分匹配（块覆盖剩余标题后还有正文）：按归一化位截断原文
        if n_t.startswith(n_name[pos:]):
            cnt, kept = 0, []
            for ch in t:
                if cnt >= len(n_name) - pos:
                    kept.append(ch)
                elif _norm(ch):
                    cnt += 1
            rest = "".join(kept).lstrip(_STRIP_TAIL_PUNCT)
            pos = len(n_name)
            if rest:
                out.append(dict(b, text=rest))
            continue
        # ③ 跳位对齐（标题中若干字由前面的行内公式承载）：允许小幅 skip
        matched = False
        for s in range(1, _STRIP_MAX_SKIP + 1):
            if pos + s >= len(n_name):
                break
            if n_name[pos + s:pos + s + len(n_t)] == n_t:
                pos += s + len(n_t)
                matched = True
                break
        if matched:
            continue
        # ④ 不匹配 → 立即停（宁重复不误删）
        pos = len(n_name)
        out.append(b)
    return out


# ---------------------------------------------------------------------------
# proof 子节点（证明）与 description 节点（与定理同级的描述信息）
# ---------------------------------------------------------------------------
_PROOF_MARKER = re.compile(
    r'^\s*[\*>]?\s*(?:PROOF|Proof|SOLUTION|Solution'
    r'|证明(?![的于了过程法])'      # 「证明 把…」「证明：」OK；「证明了/证明的」NG
    r'|证(?![明毕据实])'            # 「证 把…」「证：」OK；「证毕/证实验证」NG
    r'|解\s*[::：．。])')           # 「解：」
# 中文书「证」常与陈述同行被 OCR 合并（"……(2.13)证 把公式…"）：句末标点 / 右括号
# 之后的「证」为内联证明标记。宁整不碎，识别不了就不拆。
_CN_INLINE_PROOF = re.compile(
    r'(?<=[。．.!！?？)）\]])\s*(?:证(?![明毕据实])|证明(?![的于了过程法]))')
_QED_TEXT = re.compile(r'口|□|∎|证毕|Q\.?\s?E\.?\s?D', re.IGNORECASE)
_QED_LATEX = re.compile(r'\\(?:square|blacksquare|qed|QED|sqsupset)\b')


def _proof_name(marker):
    """证明节点 name = 标记原文（去收尾标点，如 'PROOF.' → 'PROOF'、'证明：' → '证明'）。"""
    m = _PROOF_MARKER.match(marker or "")
    return (m.group(0) if m else "").strip(" .:：．。*>")


def _is_qed(b):
    """QED 收尾块：独立短文本块（口 / □ / ∎ / 证毕 / Q.E.D.）或纯 QED 型公式。"""
    if b["kind"] == "text":
        t = (b.get("text") or "").strip()
        return bool(t) and len(t) <= 6 and bool(_QED_TEXT.search(t))
    latex = b.get("latex") or ""
    return len(latex) <= 40 and bool(_QED_LATEX.search(latex))


def _qed_cut(b):
    """内联 QED 切分：块中含「证毕 / Q.E.D.」时把块拆为（证明尾段, 余段）。

    返回 ``(proof_part, rest_part)``——``rest_part`` 为 None 表示整块即收尾
    （独立 QED 块 / 纯 QED 公式）；返回 None 表示本块不含 QED。
    """
    if b["kind"] == "formula":
        latex = b.get("latex") or ""
        if len(latex) <= 40 and _QED_LATEX.search(latex):
            return b, None
        return None
    t = b.get("text") or ""
    m = _QED_TEXT.search(t)
    if not m:
        return None
    if len(t.strip()) <= 6:
        return b, None                      # 独立 QED 块
    head, rest = t[:m.end()].rstrip(), t[m.end():].strip()
    rest_blk = dict(b, text=rest) if rest else None
    return dict(b, text=head), rest_blk


def _mark_line_geometry(blocks):
    """给 text 块打几何事实字段（``line_start`` / ``indent``），不烘焙段落判断。

    * ``line_start: true`` —— 本块从**新的一行**开始（与前一文本块无 y 重叠；
      页首块恒为新行；行内公式拼接产生的同线中段 / 同行 OCR 碎片**不写**此键）；
    * ``indent: <字高倍数>`` —— 新行的左缘缩进（相对本页正文左边界＝页内文本块
      最小 x0，除以页内文本块高中位数，保留 1 位小数）；仅当缩进 ≥ 0.3 字高时
      写出（更小视为顶格噪声）；
    * **两键都没有 = 续前一句**（同行片段或拼接段中段）。

    是否据此判新段落由消费方决定（如渲染器：``line_start`` 且 ``indent`` 落在
    首行缩进带内 → 另起一段）。尽力而为的几何事实，非段落真值。
    """
    by_page = {}
    for b in blocks:
        by_page.setdefault(b["page"], []).append(b)
    for bs in by_page.values():
        texts = [b for b in bs if b["kind"] == "text"]
        if not texts:
            continue
        left = min(b["x"] for b in texts)
        h = statistics.median(max(b["bottom"] - b["y"], 1.0) for b in texts)
        prev = None
        for b in bs:                      # bs 已按 (y, x) 页内阅读序排列
            if b["kind"] != "text":
                continue
            bh = max(b["bottom"] - b["y"], 1.0)
            if prev is None:
                same_line = False         # 页首块恒为新行
            else:
                ph = max(prev["bottom"] - prev["y"], 1.0)
                same_line = (min(b["bottom"], prev["bottom"])
                             - max(b["y"], prev["y"]) > 0.5 * min(bh, ph))
            if not same_line:
                b["line_start"] = True
                indent = (b["x"] - left) / h
                if indent >= 0.3:
                    b["indent"] = round(indent, 1)
            prev = b


def _to_content(b):
    """内部块流元素 → 输出内容块（text 块携带几何事实字段 line_start / indent）。"""
    if b["kind"] == "text":
        out = {"text": b["text"]}
        if b.get("line_start"):
            out["line_start"] = True
        if "indent" in b:
            out["indent"] = b["indent"]
        return out
    if b["kind"] == "image":
        return {"image": b["file"]}
    return {"formula": b["latex"], "display": bool(b["display"])}


def _make_description(key, blocks):
    """聚合散文块 → description 节点（与定理同级；无序标 → 合成 key、name 为空）。"""
    pages = [b["page"] for b in blocks]
    return {"type": "description", "key": key, "name": "",
            "page_start": min(pages), "page_end": max(pages),
            "sub_sec": [_to_content(b) for b in blocks]}


def _split_proofs(item_key, blocks):
    """条目正文块流拆分：证明标记开启 proof 子节点，至 QED 收束（无 QED 则至块流末尾）。

    返回 ``(elements, trailing)``：elements = 内容块与 proof 节点（保序，作条目
    ``sub_sec``）；trailing = 末个 proof 之后的残留正文块（调用方聚合为与条目同级的
    description 节点，插在该条目之后）。全程无证明标记时 trailing 为 None——正文
    全留条目内（宁整不碎：无边界信号不做描述/正文切分）。

    中文内联标记：块首无标记时，再按 :data:`_CN_INLINE_PROOF`（句末标点 / 右括号 +
    「证」边界）把合并行拆为「陈述尾段 + 证明标记」两块，Tail 作为证明起点。
    """
    elements, pending = [], []
    p_no = 0
    i, n = 0, len(blocks)
    while i < n:
        b = blocks[i]
        marker = None
        if b["kind"] == "text":
            txt = b.get("text") or ""
            if _PROOF_MARKER.match(txt):
                marker = txt                      # 块首标记：整块开启证明
            else:
                m = _CN_INLINE_PROOF.search(txt)  # 中文内联标记：拆块
                if m:
                    head = txt[:m.start()].rstrip()
                    if head:
                        pending.append(dict(b, text=head))
                    marker = txt[m.start():]
        if marker is not None:
            elements.extend(_to_content(x) for x in pending)
            pending = []
            i += 1
            pb = [dict(b, text=marker)] if marker != (b.get("text") or "") else [b]
            rest_blk = None
            while i < n:
                cut = _qed_cut(blocks[i])
                if cut is None:             # 未到 QED：块归证明
                    pb.append(blocks[i])
                    i += 1
                    continue
                proof_part, rest_blk = cut  # QED（独立块或内联切分）收束证明
                pb.append(proof_part)
                i += 1
                break
            p_no += 1
            pages = [x["page"] for x in pb]
            elements.append({"type": "proof",
                             "key": "%s-P%d" % (item_key, p_no),
                             "name": _proof_name(marker),
                             "page_start": min(pages), "page_end": max(pages),
                             "sub_sec": [_to_content(x) for x in pb]})
            if rest_blk is not None:        # 内联 QED 的余段 → 回到正文流（尾随/描述）
                pending.append(rest_blk)
        else:
            pending.append(b)
            i += 1
    if p_no == 0:
        return [_to_content(x) for x in blocks], None
    return elements, (pending or None)


# ---------------------------------------------------------------------------
# 主流程：单文件契约 + page json → 分章内容契约
# ---------------------------------------------------------------------------
def out_path(ext, ch_key):
    """分章契约路径（命名单点：数字章 ch{N}.json / 附录 appendix{X}.json）。"""
    return chapter_json_path(ext, ch_key)


def _to_skeleton(node):
    """把内容化契约还原为纯骨架（attach 的逆操作）：剥内容块与
    description / proof 派生节点，条目 sub_sec 清空——使 attach 幂等
    （对已挂内容的文件重复 attach 结果不变）。"""
    def walk(n):
        kids = []
        for c in n.get("sub_sec") or []:
            if _is_block(c) or c.get("type") in _DERIVED_TYPES:
                continue
            walk(c)
            if c.get("type") not in ("chapter", "section"):
                c["sub_sec"] = []          # 条目：正文由重建管线重新填充
            kids.append(c)
        n["sub_sec"] = kids
    walk(node)
    return node


def build_chapter_contract(ext, node):
    """纯函数：由骨架章节点 + page_*.json 构建该章内容化契约（含 stats）。

    返回 ``(chapter_dict, stats)``——stats 含 text/formula/image/proof/description
    计数与被噪声过滤丢弃的块数，供 `verify/script/check_content_completeness.py`
    复算比对（脚本确定性输出 => 可校验完整性）。
    """
    node = _to_skeleton(node)          # 幂等：已挂内容（重复 attach）先还原为骨架
    start, end = int(node.get("page_start") or 0), int(node.get("page_end") or 0)
    n_noise = [0]

    blocks, page_height = _collect_blocks(ext, start, end)
    kept = _filter_noise(blocks, page_height, max(1, end - start + 1))
    n_noise[0] = len(blocks) - len(kept)
    blocks = kept
    _mark_line_geometry(blocks)

    # 锚点分派：每块归「位置 ≤ 块位置的最后一个锚点事件」；最早事件之前 → 章首序言
    events = _build_events(ext, node)
    keys = [e[0] for e in events]
    buckets = {id(e[2]): [] for e in events}
    preamble = []
    for b in blocks:
        i = bisect.bisect_right(keys, (b["page"], b["y"])) - 1
        if i < 0:
            preamble.append(b)
        else:
            buckets[id(events[i][2])].append(b)

    # ── pass 1：剥离印刷标题 + 条目内证明拆分（proof 子节点）──
    own_blocks = {}      # id(容器节点) -> 章首/节首描述散文块
    trailing_map = {}    # id(条目节点) -> 末个 proof 之后的尾随正文块
    for e in events:
        tgt = e[2]
        blk = _strip_header(buckets.get(id(tgt)) or [], tgt.get("name") or "")
        if tgt.get("type") in ("chapter", "section"):
            own_blocks[id(tgt)] = blk
        elif tgt.get("type") == "exercise":
            # 练习的「证明：…」是题干任务而非证明过程 → 题面即正文，不拆 proof
            tgt["sub_sec"] = [_to_content(b) for b in blk]
        else:
            elements, trailing = _split_proofs(str(tgt.get("key")), blk)
            tgt["sub_sec"] = elements
            if trailing:
                trailing_map[id(tgt)] = trailing

    # ── pass 2：描述散文聚合为 description 节点（与条目同级；key 按文档序分配）──
    dcounter = [0]

    def next_dkey():
        dcounter[0] += 1
        return "D%d" % dcounter[0]

    def fill(n, own):
        # 自身描述散文 → description 节点置于最前；条目尾随散文 → 插条目之后；
        # 递归子容器，保证 key 严格按文档顺序递增。
        head = [_make_description(next_dkey(), own)] if own else []
        new_kids = []
        for child in list(n.get("sub_sec") or []):
            if not _is_block(child) and child.get("type") in ("chapter", "section"):
                fill(child, own_blocks.get(id(child)))
            new_kids.append(child)
            tr = trailing_map.get(id(child))
            if tr:
                new_kids.append(_make_description(next_dkey(), tr))
        n["sub_sec"] = head + new_kids

    fill(node, _strip_header(preamble, node.get("name") or "") if preamble else None)

    stats = {"text": 0, "formula": 0, "image": 0, "proof": 0,
             "description": 0, "noise_dropped": n_noise[0]}

    def _count(n):
        for c in n.get("sub_sec") or []:
            if _is_block(c):
                if "text" in c:
                    stats["text"] += 1
                elif "formula" in c:
                    stats["formula"] += 1
                elif "image" in c:
                    stats["image"] += 1
                continue
            t = c.get("type")
            if t in stats:
                stats[t] += 1
            _count(c)

    _count(node)
    return node, stats


def attach(ext, chapters=None):
    """对指定章（缺省全部分章骨架）挂入正文内容并**写回同一文件**。

    输入 = ``build_structure`` 产出的纯骨架 ``ch{N}.json``；输出 = 同路径的
    内容化契约（骨架 + description / proof / 内容块）。重跑 attach 会以页面
    原文重建内容（幂等）；build_structure 重跑会覆盖为骨架，须随后重跑本脚本。
    返回写出的文件路径列表。
    """
    keys = list_chapter_keys(ext)
    if chapters:
        want = {str(c) for c in chapters}
        keys = [k for k in keys if k in want]
    if not keys:
        raise SystemExit("[attach_content] 无分章骨架文件（%s/ch*.json）——"
                         "先跑 build_structure。" % os.path.join(ext, OUT_DIR_NAME))

    written = []
    for ch_key in keys:
        path = chapter_json_path(ext, ch_key)
        with open(path, encoding="utf-8") as f:
            node = json.load(f)
        node, stats = build_chapter_contract(ext, node)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(node, f, ensure_ascii=False, separators=(",", ":"))
            f.write("\n")
        print("ch%-4s ATTACH -> %s | text=%d formula=%d image=%d proof=%d "
              "description=%d noise_dropped=%d"
              % (ch_key, OUT_DIR_NAME + "/" + os.path.basename(path),
                 stats["text"], stats["formula"], stats["image"],
                 stats["proof"], stats["description"], stats["noise_dropped"]))
        written.append(path)
    return written


def _iter_blocks(node):
    for c in node.get("sub_sec") or []:
        if _is_block(c):
            yield c
        else:
            yield from _iter_blocks(c)


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    ext = argv[0]
    if not os.path.exists(os.path.join(ext, "_extraction_done.json")):
        print("[attach_content] BLOCKED: 缺 _extraction_done.json，MM Repair 未完成。")
        print("  内容块必须来自修复后的 page_*.json；先完成 MM Repair（与 build_structure 同闸）。")
        return 2
    try:
        chapters = [int(x) for x in argv[1:]]
    except ValueError:
        chapters = argv[1:]
    attach(ext, chapters or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
