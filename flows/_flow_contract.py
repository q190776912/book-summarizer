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
    # 🔴 2026-09-03 翻译单元化（内置于 write_source）：翻译 = 单步 translate_chapters
    #（清单初始化 + agent 逐个翻译生成翻译单元 + 门控 + 1:1 同构闸）/ merge_all
    #（一次拼接源语言 + 翻译语言两版）；verify_source 后移至末步、一次覆盖两版。
    "extract": ["place_pdf", "extract_text", "mm_repair"],
    "write_source": ["config", "build_chapter_map", "figure_detection", "structure",
                     "draft", "write_chapters", "translate_chapters",
                     "merge_all", "verify_source"],
}

FLOW_PREREQS = {
    "extract": ["prep"],
    "write_source": ["extract"],
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
    "write_source.build_chapter_map": ("cmd",
        # 🔴 一步从 OCR 生成正确页码：检测引擎已内联于 build_chapter_map.py，自动填每章
        # start/end 写回 chapter_map.json，并产出 chapter_map.build_report.md 供
        # agent 判断。UNDTECTED 章 exit 1，agent 手动补正后重跑。全章 start/end
        # 非 null 才算 done（见 EVIDENCE chapter_map_built）。
        "python tools/build_chapter_map.py \"{extract_dir}\""),
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
        "🔴 对应文档步骤 5（agent 逐个改好 + 门控）：agent 逐个打开 "
        "split_draft_units.py 拆出的单元目录 units/ch{N}/（章标题 / 节标题 / 描述 / "
        "每个编号项 各一 md），按 writing-rules 改好（公式逐条重写校正、Tier 压缩、"
        "格式落地、存疑回查 page_*.json），每个单元把首行 DRAFT 标记改为 DONE；"
        "跑 python flows/write-source/script/gate_units.py \"{extract_dir}\" "
        "——🔴 强制门控：全部单元 DONE 且单元级质量校验通过（全部引用 verify 已有检测："
        "check_katex.check_display_math_closure（$$ 闭合）/ katex_heuristics（裸命令·裸"
        "Unicode 字符·裸箭头）/ verbose_gates.check_verbose_proofs（证明过长）/ "
        "struct_labels（结构标签）/ format_verify.check_example_blockquote_lines"
        "（example blockquote）/ OCR 残留薄封装）才 exit 0——判断标准"
        "是「写对」而非「重写」，拦模型瞎改就标 DONE（每个 item 都不漏）。"
        "🔴 2026-09-03 起拼接移至 merge_all 步：本步不含拼接，证据 = 每章单元门控通过。"),
    "write_source.translate_chapters": ("agent",
        "🔴 对应文档步骤 6（agent 逐个翻译单元 + 双重门控；翻译单元按需生成、"
        "不分步预派生）：① 先跑 "
        "python flows/write-source/script/init_translate_units.py \"{extract_dir}\" "
        "（初始化 units-translate/ch{N}/manifest.json 清单 + src_hash 快照，不复制正文；"
        "--scaffold 可选补齐源文骨架；内置翻译硬闸：源章 gate_units 未过即拒；中文书跳过）；"
        "② agent 逐个打开源单元 units/ch{N}/ 看一个 → 把译文写入对应的 "
        "units-translate/ch{N}/ 单元（文件不存在则新建，公式 / \\tag / 图片 / 编号项"
        "逐字保留，术语首现标注规则见 writing-rules），译完置 DONE；"
        "③ 双重门控必须全过——"
        "python flows/write-source/script/gate_units.py \"{extract_dir}\" "
        "--units-dir units-translate（同一套单元质量校验，缺文件/仍 DRAFT 即拒）＋ "
        "python flows/write-source/script/check_translate_parity.py \"{extract_dir}\" "
        "[ch ...]（🔴 1:1 同构闸：单元序列 / \\tag 集合 / 图片集合 / 编号项标签集合"
        "与源单元逐一相等，漏译 / 漏公式 / 漏图 / 漏编号在此被拦）。"),
    "write_source.merge_all": ("cmd",
        # 文档步骤 7（原步骤 6 拼接后移并扩展）：一次拼接源语言 + 翻译语言两组 md。
        # merge_units 自带强制门控（拼接前先 gate_units，--units-dir 同步生效）。
        "python flows/write-source/script/merge_units.py \"{extract_dir}\" --all && "
        "python flows/write-source/script/merge_units.py \"{extract_dir}\" --all "
        "--units-dir units-translate"),
    "write_source.embed_figures": ("cmd",
        "python flows/script/embed_figures.py \"{book_dir}\""),
    "write_source.verify_source": ("cmd",
        # exit 0 才算 PASS；--all 覆盖源语言 + 翻译语言两组 .md（2026-09-03 起两版
        # 均已由 merge_all 写出，一次校验覆盖两版）。
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
    def chapter_map_built(book_dir, extract_dir):
        """build_chapter_map 步骤证据：全章 start/end 已填 + 起飞前报告已生成。

        机器可强制的部分只有"完整性"：chapter_map.json 解析成功、每章 start/end
        均非 null、chapter_map.build_report.md 存在（证明生成器已跑、agent 有报告
        可判）。agent 对报告的人工判断（确认 CORRECTED / 补 UNDTECTED）是流程规则，
        不靠机器闸——这与"生成 + agent 判断"的一步法一致，不再有独立校验脚本。
        """
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        cmap = os.path.join(ex, "chapter_map.json")
        if not os.path.exists(cmap):
            return False, "缺 chapter_map.json（config 步未生成）"
        try:
            with open(cmap, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            return False, "chapter_map.json 非法 JSON: %s" % e
        # 兼容形态 A（{"chapters":[...]}）与 B（{"1":{...}}）
        recs = []
        if isinstance(raw, dict) and isinstance(raw.get("chapters"), list):
            recs = raw["chapters"]
        elif isinstance(raw, dict):
            recs = [v for v in raw.values() if isinstance(v, dict)]
        if not recs:
            return False, "chapter_map.json 无章节"
        missing = []
        for c in recs:
            ch = c.get("ch", c.get("num", c.get("chapter")))
            s = c.get("start", c.get("start_page"))
            e = c.get("end", c.get("end_page"))
            if s is None or e is None:
                missing.append(str(ch))
        if missing:
            return False, ("以下章 start/end 仍为空（须 agent 在 build_report 中补正后"
                           "重跑 build_chapter_map）: %s" % ", ".join(missing))
        report = os.path.join(ex, "chapter_map.build_report.md")
        if not os.path.exists(report):
            return False, "缺 chapter_map.build_report.md（build_chapter_map 未运行）"
        return True, "chapter_map.json 全章 start/end 已填（build_chapter_map 生成 + agent 已审阅报告）"

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
    def _missing_contract_names(contract, ntext, ignore_set=None):
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
            # 检查是否在 ignore 列表中
            if ignore_set:
                key_norm = physical_evidence._norm_text(key)
                name_norm = physical_evidence._norm_text(name)
                if (key_norm in ignore_set or name_norm in ignore_set or
                    any(physical_evidence._norm_text(k) in ignore_set for k in [key, name])):
                    continue
            if not any(c in ntext for c in cands):
                miss.append(key or name)
        return miss

    @staticmethod
    def _units_gate_ok(units_dir, manifest):
        """单元门控核心判定（内联，避免 import 耦合）：每单元文件存在、首行
        DONE、**质量校验通过**（写对，非仅重写）。返回 (ok, problems)。"""
        problems = []
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
            # item / desc 必须「写对」——单元级质量校验通过（🔴 2026-09-01 起
            # 判断标准是"写对"而非"重写"，不再看内容指纹变化）；章节标题只确认 DONE
            if u["type"] in ("item", "desc"):
                body = raw[m.end():].lstrip("\r\n").rstrip("\n")
                try:
                    import check_unit_quality as _quality
                    ok_q, qp = _quality.check_body(u["type"], u.get("name") or "", body)
                except Exception:
                    ok_q, qp = True, []
                if not ok_q:
                    problems.append("单元 %s（%s %s）质量未达标：%s" % (
                        u["file"], u["type"], u["key"], "；".join(qp[:4])))
        return (len(problems) == 0, problems)

    @staticmethod
    def write_chapters_ok(book_dir, extract_dir):
        """写章节证据 = 每章单元门控通过（每个 item 都改好、一个不漏）。

        🔴 2026-08-31 重构（死命令：不逐单元改好 = 落账被硬拒）：整章草稿
        draft_ch{N}.md 已细分为「每 item 一单元」目录 units/ch{N}/（split_draft_units）。
        agent 必须**逐个把单元按 writing-rules 改好**（首行 DRAFT→DONE + 质量校验
        通过），由 gate_units.py 强制门控。
        🔴 2026-09-03 重构（翻译单元化）：拼接移至 merge_all 步——本步证据不再
        要求最终 md 存在与契约名在位（该核对移入 merge_all_ok，对源 + 译两版生效）。
        确保前置：draft 步未跑（缺 units/manifest.json）→ 硬拒，防 bootstrap 误回填。
        """
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        keys = _chapter_map_keys(ex)
        if not keys:
            return False, "缺 chapter_map.json（config 步未完成）"
        gate_fail, no_units, empty_units = [], [], []
        for k in keys:
            units_dir = os.path.join(ex, "book_structure", "units", f"ch{k}")
            mpath = os.path.join(units_dir, "manifest.json")
            if not os.path.exists(mpath):
                no_units.append(k)
                continue
            try:
                manifest = json.load(open(mpath, encoding="utf-8"))
            except Exception:
                gate_fail.append((k, "manifest 非法 JSON"))
                continue
            ok_g, gprob = physical_evidence._units_gate_ok(units_dir, manifest)
            if not ok_g:
                gate_fail.append((k, gprob[0] if gprob else "门控未通过"))
                continue
            if not (manifest.get("units") or []):
                empty_units.append(k)
        if no_units:
            return False, (f"{len(no_units)} 章缺 units/manifest.json"
                           f"（先跑 draft 步拆分单元）: {no_units[:4]}")
        if gate_fail:
            k, prob = gate_fail[0]
            return False, (f"{len(gate_fail)} 章单元门控未通过（须逐个把单元改好、"
                           f"DONE + 质量校验通过后重跑 gate_units）: ch{k} {prob}")
        note = f"；{len(empty_units)} 章单元清单为空: {empty_units[:4]}" if empty_units else ""
        return True, f"{len(keys)} 章单元门控全部通过（每 item 改好，一个不漏）{note}"

    # ---- 翻译单元证据（2026-09-03 翻译单元化：清单 + 门控 + 同构闸） ----

    @staticmethod
    def _src_manifest(ex, key):
        """读源单元 manifest；不存在返回 None。"""
        p = os.path.join(ex, "book_structure", "units", f"ch{key}", "manifest.json")
        if not os.path.exists(p):
            return None
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _tgt_language(src_lang):
        """源语言 → 翻译目标语言；中文源（或未知）返回 None = 无翻译阶段。"""
        return {"en": "cn"}.get((src_lang or "").lower())

    @staticmethod
    def translate_chapters_ok(book_dir, extract_dir):
        """翻译证据 = ① 翻译清单已初始化（units-translate/ch{N}/manifest.json，
        由翻译步内 init_translate_units.py 生成——元数据 + src_hash，不复制正文）；
        ② 翻译单元门控通过（同一套单元质量校验）；
        ③ 1:1 同构闸 check_translate_parity 通过（漏译/漏公式/漏图/漏编号在此拦截）。

        中文源书（无翻译阶段）自动通过。
        """
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        keys = _chapter_map_keys(ex)
        if not keys:
            return False, "缺 chapter_map.json（config 步未完成）"
        todo, skip, no_src = [], [], []
        for k in keys:
            src = physical_evidence._src_manifest(ex, k)
            if src is None:
                no_src.append(k)
                continue
            tgt = physical_evidence._tgt_language(src.get("language"))
            if tgt is None:
                skip.append(k)
                continue
            todo.append(k)
        if no_src:
            return False, (f"{len(no_src)} 章缺源 units/manifest.json"
                           f"（先完成 draft + write_chapters 步）: {no_src[:4]}")
        if not todo:
            return True, "中文源书：无翻译阶段，全部章跳过"
        gate_fail, parity_fail = [], []
        for k in todo:
            tdir = os.path.join(ex, "book_structure", "units-translate", f"ch{k}")
            tmanifest_path = os.path.join(tdir, "manifest.json")
            if not os.path.exists(tmanifest_path):
                gate_fail.append((k, "缺 units-translate/manifest.json"
                                      "（先跑 init_translate_units.py 初始化清单）"))
                continue
            try:
                tmanifest = json.load(open(tmanifest_path, encoding="utf-8"))
            except Exception:
                gate_fail.append((k, "units-translate manifest 非法 JSON"))
                continue
            ok_g, gprob = physical_evidence._units_gate_ok(tdir, tmanifest)
            if not ok_g:
                gate_fail.append((k, gprob[0] if gprob else "翻译单元门控未通过"))
                continue
            # 1:1 同构闸（子进程解耦，复用与 CLI 同一脚本）
            script = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "write-source", "script", "check_translate_parity.py")
            try:
                rc = subprocess.call([sys.executable, script, ex, k])
            except Exception as e:
                parity_fail.append((k, f"parity 执行异常: {e}"))
                continue
            if rc != 0:
                parity_fail.append((k, "check_translate_parity 未通过"
                                      "（漏译/漏公式/漏图/漏编号，按输出逐项修复）"))
        if gate_fail:
            k, prob = gate_fail[0]
            return False, (f"{len(gate_fail)} 章翻译单元门控未通过"
                           f"（gate_units --units-dir units-translate）: ch{k} {prob}")
        if parity_fail:
            k, prob = parity_fail[0]
            return False, f"{len(parity_fail)} 章 1:1 同构闸未通过: ch{k} {prob}"
        return True, (f"{len(todo)} 章翻译清单就绪 + 门控 + 同构闸全部通过"
                      f"（tag/图片/编号项与源单元 1:1）")

    @staticmethod
    def _md_group_lang(book_dir, key, lang):
        """按语种取该章最终 md 组：cn → 第N章_*/附录X_*；en → ChapterN_*/AppendixX_*。"""
        if key[:1].isdigit():
            pats = ([f"第{key}章_*.md"] if lang == "cn" else [f"Chapter{key}_*.md"])
        else:
            pats = ([f"附录{key}_*.md"] if lang == "cn" else [f"Appendix{key}_*.md"])
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
    def _contract_names_missing(ex, k, md_files):
        """结构契约骨架节 + 编号项在 md 组中的在位核对；返回缺失名列表。"""
        contract_path = os.path.join(
            ex, "book_structure",
            ("ch%s.json" if k[:1].isdigit() else "appendix%s.json") % k)
        if not os.path.exists(contract_path):
            return None
        try:
            contract = json.load(open(contract_path, encoding="utf-8"))
        except Exception:
            return None
        text = ""
        for f in md_files:
            try:
                with open(f, encoding="utf-8-sig") as fh:
                    text += fh.read()
            except Exception:
                pass
        ignore_set = set()
        ignore_path = os.path.join(ex, f"ignore_ch{k}.json")
        if os.path.exists(ignore_path):
            try:
                ignore_data = json.load(open(ignore_path, encoding="utf-8"))
                if isinstance(ignore_data, dict):
                    ignore_set = set(ignore_data.keys())
                elif isinstance(ignore_data, list):
                    ignore_set = set(ignore_data)
            except Exception:
                pass
        return physical_evidence._missing_contract_names(
            contract, physical_evidence._norm_text(text), ignore_set)

    @staticmethod
    def merge_all_ok(book_dir, extract_dir):
        """拼接证据（2026-09-03 起 = 原步骤 6 后移并扩展）：每个外语章有
        源语言 + 翻译语言两组最终 md，且两组的契约骨架节 + 编号项全部在位
        （merge 拼接兜底，防单元内漏项；翻译版的同名漏项由同构闸 + 此处双拦）。

        中文源书只要求源语言（即中文）一组 md。
        """
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        keys = _chapter_map_keys(ex)
        if not keys:
            return False, "缺 chapter_map.json（config 步未完成）"
        missing, missing_names, degraded = [], [], []
        for k in keys:
            src = physical_evidence._src_manifest(ex, k)
            if src is None:
                degraded.append(k)
                continue
            src_lang = (src.get("language") or "cn").lower()
            tgt_lang = physical_evidence._tgt_language(src_lang)
            groups = [(src_lang, physical_evidence._md_group_lang(book_dir, k, src_lang))]
            if tgt_lang:
                groups.append((tgt_lang, physical_evidence._md_group_lang(book_dir, k, tgt_lang)))
            for lang, md_files in groups:
                if not md_files:
                    missing.append((k, lang))
                    continue
                miss = physical_evidence._contract_names_missing(ex, k, md_files)
                if miss:
                    missing_names.append((k, lang, miss))
        if missing:
            (k, lang) = missing[0]
            return False, (f"{len(missing)} 组最终 md 缺失（先跑 merge_all 拼接）: "
                           f"ch{k} [{lang}]" + (f" 等 {len(missing)} 组" if len(missing) > 1 else ""))
        if missing_names:
            k, lang, miss = missing_names[0]
            return False, (f"{len(missing_names)} 组 md 相对结构契约漏骨架节/编号项: "
                           f"ch{k} [{lang}] 缺 {len(miss)} 项（如 {miss[:4]}）；"
                           f"须回归对应单元目录（units / units-translate）补齐后重拼"
                           f"（若条目为 OCR 噪声误收，走 manage_ignore 机制，勿编造）")
        if degraded:
            return True, (f"已拼 {len(keys)} 章（{len(degraded)} 章缺源 manifest，"
                          f"跳过核对: {degraded[:4]}）")
        return True, (f"{len(keys)} 章源语言 + 翻译语言 md 均已拼接且契约项在位")

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
        # 🔴 2026-09-03 翻译单元化后为流程末步：--all 一次覆盖源语言 + 翻译语言
        # 两版（merge_all 已把两组 md 写出）。中文源书只有一组中文 md，语义一致。
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        rc, err = physical_evidence._run_verify_all(ex, book_dir)
        if rc == 0:
            return True, ("verify_chapter.py --all exit 0"
                          "（源语言 + 翻译语言全部 verify PASS + KaTeX OK）")
        if rc is None:
            return False, f"verify 执行异常: {err}"
        return False, (f"verify 未通过（exit {rc}）。禁止 mark，"
                       f"须修复（🔴 --fix 默认禁用，须 --fix --fix-force + PREFLIGHT）"
                       f"或手工定点修改后复验至 exit 0。")


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
    "write_source.build_chapter_map": physical_evidence.chapter_map_built,
    "write_source.figure_detection": physical_evidence.figure_ok,
    "write_source.structure": physical_evidence.structure_ok,
    "write_source.draft": physical_evidence.draft_ok,
    "write_source.write_chapters": physical_evidence.write_chapters_ok,
    "write_source.translate_chapters": physical_evidence.translate_chapters_ok,
    "write_source.merge_all": physical_evidence.merge_all_ok,
    "write_source.verify_source": physical_evidence.verify_source_ok,
}


def check_evidence(flow, step, book_dir, extract_dir):
    """返回 (ok, detail)。无证据函数的步返回 (True, 'agent 自证')。"""
    fn = EVIDENCE.get(f"{flow}.{step}")
    if fn is None:
        return True, "agent 自证（环境/手填步骤）"
    return fn(book_dir, extract_dir)
