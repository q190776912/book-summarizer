"""check_content_completeness.py — 内容化分章契约的完整性闸门（write-source 步骤 4）。

结构完整性（章节 / 定理定义等缺项）由 structure 子流程第 2–4 步闸门保证；本脚本
补上**内容完整性**——保证所有描述信息（description 节点）、证明（proof 子节点）、
图片（image 内容块）与全部文字 / 公式块都进入内容化分章契约，无遗漏、无多余：

  1. **确定性复算比对**：`attach_content.build_chapter_contract` 是纯函数——按同一
     管线（收集 → 噪声过滤 → 行内公式拼接 → 几何标记 → 锚点分派 → 证明拆分 → 描述
     聚合）在内存中重建该章契约，与磁盘上的 `book_structure_{N}.json` 做**内容块
     多重集比对**（text 按归一化文字、formula 按 latex + display + **tag**、
     image 按路径）。不一致 = 磁盘契约相对管线过期 / 被手改 → FAIL。
     ⚠️ 本项是**幂等自证**（同管线重算 vs 磁盘），只能发现"磁盘与管线不一致"，
     发现不了"管线本身漏抓"——后者必须靠下面的独立真值项。
  2. **图片完整性（独立真值）**：`figure_index.json` 中落在该章页码区间内的每张图
     必须以 image 块出现在契约中（按路径多重集比对）→ 缺图 FAIL。
  2b. **公式序标完整性（独立真值）**：`page_*.json` 中**独立成块**的公式编号
     （形态由本书 `formula.type` 经 `ORDINAL_DEPTH` 派生，**不是**写死的
     `(C.N)`；章级编号书要求首分量等于本章章号）必须在该章契约中被“交代”：
       * 挂在某个公式块的 `tag` / `tags` 上 —— 正常（`tags` 是多行公式组逐行编号时
         `attach_content` 挂在同一块上的完整编号列表，`tag` 仅为首个）；
       * 编号仍在契约正文中（未挂上，作为散落的 `(C.N)` 文本块保留）—— **WARN**
         （信息未丢，但序标没挂到公式上，agent 调整时须手工补 `\tag`）；
       * 两者都没有（编号随文本块一起被噪声过滤/丢弃）—— **FAIL**（编号真丢了）。
  2c. **正文块守恒（独立真值）**：同一管线「收集 → 噪声过滤」后保留的**每一个 text
     块**，都必须能在契约树里找到同签名块（条目正文 / description / proof 任一）。
     收不齐 = **锚点分派把整段正文丢了** → **FAIL**。为什么还要它：① 是「同管线
     自证」（管线漏抓时两侧同样缺失 → 判 PASS），②c 拿**未经锚点分派的块流**对
     **分派之后的树**，是唯一看得见「分派阶段吞块」的一项。
     豁免（只放过管线的正常变形，逐条由 `verify/tests/test_content_block_conservation.py`
     钉住）：公式归 2b、图片归 2 各自管；归一化长度 < 40 的碎片；本块是契约节点
     `name` 的**子串**（`_strip_header` 把 OCR 粘连的印刷标题 `Lemma1.4Thegraph of…`
     吃进了带键前缀的 name）；本块被并进更大的契约块、或＝「剥掉的标题 + 契约块」
     （**只认内含 / 尾部贴合，中间包含不放行**——「节头+正文+节头」粘连块里正文在
     契约、两头丢了，正是本闸要抓的形态）；整段本就是契约块但份数不够 → 不放行
     （签名按份消耗）；本块＝「契约节点标题 + 尾随页码」= 印面**页眉**（Atiyah–
     Macdonald p50/p128 实测：`_filter_noise` 的边缘重复判据要同一文本在 ≥2 页出现，
     对奇偶页交替的章节页眉失明）；本块**越过**某个以省略号截断的节点 `name`
     （`… ` 截到的接缝落在本块里）= 该行标题的未截断原形（Rising Sea p28/p460/p516
     实测：契约存 `17.4.2. Theorem. … over a…`，印面整行比截断名长，既非 name 子串
     也不等于任何正文块 → 假丢失）。判据自身执行异常 = FAIL（fail-closed，不静默放行）。
     ⚠️ 边界：只管「丢」，不管「挂错地方」——印面有正文而某节点 content=0 多是
     **分派错位**（内容活在隔壁节点），②c 判 PASS；那类问题由 D 层结构对账与
     步骤 5 `gate_units` 的空正文闸负责。
  3. **证明覆盖审计（尽力而为）**：重算保留文本块中未被 proof 子节点收编的证明
     标记命中（内联「证…」漏检等）→ WARN 列出（供 agent 定位补拆，不阻断）。

用法
----
    python verify/script/check_content_completeness.py <extract_dir> [ch ...]
退出码：0 = 全部通过；1 = 存在 FAIL。write-source 步骤 4 以此为闸（拆分单元前执行）。
"""
import collections
import json
import os
import re
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

import attach_content as ac
from data.book_structure.book_structure import (
    chapter_label, prime_chapter_kinds)
from lib.page_dir import node_page_dir as _node_page_dir


def _norm_text(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _block_sig(b):
    """内容块 → 可比对的签名 (kind, content)。

    ⚠️ 公式块的签名必须含 ``tag``：否则「契约里全部 tag 被抹掉 / 管线漏挂 tag」
    在复算比对两侧同样缺失，闸门会误报 PASS（2026-08-29 Koopman 书实测）。
    """
    if "image" in b:
        return ("image", _norm_text(b.get("image")))
    if "formula" in b:
        return ("formula", (_norm_text(b.get("formula")), bool(b.get("display")),
                            _norm_text(b.get("tag"))))
    return ("text", _norm_text(b.get("text")))


def _source_formula_tags(ext, start, end, ch_prefix, ncomp=None,
                         letter=False, bare=True, page_dir=None):
    """书源独立公式编号块（独立真值，不经 attach 管线）。

    遍历页区间内 ``page_*.json`` 的 ``text``，取**整块恰为一个编号**的块，返回
    **裸编号集合**。编号形态（段数 / 括号 / 分隔符 / 字母后缀 / 字母章位
    ``letter``）由 ``ncomp`` 派生于本书 ``verify_config.json`` 的
    ``formula.type``——🔴 **不可硬编码成 ``(C.N)`` 一种**：实测各书还有 ``(1)``
    节级重置、``(11.1-1)`` 连字符三段、``(8.11a)`` 字母后缀、Lee 附录
    ``(B.4)`` 字母章位，以及近半数书右缘编号**不带括号**。

    ``ch_prefix`` 非空时只收首分量等于该章号的编号（排除跨章引用）。

    ``page_dir`` 为该章 page_*.json 实际所在目录（多册书传分册子目录）；省略时
    等同 ``ext``。各册页码重复，多册书直接用 ``ext`` 会读错册。

    🔴 **页边距家具排除**：页脚/页眉的**页码**（极端边缘的短纯数字）与跨页边缘
    重复的 running head **不是**公式编号。本函数仅用**几何**（页高、y/bottom、
    跨页重复）剔除它们，不调用 attach 管线，故仍保持独立真值语义。判据与
    ``attach_content._filter_noise`` 对齐——契约侧已正确把页码当噪声丢弃，若此处
    不过滤，源真值会把页码当成"独立成块的公式编号"→ 源/契约不对称 → 假 FAIL
    （数学分析 ch9-18 实测：页脚页码 '37'/'492' 等被误判为公式编号）。
    🔴 **页码类判据的文本归一化须与契约侧同源**（``lib.numbering.folio_norm``）：
    印刷页码常带装饰点（``·376·``），只压空白的归一化会让跟踪律样本被装饰点打散，
    而偶发漏掉装饰点的那一页（``386``）就会单独漏进真值集 → 同样是不对称假 FAIL。

    🔴 **图区排除**：图内坐标标签（如 ``(1,2)``、``(0,1)``）整块恰为“编号形态”，
    但它们是图内容而非公式编号。契约侧这些文本随图区域内容被 splice 拆碎 /
    图像化，源真值若不剔除图区块 → 源/契约不对称 → 假 FAIL
    （微分遍历论 ch1 p13 图1.2 内坐标 ``(1,2)`` 实测：被误报“公式编号丢失”）。
    判据：文本块 poly 中心落在 ``figure_index.json`` 该页任一图 bbox 内 → 跳过。
    """
    from page_json import PageJson
    from lib.numbering import (formula_tag_number, formula_paren_tag_re,
                               page_number_furniture, folio_norm)
    _dir = page_dir or ext
    lo, hi = int(start), int(end)

    # 图 bbox 索引（page -> [(x0,y0,x1,y1)]）：图内文本块不参与公式编号判定
    _fig_boxes = {}
    try:
        with open(os.path.join(ext, "figure_index.json"), encoding="utf-8") as _f:
            _figs = json.load(_f)
        if isinstance(_figs, list):
            for _fg in _figs:
                try:
                    _pg = int(_fg.get("page") or 0)
                    _bb = _fg.get("bbox") or []
                    if lo <= _pg <= hi and len(_bb) >= 4:
                        _fig_boxes.setdefault(_pg, []).append(
                            (float(_bb[0]), float(_bb[1]),
                             float(_bb[2]), float(_bb[3])))
                except (TypeError, ValueError):
                    continue
    except Exception:
        pass

    # 第一遍：收集原始文本块 + 本区间页高（与 _filter_noise 同口径：max bottom）
    raw = []                                   # (page, y, bottom, text, xc, yc)
    for p in range(lo, hi + 1):
        fp = os.path.join(_dir, "page_%03d.json" % p)
        if not os.path.exists(fp):
            continue
        try:
            pg = PageJson.load(fp)
        except Exception:
            continue
        for t in pg.text_blocks:
            s = t.get("text")
            if isinstance(s, dict):            # MM 修复可能嵌套一层
                s = s.get("text")
            if not isinstance(s, str) or not s.strip():
                continue
            poly = t.get("poly") or []
            y = bottom = 0.0
            xc = yc = None
            if len(poly) >= 8:
                try:
                    _xs = [float(poly[i]) for i in (0, 2, 4, 6)]
                    _ys = [float(poly[i]) for i in (1, 3, 5, 7)]
                    y, bottom = _ys[0], max(_ys)
                    xc = (min(_xs) + max(_xs)) / 2.0
                    yc = (min(_ys) + max(_ys)) / 2.0
                except (TypeError, ValueError):
                    y = bottom = 0.0
                    xc = yc = None
            # 图区排除：中心落在任一图 bbox 内 → 图内标签，非公式编号
            if xc is not None and p in _fig_boxes:
                if any(fx0 <= xc <= fx1 and fy0 <= yc <= fy1
                       for fx0, fy0, fx1, fy1 in _fig_boxes[p]):
                    continue
            raw.append((p, y, bottom, s.strip(), xc, yc))
    page_height = max((b for _p, _y, b, _t, _xc, _yc in raw), default=0.0)
    n_pages = max(1, hi - lo + 1)

    # 页边距家具统计（同 _filter_noise：跨页边缘重复 / 全章过半页重复）
    edge_pages, all_pages = {}, {}
    for p, y, bottom, s, _xc, _yc in raw:
        n = _norm_text(s).replace(" ", "")
        if len(n) < 4:
            continue
        all_pages.setdefault(n, set()).add(p)
        if page_height > 0 and (y < 0.12 * page_height
                                or bottom > 0.90 * page_height):
            edge_pages.setdefault(n, set()).add(p)

    # 🔴 页码跟踪律（2026-09-27 Strogatz 3e 实测）：上面的「极端边缘」页码判据用
    # 0.06/0.94 带，而本书奇数页页码印在**页眉**（y≈111 ≈ 页高 6.3%）→ 带外漏网，
    # 于是 13 章各页页码（16..49 / 338..383 / 498..537 …共 ~380 个）整批进入真值集，
    # 「公式编号未挂到公式」建议全线失真，还会诱导写手给页码编造 \tag{16}。
    # 判据与 attach 侧共用 lib.numbering.page_number_furniture（页码 = 页序 − 恒定
    # 偏移的算术指纹），两处不得各写一份。
    # 🔴 **归一化也必须同源**（2026-09-28 阿诺尔德附录O p401 实测）：印刷页码带装饰
    # 点（`·373·` / `: 377 .` / `380·`），只压空白的 `_norm_text` 让它们进不了纯数字
    # 统计 → 恒定偏移样本 <3 页 → 跟踪律失明；偏偏偶有一页 OCR 漏掉装饰点（p401 的
    # 干净 `386`）→ 该页页码被当成「独立成块的公式编号」，而契约侧（用 `_norm` 去标点）
    # 早已把它当噪声丢弃 → 源/契约不对称 → `CONTENT GATE: FAIL 公式编号丢失 ['386']`。
    _furn = page_number_furniture(
        [(p, y, bottom, folio_norm(s))
         for p, y, bottom, s, _xc, _yc in raw], page_height)

    out = set()
    for p, y, bottom, s, _xc, _yc in raw:
        n = _norm_text(s).replace(" ", "")
        if not n:
            continue
        nf = folio_norm(s)                    # 页码类判据的键（与契约侧同源）
        if len(n) >= 4 and len(edge_pages.get(n, ())) >= 2:
            continue                           # 页眉/页脚/版权行
        if len(all_pages.get(n, ())) >= max(3, int(0.5 * n_pages)):
            continue                           # running head 变体
        # 页码：极端边缘的短纯数字（带括号的编号豁免——它是真编号，见 _filter_noise）
        # 🔴 纯数字判定用 `nf`（去装饰点后才是数字）——`_filter_noise` 用的 `_norm`
        # 同样去标点，两侧口径一致；括号豁免仍查原样 `s`，`(7)` 永远不被当页码。
        if (page_height > 0 and nf.isdigit() and len(nf) <= 3
                and not formula_paren_tag_re(ncomp, letter=letter).match(s)
                and (y < 0.06 * page_height or bottom > 0.94 * page_height)):
            continue
        if (p, nf) in _furn:
            continue                           # 页码跟踪律命中
        # 🔴 无括号且含字母的短串（'2e' / '4c' / '020m' / '1970s'）= OCR 碎片（如
        # `2e^{x}` 被切成独立块、年份被当成编号），不是编号：括号是编号的强信号，
        # 缺了它就不接受字母位。（letter 书的 `(A.3)` 带括号，不受影响。）
        if (not formula_paren_tag_re(ncomp, letter=letter).match(s)
                and re.search(r'[A-Za-z]', n)):
            continue
        key = formula_tag_number(s, ncomp, letter=letter, bare=bare)
        if key is None:
            continue
        if ch_prefix and re.split(r'[.\-·,]', key)[0] != ch_prefix:
            continue
        out.add(key)
    return out


def _walk_nodes(node):
    """深度优先 yield 全部结构节点（含自身，跳过内容块）。"""
    yield node
    for c in node.get("sub_sec") or []:
        if not ac._is_block(c):
            yield from _walk_nodes(c)


def _collect_contract_blocks(node):
    """契约章节点 → 全部内容块签名多重集（含 description / proof 内的块）。"""
    sig = collections.Counter()
    for b in ac._iter_blocks(node):
        sig[_block_sig(b)] += 1
    return sig


def _nodes_by_type(node):
    cnt = collections.Counter()
    for n in _walk_nodes(node):
        t = n.get("type")
        if t in ("description", "proof"):
            cnt[t] += 1
    return cnt


_TRAIL_DIGITS_RE = re.compile(r"\d+$")
# 契约节点 `name` 的**截断省略号**（管线把过长的印刷标题截断显示，非印面省略号）。
_TRAIL_ELLIPSIS_RE = re.compile(r"(?:…|⋯|\.\.\.)\s*$")


def _orphan_text_blocks(kept, contract):
    """②c 判据（纯函数）：管线「收集 + 噪声过滤」后保留的 text 块 vs 契约树。

    返回丢失块清单 `[(page, text), ...]`——契约里找不到同签名块、且不属于以下
    **正常变形**豁免的正文块。① 的复算比对是同管线自证，管线自己漏抓时两侧同样
    缺失判 PASS，看不见这类丢失，故须独立真值。

    豁免：
      * 归一化长度 < 40 的碎片（页码残迹 / 单字块）；
      * **块是契约节点 `name` 的子串**——OCR 把印刷标题打成
        `Lemma1.4Thegraph of…`，而 `name` 带键前缀（`引理1.4 Lemma1.4Thegraph…`），
        该块已被 `_strip_header` 吃进标题（Shafarevich I ch1 p74/p88、ch3 p173 实测）。
        🔴 反向（`name` 是块的子串）**不豁免**：真丢失的整段正文常常正好以节头/条目标题
        开头，反向豁免等于把这类丢失放行；剥标题后的残段由下一条覆盖。
      * 去掉**尾部数字**后正好等于某契约节点 `name`——印面页眉「节/章标题 + 页码」
        （`EXTENDED AND CONTRACTED IDEALS … 41`，Atiyah–Macdonald p50/p128 实测）：
        `_filter_noise` 的「跨页边缘重复」判据要同一文本在 ≥2 页出现，而**奇偶页
        交替**的标题页眉每页文字互异（各只出现一次）→ 漏网成孤儿块。只削尾随数字，
        正文段（哪怕以「… for $n = 41$」收尾）削完不等于任何标题，照常报。
      * **越过截断标题**——契约节点 `name` 以省略号结尾（管线截断显示，剥掉省略号后
        归一化长度 ≥ 25）时取其后 20 字为「接缝」；本块含有该接缝 → 它就是那一行印刷
        标题的**未截断原形**，不算丢失（Rising Sea p28/p460/p516 实测）。🔴 只对**带
        省略号**的 name 生效：未截断的节头仍走上一条（反向不豁免），否则「以节头开头的
        真丢失整段」会被放行。
      * 与任一契约正文块**尾部贴合**——`_strip_header` 从块首剥掉印刷标题后
        契约里存的是残段，故本块 = 标题 + 契约块（`nt.endswith(c)`）；或本块整体
        被并进某个更大的契约块（`nt in c`）。
        🔴 **头部贴合不豁免**：`nt.startswith(c)` 意味着「契约只收了本块开头，
        **尾巴丢了**」——那正是真丢失的形状，不能放行。
        该豁免**不覆盖**「整段本就是契约块、只是份数不够」：这类块签名按份消耗
        （`_norm_text` 与 `ac._norm` 两级），份数用尽后不再走包含豁免，否则
        「印面两段同文、契约只挂一段」会被自己放行（判据测试钉住）。
    """
    have = collections.Counter(_collect_contract_blocks(contract))
    names = [n for n in (ac._norm(x.get("name")) for x in _walk_nodes(contract)) if n]
    names_set = set(names)
    # 🔴 **截断标题的接缝**：管线把过长的印刷标题截断存进 `name`（尾随 `…`），于是
    # 印面那一行的**未截断原形**在契约里既不是 name 的子串（比 name 长）、也不等于任何
    # 正文块（残段挂在别的节点）→ 假丢失。判据：name 归一化（剥掉省略号）长度 ≥ 25 时，
    # 取其后 20 字作「接缝」；本块若**含有**该接缝，说明它越过了截断点、正是同一行标题
    # 的续文，不算丢失。
    # 🔴 未截断的 name（无省略号）**不进这张表**——「真丢失段恰好以节头开头」的
    #    反向放行仍由上一条测试钉住不放行。
    seams = set()
    for x in _walk_nodes(contract):
        raw = (x.get("name") or "").strip()
        if not _TRAIL_ELLIPSIS_RE.search(raw):
            continue
        core = ac._norm(_TRAIL_ELLIPSIS_RE.sub("", raw))
        if len(core) >= 25:
            seams.add(core[-20:])
    ctexts_all = [ac._norm(b.get("text")) for b in ac._iter_blocks(contract)
                  if "text" in b]
    ctexts = [c for c in ctexts_all if len(c) >= 12]
    cnorm = collections.Counter(ctexts_all)
    cexact = set(ctexts_all)          # 消耗前快照：守卫用
    orphans = []
    for b in kept:
        if "text" not in b:
            continue
        sig = _block_sig(b)
        t = sig[1]
        nt = ac._norm(t)
        # 两级签名（`_norm_text` 保文 / `ac._norm` 归一）**同时**按份消耗：只销
        # 一份计数器时，同文重复块的第二份会被另一份计数器放行（判据测试钉住）。
        if have[sig] > 0 or cnorm[nt] > 0:
            if have[sig] > 0:
                have[sig] -= 1
            if cnorm[nt] > 0:
                cnorm[nt] -= 1
            continue
        if len(t) < 40:
            continue
        if any(nt in nm for nm in names):
            continue
        # 🔴 印刷**页眉**形态「节/章标题 + 尾随页码」：`nt` 去掉尾部数字后正好等于
        # 某契约节点名 → 是版面家具不是正文（Atiyah–Macdonald p50/p128 实测：
        # `EXTENDED AND CONTRACTED IDEALS … 41`、`DIMENSION THEORY … 119`，
        # `_filter_noise` 的跨页重复判据对**只出现一次的奇偶页交替页眉**失明）。
        _hd = _TRAIL_DIGITS_RE.sub("", nt)
        if _hd and _hd in names_set:
            continue
        if any(s in nt for s in seams):
            continue
        # 🔴 整段本身就是契约里的某个正文块（只是份数不够）时**不走包含豁免**。
        if nt not in cexact and any(nt in c or nt.endswith(c) for c in ctexts):
            continue
        orphans.append((b.get("page"), t))
    return orphans


def check_chapter(ext, ch_node):
    """校验单章：返回 (ok, lines[])。"""
    ch_key = str(ch_node.get("key"))
    lines = []
    ok = True

    # ① 确定性复算比对（块多重集）：build_chapter_contract 幂等
    # （内部先还原骨架），可直接对磁盘契约重建。
    built, stats = ac.build_chapter_contract(ext, ch_node)
    # 🔴 复算必须镜像 build_structure 落盘前的同一后处理：剔除**无印刷锚点**的
    # 毒 tag（`strip_unattested`，见 build_structure 收割处）。漏这一步时，磁盘
    # 契约已被剔除、复算却把 tag 挂回来 → 同一公式「缺块 + 多块」假 FAIL
    # （本书 ch15 的 `5-1` 实测；判据与闸门 ⑭ 同源）。
    from lib.tag_attestation import (dir_page_loader as _dpl,
                                     strip_unattested as _strip,
                                     attested_numbers as _attested)
    # 🔴 豁免集与闸门 ⑭ 同一份登记（verify_config `formula.known_book` = 人工目视
    # 印面确证的真编号）。扫描书 OCR 会整块漏掉页边编号，人工按印面把号回填进契约
    # 之后，复算若仍无差别剔除它，就报「磁盘比复算多一块」的假 FAIL，并把回填判成
    # 手改污染。
    _strip(built, _dpl(_node_page_dir(ext, ch_node, ch_key), ext),
           attested=_attested(ext))
    built_sig = _collect_contract_blocks(built)
    p = ac.out_path(ext, ch_key)
    if not os.path.exists(p):
        return False, [f"  x 缺内容化分章契约 book_structure_{ch_key}.json（先跑 attach_content）"]
    with open(p, encoding="utf-8") as f:
        saved = json.load(f)
    saved_sig = _collect_contract_blocks(saved)

    missing = built_sig - saved_sig      # 管线有、磁盘无 → 丢失
    extra = saved_sig - built_sig        # 磁盘有、管线无 → 手改 / 过期
    if missing:
        ok = False
        lines.append(f"  x 契约缺块 {sum(missing.values())} 个（相对重算结果丢失）：")
        for (k, c), n in list(missing.items())[:6]:
            lines.append(f"      - [{k}] {str(c)[:80]}")
    if extra:
        ok = False
        lines.append(f"  x 契约多块 {sum(extra.values())} 个（相对重算结果多余 / 过期）：")
        for (k, c), n in list(extra.items())[:6]:
            lines.append(f"      - [{k}] {str(c)[:80]}")

    # ② 图片完整性（figure_index 独立真值）
    fp = os.path.join(ext, "figure_index.json")
    if os.path.exists(fp):
        with open(fp, encoding="utf-8") as f:
            idx = json.load(f)
        start, end = int(ch_node.get("page_start") or 0), int(ch_node.get("page_end") or 0)
        # 🔴 2026-09-01 起 image 块 file = figure/xxx.png（书根相对，与 attach 同步）
        want = collections.Counter(
            (e.get("file") or "").replace("\\", "/")
            for e in (idx if isinstance(idx, list) else [])
            if start <= int(e.get("page") or 0) <= end)
        got = collections.Counter(b["image"] for b in ac._iter_blocks(saved)
                                  if "image" in b)
        miss_img = want - got
        extra_img = got - want
        if miss_img:
            ok = False
            lines.append(f"  x 图片缺失 {sum(miss_img.values())} 张："
                         f"{sorted(miss_img)[:4]}")
        if extra_img:
            lines.append(f"  ? 图片多出 {sum(extra_img.values())} 张（不在 figure_index "
                         f"页区间内，多为跨页图）：{sorted(extra_img)[:4]}")

    # ②b 公式序标完整性（page_*.json 独立真值，不经 attach 管线）
    # 🔴 序标真值 = `tag` ∪ `tags`：多行公式组（`\begin{array}` / 相邻两式被 MFD
    # 并成一个高 bbox）在原书里逐行编号，attach_content 把**全部**编号挂到同一块上
    # （`tag` 首个、`tags` 完整列表），`node_tags` / `chapter_tag_map` 也按 `tags`
    # 取真值。只读 `tag` 会把这类**已交代**的编号判成「丢失」→ 假 FAIL 阻断拆分。
    got_tags = set()
    for b in ac._iter_blocks(saved):
        if b.get("tag"):
            got_tags.add(str(b["tag"]))
        for _t in (b.get("tags") or []):
            got_tags.add(str(_t))
    ch_key_s = str(ch_node.get("key") or "")
    ncomp, scope, f_letter, f_bare = ac.formula_cfg(ext, ch_key_s)
    # 🔴 与 Q 层一致**opt-in**：书未配 `formula` 时整项跳过。否则段数兜底正则
    # （段数不限、含裸排）会把页眉页脚的**页码**当成公式编号，而页码已被
    # _filter_noise 从契约剔除 → 每章凭空报「公式编号丢失」并阻断渲染。
    if ncomp is None:
        lines.append("    公式序标：本书未配置 `formula`（Q 层同源 opt-in）→ 跳过序标比对")
    else:
        # 只有「章级编号」（scope=2）才能用「首分量 == 章号」筛编号：book 级全书
        # 连续号（scope=1）与节级重置（scope=3）的首分量都与章号无关，筛了清零。
        # 字母章键（letter=True 时 `"A"`/`"B"`…）首分量同为该字母，直接可筛。
        prefix = ""
        if scope == 2:
            if ch_key_s.isdigit():
                prefix = ch_key_s
            elif f_letter and len(ch_key_s) == 1 and ch_key_s.isalpha():
                prefix = ch_key_s
        want_tags = _source_formula_tags(ext, ch_node.get("page_start"),
                                         ch_node.get("page_end"), prefix, ncomp,
                                         letter=f_letter, bare=f_bare,
                                         page_dir=_node_page_dir(ext, ch_node))

        def _ord(k):
            return [int(y) for y in re.split(r'[.\-·,]', k) if y.isdigit()]

        unattached = sorted(want_tags - got_tags, key=_ord)
        if want_tags:
            all_text = "\n".join((b.get("text") or "")
                                 for b in ac._iter_blocks(saved) if "text" in b)
            lost_tags = [t for t in unattached if t not in all_text]
            if lost_tags:
                ok = False
                lines.append(f"  x 公式编号丢失 {len(lost_tags)} 个（书源独立成块、契约"
                             f"既未挂 tag 也无该文本）：{lost_tags[:8]}")
            if unattached and not lost_tags:
                lines.append(f"  ? 公式编号未挂到公式 {len(unattached)} 个（编号仍在正文，"
                             f"但没成为任何公式块的 tag，调整时须手工补 \\tag）："
                             f"{unattached[:8]}")
            lines.append(
                f"    公式序标：书源={len(want_tags)} 已挂tag={len(want_tags & got_tags)}"
                f" 未挂={len(unattached)}")

    # ②c **正文块守恒（独立真值）**：管线「收集 + 噪声过滤」后的每一个正文块，
    #     都必须能在契约树里找到同签名块（item / description / proof 任一）。
    #     判据是纯函数 `_orphan_text_blocks`（豁免规则与边界见其 docstring；
    #     正反用例 `verify/tests/test_content_block_conservation.py`）。
    try:
        _st, _en = int(ch_node.get("page_start") or 0), int(ch_node.get("page_end") or 0)
        _pd = _node_page_dir(ext, ch_node)
        _ncomp, _scope, _letter, _bare = ac.formula_cfg(ext, ch_key)
        _srcb, _ph = ac._collect_blocks(ext, _st, _en, ch=ch_key, page_dir=_pd)
        _kept = ac._filter_noise(_srcb, _ph, max(1, _en - _st + 1), _ncomp,
                                 letter=_letter)
        orphans = _orphan_text_blocks(_kept, built)
        if orphans:
            ok = False
            lines.append(f"  ✗ 正文块丢失 {len(orphans)} 处（印面收集到、契约里没有——"
                         f"锚点分派漏挂，须回源补进契约后重跑 attach + 拆分）：")
            for pg, t in orphans[:12]:
                lines.append(f"      - p{pg}: {t[:80]}")
            if len(orphans) > 12:
                lines.append(f"      … 其余 {len(orphans) - 12} 处同类")
        else:
            lines.append("  ✓ 正文块守恒（收集→契约无丢失）")
    except Exception as _e:            # fail-closed：判据跑不起来绝不静默放行
        ok = False
        lines.append(f"  ✗ 正文块守恒检查执行失败（fail-closed）：{_e!r}")

    # ③ 证明覆盖审计（尽力而为，WARN 不阻断）
    missed = []
    for n in _walk_nodes(saved):
        for b in n.get("sub_sec") or []:
            # 只审「普通条目正文的文本块」——proof / description 内的文本已被收编
            if not ("text" in b and n.get("type") not in ("proof", "description",
                                                          "exercise", "chapter",
                                                          "section")):
                continue
            t = b.get("text") or ""
            if ac._PROOF_MARKER.match(t) or ac._CN_INLINE_PROOF.search(t):
                missed.append((n.get("key"), _norm_text(t)[:60]))
    if missed:
        lines.append(f"  ? 疑似未拆分证明 {len(missed)} 处（标记命中但未成 proof 节点，"
                     f"agent 调整时留意）：")
        for k, t in missed[:5]:
            lines.append(f"      - 条目 {k}: {t}")

    lines.insert(0, f"{chapter_label(ch_key)}: text={stats['text']} formula={stats['formula']} "
                    f"formula_tag={len(got_tags)} "
                    f"image={stats['image']} proof={stats['proof']} "
                    f"description={stats['description']} "
                    f"noise_dropped={stats['noise_dropped']} | "
                    f"{'PASS' if ok else 'FAIL'}")
    return ok, lines


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    ext = argv[0]
    try:
        chapters = [int(x) for x in argv[1:]]
    except ValueError:
        chapters = argv[1:]
    if not os.path.exists(os.path.join(ext, "_extraction_done.json")):
        print("[check_content_completeness] BLOCKED: 缺 _extraction_done.json。")
        return 2
    # 2026-09-08：按 chapter_map 灌注 kind 注册表（Supplement 等字母章
    # 的契约文件名走 supplement{X}.json，与 SSOT chapter_label 同源）。
    prime_chapter_kinds(ext)
    keys = ac.list_chapter_keys(ext)
    if chapters:
        want = {str(c) for c in chapters}
        keys = [k for k in keys if k in want]
    if not keys:
        print("[check_content_completeness] 无分章契约（ch*.json / appendix*.json）。")
        return 2
    all_ok = True
    for k in keys:
        with open(ac.out_path(ext, k), encoding="utf-8") as f:
            node = json.load(f)
        ok, lines = check_chapter(ext, node)
        all_ok = all_ok and ok
        for ln in lines:
            print(ln)
    print("CONTENT GATE:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
