"""gate_units.py — write-source 步骤 5 强制门控：确保每个 item 单元都被 agent 改好

背景
----
写作以单元粒度进行：拆分脚本 ``split_draft_units.py``
把整章草稿切成按写作顺序的单元文件（``units/ch{N}/NNNN_<type>.md``，4 位编号；附录章 ``units/appendix{X}/``），agent
**必须逐个把单元按 writing-rules 改好**。本脚本是这一步的**强制门控**：只有全部
单元都被改好（每个 item 都不漏）才放行，之后才能进入 ``merge_units.py`` 拼接。

判定（一个单元「已改好」须同时满足）：
  ① **标记已替换**：文件首行由拆分时写入的 ``<!-- ... DRAFT unit: ... -->``
     变为 ``<!-- ... DONE unit: ... -->``（agent 改完后显式确认）；
  ② **「写对」而非「重写」**：item / desc / exercise 单元做**单元级质量校验**
     （``check_unit_quality.py``）——全部引用 verify 已有检测函数（check_katex /
     katex_heuristics / verbose_gates / struct_labels / format_verify），不重复
     造轮子。🔴 判断标准是"写对"（是否符合写作要求），
     **不看内容指纹是否变化**——防止模型瞎改（公式没渲染对 / 格式破坏）就标 DONE。
     含内容审阅类残留检测（QED 框「口/□」独立行 / OCR 乱码重复片段 /
     编码损坏字符 / 单元内私造 `#` 标题行）与**围栏形态检测**（单行 ``$$...$$``
     块 / ``$$`` 附着内容 / 缺空行或缺空 ``>`` 行 / ``\tag`` 在块外——真实
     Markdown 预览器不认单行块，而 katex_validate.js 支持、closure 只查 EOF，
     两道渲染检查都看不见，必须 heuristic 拦）。
     （章节标题单元本就无需改动，只确认 DONE。）
  ③ **单元级公式序标对账（契约 tag 真值）**：以内容化契约
     （``chapter_tag_map``）要求该单元携带的 ``formula.tag`` 集合为真值，对比
     单元正文 ``\tag{}``——缺失（漏写编号公式）与多出（编造编号）均不通过
     （Q 层是章级末步，单元粒度必须提前拦；契约缺失时跳过对账）。
  ④ **真实 KaTeX 渲染（按章批量）**：把本章全部 item/desc/exercise 单元正文拼进
     临时 md（``<extract>/_gate_render_tmp_<章目录名>.md``，带单元边界标记），跑
     ``katex_render.run_render_check``（katex_validate.js 真渲染），错误按行号
     **映射回所属单元**——启发式抓不到的 `\begin` 不配对 / 未定义宏等在门控即拦，
     不再漏到步骤 8 verify。🔴 渲染工具链缺失（node / katex 未装）= 门控不通过
     （fail-closed；须先完成 prep.env：``npm install katex --no-save``）。
  🔴 **fail-closed**：质量校验**执行失败**（脚本异常）按「质量未达标」处理，
     绝不因崩溃放行（旧实现异常即放行，曾让未审阅单元整体免检流入拼接）。

序标校验（1:1 保真，**合并前**即拦，不再漏到步骤 8，**两者均阻断**）
------------------------------------------------------------------
  ⑤ **条目序标（B 层：缺号 + 顺序错乱，含 ``uncat``「描述性标题」组）**；
  ⑥ **子项序标（O 层：``(1)(2)(3)`` / ``(a)(b)(c)`` / ``(i)(ii)(iii)`` 缺口）**。
     两者都**按章级跑**，且待校验的 md **由 `merge_units.merge_chapter` 亲自产出**
     （``_merged_chapter_md``，``require_gate=False`` 避免递归）——即**门控看到的
     就是最终章 md 本身**，故分别复用 verify 真 B 层（``_md_gap_blocking``）与真
     O 层（``check_ordinal_subitem_gaps``）后，结论与步骤 8 章级 verify **一致**。
     🔴 **不可下放到逐单元**（缺号 / 顺序天然跨单元；O 层按「行距 ≤4」成块，逐
     单元会切断或错并序列窗）；🔴 **不可手搓「等价拼接」**（缺 `---` 分隔线 /
     `clean_cjk` 等后处理会漂移，实测并窗误报）——必须调 merge 自己的函数。
     desc 描述单元已在拼接内，覆盖不丢。
     阻断口径（fail-closed：重建 md / 加载层 / 执行任一失败 = 不通过）：

完整性核对（防漏项）：
  ⑦ manifest 中每个单元都有对应文件（无缺失、无多余文件）；
  ⑧ manifest 的 ``units`` 覆盖契约全部编号项单元（item）+ 章/节/描述单元。

不满足任一 → 输出未处理 / 质量未达标清单并 exit 1（不通过）；全部通过 → exit 0。

翻译单元（2026-09-03 起，翻译并入 write-source，单元按需生成）
----------------------------------------------------------
同一套门控作用于翻译单元目录 ``book_structure/units-translate/ch{N}/``
（由 ``init_translate_units.py`` 初始化清单后按需生成），只需加 ``--units-dir units-translate``：
    python flows/write-source/script/gate_units.py <extract_dir> [ch ...] --units-dir units-translate
单元级质量校验（``check_unit_quality``）全部复用 verify 检测函数，**语言无关**
（$$ 闭合 / 裸数学 / 裸箭头 / 证明过长 / 结构标签 / 例块包裹 / OCR 残留），
故源单元与翻译单元共用同一实现，不重复造轮子。

🔴 **翻译前置硬闸（源先于译）**：``--units-dir units-translate`` 门控**先跑源章
门控**——源单元未全部修正完成（源门控未通过）即拒绝放行。init 时的硬闸只保证
「初始化那一刻」源是好的；源后续再改（补公式 tag / 修格式），翻译门控必须重新
把关，否则译文基于旧源必作废。``merge_units --units-dir units-translate`` 自带的
强制门控同样经由本入口，故拼接翻译版亦受此闸约束。

用法
----
    python flows/write-source/script/gate_units.py <extract_dir> [ch ...] [--units-dir <sub>]
    # 不传 <ch> 即全部章；<sub> 默认 units（翻译单元传 units-translate）
输出
----
    通过：exit 0；未通过：exit 1 并打印未处理 / 缺失单元清单（逐章）。
"""
import io
import json
import os
import re
import sys
import types
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

import attach_content as _ac
from data.book_structure.book_structure import (
    chapter_json_path, chapter_label, chapter_tag_map, list_chapter_keys,
    prime_chapter_kinds, unit_dir_name)
import split_draft_units as _split
import check_unit_quality as _quality

_OUT_RE = re.compile(r"<!-- book-summarizer (DRAFT|DONE) unit: id=(\S+) type=(\S+) key=(.*?) name=(.*?) -->")

_KEY_NUM_RE = re.compile(r"(\d+(?:\.\d+)*)-(\d+)$")


def _check_numbering(units):
    """B 层编号预检：同一节内 item 编号是否递增。返回问题列表。"""
    from collections import defaultdict
    sections = defaultdict(list)
    for u in units:
        if u["type"] != "item":
            continue
        m = _KEY_NUM_RE.search(u["key"])
        if m:
            sec = m.group(1)
            num = int(m.group(2))
            sections[sec].append((num, u["file"], u["key"]))
    problems = []
    for sec, items in sorted(sections.items()):
        items.sort(key=lambda x: x[0])
        for i in range(1, len(items)):
            prev_num, prev_file, prev_key = items[i - 1]
            cur_num, cur_file, cur_key = items[i]
            if cur_num <= prev_num:
                problems.append(
                    "编号不递增：节 %s 内 %s（%d）排在 %s（%d）之后" % (
                        sec, cur_key, cur_num, prev_key, prev_num))
    return problems


class _SilentOut(io.StringIO):
    """stdout 替身：吞掉 merge_chapter 的进度打印，并容忍 `reconfigure`。

    真实 stdout（TextIOWrapper）有 `reconfigure`，而 `io.StringIO` 没有；模块导入
    期/运行期若有人调 `sys.stdout.reconfigure(encoding=…)`（如 `lib.boot` 的
    `_force_utf8_stdio`、各入口脚本），纯 StringIO 会抛 AttributeError。故给替身
    补一个 no-op `reconfigure`，使重定向在任何调用上下文下都安全。
    """

    def reconfigure(self, *args, **kwargs):
        return None


def _merged_chapter_md(ext, ch_key, out_dir, units_sub="units"):
    """调用 **merge_units 自己的拼接器**，把本章 md 产出到临时文件（序标校验消费）。

    🔴 **为什么必须调 `merge_chapter` 而不是本模块自己拼**：序标校验对拼缝形态极
    敏感（B 层按 `## §` 分窗、O 层按「行距 ≤4」成块），手搓的「等价拼接」必然
    漂移——本模块曾手搓一版，缺单元间 `---` 分隔线 → 把罗马段与字母段并进同一窗、
    误报一串幽灵缺口。调**同一个函数**即**按定义**保证「门控看到的 = 最终章 md」
    （含 `clean_cjk` / `_tidy_separators` / section 单元锚点），从根上杜绝分叉。

    `require_gate=False`：跳过 merge 内置的门控，避免与 gate_units 递归。
    返回临时 md 路径；调用方负责删除。
    """
    tmp_md = os.path.join(ext, "_gate_ordinal_tmp_%s_%d.md" % (
        os.path.basename(out_dir), os.getpid()))
    import merge_units as _merge          # 延迟导入：避免与 merge_units 循环依赖
    import contextlib
    # merge_chapter 会向 stdout 打印一行「[merge_units] chN -> …」；门控内部调用
    # 只需产物、不需这行噪声，故就地静默（不改 merge_units 签名，零风险）。
    with contextlib.redirect_stdout(_SilentOut()):
        try:
            _merge.merge_chapter(ext, ch_key, out_md=tmp_md, require_gate=False,
                                 units_sub=units_sub)
        except BaseException:
            # 🔴 merge 可能已写出部分 tmp 后才抛（缺单元文件 → SystemExit）：
            # 此时路径尚未返回给调用方的 finally，须在此就地清理，防残留。
            try:
                os.unlink(tmp_md)
            except OSError:
                pass
            raise
    return tmp_md


def _check_ordinals_chapter(ext, ch_key, out_dir, units, units_sub="units"):
    """章级序标校验：**B 层（条目编号）+ O 层（子项编号）**，均阻断。

    🔴 **复用 verify 真层**（唯一真源），**不重写判据**：
      * B 层 ``item_numbering_integrity._md_gap_blocking`` —— 缺号 + 顺序错乱
        （含 ``uncat``「描述性标题」组），只取其 ``blocking``；
      * O 层 ``subitem_continuity.check_ordinal_subitem_gaps`` —— ``(1)(2)(3)`` /
        ``(a)(b)(c)`` / ``(i)(ii)(iii)`` 缺口，只取其 ``'x'`` 项。
    B 层用轻量 ctx 提供其实际消费的四个属性（``config``/``ignore``/``md_file``/
    ``language``）。

    🔴 **md 由 `merge_units.merge_chapter` 亲自产出**（`_merged_chapter_md`），
    故门控看到的就是**最终章 md 本身**——O 层对拼缝邻接极敏感，手搓「等价拼接」
    必然漂移并误报；调同一函数即按定义消除分叉，O 层因此可放心阻断。
    desc 描述单元已在拼接内，覆盖不丢。

    🔴 **fail-closed**：重建 md / 加载层 / 执行任一失败，一律按「序标校验不通过」
    返回，绝不静默放行。
    """
    try:
        tmp_md = _merged_chapter_md(ext, ch_key, out_dir, units_sub)
    except (Exception, SystemExit) as e:  # 🔴 fail-closed：无法重建 = 不能宣称校验通过
        # SystemExit 非 Exception 子类（merge_chapter 缺单元文件时抛它），须显式捕获，
        # 否则会击穿门控而非 fail-closed。
        return ["章级序标校验执行失败（fail-closed）：无法重建章 md：%r" % (e,)]
    try:
        try:
            from verify_config import ConfigLoader
            from item_numbering_integrity import _md_gap_blocking
            from subitem_continuity import check_ordinal_subitem_gaps
        except Exception as e:  # 🔴 fail-closed：层不可用 = 不能宣称校验通过
            return ["章级序标校验执行失败（fail-closed）：无法加载 B/O 层：%r" % (e,)]
        book_dir = os.path.dirname(os.path.abspath(ext.rstrip("/\\"))) or ext
        loader = ConfigLoader(ext, book_dir)
        cfg = loader.config_for_chapter(ch_key)
        ctx = types.SimpleNamespace(
            config=cfg,
            ignore=list(getattr(cfg, "ignore", None) or []),
            md_file=tmp_md,
            language=getattr(cfg, "language", None) or "cn")
        problems = ["[B层序标] %s" % b.strip()
                    for b in (_md_gap_blocking(ctx)[0] or [])]
        problems.extend("[O层序标] " + g.strip()
                        for g in (check_ordinal_subitem_gaps(tmp_md) or [])
                        if str(g).strip().startswith("x"))
        return problems
    except Exception as e:  # 🔴 fail-closed
        return ["章级序标校验执行失败（fail-closed）：%r" % (e,)]
    finally:
        try:
            os.unlink(tmp_md)
        except OSError:
            pass


def _hash_text(text):
    import hashlib
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _read_unit(path):
    """读单元文件，返回 (mark, id, type, key, body, body_hash)；解析失败返回 (None, ...)。"""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return None, None, None, None, "", ""
    m = _OUT_RE.match(raw)
    if not m:
        return None, None, None, None, raw, ""
    mark, uid, utype, key, name = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    rest = raw[m.end():]
    body = rest.lstrip("\r\n")
    return mark, uid, utype, key, body, _hash_text(body.rstrip("\n"))


def _render_check_chapter(ext, out_dir, units):
    """按章批量真实 KaTeX 渲染：把全部 item/desc/exercise 单元正文拼进一个
    临时 md（每个单元前有 ``<!-- gate-render unit: <file> -->`` 边界标记），
    调 ``katex_render.run_render_check``（katex_validate.js，每个公式真渲染），
    把 ``line N`` 错误映射回所属单元。返回问题列表（fail-closed：渲染执行失败
    / 工具链缺失均记为问题，绝不静默放行）。"""
    parts = []
    starts = []  # (正文首行行号, unit)
    line_no = 1  # 1-based；指向下一单元的 marker 行
    for u in units:
        if u["type"] not in ("item", "desc", "exercise"):
            continue
        up = os.path.join(out_dir, u["file"])
        if not os.path.exists(up):
            continue  # 缺失已在主循环记过
        mark, _uid, _ut, _k, body, _bh = _read_unit(up)
        if mark != "DONE":
            continue  # 标记问题已在主循环记过，渲染只看 DONE 单元
        marker = "<!-- gate-render unit: %s -->" % u["file"]
        nlines = len(body.rstrip("\n").splitlines())
        parts.append(marker + "\n" + body.rstrip("\n"))
        starts.append((line_no + 1, u))
        line_no += 1 + nlines + 1  # marker 行 + 正文行 + join 产生的空行
    if not parts:
        return []
    tmp_md = os.path.join(ext, "_gate_render_tmp_%s_%d.md" % (os.path.basename(out_dir), os.getpid()))
    with open(tmp_md, "w", encoding="utf-8") as f:
        f.write("\n".join(parts) + "\n")
    try:
        try:
            from katex_render import run_render_check
            rerrs = run_render_check(tmp_md)
        except Exception as e:  # 🔴 fail-closed：渲染执行失败 = 门控不通过
            return ["真实渲染检查执行失败（fail-closed）：%r" % (e,)]
        out = []
        for err in rerrs:
            m2 = re.match(r"\s*line (\d+):", err)  # js 输出带前导空格："  line N: ..."
            if m2:
                ln_no = int(m2.group(1))
                owner = None
                for st, uu in starts:
                    if st <= ln_no:
                        owner = uu
                    else:
                        break
                if owner is not None:
                    out.append("单元 %s 公式渲染失败（真实 KaTeX 渲染）：%s"
                               % (owner["file"], err))
                    continue
            out.append("公式渲染检查（%s）：%s" % (tmp_md, err))
        return out
    finally:
        # 🔴 清理临时 md（此前只写不删，5 天累积 1995 个 `_gate_render_tmp_*` 残留）。
        try:
            os.unlink(tmp_md)
        except OSError:
            pass


def gate_chapter(ext, ch_key, units_sub="units"):
    """门控单章。返回 (ok, detail)。detail 为逐条问题或通过说明。

    ``units_sub``：单元子目录名——``units``（源语言单元，默认）或
    ``units-translate``（翻译单元；2026-09-03 起翻译并入本流程，
    与源单元共用同一门控与同一套单元级质量校验，语言无关不重复造轮子）。

    🔴 **翻译前置硬闸（源先于译）**：``units_sub="units-translate"`` 时**先跑
    源章门控**——源单元未全部修正完成（源门控未通过）即拒绝放行翻译门控。
    翻译必须等源单元全部改好才开始/放行，否则译文基于旧源必作废（init 硬闸
    只保证初始化那一刻源是好的；源后续再改，翻译门控必须重新把关）。
    """
    # 🔴 翻译前置硬闸：源单元全部修正完成（源门控通过）才允许翻译门控放行。
    # 内层调用 units_sub="units" 不会再触发本分支，无递归风险。
    if units_sub != "units":
        ok_src, src_det = gate_chapter(ext, ch_key, units_sub="units")
        if not ok_src:
            return False, (
                "%s 翻译门控拒绝：源单元未全部修正完成（源章 gate_units 未通过）"
                "——先修好全部源单元再翻译/重派生，否则译文基于旧源必作废。\n"
                "源门控详情：\n  %s" % (chapter_label(ch_key), src_det))
    out_dir = os.path.join(ext, _ac.OUT_DIR_NAME, units_sub, unit_dir_name(ch_key))
    mpath = os.path.join(out_dir, "manifest.json")
    if not os.path.exists(mpath):
        return False, ("%s 缺 %s/manifest.json（先跑 split_draft_units / "
                       "init_translate_units）。" % (chapter_label(ch_key), units_sub))
    with open(mpath, encoding="utf-8") as f:
        manifest = json.load(f)
    units = manifest.get("units") or []
    # 契约 tag 真值（单元级「缺失/编造编号」对账；契约缺失 = 跳过对账）
    tag_map = {}
    cpath = chapter_json_path(ext, ch_key)
    if os.path.exists(cpath):
        try:
            with open(cpath, encoding="utf-8") as f:
                tag_map = chapter_tag_map(json.load(f))
        except Exception:
            tag_map = {}
    problems = []
    present_files = set()
    for u in units:
        up = os.path.join(out_dir, u["file"])
        if not os.path.exists(up):
            problems.append("缺失单元文件 %s（%s %s）" % (u["file"], u["type"], u["key"]))
            continue
        present_files.add(u["file"])
        mark, uid, utype, key, body, bh = _read_unit(up)
        if mark is None:
            problems.append("单元 %s（%s %s）首行标记缺失/损坏——须含 DONE 标记" % (
                u["file"], u["type"], u["key"]))
            continue
        if mark == "DRAFT":
            problems.append("单元 %s（%s %s）仍未处理（标记仍为 DRAFT）" % (
                u["file"], u["type"], u["key"]))
            continue
        # DONE：item / desc / exercise 单元必须「写对」——质量校验通过（公式闭合 /
        # 无裸数学 / 结构标签 / 无明显 OCR 残留 / 无内容审阅类残留）。
        # 🔴 判断标准是"写对"而非"重写"：不看内容指纹是否变化，而是看单元是否
        # 符合写作要求（拦"瞎改就标 DONE"）。
        if utype in ("item", "desc", "exercise"):
            try:
                ok_q, qproblems = _quality.check_body(
                    utype, u.get("name") or "", body,
                    expected_tags=tag_map.get(str(u["key"])) if tag_map else None)
            except Exception as e:  # 🔴 fail-closed：校验崩溃绝不放行
                ok_q, qproblems = False, [
                    "质量校验执行失败（fail-closed）：%r" % (e,)]
            if not ok_q:
                problems.append("单元 %s（%s %s）质量未达标（写错/格式破坏）：%s" % (
                    u["file"], u["type"], u["key"], "；".join(qproblems[:4])))
    # 多余文件检查（manifest 之外的 .md 属误放）
    for fn in sorted(os.listdir(out_dir)):
        if fn == "manifest.json" or not fn.endswith(".md"):
            continue
        if fn not in present_files:
            problems.append("多余文件 %s（不在 manifest 中，请移除）" % fn)
    # B 层编号预检：同一节内编号是否递增
    numbering_probs = _check_numbering(units)
    problems.extend(numbering_probs)
    # 🔴 章级序标校验（B 层条目编号 + O 层子项编号，含 uncat 描述性标题组）——
    # 复用 verify 真层，且 md 由 `merge_units.merge_chapter` 亲自产出（=最终章 md），
    # 故在**合并前**即拦，不再漏到步骤 8 verify。
    problems.extend(_check_ordinals_chapter(ext, ch_key, out_dir, units,
                                            units_sub=units_sub))
    # 🔴 批量真实 KaTeX 渲染（按章一次 node 子进程，错误按行号映射回单元）：
    # 启发式（裸命令 / $ 配对 / 闭合）抓不到的 \begin 不配对、未定义宏等
    # 真渲染错误在门控即拦，不再漏到步骤 8 verify / 最终输出。
    problems.extend(_render_check_chapter(ext, out_dir, units))
    if problems:
        return False, "%s 门控未通过（%d 处）：\n  %s" % (
            chapter_label(ch_key), len(problems), "\n  ".join(problems))
    return True, "%s 门控通过：%d 个单元全部改好（含 %d 个编号项，含真实 KaTeX 渲染）" % (
        chapter_label(ch_key), len(units), sum(1 for u in units if u["type"] == "item"))


def main():
    argv = sys.argv[1:]
    units_sub = "units"
    if "--units-dir" in argv:
        i = argv.index("--units-dir")
        if i + 1 >= len(argv):
            print("[gate_units] --units-dir 缺参数（units | units-translate）。")
            return 2
        units_sub = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        print(__doc__)
        return 2
    ext = argv[0]
    prime_chapter_kinds(ext)  # 🔴 灌注 kind 注册表（Supplement 前缀依赖 chapter_map）
    try:
        chapters = [int(x) for x in argv[1:]]
    except ValueError:
        chapters = argv[1:]
    keys = [k for k in list_chapter_keys(ext)
            if not chapters or k in {str(c) for c in chapters}]
    if not keys:
        print("[gate_units] 无章节可门控。")
        return 2
    if units_sub != "units":
        print("[gate_units] 门控目录：%s（翻译单元）" % units_sub)
    all_ok = True
    for k in keys:
        ok, detail = gate_chapter(ext, k, units_sub=units_sub)
        print(("[PASS] " if ok else "[FAIL] ") + detail)
        if not ok:
            all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
