#!/usr/bin/env python3
"""tools/deregister_formula_tags.py — 把契约里**印面根本不存在的公式序标**摘掉（四本账同步）。

缺陷场景（Katok–Hasselblatt《Introduction to the Modern Theory of Dynamical Systems》
实测 2026-09-29）：收割器把条目序标 / 散文交叉引用（`12.2.2` 是节内练习号、`18.3.1` 是
定理号、`i'` 是证明里条件列表的 `(i')`）误挂成展示式的 `tag`。后果与「漏号」相反但同样
两头堵：契约不该登记的号成了对账真值 → 写手照印面**不写** `\tag{}` 判「漏写」，删掉又
判「编造」，而号已顺着契约流进两侧单元正文和两版最终 md（本书 19 处：18 处经 PDF 出版方
文字层逐号复核——全章页窗里该号只作为条目号/交叉引用出现，从未以 `(N)` 编号形态出现；
剩一处 `ch14 i'` 的契约块本身是**空公式** `{"formula": "", "tag": "i'"}`，编号列不可能给
空块编号）。

判据**不自造**：检测趟与修复趟共用闸门 ⑭（`lib.tag_attestation.unattested_tags`，读页
口径 `dir_page_loader(node_page_dir(ext, tree, ch), ext)`，与
`gate_units._page_label_loader` / 收割处 `build_structure` 同源；人工确证豁免
`attested_numbers(ext)` 与
Q 层同一份登记）。于是：
  * ⑭ 没判毒的号 → 本工具**拒绝**删除（它在页窗里找得到印刷锚点，多半是真编号）；
  * 真印却被 OCR 漏掉的号 → 走 `config/verify_config/register_formula.py` 登记
    `known_book`（登记后 ⑭ 与本工具同时看见它，这才是正解，不是删）。
与 `tools/backfill_formula_tags.py`（回填丢失的号）互为反向通道，两者共用同一批谓词。

🔴 **第三类缺陷 = 「号是真的，但挂错了块」**（`--mispaired`，2026-10-16 Lehmann ch6 实测）：
上面两条通道各管「缺失」与「幻影」，唯独管不了**配对错**——号在印面确实存在（所以 ⑭ 不判毒、
常规删除被拒），但它挨着的**不是**契约里被登记的那条展示式。实测 (6.5.10)：印面 p437 该号标在
一张概率表（`bbb bbc … / 1/27 3/27 …`）左侧，契约里那张表只是 `text` 块，收割器把号给了它上面
那条**无号**展示式 `P(X*₍₁₎=b, X*₍₂₎=b, X*₍₃₎=c) = 3/27`（机械夹逼判据的盲区：前后两号之间
「唯一未挂号的展示块」并不等于「印面带号的块」，中间还可以有 text/表格块当真主）。
后果与幻影相反但同样两头堵：错号成了对账真值 → 那条无号公式被逼写 `\tag`，真主（表）永远补不上。

`--mispaired --host <真主>` 就是这条合法出口，`--host` 取二者之一：
  * 契约里真主展示块的节点 key（摘完紧接着按该 key 跑 `backfill_formula_tags.py` 落回正确块）；
  * 字面量 `non-display`：印面真主是表格/纯文字行，契约无展示块可挂 ⇒ 该号**不入账**
    （与章内其他「印面有号但非展示式」的裁决同一处置；⑱ 只扫契约树，不会因此复发）。
保险：`--mispaired` 必须配 `--host`（少一个拒）；该号必须在契约里**恰好登记一处**（一处 = 一个
公式块；同一块把号同时写进 `tag` 与 `tags` 只算一处，2026-10-30 数值分析 ch5 实测旧码把它误算成
两处 → 唯一错挂处被当成歧义假拒。跨块两处仍算歧义，拒，要求逐条处理）；写出前打印被摘块的节点
key + 公式首串，台账记 `mode`/`mispaired_from`/`host`/`contract_blocks`，
使「摘错了也能反查是谁在何时按什么证据摘的」。

🔴 **第四类缺陷 = 「锚点是假的」，⑭ 因此失明**（`--false-anchor`，2026-10-30 跨语料普查实测）。
⑭ 判「无印刷锚点」用的锚点集是**整章页窗的并集**且**不管那个数字块是什么角色**，于是页码、
节号、数学符号都能替幻影 tag 自证清白。普查（`tools/census_gate14_bare_blindness.py`）在
56 本 / 453 章里量到 8 个「±1 页外」的首要嫌疑，逐条 fitz 裁页目视，**8 个全是幻影**：
  * Gelfand–Manin `methods-of-homological-algebra` ch4 `2` / `259`——章眉
    `2. Derived Categoris are Triangulated  257` 的节号与**页码**
    （p274 页眉 `259`，该页两条展示式右缘无号）；
  * Rising Sea ch2/ch5/ch21/ch27 `0` ×4——`\\boldsymbol { 0 }` / `\\neq 0` / 孤立裸块 `0`，
    是**数学零**，不是编号；
  * 遍历论_孙文祥 ch6 `6.2`——`\\S 6 . 2` 即**节题 §6.2**（p163/166）；印面该式只有左标题
    「引理 6.6.2」，式右缘无号（fitz p185 目视）；
  * 数学分析 ch14 `4m`——印面 `\\sum 1/(m²−n²) = −3/(4m²)` 里的**分母片段**（fitz p176 目视）。
这类号 ⑭ 判不出毒（`--number` 走常规通道即被拒），语义上又**不是**「真印但挂错块」，
所以旧工具**没有合法出口**。`--false-anchor --anchor-kind <page-number|section-number|
math-glyph|list-marker|other>` 就是这条出口，机械保险两条：
  * 该号在本章页窗里**只能有裸块锚点**——只要找得到一个 `(N)` 括号锚点就拒（`(N)` 是编号本形，
    那种形态属「挂错块」，归 `--mispaired`），于是两个通道**互斥且自动分诊**；
  * 工具自己把裸锚的**原块文本 + 页码**打印出来并写进台账（`bare_anchors`/`anchor_kind`），
    「假锚」这个声称无法凭空写下。
`--false-anchor` 与 `--mispaired` 同时给 → 拒（语义相反）。

🔴 **块上多号 = 抽取器把数组元素当编号收割**（数值分析 ch5 例9 实测）：一条展示式的 `tag` 与
`tags` 里挂着 4 个号（`1.83 / 1.08 / 5.8 / 0.783`），其中只有 `(5.8)` 是印面 p183 右缘的编号，
其余三个是同一展示式右端列向量的**元素**（`page_183` 里各占一个整块，故闸门 ⑭ 的「整块裸号」
锚点自证为真，判不出毒——见 `#48`）。摘这类号时**幸存者必须提升回 `tag`**：`node_tags` 只在
`tag` 非空时才展开 `tags`，只清 `tag` 会让真号从对账眼里消失、单元照印面写它反被判「编造」。
旧 `clear_in_model` 相反：`tag` 命中即 `pop("tags")`，一次摘除顺手毁掉同块其他号。现统一为
「按号摘除 → 幸存者按常规形写回（单号不留 `tags`）」，字面替换表达不了时改走**整树语义重写**
（前提是该文件的 JSON 风格能逐字节复演原文，否则拒绝，不猜 indent）。

四本账（缺一即漂移）：
  ① 分章契约 `ch{N}.json`（附录 `appendix{X}.json` / 补篇 `supplement{S}.json`）目标公式块
     的 `tag` → `""`（与收割处 `strip_unattested` 同一形态：块留着、只是不再声称带编号；
     该块还挂着别的号时按号摘除、**幸存者提升为 `tag`**，见上文块上多号一段）
  ② `units/ch{N}/manifest.json` 与 ③ `units-translate/ch{N}/manifest.json` 的 `tags` 列表
     （无该字段/无该号时本账自动跳过并如实报告；多数书由 `split_draft_units` 写入 `tags`）
  ④ 两侧单元正文里的 `\tag{N}` / `\tag*{N}` —— **本工具直接删**（删除是纯机械操作，不像
     回填那样需要写手按印面补内容）：独占一行的 `\tag{}` 连同该行一起删（不留空围栏行），
     行尾内联形只去掉 token 与前导空格；首行 marker 一字节不动。
  写完后待办（工具打印确切命令）：重跑 `gate_units` → `tools/resync_src_hash.py --ch N --commit`
  （源正文变了，译侧 `src_hash` 快照必须重同步——🔴 **不是** `init_translate_units`：它按 init
  语义把每个单元的 `hash` 一并重算，会覆写与本次无关的派生时刻快照，2026-10-30 Gelfand–Manin ch4 实测
  31 处）→ 交付侧按收官状态二选一：**已收官书禁重 merge**，用 `tools/mirror_unit_line.py`
  只镜像被摘的那一行（独占一行的 `\tag` 用 `--delete-line`）；未收官才 `merge_units` 重拼两版 md。

保险（全部机械）：
  - 默认 dry-run，`--apply` 才写盘；写盘前把每个受影响文件备份到
    `<extract>/_bak_deregister_tags/<时间戳>/`，逐次追加台账
    `<extract>/_formula_tag_deregistrations.jsonl`。
  - **字节守恒**：逐文件探测换行符（CRLF/LF）与末尾换行，先断言「按该风格复演即原字节」，
    再做锚定字面替换；写出前断言「解析后的新契约树 == 在旧树副本上只清这些 tag 的语义模型」。
    故非标准序列化的契约（indent=1 / ensure_ascii=True / 尾部游离 LF）也能安全修，
    且除目标串外一字节不变。
  - `--number` 必须在 ⑭ 判毒集合里，**或**走 `--mispaired`（号真印但挂错块，见上文第三类缺陷），
    **或**走 `--false-anchor --anchor-kind`（锚点是页码/节号/数学符号，见上文第四类缺陷；
    该号只要有任一 `(N)` 括号锚点就拒，自动分流到 `--mispaired`）；
    契约与两侧正文都没有该 tag → NO-OP（幂等）；
    manifest 的 `tags` 账与契约同一条保险：只在该文件自己的 JSON 风格**能逐字节复演原文**
    时整文件重写（indent=1/2/4、紧凑、`ensure_ascii` 两形、尾换行 ''/'\\n'、CRLF 都跟随原样），
    复演不上（混合缩进、手改过的 `tags` 一行形、键序不同）则拒绝并说明；
    单元正文替换后断言「再无 `\tag{N}`」且首行 marker 未变。

用法:
  python tools/deregister_formula_tags.py <extract_dir> 18 --list          # 该章 ⑭ 判毒清单
  python tools/deregister_formula_tags.py <extract_dir> 18 --number 18.3.1 \\
      --number i' --evidence "fitz 文字层 p586-617 全窗：18.3.1 只作定理号出现，无 (18.3.1)" [--apply]
  python tools/deregister_formula_tags.py <extract_dir> 6 --number 6.5.10 --mispaired \\
      --host non-display --evidence "fitz 200dpi p437：(6.5.10) 标在概率表行左，非展示式" [--apply]
  python tools/deregister_formula_tags.py <extract_dir> 6 --number 6.2 --false-anchor \\
      --anchor-kind section-number \\
      --evidence "fitz 200dpi p185：该式左标题『引理 6.6.2』，右缘无号；6.2 的裸锚是 p163/166 节题 §6.2" [--apply]
退出码：0 = 已写出 / dry-run 可行 / 已在账（幂等 NO-OP）；2 = 拒绝（未写任何文件）。
"""
import argparse
import copy
import io
import json
import os
import re
import sys
import time
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

from data.book_structure.book_structure import (resolve_chapter_json_path,  # noqa: E402
                                                unit_dir_name)
from lib.page_dir import node_page_dir  # noqa: E402
from lib.tag_attestation import (anchor_locations, attested_numbers,  # noqa: E402
                                 collect_contract_tags, dir_page_loader,
                                 operand_only_paren_anchor,
                                 unattested_tags)

_TAG_OPEN = r"\\tag\*?\{\s*%s\s*\}"

# `--false-anchor --anchor-kind` 的词表：操作者必须**指名**那个假锚在印面上到底是什么。
ANCHOR_KINDS = {"page-number": "页眉/页脚页码",
                "section-number": "节号（如 `§6.2` 的节题被当编号）",
                "math-glyph": "数学符号里的数字（`\\boldsymbol{0}`、`-3/(4m²)` 的分母）",
                "list-marker": "条目/小问序号（列表 `1.` `2.` 或表头）",
                "other": "其它（须在 --evidence 里写清印面实际形态）"}


class Refuse(Exception):
    """拒绝写出（未触碰任何文件）。"""


# ── 字节守恒读写：不折行、不补末尾，按原字节复现 ─────────────────────────────
def read_text(path):
    """→ 文本（**保留原换行形态**，含混合 CRLF/LF）。非 UTF-8 即拒绝。"""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise Refuse("%s：不是 UTF-8（%s），拒绝改写" % (path, e))
    if text.encode("utf-8") != raw:
        raise Refuse("%s：UTF-8 复演与原字节不符，拒绝改写" % path)
    return text


def write_text(path, text):
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def restyle(new_text, old_text):
    """整文件重写时跟随原换行风格（混合形态按多数派；无 CRLF 即 LF）。"""
    if "\r\n" in old_text and old_text.count("\r\n") >= old_text.count("\n") / 2:
        return new_text.replace("\n", "\r\n")
    return new_text


# ── ① 契约：锚定字面替换 + 语义模型一致性断言 ────────────────────────────────
def block_tag_seq(node):
    """公式块登记的号：`tag` 与 `tags` 归并、保序去重（收割器两处都写是常态）。"""
    seq = []
    t = str(node.get("tag") or "").strip()
    if t:
        seq.append(t)
    for x in (node.get("tags") or []):
        s = str(x).strip()
        if s and s not in seq:
            seq.append(s)
    return seq


def apply_block_removal(node, nums):
    """块上摘掉 `nums` 里的号 → 被摘个数（0 = 该块与此号无关，一字节不动）。

    🔴 **幸存者必须提升回 `tag`**（2026-10-30 数值分析 ch5 例9 实测）：抽取器把展示式里
    数组的元素当编号收割，一块挂 `tag=1.83 / tags=[1.83,1.08,5.8,0.783]`，其中 `(5.8)` 是
    印面 p183 右缘的真号。而 `node_tags`（单元级 tag 对账真值）读的是 `if c.get("tag")`
    才展开 `tags`——只清 `tag` 把号留在 `tags` 里 = 真号从对账眼里消失，单元照印面写它
    反被判「编造编号」。旧 `clear_in_model` 更糟：`tag` 命中就 `pop("tags")`，一次摘除
    顺手毁掉同块所有其他号。故统一成「摘这些号 → 幸存者按常规形写回（单号不留 `tags`）」。
    """
    seq = block_tag_seq(node)
    removed = [x for x in seq if x in nums]
    if not removed:
        return 0
    surv = [x for x in seq if x not in nums]
    if surv:
        node["tag"] = surv[0]
        if len(surv) > 1:
            node["tags"] = surv
        else:
            node.pop("tags", None)
    else:
        node["tag"] = ""
        node.pop("tags", None)
    return len(removed)


def clear_in_model(tree, nums):
    """在副本上摘掉这些 tag（镜像收割处 `strip_unattested` 的语义）。

    → (新树, {号: 处数}, 变更明细)。明细 = ``[(节点 key, 公式首串, 摘掉的号, 摘后该块号列)]``，
    供台账与「幸存者提升」待办打印：摘除**顺带改了别的号的归属**（`tags` 里的幸存者被提升
    成 `tag`）必须留痕，否则事后看不出这条块曾易主。
    """
    out = copy.deepcopy(tree)
    counts, changes = {}, []

    def walk(node, own):
        if isinstance(node, dict):
            key = node.get("key")
            own = str(key) if key is not None else own
            if node.get("formula") is not None:
                seq = block_tag_seq(node)
                removed = [x for x in seq if x in nums]
                if removed:
                    for x in removed:
                        counts[x] = counts.get(x, 0) + 1
                    apply_block_removal(node, nums)
                    changes.append((own, str(node.get("formula"))[:70], removed,
                                    block_tag_seq(node)))
            for c in node.get("sub_sec") or []:
                walk(c, own)
        elif isinstance(node, list):
            for c in node:
                walk(c, own)

    walk(out, None)
    return out, counts, changes


# 契约的序列化风格**只认能逐字节复演原文的那一种**（不猜 indent / ensure_ascii）。
# 🔴 候选集要覆盖 `separators` 那一维：历史契约里有 `json.dumps(..., indent=2,`
# `separators=(",", ":"))` 写出的（冒号后不空格，2026-10-30 遍历论_孙文祥 ch6 实测——`6.2``
# 同块 `tag`+`tags` 双登记必须走整树重写，旧候选集探不到 → 假拒「风格无法逐字节复演」）。
# 加候选**不放宽安全性**：:func:`probe_dump_style` 仍拿旧树逐字节比原文，猜错就复演不上，
# 复演不上照旧拒（判据测试 `test_multi_tag_edit_works_in_no_space_colon_style` /`…refuses_…`）。
# 🔴 同一假拒也咬 `indent=1`（2026-10-31 Fraleigh ch23 实测：两侧 `units/*/manifest.json`
# 都是 indent=1，`--false-anchor` 干跑到 manifest 账本就被「请人工同步后重跑」挡死——而
# 「人工同步」正是让人手写 JSON 改 `tags`，与本工具的存在理由相反）。`indent=1` 在语料里
# 有实数（同族 `backfill_formula_tags._INDENTS` 的 2026-10-29 普查：2139 份里 indent=2 占
# 1935、indent=1 占 148），故按同一判据收进候选集；3/6/8 仍一份没有，不收。
_DUMP_STYLES = ({"ensure_ascii": False},
                {"ensure_ascii": False, "indent": 2},
                {"ensure_ascii": False, "indent": 2, "separators": (",", ": ")},
                {"ensure_ascii": False, "indent": 2, "separators": (",", ":")},
                {"ensure_ascii": False, "indent": 1},
                {"ensure_ascii": False, "indent": 1, "separators": (",", ":")},
                {"ensure_ascii": False, "indent": 4},
                {"ensure_ascii": False, "indent": 4, "separators": (",", ":")},
                {"ensure_ascii": True},
                {"ensure_ascii": True, "indent": 2},
                {"ensure_ascii": True, "indent": 2, "separators": (",", ":")})


def probe_dump_style(text, tree):
    """探测该契约的序列化风格：能**逐字节复演原文**的那一套 `json.dumps` 参数；探不到 → None。

    🔴 探测必须拿**旧树**比原文，不能拿摘改后的新树：新树与原文本来就差那些 tag，
    任何风格都比不上 → 探不到 → 误报「风格无法逐字节复演」而拒写（多号块必走这条路）。
    """
    norm = text.replace("\r\n", "\n")
    body = norm[:-1] if norm.endswith("\n") else norm
    for kw in _DUMP_STYLES:
        if json.dumps(tree, **kw) == body:
            return kw
    return None


def serialize_like(text, tree, obj):
    """用 `text` 自己的风格序列化 `obj`（风格由 `tree` 对原文探得）；探不到 → None。"""
    kw = probe_dump_style(text, tree)
    if kw is None:
        return None
    tail = "\n" if text.replace("\r\n", "\n").endswith("\n") else ""
    return restyle(json.dumps(obj, **kw) + tail, text)


def contract_edit(text, tree, nums):
    """契约文本 → (new_text, {号: 删除处数}, 变更明细)；语义不符即 Refuse。

    两条写出路径，终点都断言「解析结果 == 语义模型」：
    ① **锚定字面替换**（常规形：一块一个号，`"tag": "N"` 在文件里就是那一处）；
    ② **整树语义重写**（`tag`+`tags` 同块多号时 ① 表达不了「摘三个留一个并提升」，
       见 :func:`apply_block_removal`），前提是 :func:`serialize_like` 能逐字节复演
       原文，否则拒绝——不猜缩进/转义风格，宁可让人工同步。
    """
    model, counts, changes = clear_in_model(tree, nums)
    if not any(counts.values()):
        return text, counts, changes
    lit = text
    for num in nums:
        target = '"tag": "%s"' % num
        if target in lit:
            lit = lit.replace(target, '"tag": ""')
    try:
        literal_matches = json.loads(lit) == model
    except ValueError:
        literal_matches = False
    if literal_matches:
        return lit, counts, changes
    cand = serialize_like(text, tree, model)
    if cand is None:
        raise Refuse("契约里这些号挂在**同一块的 `tag`+`tags` 多处**（摘除要改写 `tags` 列表），"
                     "锚定字面替换表达不了，而该文件的 JSON 序列化风格无法逐字节复演"
                     "（indent/ensure_ascii 非已知形）——拒绝整树重写，请人工同步后重跑 %s"
                     % sorted(counts))
    if json.loads(cand) != model:
        raise Refuse("契约整树重写后的解析树 ≠ 语义模型（序列化风格探测失败），拒绝写出")
    return cand, counts, changes


# ── `--mispaired` 的保险：错挂处必须唯一、真主必须可查 ────────────────────────
def tag_occurrences(tree, nums):
    """契约树 → ``{号: [(所属节点 key, 公式首串, 登记位置)]}``（该号在契约里的**每一处**）。

    🔴 「一处」= **一个公式块**，不是一个字段：收割器常把同一个号同时写进块的 `tag`
    和 `tags[0]`（数组元素被当编号收割的形态），按字段数会得出「登记 2 处」→ 把
    **唯一错挂处**误判成歧义而拒改（2026-10-30 数值分析 ch5 例9 实测假拒）。
    同一号出现在**两个块**（`tag` + `tags` 各一处也算）仍算两处 → 照旧拒，要求逐条处理。

    🔴 key 取**最近的有 key 祖先**：契约里的内容块（`{"formula": …, "tag": …}`）自己
    没有 key，只有所属条目节点有——用块自己的 `key`（恒为 None）打印等于没说，
    回填也没有可用的坐标（`backfill_formula_tags.py --node` 要的就是条目节点 key）。
    """
    out = {}

    def walk(node, own):
        if isinstance(node, dict):
            key = node.get("key")
            own = str(key) if key is not None else own
            if node.get("formula") is not None:
                head = str(node.get("formula"))[:70]
                seq = block_tag_seq(node)
                t = str(node.get("tag") or "").strip()
                in_tags = {str(x).strip() for x in (node.get("tags") or [])}
                for num in seq:
                    if num not in nums:
                        continue
                    at = ("tag+tags" if num == t and num in in_tags
                          else ("tag" if num == t else "tags"))
                    out.setdefault(num, []).append((own, head, at))
            for c in node.get("sub_sec") or []:
                walk(c, own)
        elif isinstance(node, list):
            for c in node:
                walk(c, own)

    walk(tree, None)
    return out


def contract_node_keys(tree):
    """契约树 → 全部节点 key 的字符串集合（校验 `--host` 真在契约里）。"""
    keys = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get("key") is not None:
                keys.add(str(node.get("key")))
            for c in node.get("sub_sec") or []:
                walk(c)
        elif isinstance(node, list):
            for c in node:
                walk(c)

    walk(tree)
    return keys


# ── ②③ manifest 的 tags 账 ──────────────────────────────────────────────────
# 🔴 **尾换行不算「异形」**（2026-10-30 跨架普查 787 份 `units/*/manifest.json`：613 无尾换行、
# 72 恰有一份、102 真异形）：旧守卫写作 `json.dumps(obj, indent=2) != text`，于是那 72 份
# **格式完全正常**的账被挡在门外，而处方「该本账请人工同步后重跑」＝让人手写 JSON 改 `tags`
# 列表——恰是本工具存在的理由所排斥的动作（数学分析 ch15 摘 `1x` 时实测撞墙）。
# 🔴 同一处方的第二道墙是**只认 indent=2**（2026-10-31 Fraleigh ch23 实测）：那本书两侧
# manifest 全是 indent=1，`--false-anchor` 干跑到这一步就被拒，而这本账**必须**跟着契约摘——
# 留下 manifest 里的 `tags` 等于让 `node_tags` 继续把幻影号当对账真值。
# 正解不是「放宽到任意形」，而是**与契约路径共用同一个探测**：:func:`probe_dump_style`
# 拿旧树逐字节复演原文，复演得上就按该风格重出并还原尾换行/换行符，复演不上（混合缩进、
# `tags` 挤成一行、键序不同那 102 份）照旧拒。守卫的**目的**（整文件重生不夹带改写）一点
# 没被削弱；两份副本（这里与 :func:`tools.backfill_formula_tags.load_strict`）现在同源同判。
def manifest_edit(text, path, nums):
    """manifest 文本 → (new_text|None, 说明)。None = 该侧无此账（幂等跳过）。"""
    obj = json.loads(text)
    units = obj.get("units") or []
    hits = [u for u in units if any(str(x).strip() in nums for x in (u.get("tags") or []))]
    if not hits:
        return None, ("该 manifest 无 tags 字段" if not any(u.get("tags") is not None
                                                           for u in units)
                      else "无这些号的 tags 登记")
    probe = copy.deepcopy(obj)          # 风格探测必须用**改之前**的树，见 contract_edit 同款注释
    changed = []
    for u in hits:
        old = list(u["tags"])
        keep = [x for x in old if str(x).strip() not in nums]
        if keep:
            u["tags"] = keep
        else:
            u.pop("tags", None)
        changed.append("%s %s→%s" % (u.get("file"), old, keep))
    new = serialize_like(text, probe, obj)
    if new is None:
        raise Refuse("%s：要改 `tags` 账但该文件的 JSON 风格无法逐字节复演"
                     "（indent/ensure_ascii 非已知形，或手改过）——拒绝整文件重写，请人工同步后重跑"
                     % path)
    if json.loads(new) != obj:
        raise Refuse("%s：manifest 整文件重写后的解析树 ≠ 语义模型（风格探测失败），拒绝写出" % path)
    return new, "; ".join(changed)


# ── ④ 单元正文：删 \tag token ────────────────────────────────────────────────
def unit_edit(text, nums):
    """单元正文（含首行 marker）→ (new_text, 删除处数)。"""
    n = 0
    for num in nums:
        esc = re.escape(num)
        # 独占一行（可带 `> ` 前缀）：整行连换行一起去掉，避免留下空围栏行
        text, k = re.subn("(?m)^[ \t]*(?:>[ \t]*)?" + _TAG_OPEN % esc + r"[ \t]*\r?\n",
                          "", text)
        n += k
        # 内联形：只去掉 token 与其前导空格
        text, k = re.subn(r"[ \t]+" + _TAG_OPEN % esc, "", text)
        n += k
        if re.search(_TAG_OPEN % esc, text):
            raise Refuse("单元正文里仍有无法安全去除的 `\\tag{%s}` 形态，拒绝写出" % num)
    return text, n


def unit_dirs(bs, ch_key):
    """章 → 两侧单元目录，**以磁盘物理证据为准**。

    🔴 不能只信 `unit_dir_name`：它的前缀取进程级 kind 注册表（`prime_chapter_kinds`
    灌注），未灌注时把补篇键 `S` 算成 `appendixS` → 目录「不存在」→ 两侧正文/manifest
    两本账**静默跳过**，工具照样报成功（Katok supplementS 实测同型的 `sync_translate_markers`
    误跳 41 单元，见 `tools/tests/test_sync_markers_contract_path.py`）。故按三种章型
    逐一探测；同时命中多个目录 = 该键有歧义，拒绝而不是猜。
    """
    cands = []
    try:
        cands.append(unit_dir_name(ch_key))
    except Exception:
        pass
    for pre in ("ch", "appendix", "supplement"):
        cands.append("%s%s" % (pre, ch_key))
    out = []
    for side in ("units", "units-translate"):
        hits = []
        for nm in cands:
            d = os.path.join(bs, side, nm)
            if os.path.isdir(d) and d not in hits:
                hits.append(d)
        if len(hits) > 1:
            raise Refuse("%s 侧同时存在 %s 两个该章单元目录，键 %r 章型有歧义，"
                         "拒绝猜（先核对 chapter_map 的 kind）"
                         % (side, ", ".join(os.path.basename(h) for h in hits), ch_key))
        if hits:
            out.append((side, hits[0]))
    return out


def _mkdir_unique(bak):
    cand, i = bak, 0
    while True:
        try:
            os.makedirs(cand)
            return cand
        except FileExistsError:
            i += 1
            cand = "%s-%d" % (bak, i)


def _bak_name(ext, pth):
    """备份件文件名 = 相对 extract 的路径（分隔符折成 `+`），保证**每份目标各得一件**。

    🔴 与 backfill_formula_tags 同一缺陷：旧形 `<父目录名>__<文件名>` 会让
    `units/chN/manifest.json` 与 `units-translate/chN/manifest.json` 撞成同名（本工具
    一次跑两侧，见 `_manifest_sides`）→ 后写的盖掉先写的，回滚时少一份。
    """
    rel = os.path.relpath(os.path.abspath(pth), os.path.abspath(ext))
    return rel.replace("\\", "+").replace("/", "+")


# ── 主流程 ───────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("extract_dir")
    ap.add_argument("ch_key")
    ap.add_argument("--number", action="append", default=[],
                    help="要摘掉的契约 tag（可重复；须被闸门 ⑭ 判为无印刷锚点，"
                         "或给 --mispaired 声明「真印但挂错块」）")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--mispaired", action="store_true",
                    help="该号印面真实存在但**挂错了块**（⑭ 不判毒的唯一合法摘除通道）")
    ap.add_argument("--false-anchor", action="store_true",
                    help="该号在页窗里的锚点是**假锚**（页码/节号/数学符号/列表号被当编号），"
                         "印面该式从未带这个号 —— ⑭ 失明时的取证摘除通道，须配 --anchor-kind")
    ap.add_argument("--anchor-kind", default="",
                    help="与 --false-anchor 同用：假锚的真身，取值 %s" % " | ".join(ANCHOR_KINDS))
    ap.add_argument("--host", default="",
                    help="与 --mispaired 同用：真主 = 契约节点 key，或字面量 non-display"
                         "（印面真主是表格/文字行，该号不入账）")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--list", action="store_true", help="列该章 ⑭ 判毒号 + 两侧正文命中数")
    a = ap.parse_args(argv)

    ext = a.extract_dir
    bs = os.path.join(ext, "book_structure")
    try:
        cpath = resolve_chapter_json_path(ext, a.ch_key)
        if not cpath or not os.path.isfile(cpath):
            raise Refuse("找不到分章契约（%s）" % cpath)
        craw = read_text(cpath)
        tree = json.loads(craw)

        # 🔴 读页必须走 `node_page_dir`（与 `gate_units._page_label_loader` / 收割处同一口径）：
        # 分册书的页放在 `_extract/<册>/` 下，只给 `ext` 时该章**一页也读不到**，⑭ 的
        # 「缺页文件不判」会让 `condemned` 恒空 → 本工具把每个号都当成「⑭ 已判毒」照删，
        # 等于把删除闸门关掉（2026-10-30 数学分析实测，普查见 census --loader-diff）。
        page_ld = dir_page_loader(node_page_dir(ext, tree, a.ch_key), ext)
        condemned = unattested_tags(tree, page_ld, attested_numbers(ext))
        dirs = unit_dirs(bs, a.ch_key)

        if a.list:
            print("闸门 ⑭ 判毒（契约 tag 在本章页窗内无印刷锚点，已豁免 known_book）：")
            for num in sorted(str(x) for x in condemned):
                hits = []
                for side, d in dirs:
                    for name in sorted(os.listdir(d)):
                        if name.endswith(".md"):
                            body = read_text(os.path.join(d, name))
                            if re.search(_TAG_OPEN % re.escape(num), body):
                                hits.append("%s:%s" % (side, name))
                print("  %-10s 单元正文命中 %d 个文件 %s" % (num, len(hits), " ".join(hits[:8])))
            att = attested_numbers(ext)
            print("（known_book 豁免登记：%s）" % (" ".join(sorted(att)) or "空"))
            return 0

        if not a.number:
            raise Refuse("需要 --number（或 --list 看该章 ⑭ 判毒清单）")
        if len(a.evidence.strip()) < 20:
            raise Refuse("--evidence 必填且不少于 20 字（印面出处：页窗 / 该号在印面上的实际形态）")
        host = a.host.strip()
        if a.mispaired and not host:
            raise Refuse("--mispaired 必须配 --host <真主契约 key | non-display>："
                         "没有真主，摘除就只是将号从账上抹掉，与幻影通道的语义不同，"
                         "台账必须说清它该落在哪")
        if host and not a.mispaired:
            raise Refuse("--host 只在 --mispaired 通道有意义（请同时给 --mispaired），"
                         "否则该参数会被静默忽略")
        ak = a.anchor_kind.strip()
        if a.false_anchor and a.mispaired:
            raise Refuse("--false-anchor 与 --mispaired 语义相反：前者是「该号从未以编号形态印出」，"
                         "后者是「该号真印但挨错了块」。一次只能声明一种")
        if a.false_anchor and ak not in ANCHOR_KINDS:
            raise Refuse("--false-anchor 必须配 --anchor-kind <%s>——假锚通道毁掉的是对账真值，"
                         "台账必须留下「那个锚点在印面上到底是什么」的可核对声明"
                         % " | ".join(ANCHOR_KINDS))
        if ak and not a.false_anchor:
            raise Refuse("--anchor-kind 只在 --false-anchor 通道有意义（请同时给 --false-anchor），"
                         "否则该参数会被静默忽略")

        # 先扫两侧正文与 manifest（一次读盘，供幂等判定与写出复用）
        bodies, mans = [], []
        for side, d in dirs:
            for name in sorted(os.listdir(d)):
                p = os.path.join(d, name)
                if name.endswith(".md"):
                    bodies.append([side, p, read_text(p)])
                elif name == "manifest.json":
                    raw = read_text(p)
                    mans.append([side, p, raw, json.loads(raw)])

        def _in_body(text, num):
            return re.search(_TAG_OPEN % re.escape(num), text) is not None

        def _in_tags(obj, num):
            return any(num in {str(x).strip() for x in (u.get("tags") or [])}
                       for u in (obj.get("units") or []))

        registered = {str(n) for _k, n in collect_contract_tags(tree)}
        condemned = {str(x) for x in condemned}
        nums, absent, blocked, mis = [], [], [], []
        for num in {str(x) for x in a.number}:
            present = (num in registered
                       or any(_in_body(b[2], num) for b in bodies)
                       or any(_in_tags(m[3], num) for m in mans))
            if not present:
                absent.append(num)
            elif num in condemned:
                nums.append(num)
            elif a.mispaired or a.false_anchor:
                nums.append(num)
            else:
                blocked.append(num)
        if blocked:
            raise Refuse("%s：闸门 ⑭ 未判它无毒（本章页窗里找得到印刷锚点）——多半是真编号，"
                         "删除等于毁掉对账真值。确要处理请先目视印面；真印却被抽取器漏挂的号"
                         "走 config/verify_config/register_formula.py 登记 known_book；"
                         "真印但**挂错了块**（该号挨的不是契约里这条展示式）"
                         "走本工具 --mispaired --host <真主 key|non-display>；"
                         "锚点在印面上**根本不是编号**（页码/节号/数学符号被当编号，"
                         "或 `(N)` 只是阵列/陪积链**内容**里的一项而整章页边不印编号，"
                         "⑭ 因此失明）走 --false-anchor --anchor-kind <假锚真身>"
                         % ", ".join(sorted(blocked)))
        if a.mispaired:
            # 只有「⑭ 不判毒」那批号才走错挂通道；⑭ 判毒的号仍按幻影语义处理。
            occ = tag_occurrences(tree, {n for n in nums if n not in condemned})
            for num in [n for n in nums if n not in condemned]:
                hits = occ.get(num) or []
                if len(hits) != 1:
                    raise Refuse("--mispaired %s：该号在契约里登记 %d 处（%s）——"
                                 "「挂错块」只在唯一错挂处成立，多处须逐条处理"
                                 % (num, len(hits),
                                    ", ".join("%s@%s" % (k, w) for k, _h, w in hits)))
                mis.append((num, hits[0]))
            if mis and host != "non-display":
                keys = contract_node_keys(tree)
                if host not in keys:
                    raise Refuse("--mispaired --host %r：契约里查无该节点 key（本章契约可用 key：%s）"
                                 "——真主若确为表格/文字行（契约无展示块可挂），"
                                 "请写字面量 non-display"
                                 % (host, " ".join(sorted(list(keys)[:40]))))

        bare_anchors = {}
        paren_factors = {}
        if a.false_anchor:
            # 🔴 假锚通道的**机械**前置：该号在页窗里只能有裸块锚点，或它的 `(N)` 全部
            # 呈「算式因子」形（见 `lib.tag_attestation.operand_only_paren_anchor`）。
            # 旧口径是「有一个 `(N)` 就拒」，理由是「`(N)` 形就是编号本形」。这个理由在
            # **整章不印页边编号**的书里不成立：OCR 把 Z₁₂ 陪积链 `(2)(6)=(6)(2)=…` 切成
            # 页窗块后，链里的 `(3)` 与页边编号被粘进公式行的 `(3)` **同形**，机械拒于是
            # 把真幻影分流到 `--mispaired`——而那条处方要求指认一个印面上不存在的宿主。
            # 现在只有一种情况放行：**整章没有一个独立编号块**（印面不存在编号列）
            # **且**该号每个 `(N)` 都紧贴括号/运算符。两条同时成立才算，原块照打台账。
            # 🔴 放行后仍要「有锚点可指」：因子块本身就是那一指（`paren_factors`），
            # 两类锚点都没有才拒——「⑭ 因锚点失明」这个前提就不能凭空声称。
            try:
                _lo, _hi = int(tree.get("page_start")), int(tree.get("page_end"))
            except (TypeError, ValueError):
                raise Refuse("--false-anchor 需要该章契约带页窗：判「假锚」要在页窗里取回原块，"
                             "没有页窗就没有可核对的证据")
            locs = anchor_locations(page_ld, _lo, _hi)
            for num in [n for n in nums if n not in condemned]:
                d = locs.get(num) or {"paren": {}, "bare": {}}
                if d["paren"]:
                    ok, why, ev = operand_only_paren_anchor(page_ld, _lo, _hi, num)
                    if not ok:
                        raise Refuse("--false-anchor %s：该号在本章页窗里找得到**带括号**的"
                                     "印刷锚点（p%s）——%s\n"
                                     "  若是「号真印但挂错了块」请改走 "
                                     "--mispaired --host <真主 key|non-display>"
                                     % (num, ", ".join(str(p) for p in sorted(d["paren"])[:8]),
                                        why))
                    paren_factors[num] = ev
                if not d["bare"] and num not in paren_factors:
                    raise Refuse("--false-anchor %s：页窗里连裸块锚点都没有 → ⑭ 本该判它无毒。"
                                 "查不到锚点说明读页口径或号形对不上，先核对口径再声明" % num)
                if d["bare"]:
                    bare_anchors[num] = {str(p): v for p, v in sorted(d["bare"].items())}

        if not nums:
            print("NO-OP     %s：契约、两侧 manifest 与单元正文都没有这个 tag（已摘过），"
                  "无需写出" % " ".join(sorted(absent)))
            return 0
        if absent:
            print("提示      %s：四本账里都查无此号（已摘过），本次跳过" % " ".join(sorted(absent)))

        craw_after, ccounts, cchanges = contract_edit(craw, tree, nums)
        targets = []
        if any(ccounts.values()):
            targets.append({"path": cpath, "before": craw, "after": craw_after})

        touched = []
        for side, p, raw in bodies:
            new, k = unit_edit(raw, nums)
            if not k:
                continue
            if new.split("\n")[0] != raw.split("\n")[0]:
                raise Refuse("%s：首行 marker 被动过，拒绝写出" % p)
            targets.append({"path": p, "before": raw, "after": new})
            touched.append("%s:%s(%d)" % (side, os.path.basename(p), k))

        man_notes = []
        for side, mp, raw, obj in mans:
            new, note = manifest_edit(raw, mp, nums)
            man_notes.append("%s/%s" % (side, note))
            if new is not None:
                targets.append({"path": mp, "before": raw, "after": new})

        print("章        = %s   契约=%s" % (a.ch_key, os.path.basename(cpath)))
        print("通道        = %s" % ("--mispaired（号真印但挂错块）" if mis
                                   else ("--false-anchor（假锚：印面无此号，真身=%s）"
                                         % ANCHOR_KINDS[ak] if bare_anchors
                                         else "⑭ 判毒（幻影）")))
        for num in sorted(bare_anchors):
            for pg, samples in sorted(bare_anchors[num].items())[:6]:
                print("假锚证据  = (%s) p%s 裸块 %s"
                      % (num, pg, " / ".join(repr(s) for s in samples[:2])))
        for num in sorted(paren_factors):
            print("括号锚点  = (%s) 每处都贴括号/运算符，且整章无独立编号块（印面不印编号列）"
                  % num)
            for blk in paren_factors[num][:4]:
                print("           %s" % blk)
        print("摘除编号  = %s" % " ".join(sorted(nums)))
        for num, (key, head, where) in mis:
            print("错挂块    = (%s) 在节点 %s 的 %s：%s" % (num, key, where, head))
            print("真主      = %s" % ("契约无展示块可挂（表格/文字行），该号不入账"
                                     if host == "non-display"
                                     else "契约节点 %s（紧接着按下方命令回填）" % host))
        print("契约删除  = %s" % ", ".join("%s×%d" % (n, c) for n, c in sorted(ccounts.items())))
        promoted = [(k, rm, after) for k, _h, rm, after in cchanges if after]
        for key, rm, after in promoted:
            print("           节点 %s 摘 %s → 该块剩 %s（%s 已提升为 tag）"
                  % (key, " ".join(rm), " ".join(after), after[0]))
        print("单元正文  = %s" % (" ".join(touched) or "无命中"))
        print("manifest  = %s" % (" | ".join(man_notes) or "无该侧清单"))
        if not targets:
            print("NO-OP     契约、两侧 manifest 与单元正文都没有这些 tag（已摘过），无需写出")
            return 0
        if not a.apply:
            print("DRY-RUN（未写盘）：加 --apply 落盘")
            return 0

        bak = _mkdir_unique(os.path.join(ext, "_bak_deregister_tags",
                                         time.strftime("%Y%m%d-%H%M%S")))
        for t in targets:
            if t["path"].endswith(".json"):
                json.loads(t["after"])
            now = read_text(t["path"])
            if now != t["before"]:
                raise Refuse("%s：核对与写出之间文件被别人改过（并发会话？），拒绝写出"
                             % t["path"])
        for t in targets:
            write_text(os.path.join(bak, _bak_name(ext, t["path"])), t["before"])
        for t in targets:
            write_text(t["path"], t["after"])
        ledger = os.path.join(ext, "_formula_tag_deregistrations.jsonl")
        with io.open(ledger, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "extract_dir": os.path.abspath(ext),
                                "ch_key": str(a.ch_key), "numbers": nums,
                                "contract_removals": ccounts,
                                "contract_blocks": [{"node": k, "formula_head": h,
                                                     "removed": rm, "left": after}
                                                    for k, h, rm, after in cchanges],
                                "unit_files": touched, "manifest": man_notes,
                                "evidence": a.evidence.strip(),
                                "mode": ("mispaired" if mis
                                         else ("false-anchor" if bare_anchors
                                               else "unattested")),
                                "anchor_kind": ak if bare_anchors else "",
                                "bare_anchors": bare_anchors,
                                "paren_factor_anchors": paren_factors,
                                "mispaired_from": {n: {"node": k, "formula_head": h,
                                                       "at": w}
                                                   for n, (k, h, w) in mis},
                                "host": host if mis else "",
                                "gate_14_condemned": sorted(str(x) for x in condemned),
                                "backup": bak}, ensure_ascii=False) + "\n")
        print("APPLIED   备份=%s 台账=%s" % (bak, ledger))
        print("待办（顺序不可颠倒）：")
        if mis and host != "non-display":
            for num, (_k, _h, _w) in mis:
                print("  # (%s) 的真主是契约节点 %s：先把号落回正确块，再让该单元正文补 \\tag"
                      % (num, host))
                print("  python tools/backfill_formula_tags.py \"%s\" %s --number %s --node %s \\"
                      % (ext, a.ch_key, num, host))
                print("      --evidence \"<印面出处：本次摘除证据同文>\" --apply")
        if mis and host == "non-display":
            print("  # 真主是表格/文字行：该号**不入账**，对应单元正文不得写 \\tag，"
                  "⑱ 只扫契约树故不会复发")
        for key, _rm, after in promoted:
            print("  # 节点 %s 该块摘后仍带 %s（幸存者已提升为 `tag`）：manifest 的 `tags` 是"
                  " split 期按 singular `tag` 写的快照，原本只在 `tags` 列表里的号**不会**"
                  "自动进该账 → 按下面命令补，否则单元级对账仍看不见它"
                  % (key, " ".join(after)))
            print("  python tools/backfill_formula_tags.py \"%s\" %s --number %s --node %s \\"
                  % (ext, a.ch_key, after[0], key))
            print("      --evidence \"<印面出处：该号在印面上确为编号>\" --apply")
        print("  python flows/write-source/script/gate_units.py \"%s\" %s" % (ext, a.ch_key))
        # 🔴 处方按语境分叉（2026-10-30 Gelfand–Manin ch4 实测）：源正文变了确实要重同步译侧快照，
        # 但**别走 `init_translate_units`**——它按 init 语义把**每个**单元的 `hash` 一并重算，
        # 实测覆写 31 处「派生时刻」快照（`hash` 无消费者，属无关改动）。定点通道是下面这条。
        if touched:
            print("  python tools/resync_src_hash.py \"%s\" --ch %s --commit"
                  % (ext, a.ch_key))
            print("      # 只改漂移的 `src_hash`；`init_translate_units` 会连 `hash` 一起覆写，勿用")
            print("  # 交付 md 侧二选一：**已收官书禁重 merge**（读者已拿到成品），只镜像被摘的行：")
            print("  python tools/mirror_unit_line.py \"%s\" %s <该章单元文件> --commit" % (ext, a.ch_key))
            print("      # 独占一行的 `\\tag` 是整行删除 → 上面这条加 `--delete-line`")
            print("  # 未收官（交付 md 还要重拼）才走：")
        print("  python flows/write-source/script/merge_units.py \"%s\" --ch %s"
              % (ext, a.ch_key))
        return 0
    except Refuse as e:
        print("REFUSE: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
