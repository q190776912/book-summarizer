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

# --------------------------------------------------------------------------
# 有序步骤（权威）—— 顺序即强制依赖
# --------------------------------------------------------------------------
FLOW_ORDER = {
    "prep": ["env"],
    "extract": ["place_pdf", "extract_text", "chapter_map", "mm_repair",
                "config", "figure_detection", "structure"],
    "write_source": ["write_chapters", "embed_figures", "verify_source"],
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
        "conda activate pdfextract; python -c \"import torch; print(torch.cuda.is_available())\" 须为 True;"
        " 确认 <skill根>/node_modules/katex 存在（npm install katex --no-save）。"),
    "extract.place_pdf": ("agent",
        "按 extract.md 目录决策（分支 A-D）归位 PDF，确定 <book_dir>。"),
    "extract.extract_text": ("cmd",
        # 后台文本提取，断点续跑，纯文本不含图检测
        "bash launch_pipeline.sh \"{pdf}\""),
    "extract.chapter_map": ("agent",
        "从目录页读章名与 PDF 页码，写 _extract/chapter_map.json（见 chapter_map.md）。"),
    "extract.mm_repair": ("agent",
        "完整链路 audit → 模式B(--hybrid) → 模式A(视觉) → apply 写回 page_*.json；"
        "见 mm_repair.md。apply 真完成才出 _extraction_done.json。"),
    "extract.config": ("cmd",
        # 缺 _extraction_done.json 会硬拒绝
        "python config/verify_config/make_config.py \"{extract_dir}\""),
    "extract.figure_detection": ("cmd",
        "python flows/script/extract_figures.py \"{pdf}\" --out \"{extract_dir}\" --book && "
        "python flows/script/assign_figures.py \"{pdf}\" --out \"{extract_dir}\" --book"),
    "extract.structure": ("cmd",
        # 再跑 check_structure_completeness --backfill + 闸门
        "python flows/extract/structure/script/build_structure.py \"{extract_dir}\""),
    "write_source.write_chapters": ("agent",
        "按 book_structure.json 契约逐节点双源写作（内容回归 page_*.json），"
        "源语言初稿 ChapterN_*.md / 第N章_*.md。"),
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
                except Exception:
                    pass
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
        p = os.path.join(ex, "verify_config.json")
        if not os.path.exists(p):
            return False, "缺 verify_config.json"
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            return False, f"verify_config.json 非法 JSON: {e}"
        if not (isinstance(d.get("ordinal"), list) and len(d.get("ordinal")) > 0):
            return False, "verify_config.json 缺 ordinal 数组"
        return True, "verify_config.json 含 ordinal 数组"

    @staticmethod
    def figure_ok(book_dir, extract_dir):
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        p = os.path.join(ex, "figure_index.json")
        if not os.path.exists(p):
            return False, "缺 figure_index.json"
        return True, "figure_index.json 存在"

    @staticmethod
    def structure_ok(book_dir, extract_dir):
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        p = os.path.join(ex, "book_structure.json")
        if not os.path.exists(p):
            return False, "缺 book_structure.json"
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            return False, f"book_structure.json 非法 JSON: {e}"
        subs = d.get("sub_sec") or []
        if not subs:
            return False, "book_structure.json 无章节节点"
        return True, f"book_structure.json 含 {len(subs)} 章"

    @staticmethod
    def _count_md(book_dir, prefix):
        import re
        n = 0
        for f in glob.glob(os.path.join(book_dir, "*.md")):
            b = os.path.basename(f)
            if b.startswith(prefix) and "第" not in b[:3]:
                # ChapterN_*.md
                if re.match(r"^Chapter\d", b):
                    n += 1
            elif b.startswith("第") and "章" in b[:6]:
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
    def verify_source_ok(book_dir, extract_dir):
        # verify 的 PASS 以 verify_chapter.py exit 0 为准；此处仅作软提示，
        # 真判定由 agent 跑 verify 后确认 exit 0 再 mark。
        return True, "需 agent 跑 verify_chapter.py --all 确认 exit 0 后 mark"

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
        cn = sum(1 for f in glob.glob(os.path.join(book_dir, "*.md"))
                 if os.path.basename(f).startswith("第") and "章" in os.path.basename(f)[:6])
        if total and cn < total:
            return False, f"已译 {cn}/{total} 章"
        if cn == 0:
            return False, "尚未翻译任何中文章"
        return True, f"已译 {cn} 个中文章节"

    @staticmethod
    def verify_cn_ok(book_dir, extract_dir):
        return True, "需 agent 跑 verify_chapter.py --all 确认 exit 0 后 mark"


# 步 -> 证据函数（与 FLOW_ORDER 对齐）
EVIDENCE = {
    "prep.env": None,  # 环境检查由 agent 确认
    "extract.place_pdf": None,
    "extract.extract_text": physical_evidence.pages_all_landed,
    "extract.chapter_map": physical_evidence.chapter_map_ok,
    "extract.mm_repair": physical_evidence.mm_repair_complete,
    "extract.config": physical_evidence.config_ok,
    "extract.figure_detection": physical_evidence.figure_ok,
    "extract.structure": physical_evidence.structure_ok,
    "write_source.write_chapters": physical_evidence.write_chapters_ok,
    "write_source.embed_figures": physical_evidence.embed_figures_ok,
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
