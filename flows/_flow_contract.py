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
        # 基本总结草稿：内容完整性闸门 + 渲染（完整契约已由 structure 步一步
        # 产出，无需再 attach；图片经契约 image 块随草稿继承，不再单独嵌图）
        "python verify/script/check_content_completeness.py \"{extract_dir}\" && "
        "python flows/write-source/script/render_draft.py \"{extract_dir}\""),
    "write_source.write_chapters": ("agent",
        "步骤1 render_draft.py 由含内容完整契约 ch{N}.json 渲染基本总结草稿 draft_ch{N}.md；"
        "步骤2 基于草稿逐章调整（公式逐条重写校正、Tier 压缩、writing-rules 格式，"
        "存疑回查 page_*.json），写出源语言 ChapterN_*.md / 第N章_*.md。"),
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
        cm = os.path.join(ex, "chapter_map.json")
        keys = []
        if os.path.exists(cm):
            try:
                d = json.load(open(cm, encoding="utf-8"))
                chs = d.get("chapters") or d.get("ch") or []
                for c in chs:
                    n = c.get("num", c.get("ch", c.get("chapter", c.get("n"))))
                    if n is not None:
                        keys.append(str(n))
            except Exception:
                pass
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
        """基本总结草稿证据：每个结构章节都有内容化分章契约 + 渲染出的草稿文件。"""
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        sub = os.path.join(ex, "book_structure")
        cm = os.path.join(ex, "chapter_map.json")
        keys = []
        if os.path.exists(cm):
            try:
                d = json.load(open(cm, encoding="utf-8"))
                chs = d.get("chapters") or d.get("ch") or []
                for c in chs:
                    n = c.get("num", c.get("ch", c.get("chapter", c.get("n"))))
                    if n is not None:
                        keys.append(str(n))
            except Exception:
                pass
        if not keys:
            return False, "缺 chapter_map.json（config 步未完成）"
        missing, stale = [], []
        for k in keys:
            fname = (f"ch{k}.json" if k[:1].isdigit() else f"appendix{k}.json")
            jp = os.path.join(sub, fname)
            dp = os.path.join(sub, f"draft_ch{k}.md")
            if not os.path.exists(jp):
                missing.append(k)
                continue
            if not os.path.exists(dp):
                missing.append(k)
                continue
            # 新鲜度：草稿必须晚于契约（attach 重跑后必须重渲，否则草稿过期）
            if os.path.getmtime(dp) < os.path.getmtime(jp):
                stale.append(k)
        if missing:
            return False, f"缺内容化分章契约 / 草稿: {missing[:4]}"
        if stale:
            return False, f"草稿早于契约（attach 后未重渲）: {stale[:4]}"
        return True, f"{len(keys)} 章内容化契约 + 草稿齐备且新鲜"

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

    @staticmethod
    def write_chapters_ok(book_dir, extract_dir):
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        cmap = os.path.join(ex, "chapter_map.json")
        total = 0
        if os.path.exists(cmap):
            try:
                d = json.load(open(cmap, encoding="utf-8"))
                total = len(d.get("chapters") or d.get("ch") or [])
            except Exception:
                pass
        written = physical_evidence._count_md(book_dir, "Chapter")
        if total and written < total:
            return False, f"已写源版 {written}/{total} 章"
        if written == 0:
            return False, "尚未写任何源语言章节"
        return True, f"已写 {written} 个源语言章节"

    @staticmethod
    def embed_figures_ok(book_dir, extract_dir):
        # 宽松判定：存在 figures 目录或任一 md 含图片引用
        figdir = os.path.join(book_dir, "figures")
        if os.path.isdir(figdir):
            return True, "figures 目录存在"
        for f in glob.glob(os.path.join(book_dir, "*.md")):
            try:
                txt = open(f, encoding="utf-8").read()
            except Exception:
                continue
            if "![" in txt or "](figures/" in txt or "](figure/" in txt:
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
                d = json.load(open(cmap, encoding="utf-8"))
                total = len(d.get("chapters") or d.get("ch") or [])
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
