"""recognize_sections.py — 「agent 校验识别」步骤：确认书是否真实无序号标，并产出小节清单。

背景（scan_skeleton 的 depth 判节缺陷）
--------------------------------------
scan_skeleton 当前用「≥2 段数字」判定是不是节（_section_header_info 的
`len(comps) < 2` 门槛 + build_structure 的 `depths_set = {d >= 2}`）。这对
**无序号标书**（verify_config.json 的 `section_types` 含 `0`，如 Silverman
《A Friendly Introduction to Number Theory》）完全失明：小节在 OCR 里是
`## § <标题>` 形式的无数字标题，扫描不出任何 SEC 行，进而 build_structure
拼不出 sub_sec，缺节闸门沦为空检。

更糟的是：用 OCR 正则「猜」无数字标题会**编造假小节**——Silverman Ch1 实测
会误把 `Fibonacci` / `Wiles` / `Triangular numbers` / `Square numbers`（列表项
碎片、正文人名、图注标签）当成小节，直接撞「保真 / 禁止伪造」红线。OCR 文本块
只有 `poly/text/score`，无字体/加粗信号，标题有时独立成块、有时与正文粘连，
纯正则不可靠。

正确做法（本步骤）
------------------
无序号标书的小节清单，必须由 **agent / LLM 读原书（OCR 文本）** 凭借语义理解
来识别——它看得懂「哪些是真·小节标题、哪些是列表项/图注/正文」，正则做不到。
本步骤负责**汇总每章 OCR 文本**供 agent 校验识别，并约定产物格式：

    <extract_dir>/_recognized_sections.json
        { "<ch>": ["小节标题1", "小节标题2", ...], ... }

build_structure 在 `sections_unnumbered=True` 时直接消费该清单注入 sub_sec
（见 build_structure._recognized_sections），不再走 scan_skeleton 的深度检测。

用法
----
    python recognize_sections.py <extract_dir> [ch ...]
        # 汇总指定章（缺省全书）的 OCR 文本到 _extract/_recognize_work/<ch>.txt，
        # 并打印 agent 校订提示；由 agent/人工阅读后写出 _recognized_sections.json。

    python recognize_sections.py <extract_dir> --apply-llm [ch ...]
        # 若配置了 LLM 后端（见 _call_llm），自动识别并直接写
        # _recognized_sections.json；否则回退到导出模式并警告。

产物约定（agent 校订后手写）
----------------------------
    {
      "1": ["Some Typical Number Theoretic Questions", "Sums of Squares I",
            "Sums of Higher Powers", "Infinitude of Primes", "Sums of Squares II",
            "Number Shapes", "Twin Primes", "Primes of the Form N^2 + 1",
            "The Scientific Method in Number Theory", "Exercises"],
      "2": ["..."],
      ...
    }
  · 标题按原书文档顺序；**仅收录真·小节**（排除列表项、图注标签、正文碎片）。
  · 原书确为无序号标才写此文件；若 agent 复核发现原书其实带序标，应改回
    section_types 为带序标角色码（如 [1,2]）并走 scan_skeleton 常规路径，
    而非用本文件「补」编号。
  · 章节（chapter）层级由文件名 / chapter_map 承载，本清单只列「章内小节」。
"""
import glob
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
import chapter_map
from verify_config import ConfigLoader, ConfigError

sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
# LLM 后端（可选）：默认未配置即走「导出 + agent 校订」模式。
# 接入方式：设置环境变量 RECOGNIZE_LLM_ENDPOINT / RECOGNIZE_LLM_KEY，并实现
# _call_llm 的解析（返回 list[str] 小节标题）。无端点时 _call_llm 返回 None，
# 主流程回退到导出模式。
# ---------------------------------------------------------------------------
def _call_llm(prompt):
    """调用可选 LLM 后端识别小节标题；未配置返回 None。"""
    endpoint = os.environ.get("RECOGNIZE_LLM_ENDPOINT")
    key = os.environ.get("RECOGNIZE_LLM_KEY")
    if not endpoint or not key:
        return None
    # 接入具体 LLM 客户端（openai / 自建网关）在此实现；当前留作可插拔钩子。
    raise NotImplementedError(
        "RECOGNIZE_LLM 已配置端点但未实现调用；请在此接入客户端，"
        "或从环境变量移除以走 agent 校订模式。")


def _chapter_ocr_blocks(ext, start, end):
    """汇总章节区间 [start, end] 内所有 page_*.json 的 text 块（带页码）。"""
    blocks = []
    for p in range(start, end + 1):
        fp = os.path.join(ext, "page_%03d.json" % p)
        if not os.path.exists(fp):
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for b in d.get("text", []):
            if not isinstance(b, dict):
                continue
            t = (b.get("text") or "").strip()
            if t:
                blocks.append((p, t))
    return blocks


# 初筛：疑似标题行（短、Title-Case 起始）。仅用于「降低 agent 阅读噪声」，
# 不作最终判定——agent 仍通读全文上下文以排除列表项/图注/正文。
_CANDIDATE_RE = re.compile(r'^[A-Z][A-Za-z0-9 ,’\'()\-]{2,70}$')


def _is_candidate(line):
    # 整块过短（粘连正文前缀）或独立短短语都可能是标题；这里只标「疑似」，
    # 截断首个 ". " 后的标题部分用于显示。
    head = line.split(". ")[0].strip()
    return bool(_CANDIDATE_RE.match(head)) and len(head.split()) <= 8


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    ext = args[0]
    want = [int(x) for x in args[1:]]

    cfg_path = os.path.join(ext, "verify_config.json")
    try:
        loader = ConfigLoader(ext, os.path.dirname(ext.rstrip("/")) or ext)
        loader.require_complete()
        book = loader.book
    except (ConfigError, ValueError) as e:
        print("[recognize_sections] 读 verify_config 失败：%s" % e)
        return 2

    if not getattr(book, "sections_unnumbered", False):
        print("[recognize_sections] 本书 section_types 不含 0（非无序号标书），"
              "无需本步骤；请走 scan_skeleton 常规路径。")
        return 0

    cm = chapter_map.load_chapter_map_raw(os.path.join(ext, "chapter_map.json"))
    if isinstance(cm, dict) and "chapters" in cm:
        chs = cm["chapters"]
    elif isinstance(cm, dict):
        chs = [{"ch": int(k), "start": c["start"], "end": c["end"],
                "name": c.get("name", c.get("title", ""))}
               for k, c in cm.items()
               if isinstance(c, dict) and "start" in c and "end" in c]
    else:
        chs = cm

    rng = {}
    names = {}
    for c in chs:
        n = int(c.get("num", c.get("ch", c.get("chapter", c.get("n")))))
        rng[n] = (int(c["start"]), int(c["end"]))
        names[n] = c.get("name", c.get("title", ""))

    work = os.path.join(ext, "_recognize_work")
    os.makedirs(work, exist_ok=True)

    use_llm = "--apply-llm" in flags
    out_all = {}
    for ch in (want or sorted(rng)):
        if ch not in rng:
            print("ch%-3d SKIP (not in chapter_map)" % ch)
            continue
        start, end = rng[ch]
        blocks = _chapter_ocr_blocks(ext, start, end)
        # 写每章 OCR 工作文件（agent 阅读源）
        wf = os.path.join(work, "ch%02d.txt" % ch)
        with open(wf, "w", encoding="utf-8") as fh:
            fh.write("# Chapter %d — %s (pages %d-%d)\n" % (ch, names.get(ch, ""), start, end))
            fh.write("# 请识别其中【真·小节标题】（排除列表项/图注标签/正文碎片），"
                     "按文档顺序列出。\n\n")
            for p, t in blocks:
                mark = "  ?" if _is_candidate(t) else ""
                fh.write("p%-4d| %s%s\n" % (p, t, mark))
        if use_llm:
            titles = _call_llm(_build_prompt(blocks, names.get(ch, "")))
            if titles is None:
                print("ch%-3d LLM 未配置，回退导出模式" % ch)
                use_llm = False
                continue
            out_all[str(ch)] = titles
            print("ch%-3d | LLM 识别 %d 个小节" % (ch, len(titles)))
        else:
            print("ch%-3d | OCR 已导出 -> %s" % (ch, os.path.basename(wf)))

    if use_llm and out_all:
        out_path = os.path.join(ext, "_recognized_sections.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(out_all, fh, ensure_ascii=False, indent=1)
        print("\n[recognize_sections] 已写 %s（%d 章）" % (out_path, len(out_all)))
    else:
        print("\n[recognize_sections] 导出完成。请 agent/人工阅读 _recognize_work/*.txt，"
              "校订后写出 _recognized_sections.json：")
        print('  { "<ch>": ["小节标题1", "小节标题2", ...], ... }')
    return 0


def _build_prompt(blocks, ch_name):
    lines = ["以下是某章（%s）的 OCR 文本（带页码）。请识别其中真正的【小节标题】" % ch_name,
             "（排除列表项碎片、图注标签、正文句子），按文档顺序返回 JSON 数组。", ""]
    for p, t in blocks:
        lines.append("p%d: %s" % (p, t))
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
