"""_flow_contract.py — book-summarizer 流程契约（有序步骤 + 物理证据 + 命令）

这是「步骤顺序 / 什么算完成 / 每步跑什么命令」的**单一真源**，与
``lib/flow_gate.py`` 的 ``FLOW_ORDER`` 必须对齐（flow_gate 的列表是副本，
本文件是权威）。flow_runner 与所有 self-assert 的加载器都从这里取"完成证据"。

每步的「物理证据」(physical_evidence) 是**不依赖账本、只看磁盘产物**的判定，
用于：flow_runner ``verify`` 复核、bootstrap 回填、以及加载器 self-assert 时的
兜底校验。

约定
----
- book_dir：本书工作目录（含 _extract/ 与最终 .md）。
- extract_dir：book_dir/_extract。
"""
import glob
import json
import os
import re
import subprocess
import sys

# --------------------------------------------------------------------------
# 有序步骤（权威）—— 顺序即强制依赖
# --------------------------------------------------------------------------
FLOW_ORDER = {
    "prep": ["env"],
    # 🔴 2026-08-29 流程重构：extract 终于 MM Repair；config / figure_detection /
    # structure / 基本总结草稿全部移入 write_source（草稿前须过 structure 完整性闸门）。
    "extract": ["place_pdf", "extract_text", "mm_repair"],
    "write_source": ["config", "figure_detection", "structure", "draft",
                     "write_chapters", "verify_source"],
    "derive": ["translate", "verify_cn"],
}

FLOW_PREREQS = {
    "extract": ["prep"],
    "write_source": ["extract"],
    "derive": ["write_source"],
}

# --------------------------------------------------------------------------
# 每步的运行命令模板（flow_runner `run` 使用）。
#  - ("cmd", "<shell 模板>")：可机械执行；{pdf} {book_dir} {extract_dir} 占位。
#  - ("agent", "<说明>")：需 agent 按 flow 文档手动完成，完成后用 verify+mark。
# --------------------------------------------------------------------------
RUN_COMMANDS = {
    "prep.env": ("agent",
        "conda activate <env_name>（见 user_config.json 的 conda.env_name，可用 "
        "BKS_CONDA_ENV_NAME 覆盖）; python -c \"import torch; print(torch.cuda.is_available())\" 须为 True;"
        " 确认 <skill根>/node_modules/katex 存在（npm install katex --no-save）。"),
    "extract.place_pdf": ("agent",
        "按 extract.md 目录决策（分支 A-D）归位 PDF，确定 <book_dir>。"),
    "extract.extract_text": ("cmd",
        # 后台文本提取，断点续跑，纯文本不含图检测
        "bash launch_pipeline.sh \"{pdf}\""),
    "extract.mm_repair": ("agent",
        "完整链路 audit → 模式B(--hybrid) → 模式A(视觉) → apply 写回 page_*.json；"
        "见 mm_repair.md。apply 真完成才出 _extraction_done.json。"),
    "write_source.config": ("agent",
        "先按 config_setting.md 步骤 1 建章节映射 _extract/chapter_map.json"
        "（MM Repair 完成后统一生成，只建一次），再跑 "
        "python config/verify_config/make_config.py \"{extract_dir}\"；两者都完成才算 done。"),
    "write_source.figure_detection": ("cmd",
        "python flows/script/extract_figures.py \"{pdf}\" --out \"{extract_dir}\" --book && "
        "python flows/script/assign_figures.py \"{pdf}\" --out \"{extract_dir}\" --book"),
    "write_source.structure": ("cmd",
        # 2026-08-29 重构：build_structure 一步产出含内容（text/formula/image/
        # proof/description）的完整分章契约 ch{N}.json；结构完整性（章节/条目
        # 查漏回填 + gate.passed 闸门）是本步内的硬闸，见 structure.md 第 2-4 步
        "python flows/write-source/structure/script/build_structure.py \"{extract_dir}\""),
    "write_source.draft": ("cmd",
        # 基本总结草稿拆分：内容完整性闸门 + 把整章草稿细分为「每 item 一单元」
        # 的 units/ch{N}/ 目录（2026-08-31 起取代整章 draft_ch{N}.md 输出）。
        # 完整契约已由 structure 步产出，无需再 attach；图片经契约 image 块随
        # 单元继承。render_draft.py 降级为 split_draft_units 的渲染库（不再单独产出草稿）。
        "python verify/script/check_content_completeness.py \"{extract_dir}\" && "
        "python flows/write-source/script/split_draft_units.py \"{extract_dir}\""),
    "write_source.write_chapters": ("agent",
        "🔴 对应文档步骤 5（agent 逐个改好 + 门控）与步骤 6（纯脚本拼接）："
        "① agent 逐个打开 split_draft_units.py 拆出的单元目录 units/ch{N}/（章标题 / "
        "节标题 / 描述 / 每个编号项 各一 md），按 writing-rules 改好（公式逐条重写校正、"
        "Tier 压缩、格式落地、存疑回查 page_*.json）——🔴 全部写作要求在文档步骤 5 "
        "落实，每个单元把首行 DRAFT 标记改为 DONE；"
        "② 跑 python flows/write-source/script/gate_units.py \"{extract_dir}\" "
        "——🔴 强制门控：全部单元 DONE 且内容确被改写才 exit 0（每个 item 都不漏）；"
        "③ 跑 python flows/write-source/script/merge_units.py \"{extract_dir}\" <ch> "
        "逐章拼接单元成最终 ChapterN_*.md / 第N章_*.md——文档步骤 6 纯脚本机械执行"
        "（按 V-F 规则重建 --- 分隔线），无需 agent 写作调整。🔴 merge_units 自带"
        "强制门控：拼接前先跑 gate_units，任一单元未改好即直接报错拒绝拼接。"
        "🔴 落账证据机械核对（脱离单元 / 门控未过 = 硬拒）：每章 gate_units 通过"
        "（全部单元改好）+ 最终 md 存在。"),
    "write_source.embed_figures": ("cmd",
        "python flows/script/embed_figures.py \"{book_dir}\""),
    "write_source.verify_source": ("cmd",
        # exit 0 才算 PASS
        "python verify/script/verify_chapter.py --all \"{extract_dir}\" \"{book_dir}\""),
    "derive.translate": ("agent",
        "以已校验源版为唯一蓝本逐条翻译中文 第N章_*.md（1:1 同构）。"),
    "derive.verify_cn": ("cmd",
        # 针对翻译版，exit 0
        "python verify/script/verify_chapter.py --all \"{extract_dir}\" \"{book_dir}\""),
}


# --------------------------------------------------------------------------
# 物理证据检查：只看磁盘产物，不依赖账本
# --------------------------------------------------------------------------
class physical_evidence:
    """每步的完成证据（book_dir, extract_dir）-> (bool, detail)。"""

    @staticmethod
    def _extract_dir(book_dir, extract_dir):
        return extract_dir or os.path.join(book_dir, "_extract")

    @staticmethod
    def pages_all_landed(book_dir, extract_dir):
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        files = glob.glob(os.path.join(ex, "page_*.json"))
        if not files:
            return False, "无 page_*.json"
        nums = []
        for f in files:
            base = os.path.basename(f)
            try:
                nums.append(int(base[len("page_"):-len(".json")]))
            except ValueError:
                continue
        nums.sort()
        if not nums:
            return False, "page 编号解析失败"
        if nums[0] != 1:
            return False, f"首页非 1（{nums[0]}）"
        # 连续性：无空洞
        for i in range(1, len(nums)):
            if nums[i] != nums[i - 1] + 1:
                return False, f"page 序列在 {nums[i-1]} 后断裂"
        return True, f"{len(nums)} 页连续落盘 (1..{nums[-1]})"

    @staticmethod
    def chapter_map_ok(book_dir, extract_dir):
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        p = os.path.join(ex, "chapter_map.json")
        if not os.path.exists(p):
            return False, "缺 chapter_map.json"
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            return False, f"chapter_map.json 非法 JSON: {e}"
        # 支持的章节映射形式（与 data/chapter_map.load_chapter_map_raw 对齐，
        # 该函数文档明确声明列表形式与「按章号索引的扁平字典形式」均须共存支持）：
        #   * {"chapters": [...]} 列表形式
        #   * {"ch": [...]}       备用列表形式
        #   * {"1": {"name":..,"start":..,"end":..}, ...}  扁平字典形式
        if isinstance(d, dict):
            chs = d.get("chapters") or d.get("ch")
            if chs is None:
                # 扁平字典形式：值为章节条目（含 name/start/end 等）
                if d and all(isinstance(v, dict) for v in d.values()):
                    chs = list(d.values())
                else:
                    chs = []
        elif isinstance(d, list):
            chs = d
        else:
            chs = []
        if not chs:
            return False, "chapter_map.json 无章节"
        return True, f"{len(chs)} 章"

    @staticmethod
    def _all_pages_marked(extract_dir):
        pages = glob.glob(os.path.join(extract_dir, "page_*.json"))
        if not pages:
            return False
        for pf in pages:
            try:
                data = json.load(open(pf, encoding="utf-8"))
            except Exception:
                return False
            texts = data.get("text", []) + data.get("formulas", [])
            ok = any(t.get("mm_repaired") or t.get("mm_reviewed")
                     or t.get("mm_converted") for t in texts if isinstance(t, dict))
            if not ok and not data.get("MM_UNAVAILABLE"):
                return False
        return True

    @staticmethod
    def mm_repair_complete(book_dir, extract_dir):
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        marker = os.path.join(ex, "_extraction_done.json")
        if os.path.exists(marker):
            # 双重校验：manifest 条目全 resolved
            mpath = os.path.join(ex, "_mm_repair", "manifest.json")
            if os.path.exists(mpath):
                try:
                    m = json.load(open(mpath, encoding="utf-8"))
                    entries = [e for pg in m.get("pages", {}).values()
                               for e in pg.get("entries", [])]
                    total = len(entries)
                    resolved = sum(1 for e in entries if e.get("resolved"))
                    if total and resolved < total:
                        return False, f"manifest 仍 {resolved}/{total} resolved"
                except Exception as e:
                    # manifest 损坏时不得谎称「全 resolved」——完成标记仍是
                    # 权威（设计如此），但证据字符串必须如实说明复核未发生。
                    return True, (f"MM Repair 完成标记存在；manifest 损坏无法"
                                  f"复核（{e}），建议重跑 apply 复验")
            return True, "MM Repair 完成标记存在且 manifest 全 resolved"
        # 回退物理核对（legacy 书缺 marker 文件但确已完成）：manifest 全 resolved
        # 且每页有 mm 标记，才算完成；否则如实报缺口（bootstrap 据此拒绝伪造）。
        mpath = os.path.join(ex, "_mm_repair", "manifest.json")
        if not os.path.exists(mpath):
            return False, "缺 _extraction_done.json 且无 manifest 可核对"
        try:
            m = json.load(open(mpath, encoding="utf-8"))
            entries = [e for pg in m.get("pages", {}).values()
                       for e in pg.get("entries", [])]
            total = len(entries)
            resolved = sum(1 for e in entries if e.get("resolved"))
            if total and resolved < total:
                return False, f"manifest 仍 {resolved}/{total} resolved"
        except Exception as e:
            return False, f"manifest 读取失败: {e}"
        if not physical_evidence._all_pages_marked(ex):
            return False, "存在无 mm_repaired/mm_reviewed 标记的页"
        return True, "物理核对完成（缺 marker 文件，建议 bootstrap 补写）"

    @staticmethod
    def config_ok(book_dir, extract_dir):
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        # config 步骤现含 chapter_map 建映射（config_setting 步骤 1），一并核验
        ok_cm, detail_cm = physical_evidence.chapter_map_ok(book_dir, extract_dir)
        if not ok_cm:
            return False, f"config 前置 chapter_map 缺失: {detail_cm}"
        p = os.path.join(ex, "verify_config.json")
        if not os.path.exists(p):
            return False, "缺 verify_config.json"
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            return False, f"verify_config.json 非法 JSON: {e}"
        if not (isinstance(d.get("ordinal"), list) and len(d.get("ordinal")) > 0):
            return False, "verify_config.json 缺 ordinal 数组"
        return True, "chapter_map.json + verify_config.json（含 ordinal 数组）就绪"

    @staticmethod
    def figure_ok(book_dir, extract_dir):
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        p = os.path.join(ex, "figure_index.json")
        if not os.path.exists(p):
            return False, "缺 figure_index.json"
        return True, "figure_index.json 存在"

    @staticmethod
    def structure_ok(book_dir, extract_dir):
        """structure 完成证据 = 契约文件存在 **且** 每章完整性闸门 PASS。

        🔴 仅"分章契约 ch{N}.json 存在"不足以落账——章节 / 定理定义等缺项的
        查漏回填闸门（structure.md 第 2–4 步，`check_structure_completeness.py`）
        必须对全部章节跑过且 `gate.passed == true`（报告落
        `<extract_dir>/completeness_reports/ch{N}_completeness_report.json`），
        防止 `flow_runner run write_source structure` 只跑 build_structure 就
        跳过闸门落账。
        """
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        sub = os.path.join(ex, "book_structure")
        # 章节清单以 chapter_map 为准（骨架分章文件应覆盖全部章节）
        keys = _chapter_map_keys(ex)
        if not keys:
            return False, "缺 chapter_map.json（config 步未完成）"
        missing = [k for k in keys
                   if not os.path.exists(os.path.join(
                       sub, ("ch%s.json" if k[:1].isdigit() else "appendix%s.json") % k))]
        if missing:
            return False, f"缺分章骨架 {len(missing)} 章: {missing[:4]}"
        reports_missing, not_passed = [], []
        for k in keys:
            rp = os.path.join(ex, "completeness_reports",
                              f"ch{k}_completeness_report.json")
            if not os.path.exists(rp):
                reports_missing.append(k)
                continue
            try:
                r = json.load(open(rp, encoding="utf-8"))
            except Exception:
                reports_missing.append(k)
                continue
            if not (r.get("gate") or {}).get("passed"):
                not_passed.append(k)
        if reports_missing:
            return False, (f"缺完整性报告 {len(reports_missing)} 章（未跑 structure 第 2–4 步"
                           f"查漏闸门）: {reports_missing[:4]}")
        if not_passed:
            return False, f"完整性闸门未通过 {len(not_passed)} 章: {not_passed[:4]}"
        return True, f"{len(keys)} 章分章骨架齐备，完整性闸门全部 PASS"

    @staticmethod
    def draft_ok(book_dir, extract_dir):
        """单元拆分证据：每个结构章节都有内容化分章契约 + 拆出的单元目录。

        🔴 2026-08-31 重构：原「整章草稿 draft_ch{N}.md」被「每 item 一单元目录
        units/ch{N}/」取代（split_draft_units.py）。契约必须 content 化后拆分，
        且 manifest 晚于契约（attach 重跑后必须重拆，否则单元过期）。
        """
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        sub = os.path.join(ex, "book_structure")
        keys = _chapter_map_keys(ex)
        if not keys:
            return False, "缺 chapter_map.json（config 步未完成）"
        missing, stale = [], []
        for k in keys:
            fname = (f"ch{k}.json" if k[:1].isdigit() else f"appendix{k}.json")
            jp = os.path.join(sub, fname)
            mp = os.path.join(sub, "units", f"ch{k}", "manifest.json")
            if not os.path.exists(jp):
                missing.append(k)
                continue
            if not os.path.exists(mp):
                missing.append(k)
                continue
            # 新鲜度：manifest 必须晚于契约（attach 重跑后必须重拆，否则单元过期）
            if os.path.getmtime(mp) < os.path.getmtime(jp):
                stale.append(k)
        if missing:
            return False, f"缺内容化分章契约 / 单元 manifest: {missing[:4]}"
        if stale:
            return False, f"单元 manifest 早于契约（attach 后未重拆）: {stale[:4]}"
        return True, f"{len(keys)} 章内容化契约 + 单元拆分齐备且新鲜"

    @staticmethod
    def _count_md(book_dir, prefix):
        import re
        n = 0
        for f in glob.glob(os.path.join(book_dir, "*.md")):
            b = os.path.basename(f)
            # 英文源版：ChapterN_*.md；附录单元：AppendixX_*.md（结构契约名含 "Appendix X"）
            if re.match(r"^Chapter\d", b) or re.match(r"^Appendix[A-Z]", b):
                n += 1
            # 中文翻译版：第N章_*.md / 附录X_*.md
            elif (b.startswith("第") and "章" in b[:6]) or re.match(r"^附录[A-Z]", b):
                n += 1
        return n

    # ---- write_chapters 证据辅助：「基于草稿 + 零漏项」的机械核对 ----
    # 容器 / 派生 / 习题类型（与 data/book_structure/book_structure.py 对齐）
    _GATE_CONTAINER_TYPES = ("chapter", "section")
    _GATE_DERIVED_TYPES = ("description", "proof")

    @staticmethod
    def _sec_num(fn):
        """节文件名中的节号（第N章_M_*.md / ChapterN_M_*.md）；合并文件返回 None。"""
        base = os.path.basename(fn)
        m = None
        if base.startswith("第") and "章" in base:
            m = re.match(r"^第\d+章_?(\d+(?:\.\d+)*)", base)
        else:
            m = re.match(r"^Chapter\d+_([\d.]+)", base)
        if not m:
            return None
        sec = m.group(1)
        if not sec or sec.endswith("."):
            return None
        return sec

    @staticmethod
    def _md_group(book_dir, key):
        """该章最终 md 文件组：合并文件优先，否则按节号排序的节文件组。

        数字章按 第N章_*.md / ChapterN_*.md；附录章（key 为字母）按
        附录X_*.md / AppendixX_*.md（与 verify_chapter.chapter_md_groups 同规）。
        """
        if key[:1].isdigit():
            pats = [f"第{key}章_*.md", f"Chapter{key}_*.md"]
        else:
            pats = [f"附录{key}_*.md", f"Appendix{key}_*.md"]
        files = []
        for p in pats:
            files.extend(glob.glob(os.path.join(book_dir, p)))
        uniq = sorted(set(files))
        merged = [f for f in uniq if physical_evidence._sec_num(f) is None]
        if merged:
            return merged
        secs = [(f, physical_evidence._sec_num(f)) for f in uniq]
        secs = [(f, n) for f, n in secs if n]
        secs.sort(key=lambda x: tuple(int(p) for p in x[1].split(".")))
        return [f for f, _ in secs]

    @staticmethod
    def _iter_nodes(d):
        """深度优先 yield 契约节点 dict（跳过无 key/type 的内容块裸字典）。"""
        for el in (d.get("sub_sec") or []):
            if not isinstance(el, dict) or ("key" not in el and "type" not in el):
                continue  # 内容块（text/formula/image）
            yield el
            yield from physical_evidence._iter_nodes(el)

    @staticmethod
    def _norm_text(s):
        """归一化：仅保留字母数字与 CJK，用于容忍标点/空白/排版差异的在位判断。"""
        return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(s or "")).lower()

    # 条目「标签+序号」前缀提取（name 常被 OCR 黏连污染：定义1.1 1.1 (Koopman
    # operator ... — 真正的呈现键只有开头的 标签+序号，如 `定义1.1` / `Theorem 2.1`）
    _LABEL_PREFIX_RE = re.compile(
        r"^\s*([A-Za-z\u4e00-\u9fff]+)[.．·。]?\s*(\d+(?:[.．·。]\d+)*)")

    # 中英标签互译（英文书源版 md 用 EN 标签而契约 key 可能是中文，反之亦然）
    _LABEL_ZH2EN = {
        "定义": ("definition",), "定理": ("theorem",), "引理": ("lemma",),
        "推论": ("corollary",), "命题": ("proposition",), "公理": ("axiom",),
        "断言": ("assertion", "claim"), "例": ("example",),
        "反例": ("counterexample",), "评注": ("remark", "note", "comment"),
        "注": ("remark", "note"), "注记": ("remark", "note"),
        "性质": ("property",), "习题": ("exercise", "problem"),
        "问题": ("problem", "exercise"), "猜想": ("conjecture",),
        "记号": ("notation",), "约定": ("convention",),
    }
    _LABEL_EN2ZH = {}
    for _zh, _ens in _LABEL_ZH2EN.items():
        for _en in _ens:
            _LABEL_EN2ZH.setdefault(_en, _zh)

    @staticmethod
    def _label_variants(ncand):
        """把归一化候选串（如 `定义11` / `definition11`）生成中英标签互译变体。"""
        m = re.match(r"^([\u4e00-\u9fff]+|[a-z]+)(\d.*)$", ncand)
        if not m:
            return [ncand]
        lbl, rest = m.group(1), m.group(2)
        out = {ncand}
        if re.match(r"^[\u4e00-\u9fff]+$", lbl):
            out.update(en + rest for en in physical_evidence._LABEL_ZH2EN.get(lbl, ()))
        else:
            zh = physical_evidence._LABEL_EN2ZH.get(lbl)
            if zh:
                out.add(zh + rest)
        return list(out)

    @staticmethod
    def _missing_contract_names(contract, ntext):
        """契约中未在最终 md 在位的 section 名 / 编号项名列表。

        匹配键三级回退（容忍 OCR 污染与排版差异，全部经归一化包含判断）：
          ① 节点 `key`（如 `定义1.1` / `Theorem 2.1` —— 契约的干净编号键）；
          ② `name` 开头的「标签+序号」前缀（name 常黏连 OCR 题述原文）；
          ③ `name` 全文（及去尾部括注形态）。
        编号键候选额外做**中英标签互译**（英文书源版 md 用 EN 标签、契约 key
        可能是中文，反之亦然）。section 节点用 `name`（草稿 `## §` 标题与之同源）；
        容忍尾部括注被省略。
        """
        miss = []
        for el in physical_evidence._iter_nodes(contract):
            t = str(el.get("type", ""))
            # chapter 容器：章标题呈现形态差异大（# 第N章 / # Chapter N: …），不核对；
            # 派生节点（description/proof）与习题（consolidated 省略）非编号项。
            if t in ("chapter",) or t in physical_evidence._GATE_DERIVED_TYPES \
                    or t == "exercise":
                continue
            name = str(el.get("name") or "").strip()
            key = str(el.get("key") or "").strip()
            cands = []
            nk = physical_evidence._norm_text(key)
            if nk:
                cands.extend(physical_evidence._label_variants(nk))
            if name:
                m = physical_evidence._LABEL_PREFIX_RE.match(name)
                if m:
                    npfx = physical_evidence._norm_text(m.group(0))
                    cands.extend(physical_evidence._label_variants(npfx))
                nn = physical_evidence._norm_text(name)
                if nn:
                    cands.append(nn)
                core = re.sub(r"[（(][^（()）]*[)）]\s*$", "", name).strip()
                nc = physical_evidence._norm_text(core)
                if nc and nc != nn:
                    cands.append(nc)
            cands = [c for c in cands if c]
            if not cands:
                continue  # 无可用匹配键（纯符号名等），跳过避免假阳
            if not any(c in ntext for c in cands):
                miss.append(key or name)
        return miss

    @staticmethod
    def _units_gate_ok(units_dir, manifest):
        """单元门控核心判定（内联，避免 import 耦合）：每单元文件存在、首行
        DONE、内容 hash 已变。返回 (ok, problems)。"""
        import hashlib
        problems = []
        done = {"DRAFT": False, "DONE": True}
        mark_re = re.compile(
            r"<!-- book-summarizer (DRAFT|DONE) unit: id=\S+ type=\S+ key=(.*?) name=(.*?) -->")
        for u in manifest.get("units") or []:
            up = os.path.join(units_dir, u["file"])
            if not os.path.exists(up):
                problems.append("缺失单元文件 %s（%s %s）" % (u["file"], u["type"], u["key"]))
                continue
            try:
                raw = open(up, encoding="utf-8").read()
            except Exception:
                problems.append("单元 %s 读取失败" % u["file"])
                continue
            m = mark_re.match(raw)
            if not m:
                problems.append("单元 %s 首行标记缺失（须 DONE）" % u["file"])
                continue
            if m.group(1) == "DRAFT":
                problems.append("单元 %s（%s %s）仍未处理（标记仍 DRAFT）" % (
                    u["file"], u["type"], u["key"]))
                continue
            # item / desc 必须内容确被改写；章节标题本就无需改动，只确认 DONE
            if u["type"] in ("item", "desc"):
                body = raw[m.end():].lstrip("\r\n").rstrip("\n")
                if hashlib.sha1(body.encode("utf-8")).hexdigest() == (u.get("hash") or ""):
                    problems.append("单元 %s（%s %s）标记 DONE 但内容未改写" % (
                        u["file"], u["type"], u["key"]))
        return (len(problems) == 0, problems)

    @staticmethod
    def write_chapters_ok(book_dir, extract_dir):
        """写章节证据 = ① 章数齐备；② 每章单元门控通过 + 契约名在位。

        🔴 2026-08-31 重构（死命令：不逐单元改好 = 落账被硬拒）：整章草稿
        draft_ch{N}.md 已细分为「每 item 一单元」目录 units/ch{N}/（split_draft_units）。
        agent 必须**逐个把单元按 writing-rules 改好**（首行 DRAFT→DONE + 内容确被
        改写），由 gate_units.py 强制门控。mark 前机械核对每章：
          - **单元门控通过**：manifest 中每个单元文件存在、首行 DONE、正文 hash
            已变——保证「每个编号项都改好、一个不漏」；
          - **最终 md 存在**：merge_units 拼接产物；
          - **契约名在位**：结构契约全部 section 名 + 编号项 name 在最终 md 中
            在位（merge 拼接的兜底，防单元内标题被改没导致漏项）。
        单元 manifest / 契约缺失（legacy 旧书）的章退化为章数核对并如实注明。
        """
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        keys = _chapter_map_keys(ex)
        if not keys:
            return False, "缺 chapter_map.json（config 步未完成）"
        missing_md, gate_fail, missing_names, degraded = [], [], [], []
        for k in keys:
            md_files = physical_evidence._md_group(book_dir, k)
            if not md_files:
                missing_md.append(k)
                continue
            mpath = os.path.join(ex, "book_structure", "units", f"ch{k}", "manifest.json")
            contract_path = os.path.join(
                ex, "book_structure",
                ("ch%s.json" if k[:1].isdigit() else "appendix%s.json") % k)
            if not os.path.exists(mpath) or not os.path.exists(contract_path):
                degraded.append(k)
                continue
            # ① 单元门控：每单元存在 + DONE + 内容已改写（每个 item 都不漏）
            try:
                manifest = json.load(open(mpath, encoding="utf-8"))
            except Exception:
                gate_fail.append((k, "manifest 非法 JSON"))
                continue
            ok_g, gprob = physical_evidence._units_gate_ok(
                os.path.join(ex, "book_structure", "units", f"ch{k}"), manifest)
            if not ok_g:
                gate_fail.append((k, gprob[0] if gprob else "门控未通过"))
                continue
            # ② 契约名在位（merge 拼接兜底，防单元内漏项）
            try:
                contract = json.load(open(contract_path, encoding="utf-8"))
            except Exception:
                degraded.append(k)
                continue
            text = ""
            for f in md_files:
                try:
                    with open(f, encoding="utf-8-sig") as fh:
                        text += fh.read()
                except Exception:
                    pass
            miss = physical_evidence._missing_contract_names(
                contract, physical_evidence._norm_text(text))
            if miss:
                missing_names.append((k, miss))
        if missing_md:
            return False, f"缺最终 md {len(missing_md)} 章: {missing_md[:4]}"
        if gate_fail:
            k, prob = gate_fail[0]
            return False, (f"{len(gate_fail)} 章单元门控未通过（须逐个把单元改好、"
                           f"DONE + 内容改写后重跑 gate_units）: ch{k} {prob}")
        if missing_names:
            k, miss = missing_names[0]
            return False, (f"{len(missing_names)} 章相对结构契约漏骨架节/编号项: "
                           f"ch{k} 缺 {len(miss)} 项（如 {miss[:4]}）；"
                           f"须回归 units/ch{k}/ 单元补齐后再 mark"
                           f"（若条目为 OCR 噪声误收，走 manage_ignore 机制，勿编造）")
        if degraded:
            return True, (f"已写 {len(keys)} 章（{len(degraded)} 章缺单元 manifest/契约，"
                          f"退化为章数核对: {degraded[:4]}；建议重跑 draft 步后重验）")
        return True, (f"已写 {len(keys)} 章，每章单元门控全部通过（每 item 改好）"
                      f"且契约骨架节 + 编号项全部在位")

    @staticmethod
    def embed_figures_ok(book_dir, extract_dir):
        # 宽松判定：存在 figure 目录（书根，与 md 同级，2026-09-01 起）或任一 md 含图片引用
        figdir = os.path.join(book_dir, "figure")
        if os.path.isdir(figdir):
            return True, "figure 目录存在"
        for f in glob.glob(os.path.join(book_dir, "*.md")):
            try:
                txt = open(f, encoding="utf-8").read()
            except Exception:
                continue
            if "![" in txt or "](figure/" in txt:
                return True, "存在图片引用"
        return True, "嵌图为可选步骤（图少书可视为完成）"

    @staticmethod
    def _run_verify_all(ex, book_dir):
        """真实复验：跑 verify_chapter.py --all（中英两组 .md 都覆盖）。

        list-form + sys.executable：不依赖 PATH 里的 `python`（conda 环境外
        可能缺依赖），也不经 shell 规避含空格路径的引号问题。
        返回 (rc, errmsg)；rc=None 表示执行异常。
        """
        # 本文件位于 <root>/flows/_flow_contract.py —— 向上一级即技能根。
        root = os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        script = os.path.join(root, "verify", "script", "verify_chapter.py")
        try:
            rc = subprocess.call([sys.executable, script, "--all", ex, book_dir])
            return rc, None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def verify_source_ok(book_dir, extract_dir):
        # 🔴 翻译硬闸的物理证据：必须真实复验源语言版 exit 0，否则视为未完成。
        # 不再软放行——未嵌图 / 未校验 PASS 的源语言不得 mark，从而闸门挡住 derive。
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        # 仅校验源语言版：此时翻译版尚未写出，--all 只会扫到已存在的源版 .md。
        # （英文书源=ChapterN_*.md；中文书源=第N章_*.md，且无翻译版。）
        rc, err = physical_evidence._run_verify_all(ex, book_dir)
        if rc == 0:
            return True, "源语言 verify_chapter.py --all exit 0（verify PASS + KaTeX OK）"
        if rc is None:
            return False, f"verify 执行异常: {err}"
        return False, (f"源语言 verify 未通过（exit {rc}）。禁止 mark，"
                       f"须先 embed_figures + --fix 复验至 exit 0，再进 derive 翻译。")

    @staticmethod
    def translate_ok(book_dir, extract_dir):
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        cmap = os.path.join(ex, "chapter_map.json")
        total = 0
        if os.path.exists(cmap):
            try:
                total = len(_chapter_map_keys(ex))
            except Exception:
                pass
        cn = 0
        for f in glob.glob(os.path.join(book_dir, "*.md")):
            b = os.path.basename(f)
            if (b.startswith("第") and "章" in b[:6]) or re.match(r"^附录[A-Z]", b):
                cn += 1
        if total and cn < total:
            return False, f"已译 {cn}/{total} 章"
        if cn == 0:
            return False, "尚未翻译任何中文章"
        return True, f"已译 {cn} 个中文章节"

    @staticmethod
    def verify_cn_ok(book_dir, extract_dir):
        # 🔴 与源语言侧同规（不再软放行）：翻译完成后必须真实复验 exit 0。
        # --all 会同时校验中英两组 .md——源版在 write_source.verify_source 已
        # 过闸，此处复验兼作回归保护；中文书源=第N章_*.md（无独立翻译版），
        # 复验对象即源版本身，语义一致。
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        rc, err = physical_evidence._run_verify_all(ex, book_dir)
        if rc == 0:
            return True, ("verify_chapter.py --all exit 0"
                          "（源版+中文版全部 verify PASS + KaTeX OK）")
        if rc is None:
            return False, f"verify 执行异常: {err}"
        return False, (f"翻译版 verify 未通过（exit {rc}）。禁止 mark，"
                       f"须按单向修复规则 --fix / 手工修复后复验至 exit 0。")


# 步 -> 证据函数（与 FLOW_ORDER 对齐）
def _chapter_map_keys(extract_dir):
    """读 chapter_map.json 的章号清单。支持两种形式（与 chapter_map_ok /
    data/chapter_map.load_chapter_map_raw 对齐）：
      * {"chapters": [...]} / {"ch": [...]} 列表形式；
      * {"1": {"name":..,"start":..}, ...} 按章号索引的扁平字典形式
        （Leinster 等历史书实测形态；此前 structure_ok/draft_ok 只认列表形式，
        导致本书 structure 落账被误拒）。排序按数值（"0","1",...,"10"）。
    """
    cm = os.path.join(extract_dir, "chapter_map.json")
    if not os.path.exists(cm):
        return []
    try:
        d = json.load(open(cm, encoding="utf-8"))
    except Exception:
        return []
    if isinstance(d, dict):
        chs = d.get("chapters") or d.get("ch")
        if chs is None:
            if d and all(isinstance(v, dict) for v in d.values()):
                chs = list(d.values())
                keys = []
                for k in d.keys():
                    if k.isdigit():
                        keys.append(k)
                if keys:
                    return sorted(keys, key=lambda x: int(x))
            return []
        keys = []
        for c in chs:
            n = (c.get("num", c.get("ch", c.get("chapter", c.get("n"))))
                 if isinstance(c, dict) else c)
            if n is not None:
                keys.append(str(n))
        return sorted(keys, key=lambda x: (int(x) if x.isdigit() else 10**9))
    if isinstance(d, list):
        keys = []
        for c in d:
            n = (c.get("num", c.get("ch", c.get("chapter", c.get("n"))))
                 if isinstance(c, dict) else c)
            if n is not None:
                keys.append(str(n))
        return keys
    return []


EVIDENCE = {
    "prep.env": None,  # 环境检查由 agent 确认
    "extract.place_pdf": None,
    "extract.extract_text": physical_evidence.pages_all_landed,
    "extract.mm_repair": physical_evidence.mm_repair_complete,
    "write_source.config": physical_evidence.config_ok,
    "write_source.figure_detection": physical_evidence.figure_ok,
    "write_source.structure": physical_evidence.structure_ok,
    "write_source.draft": physical_evidence.draft_ok,
    "write_source.write_chapters": physical_evidence.write_chapters_ok,
    "write_source.verify_source": physical_evidence.verify_source_ok,
    "derive.translate": physical_evidence.translate_ok,
    "derive.verify_cn": physical_evidence.verify_cn_ok,
}


def check_evidence(flow, step, book_dir, extract_dir):
    """返回 (ok, detail)。无证据函数的步返回 (True, 'agent 自证')。"""
    fn = EVIDENCE.get(f"{flow}.{step}")
    if fn is None:
        return True, "agent 自证（环境/手填步骤）"
    return fn(book_dir, extract_dir)
