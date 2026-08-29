"""render_draft.py — write-source 步骤 1：由分章内容契约渲染基本总结草稿

职责（2026-08-29 用户需求）
--------------------------
🔴 **全量保真，零压缩（硬契约）**：草稿是「调整与校验」的底稿，承载的是**内容
全集**——证明与描述信息**逐块原样输出，一律不得摘要化、不得跳步、不得按 Tier
压缩、不得因长度截断**。Tier 1/2/3 只压缩**表述**，且只发生在最终 md 的调整
步骤（唯一规则源 `docs/writing-rules.md`），**不在本渲染器内**。契约里有多少
内容块，草稿就写多少内容块（唯一例外：章末集中习题块 ``consolidated=true`` 按
习题收录规则省略）。

读取 ``<extract_dir>/book_structure/book_structure_{N}.json``（attach_content 产出的
内容化分章契约），按 **writing-rules 书写格式**机械渲染出对应章的**基本总结草稿**
``draft_ch{N}.md``：

  * 标题体系：``# 第N章 / # Chapter N:``、``## §N.M``（无序号标书 ``## § 标题``）、
    节间 ``---`` 分隔线；
  * 条目：``**name**：正文``——粗体标签与首段同行（冒号随语种：CN ``：`` / EN ``: ``）；
  * 例块：``type:"example"`` 整段 ``> `` 包裹，例内证明与陈述同一连续 blockquote
    （块内空行为 ``> ``、公式为 ``> $$…$$``，符合 V-F 例块连续性）；
  * 证明：proof 子节点 → ``> **证明**：…`` / ``> **Proof**: …`` 块引用——**完整
    证明原文逐块输出，不压缩**（故用「证明」而非「证明思路」：后者是最终 md
    压成 `1. 2. …` 步骤后的标签，用在草稿上会误导调整者以为可以删内容。
    两个标签 F 层 fixer 都识别，写成 ``**Proof**`` 不影响后续校验）；
  * 习题收录规则：章末集中习题块（``consolidated=true``）**省略**，穿插练习保留；
  * 带编号的行间公式：契约公式块的 ``tag`` 以 KaTeX ``\\tag{...}`` 独立一行写入
    ``$$`` 块内（书无号不编造；草稿据此保留序标供调整与 Q 层对账）；
  * 描述信息（description 节点）为无标题纯段落；图片块按原嵌图格式（flex div + ``<img>``）输出；
  * 分段：``line_start`` + ``indent``（首行缩进带）另起一段。

草稿是 write-source 逐章「调整与校验」的**底稿**，不是成品，**不经 verify、不受任何校验层约束**（P 层冗长告警等在草稿上属预期——初版按设计保留完整信息，Tier 压缩发生在调整步骤）：

  * 公式是 OCR 原样（UniMERNet 风格，含 `` { `` 等噪声）——🔴 调整时必须逐条
    重写校正（writing-rules：OCR 公式严禁直接照抄）；
  * 页眉 / 页脚 / 版权行已由 attach_content 尽力过滤，残余噪声块在调整时剔除；
  * 条目正文首行可能与粗体标题重复（标题剥离未命中时）——调整时去重；
  * 保真分级（Tier 1/2/3）、例块包裹、习题收录、图片嵌入等写作规则在调整步骤套用
    （唯一规则源 `docs/writing-rules.md`）。

新鲜度
------
渲染前对每章做结构指纹比对（:func:`attach_content.fingerprint_matches`）：单文件
分章契约（``book_structure/ch{N}.json``）因回填 / restructure 发生变化（或缺文件）时自动对该章
重跑 attach_content，保证草稿始终基于最新契约。

用法
----
    python flows/write-source/script/render_draft.py <extract_dir> [ch ...] [--force]
    # 不传 <ch> 即全部章；--force 强制重挂内容后渲染
输出
----
    <extract_dir>/book_structure/draft_ch{N}.md
"""
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

import attach_content as _ac
from embed_figures import short_caption as _fig_short_caption, page_px_width as _fig_page_px_width
from lib.figure_io import load_fig_labels as _load_fig_labels, fig_label_alt as _fig_label_alt

_CJK = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")


def _tag_body(tag):
    """契约公式块的 ``tag`` 带外层括号（``"(5.1)"``）→ 取裸编号供 ``\\tag{}`` 使用。"""
    t = (tag or "").strip()
    return t[1:-1] if len(t) > 2 and t.startswith("(") and t.endswith(")") else t


def _is_cjk(ch):
    return bool(ch) and bool(_CJK.match(ch))


def _join(a, b):
    """段落内拼接两段文字 / 行内公式（CJK 相邻不加空格；行尾连字符还原断词）。"""
    if not a:
        return b
    if not b:
        return a
    if a.endswith("-") and re.match(r"[a-z]", b):
        return a[:-1] + b
    if _is_cjk(a[-1]) or _is_cjk(b[0]):
        return a + b
    return a + " " + b


# ---------------------------------------------------------------------------
# 章节标题格式（语种取 verify_config.json 的 language；解析失败退回 name 原样）
# ---------------------------------------------------------------------------
def _book_language(ext):
    p = os.path.join(ext, "verify_config.json")
    try:
        with open(p, encoding="utf-8-sig") as f:
            return (json.load(f).get("language") or "cn").lower()
    except Exception:
        return "cn"


_CH_NAME = re.compile(r'^([0-9A-Za-z]+)\s+(.+)$', re.DOTALL)


def _chapter_heading(node, language):
    name = (node.get("name") or "").strip()
    m = _CH_NAME.match(name)
    if not m:
        return "# " + name
    num, rest = m.group(1), m.group(2).strip()
    if num.isdigit():
        return ("# 第%s章 %s" % (num, rest)) if language == "cn" \
            else ("# Chapter %s: %s" % (num, rest))
    return ("# 附录%s %s" % (num, rest)) if language == "cn" \
        else ("# Appendix %s: %s" % (num, rest))


# ---------------------------------------------------------------------------
# 渲染（按 docs/writing-rules.md 的书写格式：粗体标签冒号接正文、例块 > 包裹、
# 证明思路块引用、$$ 公式、章节标题体系、--- 分节线；内容仍为 OCR 原文，调整步骤
# 负责公式重写与 Tier 压缩）
# ---------------------------------------------------------------------------
def _colon(lang):
    return "：" if lang == "cn" else ": "


# 英文书条目标签转换（2026-08-29 Koopman 书实测）：契约 key 用 CN 规范标签
# （"定义1.1"），英文书草稿头部必须是纯英文（writing-rules 双语铁律）——渲染时
# 把 CN 标签+编号换回 EN 标签+编号；印刷标题若以同一编号开头则去重（避免
# "Definition 1.1 1.1 (...)" 双编号）。
_EN_LABEL = {"定义": "Definition", "定理": "Theorem", "引理": "Lemma",
             "推论": "Corollary", "命题": "Proposition", "例": "Example",
             "评注": "Remark", "注": "Remark", "假设": "Assumption",
             "算法": "Algorithm", "公理": "Axiom", "猜想": "Conjecture",
             "断言": "Assertion", "性质": "Property", "练习": "Exercise",
             "习题": "Exercise"}
_CN_KEY_RE = re.compile(
    r'^(' + '|'.join(_EN_LABEL) + r')([0-9A-Za-z]+[-.][0-9A-Za-z.\-]*)\s*(.*)$',
    re.DOTALL)


def _item_header_name(name, lang):
    """英文书把 CN 规范键头转成 EN 标签头；CN 书原样返回。"""
    if lang != "en":
        return name
    m = _CN_KEY_RE.match(name)
    if not m:
        return name
    lab, num, rest = m.group(1), m.group(2), m.group(3).strip()
    rest = re.sub(r'^' + re.escape(num) + r'(?=[\s(:．.])', '', rest).strip()
    return _EN_LABEL[lab] + " " + num + ((" " + rest) if rest else "")


def _proof_label(lang):
    """草稿的证明标签 —— **完整证明**，故用「证明」/「Proof」而非「证明思路」/
    ``Proof sketch``。后者是最终 md 把证明压成 `1. 2. …` 步骤后的标签（见
    writing-rules V-F），用在草稿上会暗示"可以压缩"。两者 F 层 fixer 均识别。"""
    return "证明" if lang == "cn" else "Proof"


def _blank(out, quote):
    """空行：quote=True 时写裸空行（例块包裹器统一转为 ``> ``），否则写空行。"""
    out.append("")


def _flush(buf, out, quote=False):
    if not buf:
        return
    para = ""
    for piece in buf:
        para = _join(para, piece)
    buf.clear()
    if para.strip():
        out.append(para)
        _blank(out, quote)


def _emit_blocks(blocks, out, buf, quote=False, lang="cn"):
    """内容块流 → md：文字 + 行内公式进段缓冲（拼段由 _flush 完成）；
    ``line_start`` 且 ``indent`` 落在首行缩进带（[0.8, 3.5]×字高）→ 另起一段
    （几何事实字段由消费方判断；两键都没有 = 续前一句）；行间公式先冲刷缓冲再
    独立 ``$$...$$`` 成块；图片块按**原嵌图格式**（flex div + ``<img>``，可连续
    多图同排）输出。quote=True 时输出裸行（由例块包裹器统一加 ``> `` 前缀）。"""
    i = 0
    n = len(blocks)
    while i < n:
        blk = blocks[i]
        if "image" in blk:
            _flush(buf, out, quote)
            run = []
            while i < n and "image" in blocks[i]:
                run.append(blocks[i])
                i += 1
            _emit_img_run(run, out, quote)
            continue
        if "formula" in blk:
            latex = re.sub(r"\s+", " ", (blk.get("formula") or "").strip())
            if blk.get("display"):
                _flush(buf, out, quote)
                out.append("$$")
                out.append(latex)
                if _tag_body(blk.get("tag")):
                    out.append("\\tag{%s}" % _tag_body(blk["tag"]))
                out.append("$$")
                _blank(out, quote)
            else:
                buf.append("$" + latex + "$")
        else:
            t = (blk.get("text") or "").strip()
            if t and buf and blk.get("line_start") and 0.8 <= (blk.get("indent") or 0) <= 3.5:
                _flush(buf, out, quote)   # 新行 + 首行缩进带 → 另起一段
            buf.append(t)
        i += 1


_FLEX_STYLE = 'display:flex; gap:6px; flex-wrap:wrap; justify-content:center'
_FIGCTX = {}          # render_chapter 初始化：{index_by_basename, labels, book_dir}
_CTX = {"prev": "heading"}   # V-F 条目级分割线状态机（render_chapter 每章重置）


def _img_html(path):
    """按原嵌图格式（embed_figures）构造 ``<img>``：alt = 图号 + 短说明，
    width = 裁剪宽 / 页宽（bbox 比例，A4@200dpi=1653 兜底）。"""
    import os as _os
    ctx = _FIGCTX
    entry = ctx.get("index_by_basename", {}).get(_os.path.basename(path)) or {}
    labels = ctx.get("labels") or ["图"]
    cap_raw = entry.get("caption", "") or ""
    cap = _fig_short_caption(cap_raw, labels)
    mt = re.search(rf"(?:{_fig_label_alt(labels)})\s*\d+(?:\.\d+)*", cap_raw, re.IGNORECASE)
    tag = mt.group(0) if mt else (labels[0] if labels else "图")
    alt = (tag + " " + cap).replace('"', "'")
    bbox = entry.get("bbox") or None
    if bbox:
        crop_w = bbox[2] - bbox[0] + 16
        denom = _fig_page_px_width(ctx.get("book_dir"), entry.get("page"), 200) or 1653
        pct = min(round(crop_w / denom * 100, 1), 100.0)
    else:
        pct = 45.0
    return '<img src="%s" alt="%s" width="%s%%" height="auto">' % (path, alt, pct)


def _emit_img_run(run, out, quote):
    """连续图片块 → flex div 包裹（原嵌图格式：紧凑 div，内部无空行）。"""
    _blank(out, quote)
    out.append('<div style="' + _FLEX_STYLE + '">')
    for blk in run:
        img = _img_html((blk.get("image") or "").strip())
        out.append(("  " + img) if not quote else img)
    out.append("</div>")
    _blank(out, quote)


def _render_proof(pr, out, quote, lang):
    """proof 子节点 → ``> **证明思路**：…`` 块引用（quote=True 时输出裸行，由例块
    包裹器加前缀；例块内证明与陈述同一连续 blockquote，符合 writing-rules V-F）。
    块内空行保留为 ``> ``（V-F：``> $$`` 前后须有空行），仅去首尾空行。"""
    body = []
    buf = []
    _emit_blocks(pr.get("sub_sec") or [], body, buf, quote=False, lang=lang)
    _flush(buf, body, quote=False)
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    header = "**" + _proof_label(lang) + "**" + _colon(lang)
    if body and not body[0].startswith("$$"):
        body[0] = header + body[0]
    else:
        body.insert(0, header)
        if len(body) > 1 and body[1].startswith("$$"):
            body.insert(1, "")          # $$ 前必须有空行（V-K #1）
    for ln in body:
        out.append(("> " + ln) if not quote else ln)


def _walk_mixed(node, out, quote=False, lang="cn", top=False):
    """sub_sec 混合列表：内容块成段（连续块成组传入，供连续图片 run 合并 flex
    div）；description 无标题纯段落；proof 证明思路块引用；章末集中习题块
    （consolidated）按习题收录规则省略；其余结构节点递归。

    top=True（章 / 节的直接子层）时按 V-F 边界规则 emit 条目级 ``---``：
    item↔item、item↔描述散文之间必须有 ``---``；标题之下第一个元素、
    desc↔desc（连续散文）不加；item 与其内部附属块（proof）之间禁止。"""
    buf = []
    kids = node.get("sub_sec") or []
    i = 0
    while i < len(kids):
        el = kids[i]
        if _ac._is_block(el):
            run = []
            while i < len(kids) and _ac._is_block(kids[i]):
                run.append(kids[i])
                i += 1
            _emit_blocks(run, out, buf, quote, lang)
            if top:
                _CTX["prev"] = "desc"
            continue
        _flush(buf, out, quote)
        t = el.get("type")
        if t == "exercise" and el.get("consolidated"):
            i += 1                        # 章末「集中习题块」省略（writing-rules 习题收录）
            continue
        if top and t != "section":
            # V-F：item↔item、item↔描述 之间必须有 ---；标题之下第一个元素、
            # desc↔desc（连续散文）不加
            if _CTX["prev"] in ("item", "desc") and \
                    (t != "description" or _CTX["prev"] == "item"):
                out.append("---")
                out.append("")
        if t == "description":
            _walk_mixed(el, out, quote, lang)   # 无序标散文：纯段落，无标题
            if top:
                _CTX["prev"] = "desc"
        elif t == "proof":
            _render_proof(el, out, quote, lang)
        else:
            _render_node(el, out, lang)
            if top:
                _CTX["prev"] = "heading" if t == "section" else "item"
        i += 1
    _flush(buf, out, quote)


def _render_item(node, out, lang):
    """条目 → ``**name**：正文``（首段与粗体标签同行；例块整段 ``> `` 包裹）。"""
    t = node.get("type")
    name = _item_header_name((node.get("name") or "").strip(), lang)
    is_example = (t == "example")
    body = []
    _walk_mixed(node, body, quote=is_example, lang=lang)
    header = "**" + name + "**" + _colon(lang)
    if body and body[0].strip() and not body[0].startswith("$$") \
            and not body[0].startswith("![图]"):
        body[0] = header + body[0]
    else:
        body.insert(0, header)
        if len(body) > 1 and body[1].startswith("$$"):
            body.insert(1, "")          # $$ 前必须有空行（V-K #1）
    if is_example:
        for ln in body:
            out.append(("> " + ln) if ln.strip() else "> ")
    else:
        out.extend(body)


def _render_node(node, out, lang="cn"):
    t = node.get("type")
    if t == "chapter":
        out.append(_chapter_heading(node, lang))
        out.append("")
        _CTX["prev"] = "heading"
        _walk_mixed(node, out, False, lang, top=True)
    elif t == "section":
        key = str(node.get("key") or "")
        name = (node.get("name") or "").strip()
        if re.fullmatch(r"U\d+", key):
            out.append("## § " + name)      # 无序号标小节：仅保留 §
        else:
            out.append("## §" + name)       # name 自带 "N.M 标题" 序标
        out.append("")
        _CTX["prev"] = "heading"
        _walk_mixed(node, out, False, lang, top=True)
        out.append("---")
        out.append("")
    else:
        _render_item(node, out, lang)


def _tidy_separators(lines):
    """草稿分割线整理（2026-08-29 Koopman 书实测）：
    1) 堆叠 ``---`` 合并——嵌套小节边界各自 emit ``---``（子节末 + 父节末），
       产生 "``---`` 空行 ``---``" 堆叠；间距 ≤2 行的 ``---`` 组合并为一个；
    2) 每个保留的 ``---`` 上下恰有一个空行（V-F：``---`` 上下必须空行）；
    3) 连续多空行折叠为单个空行。幂等。"""
    out = []
    i, n = 0, len(lines)
    while i < n:
        if lines[i].strip() == "---":
            last = i
            while True:
                k = last + 1
                while k < n and not lines[k].strip():
                    k += 1
                if k < n and lines[k].strip() == "---" and k - last <= 2:
                    last = k
                else:
                    break
            out.append("---")
            i = last + 1
        else:
            out.append(lines[i])
            i += 1
    res = []
    for ln in out:
        if ln.strip() == "---":
            while res and not res[-1].strip():
                res.pop()
            if res:
                res.append("")
            res.append("---")
            res.append("")
        elif not ln.strip():
            if res and res[-1].strip():
                res.append("")
        else:
            res.append(ln)
    while res and not res[-1].strip():
        res.pop()
    return res


def render_chapter(ext, ch_key, language):
    """渲染单章草稿；返回输出路径。"""
    p = _ac.out_path(ext, ch_key)
    if not os.path.exists(p):
        raise SystemExit("[render_draft] 缺 %s——先跑 build_structure + attach_content。" % p)
    with open(p, encoding="utf-8") as f:
        node = json.load(f)
    # 原嵌图格式上下文：figure_index 按文件名索引 + 图号标签（verify_config Figure 组）
    fp = os.path.join(ext, "figure_index.json")
    try:
        with open(fp, encoding="utf-8") as f:
            idx = json.load(f)
    except Exception:
        idx = []
    _FIGCTX.clear()
    _FIGCTX["index_by_basename"] = {
        os.path.basename(e.get("file") or ""): e
        for e in (idx if isinstance(idx, list) else [])}
    _FIGCTX["labels"] = _load_fig_labels(ext)
    _FIGCTX["book_dir"] = os.path.dirname(os.path.abspath(ext.rstrip("/\\")))
    _CTX["prev"] = "heading"
    if language == "en":
        out = [
            "<!-- book-summarizer auto-draft (write-source): rendered from %s per" % os.path.basename(p),
            "     writing-rules base formatting (bold-label items, > example blocks, proof-sketch",
            "     quotes, paragraphing). Formulas are raw OCR -- MUST be rewritten during the",
            "     adjustment pass (never copy verbatim); proofs compressed to numbered steps;",
            "     Tier compression / noise cleanup happen in the adjustment pass. -->",
            "",
        ]
    else:
        out = [
            "<!-- book-summarizer 自动草稿（write-source 步骤 1）：由 %s 渲染，已按" % os.path.basename(p),
            "     writing-rules 基本格式排版（粗体标签冒号接正文、例块 > 包裹、证明思路块引用、",
            "     分段）。公式为 OCR 原样，调整时必须逐条重写校正（严禁照抄）；证明须压缩为",
            "     1. 2. … 编号步骤；Tier 压缩 / 英文标注 / 残余噪声清理在调整时执行。 -->",
            "",
        ]
    _render_node(node, out, language)
    out = _tidy_separators(out)
    if language == "en":
        # 英文书草稿禁任何 CJK（writing-rules 双语铁律）：契约 CN 标签已由
        # _item_header_name 转换，此处清除 OCR 数学字形误读残留的单字 CJK 碎片
        # （入/口/哆 等，均在 $$ 块外，实测不破坏公式）。
        out = [re.sub(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+", "", ln) for ln in out]
    out_p = os.path.join(ext, _ac.OUT_DIR_NAME, "draft_ch%s.md" % ch_key)
    with open(out_p, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip() + "\n")
    return out_p


def main():
    argv = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    ext = argv[0]
    if not os.path.exists(os.path.join(ext, "_extraction_done.json")):
        print("[render_draft] BLOCKED: 缺 _extraction_done.json（MM Repair 未完成）。")
        return 2
    try:
        chapters = [int(x) for x in argv[1:]]
    except ValueError:
        chapters = argv[1:]
    if force:
        _ac.attach(ext, chapters or None)
    keys = [k for k in _ac.list_chapter_keys(ext)
            if not chapters or k in {str(c) for c in chapters}]
    language = _book_language(ext)
    for k in keys:
        out = render_chapter(ext, k, language)
        print("draft -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
