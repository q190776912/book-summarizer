"""attach_content.py — structure 子流程 Step 5：正文内容化 + 按章拆分契约

职责
----
把「描述信息 + 每个定理/定义/练习等条目的文字与公式内容」按**文档顺序**挂进结构契约的
``sub_sec``，并**按章拆分**落盘：

  * **分章契约 = 结构契约唯一真源**（``ch{N}.json`` /
    ``appendix{X}.json``）：``build_structure`` 产出骨架后，
    本脚本读入骨架、挂入正文内容并**写回同一文件**——verify（data_provider / B/D
    层）经 ``BookStructure.load`` 聚合读取分章文件为编号项基准。
  * 分章契约 ``sub_sec`` 内按文档顺序混合三类元素——
      * 结构节点（key/type/name/page_start/page_end/sub_sec）；
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
        ``{"image": "<裁剪图路径>"}``（图检测产物，**书根相对 ``figure/xxx.png``**，
        figure 目录与总结 md 同级（2026-09-01 起）；按 ``figure_index.json`` 的
        page/bbox 并入阅读序，无图管线则为零图片块）。
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
from lib.numbering import (ordinal_depth, resolve_ordinal_code,
                           formula_paren_tag_re,
                           formula_tag_number, formula_trailing_tag, formula_tag_re)
from lib.page_dir import node_page_dir as _node_page_dir

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
                         "x1": t["x1"], "bottom": t["bottom"], "kind": "text",
                         "text": txt[prev:pos].strip()})
            segs.append({"page": t["page"], "y": t["y"], "x": t["x"],
                         "x1": t["x1"], "bottom": t["bottom"], "kind": "formula",
                         "latex": latex, "display": False})
            prev = pos
        segs.append({"page": t["page"], "y": t["y"], "x": t["x"],
                     "x1": t["x1"], "bottom": t["bottom"], "kind": "text",
                     "text": txt[prev:].strip()})
        out.extend(s for s in segs if s.get("text") or "latex" in s)
    out.extend(inline)
    out.extend(display_kept)
    return out


_FIG_INDEX_CACHE = {}


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
                    # 🔴 2026-09-01 起 figure 目录与总结 md 同级（书根 figure/）：
                    # file = figure/xxx.png 即书根相对路径，最终 md 落书根直接渲染。
                    "file": (fig.get("file") or "")})
    return out


def _collect_blocks(ext, start, end, ch=None, page_dir=None):
    """收集 [start, end] 页全部内容块，页内按 (y, x) 稳定排序，跨页拼接。

    `ch` 为章键（数字章 `"10"` / 字母章 `"A"`）——供 `formula_cfg` 分章路由
    （字母章读 `appendix` 段的 formula 配置，见其 docstring）。

    `page_dir` 为实际存放 page_*.json 的目录（多册书为对应分册子目录）；
    省略时等同 `ext`（单册书，保持历史行为）。

    返回 (blocks, page_height)；page_height 为全书观测到的最大 bottom（同一本书
    扫描页高一致；用全书值而非单页值，避免稀疏页页高被低估、页眉页脚落不进
    边缘区）。行内公式先经 :func:`_splice_inline` 拼回宿主文本行。
    """
    ncomp, scope, letter, bare = formula_cfg(ext, ch)
    _dir = page_dir or ext
    blocks = []
    # 跨页累积：已认领的公式编号（一个编号全书只挂一次，第二次出现是 OCR 碎片）
    claimed = set()
    for p in range(int(start), int(end) + 1):
        fp = os.path.join(_dir, "page_%03d.json" % p)
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
            _latex_raw = f.get("latex") or ""
            if isinstance(_latex_raw, dict):
                _latex_raw = _latex_raw.get("latex") or _latex_raw.get("latex_ocr") or ""
            latex = _latex_raw.strip() if isinstance(_latex_raw, str) else ""
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
        # 行间公式的 OCR 文本重复行剔除（2026-08-29 Koopman 书实测）：OCR 引擎对
        # 公式区域既输出 MFD latex 块、又输出一行乱码文本读数（如 "Usf =f os f e ."），
        # 其 poly 与公式 bbox 几乎重合——按几何重叠丢弃文本块，保留 latex 块。
        # 仅对 display 公式做重叠测试（行内公式宿主行必须保留，供 _splice_inline 拼接）。
        disp_boxes = [(b["x"], b["y"], b["x1"], b["bottom"])
                      for b in disp if b.get("display")]
        if disp_boxes:
            kept = []
            for tb in texts:
                # 🔴 末尾编号载体豁免重复行剔除：OCR 把「公式文本 + 右缘编号」读成
                # 一整块时，其 poly 与公式 bbox **大面积重合**（Koopman 实测
                # 5.12 / 7.17 / 20.9 重叠 78–100%），若按重复行删掉，该编号就
                # 永远挂不上（契约里直接消失）。保留它，交由 `_attach_formula_tags`
                # 摘取末尾编号并消耗掉该块。
                if formula_trailing_tag(tb["text"], ncomp, letter=letter,
                                        bare=bare):
                    kept.append(tb)
                    continue
                bx0, by0, bx1, by1 = tb["x"], tb["y"], tb["x1"], tb["bottom"]
                ta = max(bx1 - bx0, 0.0) * max(by1 - by0, 0.0)
                dup = False
                if ta > 0:
                    for fx0, fy0, fx1, fy1 in disp_boxes:
                        ix0, iy0 = max(bx0, fx0), max(by0, fy0)
                        ix1, iy1 = min(bx1, fx1), min(by1, fy1)
                        if ix1 > ix0 and iy1 > iy0:
                            inter = (ix1 - ix0) * (iy1 - iy0)
                            fa = max((fx1 - fx0) * (fy1 - fy0), 1e-6)
                            # 除以较大面积：须互相重合（garbled 读数行）才算 dup；
                            # 高文本块包含小公式 bbox 时 inter/ta < 0.5 → 保留正文
                            if inter / max(ta, fa) > 0.5:
                                dup = True
                                break
                if not dup:
                    kept.append(tb)
            texts = kept
        # 章首页版面家具剔除（作者单位 / 版权 / Check for updates）——必须在
        # _splice_inline 之前，否则家具块内的行内公式会被拼进上一行正文。
        texts, disp = _strip_furniture(texts, disp, p)
        page_blocks = _splice_inline(texts, disp)
        page_blocks.extend(_figure_blocks(ext, p))
        page_blocks.sort(key=lambda b: (b["y"], b["x"]))
        page_blocks = _attach_formula_tags(page_blocks, ncomp,
                                           letter=letter, bare=bare,
                                           scope=scope, ch=ch,
                                           claimed=claimed)
        blocks.extend(page_blocks)
    page_height = max((b["bottom"] for b in blocks), default=0.0)
    return blocks, page_height


_FORMULA_CFG_CACHE = {}


def formula_cfg(ext, ch=None):
    """本书公式序标配置 → ``(ncomp, scope, letter, bare)``；未配置时为 ``(None, None, False, True)``。

    🔴 **编号段数必须由 `verify_config.json` 的 `formula.type` 经
    `ORDINAL_DEPTH` 派生，不得硬编码**。各书形态差异极大（全语料实测）：
    ``(1)`` 节级重置 / ``(2.17)`` 章.号 / ``(11.1-1)`` 章.节-号 / ``(8.11a)``
    字母后缀 / 大量书右缘编号**不带括号**。段数错 → 整章编号一个都挂不上。

    🔴 **配置位置（新旧两版并存）**：`make_config.py` 现行版按
    ``{"ch": {...}, "appendix": {...}, "supplement": {...}}`` 分段落盘，
    `formula` 落在 `ch` 段内；早期版是扁平配置、`formula` 在顶层。本函数
    **两种都认**——先读顶层，缺失再回退 `ch` 段（正文体例）。漏掉回退会让
    分段落盘的书（如 Katok）取到空配置 → `ncomp=None` → 段数不限 → 把页码 /
    矩阵里的裸数字（``0`` / ``153`` / ``166``）当成公式编号挂上 tag，污染
    单元级 tag 对账真值。

    🔴 **分章路由（2026-09-14，Lee ISM 附录 letter-led 实测）**：`ch` 为字母
    章键（``"A"``/``"B"``…，非纯数字）时读 **`appendix` 段**的 `formula`（缺失
    回退顶层/`ch` 段——主配置 digit 形态对字母编号抽不到，零污染）。附录段的
    `formula.letter_ch: true` 置 ``letter=True``（`(A.3)` 字母章位形态）。

    `bare` 读 `formula.bare_number`（默认 True；显式 false 的书——如 Lee——
    裸排 `1-11` Problem 标签不可当编号，挂 tag 侧与 Q 层同口径）。
    """
    ck = _FORMULA_CFG_CACHE
    cache_key = (ext, None if ch is None else str(ch))
    if cache_key not in ck:
        ncomp = scope = None
        letter, bare = False, True
        try:
            with open(os.path.join(ext, "verify_config.json"),
                      encoding="utf-8-sig") as f:
                data = json.load(f) or {}
            sub = ("appendix"
                   if (ch is not None and not str(ch).isdigit()
                       and isinstance(data.get("appendix"), dict))
                   else None)
            fc = data.get("formula")
            if sub is not None:
                fc = data[sub].get("formula") or fc
            if not fc and isinstance(data.get("ch"), dict):
                fc = data["ch"].get("formula")
            fc = fc or {}
            ncomp = ordinal_depth(resolve_ordinal_code(fc.get("type")))
            s = fc.get("scope")
            if isinstance(s, int):
                scope = s
            letter = bool(fc.get("letter_ch"))
            bare = bool(fc.get("bare_number", True))
        except Exception:
            ncomp = scope = None
            letter, bare = False, True
        ck[cache_key] = (ncomp, scope, letter, bare)
    return ck[cache_key]


def tag_re(ext, bare=True, ch=None):
    """本书「独立成块的公式编号」锚定正则（供 attach 与完整性闸门共用）。"""
    ncomp, _scope, letter, _bare = formula_cfg(ext, ch)
    return formula_tag_re(ncomp, bare=bare, letter=letter)


def _attach_formula_tags(page_blocks, ncomp=None, letter=False, bare=True,
                         scope=None, ch=None, claimed=None):
    """把行间公式同行右缘的编号挂到公式块的 ``tag`` 键上（存**裸编号**），
    并从散文流剔除该文本块（纯版面锚点，不是正文）。

    编号形态（段数 / 括号 / 分隔符 / 字母后缀 / 字母章位）由 ``ncomp`` /
    ``letter`` 经 :func:`lib.numbering.formula_tag_re` 决定，调用方从
    ``formula_cfg(ext, ch)`` 取得——**绝不在此硬编码某一种编号样式**。
    ``bare=False``（config `formula.bare_number: false`）时只认带括号形态。

    判定（宁缺勿滥）：整块恰为一个编号，且同时满足两个几何条件：

      * **水平**：编号排在公式行的**右侧或左侧**——🔴 两种版式都实测存在，
        **不可只认一侧**：Koopman / 随机过程 / 实变函数等书编号在右缘，而
        Kreyszig / Introduction to Analytic Number Theory / PDE 等书编号在
        **左缘**（这批书用「只认右缘」的旧判据整章 0 命中）。
          - **右侧**：``x0 ≥ min(公式 x1 - 容差, 公式水平中点)``。MFD 对居中
            多行公式（``\\begin{array}`` 等）的 bbox 会横跨整行、把右缘编号列
            一并圈入，此时编号在 bbox 内部右侧而非其右方（Koopman 实测 18/80
            因此漏挂）。**裸排编号**要求更靠右（右侧 1/4）——裸数字与列表号 /
            脚注号无形态区别，只在"确实排在公式行最右端"时才认。
          - **左侧**：编号须**整块在公式 bbox 左缘之外**（``x1 ≤ 公式 x0 +
            容差``）。左缘正是这批书放编号的位置，但也正是列表号 / 小节号的
            位置，故只认"确实排在公式行左端外侧"的块。
      * **垂直**：与公式带**垂直有交集**（含相切，容差 0.2 倍行高的外扩），
        **或**垂直中心距 ≤ 行高 0.6 倍。中心距判据对居中编号有效；交集判据补上
        MFD bbox 偏上（带上下限 / 多行公式）导致编号落在下缘甚至略下方的情况。

    纯几何 + 文本判定，无状态，保证 check_content_completeness 的
    确定性复算两侧一致。

    🔴 **一块可挂多个编号**：多行公式组在原书里逐行编号，几何上这些编号都落在
    同一个（很高的）公式 bbox 内。全部合格编号按 y 升序一并挂上——``tag`` 取
    首个（既有单号语义不变），``tags`` 为完整列表（供单元级 tag 对账作真值）。

    🔴 **末尾编号**（OCR 把「公式文本 + 右缘编号」读成一整块，如
    ``'…dt.  (3.35)'``）也算编号锚点，但需额外护栏：该文本块必须与 display 公式
    **实质垂直重叠**（≥ 自身高度 60%）——它本就是公式的 OCR 读数行（实测真例
    91–100%）。散文行末尾的交叉引用（``…flow (6.20),``）与公式无重叠，据此排除。
    🔴 **一个编号只认一次**：``claimed`` 是跨页共享的「已认领编号」集合。同一
    编号在全书只应出现一次（章级编号书的编号唯一），故第二次出现必是 OCR 碎片
    或截断（实测 Koopman：p166 的 ``…=01.1.(6.7)`` 实为 ``(6.70)`` 的截断，
    真正的 (6.7) 在 p153）→ 不得再挂，否则制造假「缺编号」。
    """
    tags = []
    # 跨章守卫（与 Q 层 `norm().split('.')[0] == ch` 同口径）：章级编号书
    # （scope==2）中，只有首段 == 本章章号的编号才是「本章自带公式编号」；
    # 首段不等者要么是**跨章引用**（如第 3 章正文里的 "(2.1)"），要么是 OCR
    # 碎片（如指数 l-1 被误读成裸块 "2-1"），一律不得当作本章公式的锚点。
    # 仅对纯数字 / 单字母章键启用；裸 "appendix"/"supplement" 等多字符键沿用
    # 旧行为（无章号可比），book/section scope（1/3）不启用。
    _guard_head = None
    if scope == 2 and ch is not None:
        _cks = str(ch).strip()
        if _cks.isdigit() or (len(_cks) == 1 and _cks.isalpha()):
            _guard_head = _cks
    for b in page_blocks:
        if b["kind"] != "text":
            continue
        raw = (b["text"] or "").strip()
        num = formula_tag_number(raw, ncomp, letter=letter, bare=bare)
        trailing = None
        if num is None:
            # 编号粘在文本块末尾：OCR 把「公式文本 + 右缘编号」读成一整块
            tr = formula_trailing_tag(raw, ncomp, letter=letter, bare=bare)
            if tr is not None:
                num, trailing = tr[0], tr[1]
        if num is not None:
            if _guard_head is not None:
                head = re.split(r"[.\-–]", str(num).strip(), maxsplit=1)[0]
                if head.upper() != _guard_head.upper():
                    continue   # 跨章引用 / OCR 碎片：不挂为编号
            if trailing is None:
                tx = b["x"]                      # 独立编号块：整块就是编号
                paren = raw[:1] in "（("
            else:
                # 末尾编号：按字符数比例从右缘回推其横向位置
                frac = min(len(trailing) / max(len(raw), 1), 1.0)
                tx = b["x1"] - frac * max(b["x1"] - b["x"], 1.0)
                paren = trailing[:1] in "（("
            tags.append((b, num, paren, trailing is not None, tx))
    if not tags:
        return page_blocks
    consumed = set()
    for b in page_blocks:
        if b["kind"] != "formula" or not b.get("display") or "tag" in b:
            continue
        cy = (b["y"] + b["bottom"]) / 2.0
        hh = max(b["bottom"] - b["y"], 1.0)
        fw = max(b["x1"] - b["x"], 1.0)
        # 带括号：落在公式 bbox 右半侧即可（bbox 常横跨整行、把编号列圈进去）。
        # 裸排：要求更靠右（右侧 1/4）——裸数字与列表号 / 脚注号无形态区别，只在
        # 「确实排在公式行最右端」时才认；宽松到 1/4 是因为 MFD 对居中公式的 bbox
        # 常常横跨整行，此时右缘编号在 bbox 之内而非其右方（Kreyszig 实测：严格
        # 「bbox 右缘之外」判据下整章 0 命中）。
        x_paren = min(b["x1"] - 5.0, b["x"] + 0.5 * fw)
        x_bare = min(b["x1"] - 5.0, b["x"] + 0.75 * fw)
        x_left = b["x"] + 5.0
        hits = []
        for t, num, paren, trailing, tx in tags:
            if id(t) in consumed:
                continue
            # 已在别处认领过的编号不再挂（OCR 截断 / 碎片会造出重复编号）
            if claimed is not None and str(num) in claimed:
                continue
            ov = min(t["bottom"], b["bottom"]) - max(t["y"], b["y"])
            if trailing:
                # 🔴 末尾编号必须与 display 公式**实质垂直重叠**——该文本行正是
                # 公式的 OCR 读数行（实测真例 91–100% 自身高度）。散文行末尾的
                # 交叉引用（``…flow (6.20),``）与最近公式 ov<0，据此排除。
                if ov < 0.6 * min(max(t["bottom"] - t["y"], 1.0), hh):
                    continue
            else:
                tcy = (t["y"] + t["bottom"]) / 2.0
                if abs(tcy - cy) > 0.6 * hh and ov < -0.2 * hh:
                    continue
            on_right = tx >= (x_paren if paren else x_bare)
            on_left = t["x1"] <= x_left
            if not (on_right or on_left):
                continue
            hits.append((t, num))
        if hits:
            # 🔴 多行公式组（`\begin{array}` / aligned）在原书里**逐行编号**，而 MFD
            # 把它识别成**一个**公式块（bbox 纵向很高）。旧实现「一块只挂一个编号」，
            # 组内其余编号只能掉进散文 → 契约只认 1 个 tag，而 agent 在步骤 5 把
            # array 拆成逐条公式并各自保留原书编号 → 门控报大量**假「编造」**
            # （实测 Koopman ch3：块 y=[220,420] 内含 3.21+3.22，块 y=[692,819]
            # 内含 3.23+3.24+3.25）。改为块内全部合格编号按文档序（y 升序）一并
            # 挂上：`tag` 仍为首个（兼容既有单号语义），`tags` 为完整列表。
            hits.sort(key=lambda z: (z[0]["y"], z[0]["x"]))
            b["tag"] = hits[0][1]
            if len(hits) > 1:
                b["tags"] = [str(n) for _, n in hits]
            for t, num in hits:
                consumed.add(id(t))
                if claimed is not None:
                    claimed.add(str(num))
    if consumed:
        page_blocks = [b for b in page_blocks if id(b) not in consumed]
    return page_blocks


_FURNITURE_RE = re.compile(r'e-mail|springer nature', re.I)
_CHECKFOR_RE = re.compile(r'check\s*for\s*updat\w*', re.I)
_CHECKFOR_BLOCK_RE = re.compile(r'^\s*(?:Check\s*for\b\w*|updates?)\s*[.。\s]*$', re.I)
_TRAILING_URL_RE = re.compile(r'\s*(?:https?[:.\s]|www\.)\S+\s*(?:\d{1,4})?\s*$', re.I)


def _strip_furniture(texts, disp, page):
    """章首页版面家具剔除（2026-08-29 Koopman 书实测；须在 _splice_inline 之前
    执行——家具块里的行内公式（$(\bowtie)$、$@$ 等）否则会被拼进上一行正文）：

    ① ``Check for updates`` 小部件：合并进标题/摘要块时**就地剥离**，独立成块
       （``^Check for`` 开头）时整块丢弃；
    ② ``e-mail`` / ``Springer Nature`` 强标记块整块丢弃（作者单位、版权行）；
    ③ 以强标记块为种子做 y 带聚类（间距 ≤90px 合并，上外扩 80 / 下外扩 40px），
       带内其余文本块（作者名、单位、DOI 行）与**全部公式块**一并剔除——正文块
       都在带外。"""
    kept_texts, furn_boxes = [], []
    for tb in texts:
        t = tb["text"]
        if _CHECKFOR_RE.search(t):
            t = _CHECKFOR_RE.sub(" ", t)
        # 块尾 URL（版权 / DOI 行与正文合并的块）：URL + 可选尾随页码属家具，
        # 剥离尾部；参考文献条目的 URL 在块中部（后接下一条），不受影响。
        t = _TRAILING_URL_RE.sub(" ", t)
        t = re.sub(r"\s+", " ", t).strip()
        if not t:
            continue
        tb = dict(tb, text=t)
        if _CHECKFOR_BLOCK_RE.match(t):
            continue                # 独立成块的 Check for updates 小部件
        if _FURNITURE_RE.search(t):
            furn_boxes.append((tb["y"], tb["bottom"]))
            continue
        kept_texts.append(tb)
    if furn_boxes:
        furn_boxes.sort()
        clusters = []
        for lo, hi in furn_boxes:
            if clusters and lo - clusters[-1][1] <= 90.0:
                p = clusters[-1]
                clusters[-1] = (min(p[0], lo), max(p[1], hi))
            else:
                clusters.append((lo, hi))
        bands = [(lo - 80.0, hi + 160.0) for lo, hi in clusters]
        kept_texts = [tb for tb in kept_texts
                      if not any(lo <= (tb["y"] + tb["bottom"]) / 2.0 <= hi
                                 for lo, hi in bands)]
        disp = [fb for fb in disp
                if not any(lo <= (fb["y"] + fb["bottom"]) / 2.0 <= hi
                           for lo, hi in bands)]
    return kept_texts, disp


def _filter_noise(blocks, page_height, n_pages, ncomp=None, letter=False):

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
            # 页码：极端边缘纯数字短行。⚠️ 公式编号归一化后同为纯数字短串，
            # 排在页面下缘时会被误判为页码整块丢弃（2026-08-29 Koopman ch7
            # (7.13) 实测）→ 对**带括号**的编号豁免。裸排编号不豁免：它与页码
            # 无法区分（页码永远是裸数字），豁免会让页码重新漏进正文。
            h = page_height
            if (h and n.isdigit() and len(n) <= 3
                    and not formula_paren_tag_re(ncomp, letter=letter).match(
                        (b.get("text") or "").strip())
                    and (b["y"] < 0.06 * h or b["bottom"] > 0.94 * h)):
                continue
        kept.append(b)
    return kept


# ---------------------------------------------------------------------------
# 锚点事件（结构节点 → (page, y)），复用 build_structure 的定位逻辑
# ---------------------------------------------------------------------------
_SEC_NO_PREFIX = re.compile(r'^[\dA-Z]+(?:\.[\dA-Z]+)*\s+(.*)$', re.DOTALL)
_NUM_KEY_RE = re.compile(r'^[\dA-Z]+(?:\.[\dA-Z]+)+$')


def _section_anchor(ext, node, page_dir=None):
    page = int(node.get("page_start") or 0)
    name = (node.get("name") or "").strip()
    key = str(node.get("key") or "")
    title = name if key.startswith("U") else (_SEC_NO_PREFIX.match(name).group(1)
                                              if _SEC_NO_PREFIX.match(name) else name)
    y = _bs._numbered_heading_y(ext, key, page, page_dir=page_dir)
    if y is not None:
        return page, float(y)
    if title:
        pos = _bs._find_title_pos(ext, title, page, page, page_dir=page_dir)
        if pos:
            return page, float(pos[1])
    return page, 0.0


def _item_anchor(ext, node, page_dir=None):
    page = int(node.get("page_start") or 0)
    pos = _bs._item_pos(ext, {"key": node.get("key") or "",
                              "page": page,
                              "text": node.get("name") or "",
                              "type": node.get("type") or ""},
                        page_dir=page_dir)
    if pos and pos[0] == page and pos[1] is not None and pos[1] >= 0:
        return page, float(pos[1])
    # y=-1 是 _item_pos 的「整块丢失」哨兵：在 attach 事件流里必须落在
    # (page, 0.0)，否则会排到同页所有节头之前、吞掉/错失内容块。
    return page, 0.0


def _build_events(ext, ch_node, page_dir=None):
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
                add(child, *_section_anchor(ext, child, page_dir=page_dir))
                walk(child)
            elif t == "chapter":
                walk(child)
            else:
                add(child, *_item_anchor(ext, child, page_dir=page_dir))

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
# 章尾标题（🔴 2026-09-21 实测缺陷修复）：一章节末常挂「习题N / 思考题 / 内容提要 /
# 评注 / 小结 / 注记」等**非条目**尾料，且这些标题不带 定理/定义 序标 → 结构检测器
# 在其后不再产生锚点，末条目正文块流一路延伸到章末。若该末条目证明又没有显式 QED，
# `_split_proofs` 的「无 QED 则至块流末尾」逻辑会把整段尾料**吞进证明子节点**（实测
# 周民强《实变函数论》每章末条目都 REACHES_CH_END、例5-P1 吞 144-149 共 463 块）。
# 补救：证明扫描遇章尾标题即**收束**，标题及其后残留走既有 trailing→description 通道。
# 仅认「独立成行、以这些标题词开头」的块，避免误切正文里出现的同名子串。
_TAIL_HEADING = re.compile(
    r'^\s*(?:思考与练习|思考题|习题|练习|内容提要|本章小结|小结|重\s*要\s*提示|'
    r'评注|注\s*记|提\s*要)')


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


def _is_tail_heading(b):
    """块是否「章尾标题」（习题/思考题/内容提要/评注/小结/注记…）。

    判定收紧以免误切正文：须为 text 块、以标题词起头，且**独立成行**
    （line_start）或为**短标题行**（≤12 字，如 '习题3'/'注记127'）。
    """
    if b.get("kind") != "text":
        return False
    t = (b.get("text") or "").strip()
    if not t or not _TAIL_HEADING.match(t):
        return False
    return bool(b.get("line_start")) or len(t) <= 12


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
    out = {"formula": b["latex"], "display": bool(b["display"])}
    if b.get("tag"):
        out["tag"] = b["tag"]
    # 多行公式组逐行编号：`tags` 为该块携带的**全部**编号（文档序），`tag` 是首个。
    if b.get("tags"):
        out["tags"] = list(b["tags"])
    return out


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
            hit_tail = False
            while i < n:
                if _is_tail_heading(blocks[i]):
                    hit_tail = True
                    break  # 章尾标题：证明到此收束；其后全部转残留，不再扫描
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
            if hit_tail:                    # 遇章尾标题：其后全部转残留，停止再扫描
                pending.extend(blocks[i:])
                i = n
                break
        else:
            pending.append(b)
            i += 1
    if p_no == 0:
        ti = next((idx for idx, x in enumerate(blocks) if _is_tail_heading(x)), None)
        if ti is None:
            return [_to_content(x) for x in blocks], None
        # 无证明但含章尾标题：标题前留条目，标题及其后作残留（→ 同级 description）
        return [_to_content(x) for x in blocks[:ti]], (blocks[ti:] or None)
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


def build_chapter_contract(ext, node, page_dir=None):
    """纯函数：由骨架章节点 + page_*.json 构建该章内容化契约（含 stats）。

    `page_dir` 为实际存放 page_*.json 的目录（多册书传对应分册子目录）；
    省略时等同 `ext`。多册书各册页码通常重新从 1 开始，若此处仍读 `ext`
    会把上册页内容挂到下册章上（静默错乱），故必须由调用方按章解析后传入。

    返回 ``(chapter_dict, stats)``——stats 含 text/formula/image/proof/description
    计数与被噪声过滤丢弃的块数，供 `verify/script/check_content_completeness.py`
    复算比对（脚本确定性输出 => 可校验完整性）。
    """
    node = _to_skeleton(node)          # 幂等：已挂内容（重复 attach）先还原为骨架
    # page_dir 未显式给出时从契约自带字段派生（多册书章级 `page_dir`；老契约缺
    # 字段 → 按章号走 lib.page_dir 的证据链）。**绝不能默认成 ext**：多册书各册
    # 页码重复，读 ext 会静默命中某一册、把内容挂到别的册的章上且不报错。
    if not page_dir:
        page_dir = _node_page_dir(ext, node)
    start, end = int(node.get("page_start") or 0), int(node.get("page_end") or 0)
    ch_key = str(node.get("key") or "")
    _fc_ncomp, _fc_scope, _fc_letter, _fc_bare = formula_cfg(ext, ch_key)
    n_noise = [0]

    blocks, page_height = _collect_blocks(ext, start, end, ch=ch_key,
                                          page_dir=page_dir)
    kept = _filter_noise(blocks, page_height, max(1, end - start + 1),
                         _fc_ncomp, letter=_fc_letter)
    n_noise[0] = len(blocks) - len(kept)
    blocks = kept
    _mark_line_geometry(blocks)

    # 锚点分派：每块归「位置 ≤ 块位置的最后一个锚点事件」；最早事件之前 → 章首序言
    events = _build_events(ext, node, page_dir=page_dir)
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
        elif tgt.get("type") in ("exercise", "problem"):
            # 练习/问题的「证明：…」是题干任务而非证明过程 → 题面即正文，不拆 proof
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
        # 多册书：page_*.json 在各分册子目录且各册页码重复。目录由
        # build_chapter_contract 内部从契约 `page_dir` 字段派生（老契约按章号
        # 走证据链），此处无需再解析。
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
