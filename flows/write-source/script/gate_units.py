"""gate_units.py — write-source 步骤 5 强制门控：确保每个 item 单元都被 agent 改好

背景
----
写作以单元粒度进行：拆分脚本 ``split_draft_units.py``
把整章草稿切成按写作顺序的单元文件（``units/ch{N}/NNNN_<type>_<key>.md``，4 位编号；附录章 ``units/appendix{X}/``），agent
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
  ③b **单元级图片对账 + 空正文闸 + 章级图片覆盖**：
     · manifest 的 ``images``（split 时按契约节点写入；老 manifest 在 key 唯一
       对应一个内容单元时按 ``chapter_image_map`` 回退）为该单元应嵌图片真值，
       缺图 / 多图均不通过（曾发生步骤 5 agent 清噪时把图块连同习题正文删光，
       而旧门控只对账 tag、图片无人管 → 一路绿灯流入拼接）；
     · manifest 的 ``content``（契约节点内容块数）> 0 而单元正文为空 = 整体
       清空，不通过（幻影节点 content==0 允许空正文）；
     · 章级兜底：契约全部图片（``chapter_images``）必须被本章单元**合起来**一个
       不漏地嵌入，且单元不得嵌契约外图片。
  ④ **真实 KaTeX 渲染（按章批量）**：把本章全部 item/desc/exercise 单元正文拼进
     临时 md（``<extract>/_gate_render_tmp_<章目录名>.md``，带单元边界标记），跑
     ``katex_render.run_render_check``（katex_validate.js 真渲染），错误按行号
     **映射回所属单元**——启发式抓不到的 `\begin` 不配对 / 未定义宏等在门控即拦，
     不再漏到步骤 8 verify。🔴 渲染工具链缺失（node / katex 未装）= 门控不通过
     （fail-closed；须先完成 prep.env：``npm install katex --no-save``）。
  🔴 **fail-closed**：质量校验**执行失败**（脚本异常）按「质量未达标」处理，
     绝不因崩溃放行（旧实现异常即放行，曾让未审阅单元整体免检流入拼接）。

序标校验（本门控不再冗余重跑 → 权威检测点在 structure 完整性闸门 + 步骤 8 复检）
------------------------------------------------------------------
  序标判据天然是**章级 / 文件级**（B 层条目缺号 / 顺序跨单元，O 层按「行距 ≤4」成块），
  故门控**不再冗余重跑** B / O：
  · **B 层条目编号**的权威检测在 **book structure 完整性校验**（write-source 步骤 3，
    ``check_structure_completeness.py`` 第 3 步：喂 book_structure 派生「合成 md」+ 源条目集
    查条目连续性 / 重要概念遗漏并回填契约）；步骤 8 ``verify_chapter.py --all`` 在最终合并
    md 上**复检** B 层。
  · **O 层子项编号** ``(1)(2)(3)`` 缺口**只在步骤 8** 完全拼接后的章 md 由 ``verify_chapter.py
    --all``（O 真层）校验（structure 完整性闸门只覆盖 D + B，不含 O）。
  门控看到的合并 md 与步骤 8 同源（merge 亲手产出）、等价，故在门控内跑纯属重复。
  🔴 **回填落点**：步骤 8 复检发现的缺号缺口由 **``backfill_ordinals.py``**（步骤 7 拼接
  之后运行）**写回其归属的总结单元 ``.md``**（你在哪个单元找回的序标就放回哪个单元），插入
  明确标注的占位条目（不编造内容），便利后续补全。默认 ``--dry-run``（只报告），``--apply`` 写盘。
  🔴 门控仍保留 ①标记替换 ②单元级质量 ③公式序标对账 ③b图片/空正文/章级图片
  覆盖对账 ④真实 KaTeX 渲染 + ⑦⑧完整性核对 + ⑨章级习题重号（幻影条目契约痕迹）
  + ⑩契约→manifest 反向覆盖对账 + ⑪单元结构阅读顺序（页码单调）+ 单元标签编号须
  契约在账（质量校验第 23 项）。

完整性核对（防漏项）：
  ⑦ manifest 中每个单元都有对应文件（无缺失、无多余文件）；
  ⑧ manifest 的 ``units`` 覆盖契约全部编号项单元（item）+ 章/节/描述单元；
  ⑨ 习题条目键在本章内唯一——重号 = 契约里有一条 OCR 续行碎片被切成的幻影习题
     （单元级配套判据见 ``check_unit_quality`` 第 16 项：句中起始标题 / 零内容块 /
     吞并别的小节的编号公式或插图）。
  ⑩ 契约→manifest **反向**对账：契约里每个应成单元的节点（``unit_node_entries``，
     含 description / 编号项 / 非 consolidated 习题）都必须有至少一条单元记录，
     否则该内容在 merge 后**整条消失**而既有闸门（全部按 manifest 遍历）看不见。
     比较按「习题 / 结果项分桶 + 序标归一」——Katok 实测：结果项与习题共用编号
     空间（不分桶会互相销账），而 manifest 旧键形 ``6.2-5`` 与重建后的契约键
     ``推论6.2.5`` 同号（直比字符串会假报整条丢失）。
  ⑪ 单元**结构阅读顺序**（合并前）：manifest 顺序 == 拼接顺序，按契约节点 ``page_start``
     （源书物理页序）断言**页码单调不减**——某单元页码 < 其前已出现的最大页码 = 早页内容
     排到晚页之后（阅读顺序倒退）。补 B 层（只查同节前缀序标单调）/ ⑩（集合比较，同集合
     任意排列放行）/ ``subsection_order``（只查契约数字键、跑在拆分前）三者都看不见的**跨节
     / 跨页错乱**——即「全绿仍读起来次序混乱」的根因。页码相等允许（同页多单元交 B 层），
     章末 dash 习题 ``N-M``（正文首现页早于章末）豁免，锚点缺失单元跳过。实现见
     ``lib/unit_order.check_unit_order``（verify 侧 unit_order 层复用同一实现）。

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
    chapter_json_path, chapter_label, chapter_tag_map, chapter_image_map,
    chapter_images, list_chapter_keys, prime_chapter_kinds, unit_dir_name,
    chapter_ordinals, unit_node_entries)
import split_draft_units as _split
import check_unit_quality as _quality
from lib.unit_order import check_unit_order
from lib.problem_coverage import coverage_problems, page_floor_problems
from lib.tag_attestation import tag_attestation_problems
from lib.numbering import formula_tag_noise

_OUT_RE = re.compile(r"<!-- book-summarizer (DRAFT|DONE) unit: id=(\S+) type=(\S+) key=(.*?) name=(.*?) -->")

_KEY_NUM_RE = re.compile(r"(\d+(?:\.\d+)*)-(\d+)$")


def _formula_layer_enabled(ext):
    """本书该 extract 是否**声明**了公式序标层（Q 层 / `\tag` 对账）。

    Q 层是 opt-in：只有 `verify_config.json` 配置了 `formula` 块（含 `type` /
    `known_book` / `ignore` 等键）才启用。门控的单元级 `\tag` 对账必须与章级 verify
    的 Q 层同开同关——否则「未声明公式层」的书（如 Vakil：make_config 判定为不追踪
    编号公式）会因 build_structure 在 `ncomp=None` 下**过度**给裸数字 / 交叉引用挂上
    `tag`，被单元门控误判成「漏写编号公式」而阻断（且这类编号本就不作 `\tag` 呈现）。
    兼容扁平 / 分组（ch/appendix/supplement）/ 历史 data 三种配置形状。
    """
    path = os.path.join(ext, "verify_config.json")
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return False

    def _is_formula_map(node):
        return isinstance(node, dict) and any(
            k in node for k in ("type", "known_book", "ignore", "letter_ch",
                                "bare_number", "enabled"))

    def _node_enabled(node):
        if not isinstance(node, dict):
            return False
        if _is_formula_map(node.get("formula")):
            return True
        # 节点自身即是一个 formula map 的兜底（含 type/known_book 键）
        if "known_book" in node or ("type" in node and "scope" not in node):
            return _is_formula_map(node)
        return False

    if _is_formula_map(cfg.get("formula")):
        return True
    for grp in (cfg.get("ch"), cfg.get("appendix"), cfg.get("supplement")):
        if _node_enabled(grp):
            return True
    data = cfg.get("data")
    if isinstance(data, dict):
        for sub in data.values():
            if _node_enabled(sub):
                return True
    for v in cfg.values():
        if isinstance(v, dict) and _node_enabled(v):
            return True
    return False


def _formula_scope(ext):
    """verify_config.json 的 ``formula.scope``（取不到 → None）。

    单元级 tag 对账要按**书的体例**剔噪：scope==3（编号节内重置）的书里，纯数字
    ≥3 位的 tag 必是表格单元 / 页码碎片（Kreyszig 4.11-5 的 ``931`` / ``144``）。
    """
    path = os.path.join(ext, "verify_config.json")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None
    node = cfg.get("formula")
    if isinstance(node, dict):
        return node.get("scope")
    for v in cfg.values():
        if isinstance(v, dict) and isinstance(v.get("formula"), dict):
            return v["formula"].get("scope")
    return None


def _load_known_book(ext):
    """读 verify_config.json 的 ``formula.known_book`` → 裸编号集合。

    known_book 登记「书源确有、但被契约抽取器漏挂」的真实公式编号（典型：编号
    与公式同行内联粘连，非独立右缘块）。门控据此豁免「编造编号」误判。兼容扁平
    （顶层 ``formula``）与分段（``data[section]["formula"]``）两种配置形状；任何
    缺失 / 异常 → 空集（不影响正常对账）。
    """
    path = os.path.join(ext, "verify_config.json")
    if not os.path.exists(path):
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return set()
    nums = set()

    def _harvest(formula):
        if isinstance(formula, dict):
            for x in (formula.get("known_book") or []):
                nums.add(str(x).strip())

    def _harvest_node(node):
        """从一处配置节点采集 known_book：节点自身是 formula map，或节点是含
        ``formula`` 子 map 的（子）配置组。"""
        if not isinstance(node, dict):
            return
        _harvest(node.get("formula"))
        # 节点自身即是一个 formula map（含 type/scope/known_book 键）的兜底
        if "known_book" in node:
            _harvest(node)

    # 扁平形状：顶层 ``formula``
    _harvest(cfg.get("formula"))
    # 外层 map 形状（当前 SSOT）：顶层按 kind 路由的组 ch/appendix/supplement，
    # 每组的 ``formula.known_book``。
    for grp in (cfg.get("ch"), cfg.get("appendix"), cfg.get("supplement")):
        _harvest_node(grp)
    # 历史 ``data`` 包装形状（若有）：data[section]["formula"]
    data = cfg.get("data")
    if isinstance(data, dict):
        for sub in data.values():
            _harvest_node(sub)
    # 兜底：遍历所有顶层 dict 值，采集其 ``formula.known_book``（对未知分组名稳健）
    for v in cfg.values():
        if isinstance(v, dict):
            _harvest_node(v)
    return nums


def _unit_source_map(contract):
    """薄封装：真值实现见 ``check_unit_quality.unit_source_map``（单一来源，
    假省略闸的忠实引用豁免用）。"""
    import check_unit_quality as _quality
    return _quality.unit_source_map(contract)


def _check_numbering(units):
    """B 层编号预检：同一节内 item 编号是否递增。返回问题列表。

    🔴 **按 (节, 条目种类) 分组**比较：中文教材（如《数学分析教程》）同一节内
    「定义 / 定理 / 推论 / 例」各自独立编号，「定义1.3.1」与「定理1.3.1」同号是
    书本体例而非缺号。若只按节分组，这类同号会被误报成「编号不递增」，
    而真正的缺号（同节同种类内编号回退/重复）仍会被抓到。
    """
    from collections import defaultdict
    sections = defaultdict(list)
    for u in units:
        if u["type"] != "item":
            continue
        m = _KEY_NUM_RE.search(u["key"])
        if m:
            sec = m.group(1)
            num = int(m.group(2))
            # ntype = 契约条目种类（definition / theorem / …）；老 manifest 缺失时退化为按节分组
            kind = u.get("ntype") or ""
            sections[(sec, kind)].append((num, u["file"], u["key"]))
    problems = []
    for sec, items in sorted(sections.items()):
        items.sort(key=lambda x: x[0])
        # 🔴 与 verify B 层语义对齐（「按阅读顺序**去重**后的编号须单调递增」）：
        # 同 (节, 种类, 号) 的重复先去重再比较——个别书源自身排印重复同号条目
        # （Lasota-Mackey §5.6 两条 Remark 5.6.1，PDF p124/p126 目视核实），
        # B 层在最终 md 上去重后放行；预检若不去重会假报「编号不递增」。
        # 真正的抽取器重号错误由 exercise 键唯一性闸与步骤 8 B 层兜底。
        deduped = []
        seen_nums = set()
        for num, f, k in items:
            if num in seen_nums:
                continue
            seen_nums.add(num)
            deduped.append((num, f, k))
        items = deduped
        for i in range(1, len(items)):
            prev_num, prev_file, prev_key = items[i - 1]
            cur_num, cur_file, cur_key = items[i]
            if cur_num <= prev_num:
                problems.append(
                    "编号不递增：节 %s%s 内 %s（%d）排在 %s（%d）之后" % (
                        sec[0], "（%s）" % sec[1] if sec[1] else "",
                        cur_key, cur_num, prev_key, prev_num))
    return problems


def _check_exercise_key_uniqueness(units):
    """章级闸：习题条目键必须唯一（manifest 与契约节点 1:1，重复即契约重号）。

    同一章出现两个 ``key=2.1.7`` 的 exercise 记录 = 抽取器把 OCR 续行碎片切成了
    第二条「习题」（Katok ch2/ch3/ch9/ch17 各一例）。后果：真条目被挤到错误的键上、
    或凭空多出一个空单元，读者看到的习题编号与原书不符。修法在契约层（把碎片并回
    上一条目 / 补回被吞的真条目），不是删单元文件了事。
    """
    seen = {}
    dup = []
    for u in units:
        if u.get("type") != "exercise":
            continue
        k = str(u.get("key"))
        if k in seen:
            dup.append("%s（%s 与 %s）" % (k, seen[k], u.get("file")))
        else:
            seen[k] = u.get("file")
    if not dup:
        return []
    return ["契约本章习题条目重号：%s——后一个是 OCR 续行碎片被误判成的幻影条目，"
            "须在分章契约里并回所属条目（或补回被吞的真条目）后重拆/同步单元"
            % "、".join(dup)]


def _check_contract_unit_coverage(contract, units, ch_key):
    """章级闸 ⑩：契约里每个应成单元的节点都必须在 manifest 有记录（反向对账）。

    正向对账（manifest 记录 → 契约）早就有（tag / 图片 / 正文非空），但**反向**一直
    缺位：契约里的条目被 manifest 漏掉时，该条目内容在 merge 后凭空消失，而所有
    既有闸门（按 manifest 遍历）都看不见它。Katok ch17 实测：习题 17.6.3/17.6.4
    的题面被塞进无关 description 单元里，两者都没有自己的记录。
    同键多记录是合法形态（同节定义/定理共用键），故只报「零记录」不报重复。

    两条必要的比较细则（Katok 实测，缺一即假阳/假阴）：
    1. **按 kind 分桶**（习题 / 结果项）：结果项与习题共用编号空间（Exercise 6.2.5
       与 Corollary 6.2.5 同号），不分桶会让真丢的习题拿同号结果项销账。
    2. **序标归一后比较**：manifest 键可能是拆分当时的旧形态（``6.2-5`` 连字符体例、
       无「推论」前缀），而契约已重建为 ``推论6.2.5``。键串直比会把这些「内容其实
       在单元里」的条目误报成整条丢失（ch6/ch12 三例）。
    """
    if contract is None:
        return []
    from lib.util import norm_secnum, sec_ordinals
    buckets = {}   # kind -> (归一键集合, 序标集合)
    for u in units:
        t = u.get("type")
        if t not in ("item", "desc", "exercise", "section"):
            continue
        nk, ho = buckets.setdefault("exercise" if t == "exercise" else "content",
                                    (set(), set()))
        kn = norm_secnum(u.get("key"))
        nk.add(kn)
        ho.update(sec_ordinals(kn))
    missing = []
    for kind, key in unit_node_entries(contract):
        nk, ho = buckets.get(kind, (set(), set()))
        kn = norm_secnum(key)
        if kn in nk or (set(sec_ordinals(kn)) & ho) or key in missing:
            continue
        missing.append(key)
    if not missing:
        return []
    shown = "、".join(missing[:8]) + ("…（共 %d 个）" % len(missing) if len(missing) > 8 else "")
    return ["契约条目 %s 在 manifest 无对应单元记录（内容不会出现在合并 md 里 = "
            "整条丢失）——须按契约重拆（split_draft_units）或补建记录后同步单元"
            % shown]


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


def _unit_body_reader(out_dir):
    """→ read(unit) = 该单元正文（去掉首行标记；文件缺失给空串，缺失另有闸门报）。"""
    def read(u):
        path = os.path.join(out_dir, str(u.get("file") or ""))
        if not os.path.exists(path):
            return ""
        return _read_unit(path)[4]
    return read


_PAGE_CACHE = {}


def _page_block_loader(ext):
    """→ load(pdf_page) = 该页文本块内容的**阅读序**列表；无 page_NNN.json 时给 None。

    闸门只数「行首题号」，OCR 糊掉的数学不影响判据；阅读序按 bbox 顶边排（抽取期
    ``text`` 块本身的顺序不保证）。整本书的页文件在进程内缓存。
    """
    def load(pg):
        if pg in _PAGE_CACHE:
            return _PAGE_CACHE[pg]
        # 🔴 页文件名有零补齐惯例（Kreyszig = page_031.json，部分书 = page_31.json）：
        # 只试一种命名会让前 99 页**静默**查不到 → 页侧下限对第一章整章失明。
        path = None
        for cand in ("page_%03d.json" % pg, "page_%d.json" % pg, "page_%04d.json" % pg):
            p = os.path.join(ext, cand)
            if os.path.exists(p):
                path = p
                break
        val = None
        if path:
            try:
                with io.open(path, encoding="utf-8") as f:
                    d = json.load(f)
                blocks = sorted(d.get("text") or [],
                                key=lambda b: (b.get("bbox") or [0, 0])[1])
                val = [str(b.get("text") or "") for b in blocks]
            except Exception:
                val = None
        _PAGE_CACHE[pg] = val
        return val
    return load


_PAGE_LABEL_CACHE = {}


def _page_label_loader(ext):
    """→ load(pdf_page) = 该页**可能承载印刷编号**的全部块文本（正文 + MFD 公式 latex）。

    ⑭ 用：左缘印刷编号常被 MFD 当公式检测出来（`( 7 \\mathbf { c } ^ { \\prime } )`），
    只看 ``text`` 流会把真实编号判成「查无锚点」。公式块只有 ``bbox``/``latex`` 两个
    字段可用，按 y 排序即可。
    """
    def load(pg):
        if pg in _PAGE_LABEL_CACHE:
            return _PAGE_LABEL_CACHE[pg]
        path = None
        for cand in ("page_%03d.json" % pg, "page_%d.json" % pg, "page_%04d.json" % pg):
            p = os.path.join(ext, cand)
            if os.path.exists(p):
                path = p
                break
        val = None
        if path:
            try:
                with io.open(path, encoding="utf-8") as f:
                    d = json.load(f)
                val = [str(b.get("text") or "") for b in (d.get("text") or [])]
                val += [str(b.get("latex") or "") for b in (d.get("formulas") or [])]
            except Exception:
                val = None
        _PAGE_LABEL_CACHE[pg] = val
        return val
    return load


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
        # 🔴 拼接用 "\n".join(parts)，part 之间**不产生空行**；每个 part 占
        # 「1 行 marker + nlines 行正文」，故下一个 marker 行 = line_no + 1 + nlines。
        # 旧实现多加了 1（按「marker 后有空行」计算），使每个单元累计偏移 1 行，
        # 渲染错误被归到**上一个**单元（实测 ch1 报 0039、实为 0040），误导返修。
        line_no += 1 + nlines
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
    img_map = {}
    contract = None
    cpath = chapter_json_path(ext, ch_key)
    if os.path.exists(cpath):
        try:
            with open(cpath, encoding="utf-8") as f:
                contract = json.load(f)
            tag_map = chapter_tag_map(contract)
            img_map = chapter_image_map(contract)
        except Exception:
            tag_map, img_map, contract = {}, {}, None
    src_map = _unit_source_map(contract) if contract is not None else {}
    # 契约序标真值（单元标签对账：单元里写出的条目/习题编号必须契约有登记）
    ord_keys = chapter_ordinals(contract) if contract is not None else set()
    problems = []
    known_book = _load_known_book(ext)
    _sec_scoped = _formula_scope(ext) == 3
    # 🔴 `\tag` 对账与章级 verify 的 Q 层同开关：未声明公式层时，单元级跳过 `\tag`
    # 缺失/编造对账（含 phantom 的跨节编号判定），不把 build_structure 过度挂上的
    # 裸数字/交叉引用 tag 当作硬真值。图片/结构/渲染等其余质量校验不受影响。
    formula_on = _formula_layer_enabled(ext)
    present_files = set()

    def _bn(p):
        return str(p).replace("\\", "/").rstrip("/").split("/")[-1]

    # 契约图片真值（单元级对账回退 + 章级覆盖闸）：老 manifest（拆分时未写
    # images/content）按 key 回退——仅当该 key 在章内只对应**一个**内容单元时才
    # 做单元级对账，避免「定义/定理共用 key」式假缺图（同 tags 聚合陷阱）；
    # 歧义情形交给章级覆盖闸兜底（契约任一图全无单元嵌入 = FAIL）。
    contract_imgs = chapter_images(contract) if contract is not None else None
    img_units_by_key = {}
    for u in units:
        if u["type"] in ("item", "desc", "exercise"):
            img_units_by_key.setdefault(str(u["key"]), []).append(u["file"])
    observed_imgs = set()
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
            observed_imgs.update(
                _bn(m) for m in re.findall(r'<img[^>]+src="([^"]+)"', body))
            continue
        if mark == "DRAFT":
            problems.append("单元 %s（%s %s）仍未处理（标记仍为 DRAFT）" % (
                u["file"], u["type"], u["key"]))
            observed_imgs.update(
                _bn(m) for m in re.findall(r'<img[^>]+src="([^"]+)"', body))
            continue
        # DONE：item / desc / exercise 单元必须「写对」——质量校验通过（公式闭合 /
        # 无裸数学 / 结构标签 / 无明显 OCR 残留 / 无内容审阅类残留）。
        # 🔴 判断标准是"写对"而非"重写"：不看内容指纹是否变化，而是看单元是否
        # 符合写作要求（拦"瞎改就标 DONE"）。
        # 🔴 序标真值**按单元所属契约节点**取（manifest.tags，拆分时写入）：
        # 同节内定义/定理/推论共用 key，按 key 聚合会要求「定义」单元写出
        # 「定理」单元的编号公式（假缺号）。老 manifest 缺 tags 时退回 key 映射。
        exp = u.get("tags")
        if not isinstance(exp, list):
            exp = tag_map.get(str(u["key"])) if tag_map else None
        if exp:
            # 契约/manifest 里遗留的 OCR 噪声编号（`0`/`00`/`07`，来自「< ∞」被读成
            # 编号列）不作真值：既不再**要求**单元写 `\tag{00}`，单元里真写了就按
            # 「编造」报出，脏数据自动暴露（判据见 lib.numbering.formula_tag_noise，
            # 抽取侧同用，新契约不会再产生）。
            exp = [str(t) for t in exp
                   if not formula_tag_noise(t, section_scoped=_sec_scoped)]
        if not formula_on:
            exp = None
        # 图片 / 内容块真值（同 tags 语义）：主真值 = manifest.images / manifest.content
        # （split 时按契约节点写入）；老 manifest 缺字段时按 key 回退，且仅在
        # 该 key 唯一对应一个内容单元时使用（歧义交给章级覆盖闸兜底）。
        exp_imgs = u.get("images")
        if not isinstance(exp_imgs, list):
            exp_imgs = None
            if img_map:
                _k = str(u["key"])
                if len(img_units_by_key.get(_k, [])) == 1:
                    exp_imgs = img_map.get(_k)
        exp_content = u.get("content")
        if not isinstance(exp_content, int):
            exp_content = None
        observed_imgs.update(
            _bn(m) for m in re.findall(r'<img[^>]+src="([^"]+)"', body))
        if utype in ("item", "desc", "exercise"):
            try:
                ok_q, qproblems = _quality.check_body(
                    utype, u.get("name") or "", body,
                    expected_tags=exp, allow_extra=known_book,
                    expected_images=exp_imgs, content_blocks=exp_content,
                    source_text=src_map.get(str(u["key"])), key=str(u["key"]))
            except Exception as e:  # 🔴 fail-closed：校验崩溃绝不放行
                ok_q, qproblems = False, [
                    "质量校验执行失败（fail-closed）：%r" % (e,)]
            # 第 23 项：单元行首标签的编号须在契约登记（契约漏抽的跨节习题在此拦，
            # 不等步骤 8 verify 的 P 层——P 层只认裸编号，标签式形态会漏）
            try:
                _lp = _quality.label_key_problems(body, ord_keys, str(ch_key))
                if _lp:
                    ok_q = False
                    qproblems = list(qproblems) + _lp
            except Exception as e:
                ok_q, qproblems = False, list(qproblems) + [
                    "标签对账执行失败（fail-closed）：%r" % (e,)]
            if not ok_q:
                problems.append("单元 %s（%s %s）质量未达标（写错/格式破坏）：%s" % (
                    u["file"], u["type"], u["key"], "；".join(qproblems[:4])))
            # 🔴 译文语言残留闸（仅 units-translate；2026-09-24 real-analysis
            # ch21/22 教训：标签译了、证明散文仍整段英文的半截翻译，哈希对账抓不住）
            if units_sub != "units":
                lang_probs = _quality.english_residues(body)
                if lang_probs:
                    problems.append("单元 %s（%s %s）翻译语言残留：%s" % (
                        u["file"], u["type"], u["key"], "；".join(lang_probs)))
    # 🔴 章级图片覆盖闸（契约图片全集 =「一个不漏」真值）：契约任一图未被任何
    # 单元嵌入 = 图片被整体删除（ch2 事故：步骤 5 清噪时图块连正文一起删光，
    # tag 有对账、图片没有 → 一路绿灯到 merge）；单元嵌契约外图 = 编造/引用未
    # 回填契约的图。单元级对账有「key 歧义跳过」缝隙，本闸兜死。
    if contract_imgs is not None:
        want_set = set(_bn(p) for p in contract_imgs)
        missing_imgs, stray_imgs = _quality.reconcile_images(
            want_set, observed_imgs)
        if missing_imgs:
            problems.append(
                "章级图片对账：契约图片 %s 未被任何单元嵌入（漏图 = 内容丢失，"
                "按 V-E 归属回补到契约所在单元）" % "、".join(missing_imgs))
        if stray_imgs:
            problems.append(
                "单元嵌入了契约之外的图片 %s（图片文件名须来自契约 image 块；"
                "书源确有而契约缺图先回填契约再引用）" % "、".join(stray_imgs))
    # 多余文件检查（manifest 之外的 .md 属误放）
    for fn in sorted(os.listdir(out_dir)):
        if fn == "manifest.json" or not fn.endswith(".md"):
            continue
        if fn not in present_files:
            problems.append("多余文件 %s（不在 manifest 中，请移除）" % fn)
    # B 层编号预检：同一节内编号是否递增
    numbering_probs = _check_numbering(units)
    problems.extend(numbering_probs)
    # 🔴 章级习题重号闸（幻影习题条目的契约侧痕迹，单元级判据见 check_body 第 16 项）
    problems.extend(_check_exercise_key_uniqueness(units))
    # 🔴 章级闸 ⑩：契约 → manifest 反向对账（契约条目没有单元记录 = merge 后整条消失）
    problems.extend(_check_contract_unit_coverage(contract, units, ch_key))
    # 🔴 章级闸 ⑪：单元**结构阅读顺序**（合并前，页码单调真值）——manifest 顺序即拼接
    # 顺序，若某单元的契约页码 < 其前已出现的最大页码 = 早页内容排到晚页之后（读者视角
    # 阅读顺序倒退）。B 层只查同节前缀内序标单调、反向覆盖闸只做集合比较（同集合任意
    # 排列放行）、subsection_order 只查契约数字键且跑在拆分前——**都看不见跨节/跨页错乱**，
    # 这正是「全绿仍读起来次序混乱」的根因。真值取契约节点 page_start（源书物理页序，
    # 比契约列表序更可靠，列表序可能被陈旧拆分排乱）。章末 dash 习题（N-M）豁免。
    problems.extend(check_unit_order(contract, units))
    # 🔴 章级闸 ⑫：节末**编号内容**（典型形态＝节末 Problems 题面）覆盖对账。抽取期把
    # 习题块灌进前一编号项 / 证明节点的子树时，该节根本不出习题单元，写手看不见「该写
    # 12 道题」这件事，既有闸门也全看不见（tag / 图片 / 正文非空 / ⑩ 反向覆盖都是按
    # **节点**比较，题面挂在别的节点子树里照样绿灯）——Kreyszig 实测：11 章 572 单元
    # 门控全绿，却有约 51 节 / 500+ 道习题整块没进笔记。两侧用**同一**判据（该节子树
    # 里「从 1 起连续」的最长编号链 vs 本章单元按 manifest 序拼接后的最长链），短了即
    # 整块漏写；契约侧 OCR 断号只会让真值偏小 = 保守；契约标 consolidated 的成堆习题
    # 是流水线认可的省略，跳过。实现与负向测试见 lib/problem_coverage.py。
    problems.extend(coverage_problems(contract, units, _unit_body_reader(out_dir)))
    # 🔴 章级闸 ⑬：习题数的**页侧**下限对账（``_extract/page_NNN.json``）。⑫ 拿契约当
    # 真值，可契约自己会瞎：有的节末整页习题在抽取期根本没进契约（跨页题块被丢、或被
    # 灌进**另一节**的子树），于是「印刷 10 题 / 契约 4 题 / 单元写了 5 题」在 ⑫ 里是
    # 绿灯。本闸直接从该节页窗里「Problems」标题之后出现过的最大题号取下限（只作下限、
    # 遇下一条节标题即停、>30 视为噪声 = 永不低于印刷真值之上），单元侧短了就报。
    # 没有页 JSON 的书（纯知识库输入）自然取不到下限 = 不报，不影响其它项目。
    problems.extend(page_floor_problems(
        contract, units, _unit_body_reader(out_dir), _page_block_loader(ext),
        (int(contract.get("page_start") or 0), int(contract.get("page_end") or 0))))
    # 🔴 章级闸 ⑭：契约 tag 的**印刷锚点**对账。tag 是本门控「契约 ↔ 单元」的真值来源，
    # 契约里多一个原书没印过的编号，写手就被逼凭空 `\tag{}`（多出=编造），删了又报漏写，
    # 两头堵、且到步骤 8 Q 层才暴露。Kreyszig 实测 5 个毒 tag：`22`（display 里 ε/2 的
    # 两个分母被 OCR 成独立数字块）、`50`/`25`（`= 0.50` 小数尾巴）、`18751A`/`12818A`
    # （波长 `18 751 Å`）。判据保守（漏报可接受）：页窗内既无 `(N)` 又无独立裸块 → 判毒；
    # 本章编号以 `(N)` 为主时，只有裸锚点的 tag 也判毒。缺页文件不判。
    # 修法在**收割处**（attach_content / lib.numbering 的形态与几何闸），不是写手台。
    problems.extend(tag_attestation_problems(contract, _page_label_loader(ext),
                                             chapter_label(ch_key)))
    # 🔴 章级序标校验（B 层 _md_gap_blocking / O 层 check_ordinal_subitem_gaps）不在本门控冗余重跑：
    # B 层条目编号的权威检测在步骤 3 structure 完整性闸门（check_structure_completeness 第 3 步），
    # 步骤 8 verify 在最终合并 md 复检 B 层、且仅步骤 8 校验 O 层；缺口由 backfill_ordinals.py
    # 写回归属单元（回填）。此处不再跑章级序标校验（门控看到的合并 md 与步骤 8 同源、等价）。
    # 注意：上方 _check_numbering 仍是单元内「同节编号单调」的轻量预检，与章级序标校验是两回事。
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
