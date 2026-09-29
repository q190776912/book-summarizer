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

from data.book_structure.book_structure import (
    chapter_label, prime_chapter_kinds, unit_dir_name, chapter_ordinal,
    is_numbered_chapter)

# --------------------------------------------------------------------------
# 有序步骤（权威）—— 顺序即强制依赖
# --------------------------------------------------------------------------
FLOW_ORDER = {
    "prep": ["env"],
    # 🔴 extract 终于 MM Repair；config / figure_detection / structure / 单元拆分
    # 等写作前置全部属于 write_source（草稿前须过 structure 完整性闸门）。
    "extract": ["place_pdf", "extract_text", "mm_repair"],
    # 🔴 源先校验、再翻译（与 lib/flow_gate.py 对齐）：write_chapters 改好源单元 →
    # merge_source（只拼源语言 + 只校验源版，源书层面图/编号/公式问题在翻译前暴露并
    # 回填修源单元）→ translate_chapters（逐单元翻译 + 双重门控）→ merge_translation
    # （末步：拼翻译语言 + 全量校验源+译两版，吸收原独立 verify 步，不再单列第 9 步）。
    "write_source": ["config", "build_chapter_map", "figure_detection", "structure",
                     "draft", "write_chapters", "merge_source", "translate_chapters",
                     "merge_translation"],
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
        # build_structure 一步产出含内容（text/formula/image/
        # proof/description）的完整分章契约 ch{N}.json；结构完整性（章节/条目
        # 查漏回填 + gate.passed 闸门）是本步内的硬闸，见 structure.md 第 2-4 步
        "python flows/write-source/structure/script/build_structure.py \"{extract_dir}\""),
    "write_source.draft": ("cmd",
        # 基本总结草稿拆分：内容完整性闸门 + 把整章草稿细分为「每 item 一单元」
        # 的 units/ch{N}/ 目录。
        # 完整契约已由 structure 步产出，无需再 attach；图片经契约 image 块随
        # 单元继承。render_draft.py 是 split_draft_units 的渲染库。
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
        "🔴 源版拼接 + 源版校验在 merge_source 步（翻译之前）：本步不含拼接，"
        "证据 = 每章单元门控通过。"),
    "write_source.translate_chapters": ("agent",
        "🔴 对应文档步骤 7（源版已在 merge_source 步合并 + 校验通过后，agent 逐个翻译"
        "单元 + 双重门控；翻译单元按需生成、不分步预派生）：① 先跑 "
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
    "write_source.merge_source": ("cmd",
        # 文档步骤 6：先拼**源语言**单元（--all 默认 units = 源），再校验源版；
        # merge_units 自带强制门控（拼接前先 gate_units）。
        # 🔴 源书层面的图 / 编号 / 公式问题在**翻译之前**暴露，回填修源单元。
        # 🔴 规则3：源版合并 md > MERGED_MD_CHAR_LIMIT 字符必须随即跑
        # tools/split_chapters.py 按节拆分（merge_source 证据复核硬拦，见 merge_source_ok）。
        "python flows/write-source/script/merge_units.py \"{extract_dir}\" --all && "
        "python verify/script/verify_chapter.py --all \"{extract_dir}\" \"{book_dir}\""),
    "write_source.embed_figures": ("cmd",
        "python flows/script/embed_figures.py \"{book_dir}\""),
    "write_source.merge_translation": ("cmd",
        # 文档步骤 8（末步）：拼**翻译语言**单元（--units-dir units-translate），
        # 再全量校验源 + 译两版（--all 一次覆盖两组），exit 0 才算流程完成。
        # 中文书无 units-translate → merge 自动跳过、verify 只校验唯一中文版，语义一致。
        "python flows/write-source/script/merge_units.py \"{extract_dir}\" --all "
        "--units-dir units-translate && "
        "python verify/script/verify_chapter.py --all \"{extract_dir}\" \"{book_dir}\""),
}


# 🔴 规则3（write-source.md）：合并形态章 md 超此字符数必须经 tools/split_chapters.py
# 按节拆分。阈值与 split_chapters.DEFAULT_THRESHOLD 保持一致。
MERGED_MD_CHAR_LIMIT = 60000


def _contract_unit_orphans(contract_path, manifest_path, ch_key):
    """契约晚于清单时，用**权威判据**判定单元是否真的过期（返回问题列表，非空 = 过期）。

    判据不另起炉灶：直接调 `gate_units` 的章级闸 ⑩（契约 → manifest 反向对账，
    按「习题 / 结果项」分桶 + `sec_ordinals` 序标归一），检测趟与修复趟共用同一个
    谓词。🔴 fail-closed：契约 / 清单读不到、或 ⑩ 判据载不进来，一律按「真过期」
    处理——本函数唯一的放行对象是**已对账一致**的写源后定点修补。
    """
    try:
        import json as _json
        with open(contract_path, encoding="utf-8") as f:
            contract = _json.load(f)
        with open(manifest_path, encoding="utf-8") as f:
            man = _json.load(f)
        units = (man.get("units") if isinstance(man, dict) else man) or []
        from gate_units import _check_contract_unit_coverage
    except Exception:
        return ["<契约/清单或闸⑩判据不可读，按过期处理>"]
    return _check_contract_unit_coverage(contract, units, ch_key) or []


# --------------------------------------------------------------------------
# 物理证据检查：只看磁盘产物，不依赖账本
# --------------------------------------------------------------------------
class physical_evidence:
    """每步的完成证据（book_dir, extract_dir）-> (bool, detail)。"""

    @staticmethod
    def _extract_dir(book_dir, extract_dir):
        ex = extract_dir or os.path.join(book_dir, "_extract")
        # 按 chapter_map.json 灌注 kind 注册表，使 chapter_label /
        # unit_dir_name 对 Supplement（kind=3）等字母章返回正确前缀（幂等）。
        prime_chapter_kinds(ex)
        return ex

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
        # verify_config.json 支持外层 map 格式（kind 路由：
        # "ch"/"appendix"/"supplement" 各含子配置；见 ConfigLoader 零回归语义）。
        # 顶层 ordinal → 扁平格式（正文章）；顶层 map → 正文章 ordinal 在 "ch" 键内。
        cfg = d if isinstance(d.get("ordinal"), list) else d.get("ch")
        if not (isinstance(cfg, dict)
                and isinstance(cfg.get("ordinal"), list)
                and len(cfg.get("ordinal")) > 0):
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
        `<extract_dir>/completeness_reports/{ch{N},appendix{X}}_completeness_report.json`），
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
                       sub, chapter_label(k) + ".json"))]
        if missing:
            return False, f"缺分章骨架 {len(missing)} 章: {missing[:4]}"
        reports_missing, not_passed = [], []
        for k in keys:
            rp = os.path.join(ex, "completeness_reports",
                              f"{chapter_label(k)}_completeness_report.json")
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

        写作底稿 = 「每 item 一单元目录 units/ch{N}/」（split_draft_units.py）。
        契约必须 content 化后拆分，且 manifest 晚于契约（attach 重跑后必须重拆，
        否则单元过期）。
        """
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        sub = os.path.join(ex, "book_structure")
        keys = _chapter_map_keys(ex)
        if not keys:
            return False, "缺 chapter_map.json（config 步未完成）"
        missing, stale, repaired = [], [], []
        for k in keys:
            fname = chapter_label(k) + ".json"
            jp = os.path.join(sub, fname)
            mp = os.path.join(sub, "units", unit_dir_name(k), "manifest.json")
            if not os.path.exists(jp):
                missing.append(k)
                continue
            if not os.path.exists(mp):
                missing.append(k)
                continue
            # 新鲜度：manifest 必须晚于契约（attach 重跑后必须重拆，否则单元过期）
            if os.path.getmtime(mp) < os.path.getmtime(jp):
                # 🔴 mtime 只是**代理**，真不变量是「契约里每个应成单元的节点在
                # manifest 都有记录」。写源后的**定点修补**（SKILL.md「结构修复」：
                # 单元已写毕的旧契约不许重建，只在契约里把节点插回正确位置 +
                # 同步搬 manifest 记录）天然会「先改清单、后改契约」，方向与
                # attach 相反 ⇒ 纯 mtime 判据把这类修补一律判成过期，
                # 而 `mark` 会因此拒绝落账（Arnold《经典力学的数学方法》ch10 §51
                # 互换 系1/系2 实测 2026-09-29：契约 03:32 / 清单 03:26，节点集合
                # 与顺序两方一致，gate_units ⑩ 与 verify 全绿，只有本代理报警）。
                # 故报警前先跑**权威判据**（gate_units 章级闸 ⑩，判据只此一份）：
                # 无孤儿节点 = 定点修补，放行并如实记数；有孤儿 = 真过期，照旧拒。
                if _contract_unit_orphans(jp, mp, k):
                    stale.append(k)
                else:
                    repaired.append(k)
        if missing:
            return False, f"缺内容化分章契约 / 单元 manifest: {missing[:4]}"
        if stale:
            return False, (f"单元 manifest 早于契约且契约有孤儿节点（attach 后未重拆）: "
                           f"{stale[:4]}")
        note = (f"；{len(repaired)} 章为写源后定点修补（契约晚于清单，"
                f"闸⑩ 对账无孤儿节点）" if repaired else "")
        return True, f"{len(keys)} 章内容化契约 + 单元拆分齐备且新鲜{note}"

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

        数字章按 第N章_*.md / ChapterN_*.md；附录/补篇章按 kind（chapter_map 注册表，
        见 ``is_numbered_chapter``）取 附录X_*.md / AppendixX_*.md——键本身可以是数字
        （Rosen 8e 的 Appendix A/B/C 登记成章键 14/15/16），故**不得**用「键首字符是否
        数字」判章型（与 verify_chapter.chapter_md_groups 同规）。
        """
        _ord = chapter_ordinal(key)
        if is_numbered_chapter(key) and _ord:
            pats = [f"第{_ord}章_*.md", f"Chapter{_ord}_*.md"]
        elif _ord:
            pats = [f"附录{_ord}_*.md", f"Appendix{_ord}_*.md"]
        else:
            pats = ["附录.md", "附录_*.md", "Appendix.md", "Appendix_*.md"]
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
    # 🔴 词表缺词 = **假报「契约项在 md 不在位」**：Rosen 8e 契约 key `算法1`…（46 个）
    # 在英文 md 里印作 `**Algorithm 1 (…)**`，缺 `算法` 一词时 8 章 merge_source 证据
    # 被硬拒（md 明明在位）。新增条目前先按契约键普查（`_iter_nodes` 取 key 词头计数）。
    _LABEL_ZH2EN = {
        "定义": ("definition",), "定理": ("theorem",), "引理": ("lemma",),
        "推论": ("corollary",), "命题": ("proposition",), "公理": ("axiom",),
        "断言": ("assertion", "claim"), "例": ("example",),
        "反例": ("counterexample",), "评注": ("remark", "note", "comment"),
        "注": ("remark", "note"), "注记": ("remark", "note"),
        "性质": ("property",), "习题": ("exercise", "problem"),
        "练习": ("exercise", "problem"),
        "问题": ("problem", "exercise"), "猜想": ("conjecture",),
        "记号": ("notation",), "约定": ("convention",),
        "算法": ("algorithm",),
        # 图 / 表：英文书契约把 `Figure N.M` / `Table N.M` 收作编号项，中文笔记版
        # 按惯例印作「图 N.M」「表 N.M」。缺这两条时 CN 组会假报「契约项不在位」，
        # 硬拒 merge_translation 证据（Fraleigh 实测 8 章 14 项全为真在位）。
        "图": ("figure", "graph", "diagram"), "示意图": ("figure", "diagram"),
        "表": ("table",), "表格": ("table",),
    }
    _LABEL_EN2ZH = {}
    for _zh, _ens in _LABEL_ZH2EN.items():
        for _en in _ens:
            _LABEL_EN2ZH.setdefault(_en, _zh)

    @staticmethod
    def _label_variants(ncand):
        """把归一化候选串（如 `定义11` / `definition11`）生成中英标签互译变体。"""
        # 🔴 序标既可为数字也可为字母：Shafarevich BA1 ch3 §4.2 印 Theorem A/B/C、
        # §4.4 印 Theorem D，契约键 = 中文标签 + 字母序标（`定理 A` → 归一 `定理a`）。
        # 旧正则只认数字起头 → `定理a` 生成不出 `theorema` 变体 → 英文源 md（印
        # `**Theorem A**`）判「编号项不在位」，merge_source 证据被假报硬拒（实测 4 项）。
        # 字母序标是教材标准形态（附录 Proposition A.1 / 正文 Theorem B），故序标放宽到
        # 字母起头（含 a1 / a.1），数字分支逐字节不变；反方向（契约键为 EN Theorem A、
        # 中文版印 定理 A）由同一条正则回溯自然覆盖（theorem + a）。
        m = re.match(r"^([\u4e00-\u9fff]+|[a-z]+)(\d.*|[a-z]\d*(?:\.\d*[a-z0-9]+)*)$",
                     ncand)
        if not m:
            return [ncand]
        lbl, rest = m.group(1), m.group(2)
        out = {ncand}
        if re.match(r"^[\u4e00-\u9fff]+$", lbl):
            ens = physical_evidence._LABEL_ZH2EN.get(lbl, ())
            out.update(en + rest for en in ens)
            # 中文同胞标签：契约 key 与译版 md 各用不同中文标签（do Carmo 中文版
            # 契约 `评注N` 在译文里印作 `注N`）。二者英文语义组相交即可互换；
            # 不做这一步，CN 组会假报「契约项不在位」硬拒 merge 证据。
            if ens:
                for zh2, ens2 in physical_evidence._LABEL_ZH2EN.items():
                    if zh2 != lbl and set(ens2) & set(ens):
                        out.add(zh2 + rest)
        else:
            zh = physical_evidence._LABEL_EN2ZH.get(lbl)
            if zh:
                out.add(zh + rest)
            for zh2, ens2 in physical_evidence._LABEL_ZH2EN.items():
                if lbl in ens2:
                    out.add(zh2 + rest)
        return list(out)

    @staticmethod
    def _missing_contract_names(contract, ntext, ignore_set=None,
                               check_sections=True):
        """契约中未在最终 md 在位的 section 名 / 编号项名列表。

        ``check_sections``（默认 True，保持既有行为）：仅当被核对的 md 组与契约**同源
        语言**时才核对 `section` 节点。译本 md 的节标题是译文（`### 10. 例：按相对定额
        捕获`），而结构契约的 section `name` 是原书语言（`1.10 Example: Harvesting…`），
        用原书标题子串去匹配译文标题在结构上必然落空——Arnold ODE（EN→CN）实测全书 5 章
        仅译文组假报 81 个 section「不在位」。译本版块完整性已由 ``check_translate_parity``
        （#1 单元 id/type/key/name/file 1:1、#4 节号一致）机械保证，故译文组跳过 section 名
        核对不构成放宽。**编号项**（定义 / 定理 / …）两语都核对：其数字条题在两版渲染一致。

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
            # 🔴 `uncat` 同豁免（Arnold《经典力学的数学方法》附录K 系91 实测
            # 2026-09-29）：它是 `TYPE_TO_LABEL.get(type, 'uncat')` 的**兜底族**——
            # 配置分组表没认领的号（图/表题号、OCR 把「坐标 系91，…」里的“系”+
            # 误读数字当成条目头）都落在这里。写作规则要求这类号**只在散文里引用**、
            # 不做 `**…**` 条头，故 B/M 层一直按 `label != 'uncat'` 把它们排除在
            # 「须成条目」之外（`item_numbering_integrity` 的 `extracted_raw`）。本闸
            # 此前不认这一豁免，于是要求 md 给一个书里根本不存在的条头——**闸逼代理
            # 编造条目**。判据与 B/M 层同源：内容在位由覆盖闸⑩（契约manifest）与
            # 内容完整性闸门保证，本处只免「条头必须出现」这一项。
            if t in ("chapter",) or t in physical_evidence._GATE_DERIVED_TYPES \
                    or t in ("exercise", "problem", "uncat"):
                continue
            # 译本 md：跳过 section 名核对（原书语言标题匹配不到译文标题，见 docstring）。
            if t == "section" and not check_sections:
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
                # 🔴 译本节标题在位判据（merge_translation 证据，Evans SDE 2026-09-28 实测）。
                #    source 版 section 的 name 常把「字母/编号 enumerator + 标题」黏在一起
                #    （`A. MOTIVATION`），中文节头却把原文标题放进括注、并被译文与 enumerator
                #    隔开（`## § A. 动机 (MOTIVATION)`）。于是整名归一串 `amotivation` 在译文里
                #    不连续 → 假报「契约骨架节在 md 不在位」。这类书的 section 键又常是非印刷
                #    占位符（U1/U2…，见无编号小节抽取器），键候选同样落空，两道回退同时失效。
                #    补一条「剥去前导 enumerator 后的纯标题」候选即可命中括注内的原文标题；
                #    真正漏写时该标题整词仍不在位，照常报缺（已做负向对照：删去 (MOTIVATION)
                #    后 U1 复现缺失）。仅对 `section` 节点生效，不改编号项（定义/定理…）判据。
                if t == "section":
                    _sm = re.match(r'^[§＃#\s]*[A-Za-z]{1,4}[.\-－．、]\s+(.*)$', name.strip())
                    if _sm:
                        _nsm = physical_evidence._norm_text(_sm.group(1))
                        if len(_nsm) >= 4 and _nsm not in cands:
                            cands.append(_nsm)
                    # 🔴 「父号+子号」点分小节标题的**局部号渲染**形态（Arnold ODE
                    #   2026-09-28 实测，全书 5 章 84 个 section 节点全被误报「不在位」）。
                    #   契约 section 的 name 写成「全局节号 + 标题」（`1.10 Example:
                    #   Harvesting…`），而原书小节标题按**本节内局部号**印刷（`### 10.
                    #   Example: Harvesting…`）——于是整名归一串 `110example…` 在 md 里
                    #   永远不连续（前导父号 `1.` 在渲染时被剥成局部号 `10.`），
                    #   merge_source 证据门假报「骨架节不在位」。补一条「剥去前导父号
                    #   `P.` 后保留 `S <标题>`」的候选即可命中局部渲染；**局部号单独不作
                    #   候选**（裸数字 `10` 到处乱撞会误命中），必须带完整标题，故真正
                    #   漏写的小节其 `S+标题` 整串仍不在位，照常报缺。仅对 `section` 生效。
                    _pm = re.match(r'^\d+\.(\d+[^\d].*)$', name.strip())
                    if _pm:
                        _npx = physical_evidence._norm_text(_pm.group(1))
                        if len(_npx) >= 6 and _npx not in cands:
                            cands.append(_npx)
            cands = [c for c in cands if c]
            # 🔴 「定位符键」回退（hum 型抽取器，Robinson/Humphreys 式书）：契约键写成
            #   `Corollary §3.3` = 「第 3.3 节里的推论」，**印面条头只有裸标签词、不带任何
            #   编号**（同书 ch1 实测：Corollary §3.3 / Lemma §3.3 已如实写出，整键归一
            #   串 `corollary33` 却永远不在 md 里 → merge_source 证据被假拒）。
            #   故键含 `§` 定位符时，追加「裸标签词」候选（条头 `**Corollary**` 归一后
            #   即标签词，中英两版互译同口径）。真漏写仍由 gate_units ⑩（契约↔manifest
            #   双向覆盖，逐单元机械核对）与 verify B 层拦截，本处只作在位抽查。
            if "§" in key:
                lm = re.match(r"^([A-Za-z一-鿿]+)", key.strip())
                if lm:
                    lw = physical_evidence._norm_text(lm.group(1))
                    if lw:
                        cands.append(lw)
                        if re.match(r"^[a-z]+$", lw):
                            zh = physical_evidence._LABEL_EN2ZH.get(lw)
                            if zh:
                                cands.append(physical_evidence._norm_text(zh))
                        else:
                            for _zh, _ens in physical_evidence._LABEL_ZH2EN.items():
                                if physical_evidence._norm_text(_zh) == lw:
                                    cands.extend(_ens)
                                    break
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
    def _units_gate_ok(units_dir, manifest, ch_key=None, translation=False):
        """单元门控核心判定（内联，避免 import 耦合）：每单元文件存在、首行
        DONE、**质量校验通过**（写对，非仅重写）。返回 (ok, problems)。

        🔴 `translation=True`（译单元目录）必须与 `gate_units.gate_chapter` 的
        `translation=(units_sub != "units")` 同源（Iwaniec–Kowalski 解析数论
        translate_chapters 落账被拒实测 2026-09-29）：Tier-3 证明分条闸只管自撰
        文本，译单元逐行镜像已过该闸的冻结源单元；本 shadow 曾漏传 → 权威 CLI
        `gate_units --units-dir units-translate` 全 27 章 exit 0，落账证据趟却按
        源侧判据罚译单元的散文式证明，两趟判据分叉。

        🔴 **fail-closed**：质量校验执行失败（import / 运行异常）按「未达标」
        处理并记入 problems——绝不能因校验崩溃而放行（否则未审阅单元会整体
        免检通过、被 mark 落账后流入拼接）。真实 KaTeX 渲染不在此重复：
        ``gate_units.gate_chapter``（merge 前最后一道）按章批量真渲染。
        """
        problems = []
        # known_book 白名单（与 gate_units._load_known_book 同语义）：登记「书源
        # 确有、契约抽取器漏挂」的编号，豁免「编造编号」误判。从 units_dir 逐级
        # 上溯找 verify_config.json（内联采集，避免 import 耦合，同上）。
        known = set()
        _d = os.path.abspath(units_dir)
        for _ in range(6):
            _vp = os.path.join(_d, "verify_config.json")
            if os.path.exists(_vp):
                try:
                    with open(_vp, encoding="utf-8") as vf:
                        _cfg = json.load(vf)

                    def _harvest(formula):
                        if isinstance(formula, dict):
                            for x in (formula.get("known_book") or []):
                                known.add(str(x).strip())

                    def _harvest_node(node):
                        """节点自身是 formula map，或是含 ``formula`` 子 map 的配置组。"""
                        if not isinstance(node, dict):
                            return
                        _harvest(node.get("formula"))
                        if "known_book" in node:
                            _harvest(node)

                    # 扁平形状：顶层 ``formula``
                    _harvest(_cfg.get("formula"))
                    # 外层 map 形状（当前 SSOT）：ch/appendix/supplement 组
                    for _grp in (_cfg.get("ch"), _cfg.get("appendix"),
                                 _cfg.get("supplement")):
                        _harvest_node(_grp)
                    # 历史 ``data`` 包装形状（若有）：data[section]["formula"]
                    _data = _cfg.get("data")
                    if isinstance(_data, dict):
                        for _node in _data.values():
                            _harvest_node(_node)
                    # 兜底：遍历所有顶层 dict 值（对未知分组名稳健，与
                    # gate_units._load_known_book 同语义）
                    for _v in _cfg.values():
                        if isinstance(_v, dict):
                            _harvest_node(_v)
                except Exception:
                    known = set()
                break
            _d = os.path.dirname(_d)
        # 章契约路径（tag 真值回退 / src_text 忠实豁免共用）：units_dir =
        # <ex>/book_structure/units/<label>，ex 上溯三级；🔴 必须经
        # chapter_json_path(ex, ch_key)——曾按 label 拼接出
        # "units/book_structure/appendixch6.json" 式假路径，契约恒缺位 →
        # src_text=None，gate-15 对书源原句「omitted here」假阳。
        cpath = None
        _ext = os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(units_dir))))
        if ch_key is not None:
            try:
                from data.book_structure.book_structure import chapter_json_path
                cpath = chapter_json_path(_ext, ch_key)
            except Exception:
                cpath = None
        # 🔴 `\tag` 对账与权威门控 gate_units 同开同关：Q 公式层是 opt-in，本书
        # 未声明 `formula` 块时（如 Vakil，make_config 判定不追踪编号公式、build_structure
        # 在 ncomp=None 下把 diagram/交叉引用裸数字过度挂成 tag），单元级必须**跳过**
        # 「缺/编造编号公式」对账——否则本 shadow 会把那些并非以 `\tag` 呈现的编号
        # 当成硬真值，误判「漏写编号公式」而阻断落账（gate_units.py 第 549-550 行有
        # 同一判据，本内联版曾遗漏 → 29 章假失败）。真值源单一化：直接复用 gate_units
        # 的判定函数，导入不可用时退回「读 verify_config.json 是否含 formula 块」的兜底。
        try:
            from gate_units import _formula_layer_enabled
            _formula_on = bool(_formula_layer_enabled(_ext))
        except Exception:
            # 兜底：直接读 verify_config.json 是否含 formula 块（gate_units 导入不可用时）。
            _formula_on = False
            try:
                with open(os.path.join(_ext, "verify_config.json"),
                          encoding="utf-8") as _vf:
                    _vc = json.load(_vf)

                def _has_formula_map(nd):
                    if not isinstance(nd, dict):
                        return False
                    if any(k in nd for k in ("known_book", "ignore", "letter_ch",
                                             "bare_number", "enabled")):
                        return True
                    # 仅 ``type`` 且无 ``scope`` 才算 formula map（``scope`` = 分组配置，
                    # 非公式层；与 gate_units._is_formula_map 的兜底一致）。
                    return "type" in nd and "scope" not in nd
                _nodes = [_vc, _vc.get("ch"), _vc.get("appendix"),
                          _vc.get("supplement")]
                if isinstance(_vc.get("data"), dict):
                    _nodes.extend(_vc["data"].values())
                for _nd in _nodes:
                    if isinstance(_nd, dict) and (
                            _has_formula_map(_nd.get("formula"))
                            or _has_formula_map(_nd)):
                        _formula_on = True
                        break
            except Exception:
                _formula_on = False
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
            # item / desc / exercise 必须「写对」——单元级质量校验通过（判断
            # 标准是"写对"而非"重写"，非内容指纹比对）；章节标题只确认 DONE
            if u["type"] in ("item", "desc", "exercise"):
                body = raw[m.end():].lstrip("\r\n").rstrip("\n")
                try:
                    import check_unit_quality as _quality
                    # 单元级 tag 对账：真值优先取 **manifest.tags**（拆分时按契约
                    # 节点自身写入），回退章契约 chapter_tag_map 的 key 映射。
                    # 🔴 不可只按 key 聚合：同节内定义/定理/推论各自编号、共用 key，
                    # 聚合会让「定义」单元被要求写出「定理」单元的编号公式。
                    expected = u.get("tags") if isinstance(u.get("tags"), list) else None
                    if expected is None and cpath and os.path.exists(cpath):
                        try:
                            from data.book_structure.book_structure import (
                                chapter_tag_map)
                            with open(cpath, encoding="utf-8") as cf:
                                expected = chapter_tag_map(json.load(cf)).get(
                                    str(u["key"]))
                        except Exception:
                            expected = None  # 契约不可得 = 跳过 tag 对账（其余检查照常）
                    # 🔴 与 gate_units 同开关：未声明公式层 → 不做 `\tag` 对账。
                    if not _formula_on:
                        expected = None
                    # 图片 / 内容块真值随 manifest 透传（与 gate_units 同一套对账；
                    # 老 manifest 缺字段 = None 跳过，缺图由 gate_units 章级闸兜底）
                    exp_imgs = u.get("images")
                    if not isinstance(exp_imgs, list):
                        exp_imgs = None
                    exp_content = u.get("content")
                    if not isinstance(exp_content, int):
                        exp_content = None
                    # 假省略闸「忠实引用豁免」源文（契约 key→内容块拼接原文；
                    # 契约不可得 = None，不豁免，fail-closed 与 gate_units 同语义）
                    src_text = None
                    try:
                        if cpath and os.path.exists(cpath):
                            with open(cpath, encoding="utf-8") as cf:
                                src_text = _quality.unit_source_map(
                                    json.load(cf)).get(str(u["key"]))
                    except Exception:
                        src_text = None
                    ok_q, qp = _quality.check_body(
                        u["type"], u.get("name") or "", body,
                        expected_tags=expected, allow_extra=known,
                        expected_images=exp_imgs, content_blocks=exp_content,
                        source_text=src_text, key=str(u["key"]),
                        translation=translation,
                        # 🔴 与 gate_units 同一份配对读取：译文的两条结构继承豁免
                        # （顶层标签族 / 分隔线指纹）都要源单元正文。此前本趟不传 →
                        # 权威 CLI 全绿而落账被拒（Apostol ch2/0077 实测 2026-09-29）。
                        src_body=(_quality.paired_source_body(
                            units_dir, u["file"]) if translation else None))
                except Exception as e:
                    # 🔴 fail-closed：校验崩溃 = 该单元不合格，绝不放行
                    ok_q, qp = False, ["质量校验执行失败（fail-closed）：%r" % (e,)]
                if not ok_q:
                    problems.append("单元 %s（%s %s）质量未达标：%s" % (
                        u["file"], u["type"], u["key"], "；".join(qp[:4])))
        return (len(problems) == 0, problems)

    @staticmethod
    def write_chapters_ok(book_dir, extract_dir):
        """写章节证据 = 每章单元门控通过（每个 item 都改好、一个不漏）。

        🔴 死命令：不逐单元改好 = 落账被硬拒。写作底稿 = 「每 item 一单元」
        目录 units/ch{N}/（split_draft_units 拆出）。agent 必须**逐个把单元按
        writing-rules 改好**（首行 DRAFT→DONE + 质量校验通过），由 gate_units.py
        强制门控。
        🔴 拼接与合并 md 的契约名在位核对移至 merge_source 步（源版，翻译之前）
        与 merge_translation 步（源 + 译两版，末步）——本步证据不要求最终 md 存在。
        确保前置：draft 步未跑（缺 units/manifest.json）→ 硬拒，防 bootstrap 误回填。
        """
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        keys = _chapter_map_keys(ex)
        if not keys:
            return False, "缺 chapter_map.json（config 步未完成）"
        gate_fail, no_units, empty_units = [], [], []
        for k in keys:
            units_dir = os.path.join(ex, "book_structure", "units", unit_dir_name(k))
            mpath = os.path.join(units_dir, "manifest.json")
            if not os.path.exists(mpath):
                no_units.append(k)
                continue
            try:
                manifest = json.load(open(mpath, encoding="utf-8"))
            except Exception:
                gate_fail.append((k, "manifest 非法 JSON"))
                continue
            ok_g, gprob = physical_evidence._units_gate_ok(units_dir, manifest, ch_key=k)
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
                           f"DONE + 质量校验通过后重跑 gate_units）: {chapter_label(k)} {prob}")
        note = f"；{len(empty_units)} 章单元清单为空: {empty_units[:4]}" if empty_units else ""
        return True, f"{len(keys)} 章单元门控全部通过（每 item 改好，一个不漏）{note}"

    # ---- 翻译单元证据（清单 + 门控 + 同构闸） ----

    @staticmethod
    def _src_manifest(ex, key):
        """读源单元 manifest；不存在返回 None。"""
        p = os.path.join(ex, "book_structure", "units", unit_dir_name(key), "manifest.json")
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
        ② 🔴 源单元全部修正完成（源门控通过——源先于译，源没修好译文必作废）
        ＋翻译单元门控通过（同一套单元质量校验）；
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
            # 🔴 源先于译：源单元未全部修正完成（源门控未通过）→ 翻译证据不成立。
            # 与 gate_units 翻译前置硬闸同判据（此处为轻量 _units_gate_ok 口径）。
            src_dir = os.path.join(ex, "book_structure", "units", unit_dir_name(k))
            try:
                src_manifest = json.load(open(os.path.join(src_dir, "manifest.json"),
                                             encoding="utf-8"))
            except Exception:
                gate_fail.append((k, "源 units/manifest.json 缺失或非法——翻译禁止开始"))
                continue
            ok_src, src_prob = physical_evidence._units_gate_ok(src_dir, src_manifest, ch_key=k)
            if not ok_src:
                gate_fail.append((k, "源单元未全部修正完成（源门控未通过）——先修好源单元"
                                     "再翻译/重派生: " + (src_prob[0] if src_prob else "")))
                continue
            tdir = os.path.join(ex, "book_structure", "units-translate", unit_dir_name(k))
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
            ok_g, gprob = physical_evidence._units_gate_ok(tdir, tmanifest,
                                                           ch_key=k,
                                                           translation=True)
            if not ok_g:
                gate_fail.append((k, gprob[0] if gprob else "翻译单元门控未通过"))
                continue
            # 1:1 同构闸（子进程解耦，复用与 CLI 同一脚本）
            script = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
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
                           f"（gate_units --units-dir units-translate）: {chapter_label(k)} {prob}")
        if parity_fail:
            k, prob = parity_fail[0]
            return False, f"{len(parity_fail)} 章 1:1 同构闸未通过: {chapter_label(k)} {prob}"
        return True, (f"{len(todo)} 章翻译清单就绪 + 门控 + 同构闸全部通过"
                      f"（tag/图片/编号项与源单元 1:1）")

    @staticmethod
    def _md_group_lang(book_dir, key, lang):
        """按语种取该章最终 md 组：cn → 第N章_*/附录X_*；en → ChapterN_*/AppendixX_*。"""
        _ord = chapter_ordinal(key)
        if is_numbered_chapter(key) and _ord:
            pats = ([f"第{_ord}章_*.md"] if lang == "cn" else [f"Chapter{_ord}_*.md"])
        elif _ord:
            pats = ([f"附录{_ord}_*.md"] if lang == "cn" else [f"Appendix{_ord}_*.md"])
        else:
            pats = (["附录.md", "附录_*.md"] if lang == "cn"
                    else ["Appendix.md", "Appendix_*.md"])
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
    def _oversized_merged_md(md_files):
        """🔴 规则3 机械闸：合并形态（无节号）章 md 字符 > MERGED_MD_CHAR_LIMIT
        而未按节拆分 → 返回 [(文件名, 字符数)]。已拆分（节文件形态）不查——
        规则只拆到「节」一级，单个节文件超阈是允许形态。
        🔴 本判据**逐语独立**，看不见「一语已拆 / 另一语仍合并」的跨语不对称，
        那道盲区由 ``_split_form_pairing_problems`` 兜。"""
        over = []
        for f in md_files:
            if physical_evidence._sec_num(f) is not None:
                continue
            try:
                with open(f, encoding="utf-8-sig") as fh:
                    n = len(fh.read())
            except OSError:
                continue
            if n > MERGED_MD_CHAR_LIMIT:
                over.append((os.path.basename(f), n))
        return over

    @staticmethod
    def _split_form_pairing_problems(book_dir, key, langs):
        """🔴 规则3 跨语配对机械闸：一章源 / 译两组最终 md **形态须配对**。

        任一语言已按节拆分（节文件形态）则其余语言不得留合并件；两边都拆时节号
        集合须一致。既有 ``_oversized_merged_md`` 逐语独立判「本语合并件超阈未拆」，
        **看不见跨语不对称**：``tools/split_chapters.py`` 的配对逻辑只写在 CLI
        （``main()`` 的 ``pair`` 分支），一旦绕过 CLI 手工只拆一语，另一语的整章
        合并件就一路绿灯交付（2026-09-28 Strogatz 实测：EN 六章已拆成 8/9/7/8/7/8
        个节文件，CN 同名六章仍是单文件 33k–47k 字符，读者两版对不上）。
        单语书（``langs`` 只一项）无配对可言 → 恒放行。→ 人类可读问题列表。
        """
        if len(langs) < 2:
            return []
        forms = {}
        for lang in langs:
            files = physical_evidence._md_group_lang(book_dir, key, lang)
            if not files:
                continue                        # 缺组由 missing 分支判，不在本闸重复报
            secs = sorted({s for s in (physical_evidence._sec_num(f) for f in files) if s})
            forms[lang] = secs
        split = [l for l, s in forms.items() if s]
        merged = [l for l, s in forms.items() if not s]
        out = []
        if split and merged:
            ref = split[0]
            mfile = os.path.basename(physical_evidence._md_group_lang(
                book_dir, key, merged[0])[0])
            out.append("[%s] 语言 %s 仍是合并件 %s，而 %s 版已按节拆成 %d 个节文件"
                       "（规则3 要求中英文**配对拆分**，跑 "
                       "python tools/split_chapters.py \"%s\" 由其 pair 分支补拆）"
                       % (chapter_label(key), "、".join(merged), mfile,
                          "、".join(split), len(forms[ref]), book_dir))
        sets = {l: tuple(s) for l, s in forms.items() if s}
        if len(set(sets.values())) > 1:
            out.append("[%s] 各语言均按节拆分但节号集合不一致：%s（须以同一节界重拆）"
                       % (chapter_label(key),
                          "；".join("%s=%s" % (l, list(s)) for l, s in sets.items())))
        return out

    @staticmethod
    def _contract_names_missing(ex, k, md_files, check_sections=True):
        """结构契约骨架节 + 编号项在 md 组中的在位核对；返回缺失名列表。
        ``check_sections``：见 ``_missing_contract_names``——译文组须传 False。"""
        contract_path = os.path.join(
            ex, "book_structure", chapter_label(k) + ".json")
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
        ignore_path = os.path.join(ex, f"ignore_{chapter_label(k)}.json")
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
            contract, physical_evidence._norm_text(text), ignore_set,
            check_sections=check_sections)

    @staticmethod
    def _merge_present_ok(book_dir, ex, keys, want_tgt):
        """拼接「产物在位」机械核对（merge_source / merge_translation 共用）：
        每章**源语言**组必须存在；``want_tgt=True`` 时该书若有翻译版则**翻译语言**组
        也须存在。各组核对 oversized（规则3）+ 契约骨架节 / 编号项在位。
        返回 (bool, detail)。"""
        missing, missing_names, degraded, oversized, unpaired = [], [], [], [], []
        for k in keys:
            src = physical_evidence._src_manifest(ex, k)
            if src is None:
                degraded.append(k)
                continue
            src_lang = (src.get("language") or "cn").lower()
            tgt_lang = physical_evidence._tgt_language(src_lang)
            groups = [(src_lang, physical_evidence._md_group_lang(book_dir, k, src_lang))]
            if want_tgt and tgt_lang:
                groups.append((tgt_lang, physical_evidence._md_group_lang(book_dir, k, tgt_lang)))
            for lang, md_files in groups:
                if not md_files:
                    missing.append((k, lang))
                    continue
                ov = physical_evidence._oversized_merged_md(md_files)
                if ov:
                    oversized.append((k, lang, ov))
                miss = physical_evidence._contract_names_missing(
                    ex, k, md_files, check_sections=(lang == src_lang))
                if miss:
                    missing_names.append((k, lang, miss))
            unpaired.extend(physical_evidence._split_form_pairing_problems(
                book_dir, k, [lang for lang, _ in groups]))
        if missing:
            (k, lang) = missing[0]
            return False, (f"{len(missing)} 组最终 md 缺失（先跑 merge_units 拼接）: "
                           f"{chapter_label(k)} [{lang}]" + (f" 等 {len(missing)} 组" if len(missing) > 1 else ""))
        if oversized:
            k, lang, ov = oversized[0]
            return False, (f"{len(oversized)} 章/版为合并形态且超 {MERGED_MD_CHAR_LIMIT} 字符"
                           f"未拆（write-source 规则3）: {chapter_label(k)} [{lang}] "
                           f"{ov[0][0]} = {ov[0][1]} 字符；"
                           f"跑 python tools/split_chapters.py \"{book_dir}\" "
                           f"按节拆分（默认删合并文件）后复核")
        if unpaired:
            return False, (f"{len(unpaired)} 处各语言最终 md 形态不配对"
                           f"（write-source 规则3「中英文配对拆分」）: "
                           + "；".join(unpaired[:3]))
        if missing_names:
            k, lang, miss = missing_names[0]
            return False, (f"{len(missing_names)} 组 md 相对结构契约漏骨架节/编号项: "
                           f"{chapter_label(k)} [{lang}] 缺 {len(miss)} 项（如 {miss[:4]}）；"
                           f"须回归对应单元目录（units / units-translate）补齐后重拼"
                           f"（若条目为 OCR 噪声误收，走 manage_ignore 机制，勿编造）")
        return True, (f"{len(keys)} 章拼接产物在位"
                      + (f"（{len(degraded)} 章缺源 manifest 跳过核对: {degraded[:4]}）"
                         if degraded else ""))

    @staticmethod
    def _source_langs(ex, keys):
        """收集各章源 manifest 的 language（源版校验 --only-lang 依据）。"""
        langs = set()
        for k in keys:
            src = physical_evidence._src_manifest(ex, k)
            if src:
                langs.add((src.get("language") or "cn").lower())
        return langs

    @staticmethod
    def merge_source_ok(book_dir, extract_dir):
        """文档步骤 6 证据（**翻译之前**先把源版校验收口）：
        ① 源语言章 md 已拼、契约骨架节 / 编号项在位（不含翻译版——翻译尚未开始）；
        ② 源版 verify 通过（``--only-lang 源语言``）——源书层面的图 / 编号 / 公式问题
        在此暴露，须回填修**源单元**后才放行翻译。"""
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        keys = _chapter_map_keys(ex)
        if not keys:
            return False, "缺 chapter_map.json（config 步未完成）"
        ok, detail = physical_evidence._merge_present_ok(book_dir, ex, keys, want_tgt=False)
        if not ok:
            return False, detail
        langs = physical_evidence._source_langs(ex, keys)
        only = langs.pop() if len(langs) == 1 else None
        rc, err = physical_evidence._run_verify_all(ex, book_dir, only_lang=only)
        if rc == 0:
            return True, (f"{detail}；源版 verify --all"
                          + (f" --only-lang {only}" if only else "") + " exit 0")
        if rc is None:
            return False, f"源版 verify 执行异常: {err}"
        return False, (f"源版 verify 未通过（exit {rc}）——🔴 翻译前须先把源书层面的图 /"
                       f" 编号 / 公式问题修好（缺号经 backfill_ordinals 回填归属源单元），"
                       f"--fix 默认禁用须 --fix --fix-force + PREFLIGHT，复验至 exit 0。")

    @staticmethod
    def merge_translation_ok(book_dir, extract_dir):
        """文档步骤 8（末步）证据：
        ① 源语言 + 翻译语言两组章 md 均已拼、契约项在位；
        ② 全量 verify --all（源 + 译两版）exit 0（verify PASS + KaTeX OK）。
        中文源书只有一组中文 md，语义一致。"""
        ex = physical_evidence._extract_dir(book_dir, extract_dir)
        keys = _chapter_map_keys(ex)
        if not keys:
            return False, "缺 chapter_map.json（config 步未完成）"
        ok, detail = physical_evidence._merge_present_ok(book_dir, ex, keys, want_tgt=True)
        if not ok:
            return False, detail
        rc, err = physical_evidence._run_verify_all(ex, book_dir)
        if rc == 0:
            return True, (f"{detail}；全量 verify_chapter.py --all exit 0"
                          f"（源语言 + 翻译语言全部 verify PASS + KaTeX OK）")
        if rc is None:
            return False, f"verify 执行异常: {err}"
        return False, (f"全量 verify 未通过（exit {rc}）。禁止 mark，须修复"
                       f"（🔴 --fix 默认禁用，须 --fix --fix-force + PREFLIGHT）"
                       f"或手工定点修改后复验至 exit 0。")

    @staticmethod
    def embed_figures_ok(book_dir, extract_dir):
        # 宽松判定：存在 figure 目录（书根，与 md 同级）或任一 md 含图片引用
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
    def _run_verify_all(ex, book_dir, only_lang=None):
        """真实复验：跑 verify_chapter.py --all。

        ``only_lang``（'cn' / 'en'）：只校验该语种版本的 md（供 merge_source 步在
        翻译前只校验源版）；为 None 时源 + 译两组都覆盖。
        list-form + sys.executable：不依赖 PATH 里的 `python`（conda 环境外
        可能缺依赖），也不经 shell 规避含空格路径的引号问题。
        返回 (rc, errmsg)；rc=None 表示执行异常。
        """
        # 本文件位于 <root>/flows/_flow_contract.py —— 向上一级即技能根。
        root = os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        script = os.path.join(root, "verify", "script", "verify_chapter.py")
        args = [sys.executable, script, "--all", ex, book_dir]
        if only_lang:
            args += ["--only-lang", str(only_lang)]
        try:
            rc = subprocess.call(args)
            return rc, None
        except Exception as e:
            return None, str(e)


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
    "write_source.merge_source": physical_evidence.merge_source_ok,
    "write_source.translate_chapters": physical_evidence.translate_chapters_ok,
    "write_source.merge_translation": physical_evidence.merge_translation_ok,
}


def check_evidence(flow, step, book_dir, extract_dir):
    """返回 (ok, detail)。无证据函数的步返回 (True, 'agent 自证')。"""
    fn = EVIDENCE.get(f"{flow}.{step}")
    if fn is None:
        return True, "agent 自证（环境/手填步骤）"
    return fn(book_dir, extract_dir)
