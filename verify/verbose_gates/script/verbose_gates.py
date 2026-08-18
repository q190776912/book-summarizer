import os
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

from data.book_structure.book_structure import BookStructure

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/verbose_gates/verbose_gates.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""verbose_gates.py — P-LAYER (order 16): anti-regression gate for content/structure defects.

新增于 2026-08-02 整改后，作为「验收闸门」兜底：即使写章的 agent 无视 SKILL.md 的
文字规则，本层也能让 verify --all 判 FAIL，杜绝 Vakil 事故（练习归拢块 / 照抄 OCR
页眉 / 条目标题缺失 / 缺节）再次整批通过。

本 skill 的体例铁律（详见 SKILL.md）：
  - 习题策略（详见 `verify/verbose_gates/verbose_gates.md`「习题收录规则」）：**穿插在小节中的习题
    原位内联保留**（`**练习 N.M.X（Exercise N.M.X）：**`）；**章末整块习题（带专门习题
    小标题 / 整节都是习题）省略不写**。绝不可把原书穿插排布的内容抽出来在节末/章末新建
    `### 练习` / `### 习题` / `### Exercises` 归拢块（= 重排原书结构，由 p_exer_block 拦截）。
  - 必须逐条读懂重写，剔除页眉/页脚/版权行，不得照抄 OCR 文本流。
  - number-first 体例（编号在前、标题在后）：条目标签必须是
    `**N.M.K（标题）：**` 或 `**定义 N.M.K**：`，禁止裸 `**N.M.K**` 把标题甩到正文。
  - 结构契约 `book_structure.json`（SSOT 见 `flows/extract/structure/structure.md`）是写作契约：几节写几节、顺序照抄、条目不增不减。旧书须先重跑 build_structure 生成 JSON。

检测七类缺陷（全部 BLOCKING，不可 --fix，需重写）：
  p_exer_block  — 练习归拢块：独立的 `### 练习`/`### 习题`/`### Exercises` 标题，
                 或独立加粗 `**练习**`/`**习题**`/`**Exercise**`（无编号）。
  p_noise       — 照抄 OCR 噪声：页眉/页脚/版权行（(c) 2024 / draft / out-of-date /
                 Published by / 全大写 running header / 作者名 / 机构域名 等）。
  p_bare_item   — number-first 体例下条目标题缺失：裸 `**N.M.K**`（无标题、无类型词，
                 或标题被甩到下一行）。
  p_missing_sec — 缺节：md 的 `## §` 数量 < 骨架 SEC 数量，列出缺失的 § 号。
  p_extra_item  — 编造条目：md 里出现骨架 ITEM 清单中没有的编号条目（如原书 §X.1 是
                 散文无编号，却被凭空补出 `**X.1.1（Implicit）：**` 之类）。属无中生有结构，
                 必须删除或改为普通散文/备注，绝不可伪造编号。
  p_verbose     — 过度照抄（非核心内容未摘要）：顶层长散文段（不含 `**` 标签条目/例/练习/
                 注记的忠实内容，这些属 Tier 1 高保真豁免）超过 ~350 字/段的段落数 ≥ 6
                 （VERBOSE_PARA_GATE），判为把动机/导语等非核心内容整段搬自原书，须压缩为
                 核心要点或省略（Tier 2）。
  p_proof_verbose — 证明/解答块过长且未分条：单个 `> **证明/解答/Proof/Solution**` 块引用内
                 文本 > 700 字（VERBOSE_PROOF_CHARS）且**未写成核心步骤式**（即没有 ≥2 个
                 `1.` / `（1）` / `(a)` 这类步骤标号）的块数 ≥ 2（VERBOSE_PROOF_GATE），判为
                 逐段翻译原书 proof，须压成核心步骤（Tier 3）。
                 ⚠️ 已分条枚举的证明【不论步数多少】一律豁免——「1,2,3」只是示意，核心步骤
                 按实际需数列出即可，只要用 `1. 2. 3. …` 标号就不会被本闸门拦截。
                 例（Example）块的忠实陈述与**注记（Remark/Aside）**均豁免（Tier 1 高保真：
                 例题面忠于原文、注记保留完整少修改），但例内的解答/证明子块
                 （`> **解答/证明**：`）同样受本闸门约束。

非 auto_fixable：内容/结构缺陷需人工重写，机械修复无意义。
"""
import os
import re
import json

from verify.script.base import VerifyLayer, LayerResult, LayerFixResult

# ── 练习归拢块：独立标题 / 独立加粗 ───────────────────────────────────────
# 节末/章末「自建」的 `### 练习` `### 习题` `### Exercises` 归拢标题块——策略上章末整块习题本就省略不写，
# 此处专拦「无中生有新建归拢块」的违规（穿插习题应原位内联为 `**练习 N.M.X**：` 而非标题块）。
EXER_HEADING_RE = re.compile(r'^#{1,6}\s+.*(?:练习|习题|[Ee]xercises?)\s*$')
# 独立加粗（无编号）：`**练习**` / `**习题**` / `**Exercise**` / `**练习：**`
EXER_BOLD_RE = re.compile(r'^\*\*(?:练习|习题|Exercise)\b[：:]*\*\*\s*$')

# ── OCR 噪声：页眉/页脚/版权 ──────────────────────────────────────────────
NOISE_RES = [
    re.compile(r'\(c\)\s*\d{4}', re.I),            # (c) 2024
    re.compile(r'©'),                               # ©
    re.compile(r'copyright', re.I),
    re.compile(r'\bdraft\b', re.I),                 # draft
    re.compile(r'out[- ]of[- ]date', re.I),         # out-of-date
    re.compile(r'Published by', re.I),
    re.compile(r'Princeton University Press', re.I),
    re.compile(r'Ravi Vakil', re.I),
    re.compile(r'math[0-9]*\.stanford\.edu', re.I),
    re.compile(r'Available at', re.I),
    # 全大写 running header：整行仅大写字母与空格，首末为大写字母，长度 ≥ 15
    # （例：FOUNDATIONS OF ALGEBRAIC GEOMETRY / CATEGORIES AND FUNCTORS）
    re.compile(r'^\s*[A-Z][A-Z ]{13,}[A-Z]\s*$'),
]

# ── number-first 裸编号（条目标题缺失） ──────────────────────────────────
BARE_ITEM_3 = re.compile(r'^\*\*(\d{1,2})\.(\d{1,2})\.(\d{1,3})\*\*\s*$')
BARE_ITEM_2 = re.compile(r'^\*\*(\d{1,2})\.(\d{1,3})\*\*\s*$')
# `**N.M.K** 空格 非括号文字` —— 标题被甩到 bold 之外（应为 `**N.M.K（标题）：**`）
DETACHED_3 = re.compile(r'^\*\*(\d{1,2})\.(\d{1,2})\.(\d{1,3})\*\*\s+(?!\s*[（(])(\S+)')
DETACHED_2 = re.compile(r'^\*\*(\d{1,2})\.(\d{1,3})\*\*\s+(?!\s*[（(])(\S+)')

# md 中的节标题（兼容 `## §1.2` 与 `## 1.2`）
SEC_HEADING_RE = re.compile(r'^##\s*§?\s*(\d+(?:\.\d+)?)')
# 无编号小节（原书小节无序号标）专用：要求 `§` 符号、编号可选。用于
# `section_numbers=False` 的书——闸门改用「按位置/顺序」比对结构契约小节，
# 不依赖 md 标题里的数字（详见 SKILL.md 写作规则：尊重原书编号）。
SEC_HEADING_RE_OPT = re.compile(r'^##\s*§\s*(\d+(?:\.\d+)?)?')


def check_exer_blocks(lines):
    out = []
    for i, ln in enumerate(lines):
        if EXER_HEADING_RE.match(ln) or EXER_BOLD_RE.match(ln):
            out.append(f"  x L{i+1}: 练习归拢块（练习须原位内联为 "
                       f"`**练习 N.M.X（Exercise N.M.X）：**`，不可抽出来建标题块）— {ln.strip()[:78]}")
    return out


def check_noise(lines):
    out = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        for rx in NOISE_RES:
            if rx.search(s):
                out.append(f"  x L{i+1}: 疑似 OCR 页眉/版权噪声（须剔除，不得照抄）— {s[:78]}")
                break
    return out


def check_bare_items(lines, ordinal):
    out = []
    n = len(lines)
    # ordinal == 3 (three_level) uses the 3-component bare-item detector;
    # every other style (single / two_level / en / roman / gm / fraleigh) uses
    # the 2-component detector.
    bare = BARE_ITEM_3 if ordinal == 3 else BARE_ITEM_2
    detached = DETACHED_3 if ordinal == 3 else DETACHED_2
    for i, ln in enumerate(lines):
        if bare.match(ln):
            # 标题可能在下一行（英文 "Categories." 之类）
            j = i + 1
            while j < n and lines[j].strip() == '':
                j += 1
            nxt = lines[j].strip() if j < n else ''
            if nxt == '' or re.match(r'^[A-Z][a-z]+[\.]?$', nxt):
                out.append(f"  x L{i+1}: 条目标题缺失（裸编号，无 `（标题）`/`类型词`）— {ln.strip()[:78]}")
            continue
        m = detached.match(ln)
        if m:
            out.append(f"  x L{i+1}: 条目标题被甩到 bold 外（应为 `**{m.group(0).strip('* ')}（标题）：**`）— {ln.strip()[:78]}")
    return out


# 习题专属节（如 "1.11 Exercises" / "3.9 习题" / "Problems"）——按习题收录规则可省略，
# 不计入「骨架必写节」契约（详见 verify/verbose_gates/verbose_gates.md 习题收录规则）
EXER_SEC_TITLE_RE = re.compile(r'(练习|习题|[Ee]xercises?|[Pp]roblems?)\b')


def _iter_nodes(node):
    """展平结构树（不含 chapter 自身），供契约加载使用。"""
    for k in node.get("sub_sec", []):
        yield k
        yield from _iter_nodes(k)


def _load_contract(ext_dir, ch):
    """返回 (sections, item_keys)。

    sections : list[(num, title)]，title 含印刷标题（用于习题节判定）。
    item_keys: set[str]，允许出现的编号项编号集合（仅 three-level 点分格式，
               与 md 侧 ITEM_LABEL_RE 对齐）。

    读取单文件书对象 book_structure.json（结构树）；
    旧书须先重跑 build_structure 生成该单文件。
    """
    sections, item_keys = [], set()
    bs = BookStructure.load(ext_dir)
    if bs is None:
        return sections, item_keys
    ch_node = bs.find_chapter(ch)
    if ch_node is None:
        return sections, item_keys
    for n in _iter_nodes(ch_node.to_dict()):
        t = n.get("type")
        if t == "section":
            sections.append((str(n.get("key", "")), str(n.get("name", ""))))
        elif t not in ("section", "chapter", "exercise"):
            k = str(n.get("key", ""))
            if re.match(r"^\d+\.\d+\.\d+$", k):
                item_keys.add(k)
    return sections, item_keys


def check_missing_sections(md_lines, ext_dir, ch, section_numbers=True):
    sections, _ = _load_contract(ext_dir, ch)
    if not sections:
        return []
    # 习题专属节按规则可省略，不计入「骨架必写节」契约
    required = [(s, title) for (s, title) in sections
                if not EXER_SEC_TITLE_RE.search(title)]
    if not required:
        return []

    if section_numbers:
        # 标准书：md `## §N` 的数字必须与契约编号逐一对齐
        present = set()
        present_first = set()
        for ln in md_lines:
            m = SEC_HEADING_RE.match(ln)
            if m:
                num = m.group(1)
                present.add(num)
                # 首级分量（如 "26.1" -> "26"），用于兼容「全书全局编号」书
                # （Fraleigh 等：契约存 "6.26"，md 用 `## §26.1` —— 全局节号 26
                # 是 md 的首级分量、也是契约的末级分量）。该匹配为「附加」，
                # 不破坏标准书，仅对全局编号书放行 contract-last in present_first。
                present_first.add(num.split('.')[0])
        out = []
        for s, title in required:
            ok = (s in present) or (s.split('.')[-1] in present_first)
            if not ok:
                out.append(f"  x Ch{ch} §{s}: 结构契约要求此节，但 md 无对应 `## §{s}` 标题")
        return out

    # section_numbers=False：原书小节无序号标（如 Silverman），尊重原书。
    # 闸门不依赖 md 标题里的数字，改为「按位置」比对结构契约小节——仅校验
    # 契约要求的每一节在 md 中位置对齐地存在（md 的 `## §` 编号可选，见
    # SEC_HEADING_RE_OPT）。保持与原编号模式一致的**非对称**语义：只报
    # 「契约要求但 md 缺失」的节，不报「md 多出契约未记的节」——因为原书
    # subsection 可能多于契约（契约由抽取器生成、本身稀疏），且真实 md 忠实
    # 于原书，多出的 `## §` 是合理的小节，不应阻断闸门。
    md_secs = [ln for ln in md_lines if SEC_HEADING_RE_OPT.match(ln)]
    out = []
    for idx, (s, title) in enumerate(required):
        if idx >= len(md_secs):
            out.append(
                f"  x Ch{ch} §{s}: 结构契约要求此节（位置 {idx+1}），"
                f"但 md 仅 {len(md_secs)} 个 `## §` 标题（缺 {len(required)-len(md_secs)} 节）")
    return out


# md 中的编号条目标签（数字 K，排除 `**Exercise ...` 练习标签）
ITEM_LABEL_RE = re.compile(r'^\*\*(\d{1,2}\.\d{1,2}\.\d{1,3})')

# ── 过度照抄：证明/解答块引用过长（Tier 3 闸门） ─────────────────────────
# 盯证明/解答类块引用（注记 Remark/Aside 与例的题面一样按 Tier 1 高保真：保留完整、少修改，豁免）
PROOF_OPEN_RE = re.compile(
    r'>\s*\*\*(?:证明|证明思路|证明梗概|证明概要|Proof|Proof sketch|Proof Sketch|'
    r'梗概|概要|解答|Solution)\b', re.I)

# 顶层长散文段的最小字符数（超过即疑似整段照抄非核心内容）
# 注：含公式($...$/$$/\begin{})的段落视为「内容承载的描述性内容」，豁免本闸门
# （忠实保留公式/概念的描述本就该较长，不应被误杀；见 SKILL.md Tier 2）。
VERBOSE_PARA_CHARS = 450
# 单证明块过长的字符阈值
VERBOSE_PROOF_CHARS = 700
# 触发 FAIL 的聚合阈值（report.py 读取）
VERBOSE_PARA_GATE = 6      # 顶层长散文段 ≥ 6 段 → 非核心内容未摘要
VERBOSE_PROOF_GATE = 2     # 过长且未分条的证明/解答块 ≥ 2 块 → 逐段翻译

# 核心步骤标号：行首 `1.` / `（1）` / `(1)` / `（a）` / `(a)` 等
STEP_RE = re.compile(r'^\s*(?:\d+\.|[（(]\d+[)）]|[（(][a-zA-Z][)）])\s')


def _is_enumerated(buf):
    """块内是否已是核心步骤式写法（步数不限）。≥2 个步骤标号即视为已分条，豁免。"""
    cnt = 0
    for line in buf:
        if STEP_RE.match(line):
            cnt += 1
            if cnt >= 2:
                return True
    return False


def _para_has_math(text):
    """段落是否承载数学内容（视为内容而非照抄 padding）。"""
    return ('$' in text) or ('\\begin{' in text) or ('\\(' in text)


def check_verbose_paragraphs(lines):
    """顶层长散文段（非核心内容未摘要）。

    豁免：块引用(`>`)内、标题(`#`)、`**` 标签条目/例/练习的忠实陈述、$$ 公式、
    `---` 分隔线、表格行。只统计「无标签的顶层散文」——即动机/直观/注记非核心
    阐述/导语等 Tier 2 内容；这些若被整段搬自原书（>450 字/段）即违规。
    ⚠️ **含公式的段落豁免**：凡承载数学（`$...$`/`$$`/`\\begin{}`/`\\(`）的段落视为
    忠实保留公式的描述性内容（SKILL.md Tier 2 要求保留公式），不计入长散文闸门，
    避免「忠实描述」被误杀。纯散文（无公式）仍按 450 字阈值约束。
    """
    out = []
    n = len(lines)
    i = 0
    while i < n:
        ln = lines[i]
        s = ln.strip()
        if not s or s.startswith('>') or s.startswith('#') or s.startswith('$$') \
           or s.startswith('---') or s.startswith('|'):
            i += 1
            continue
        if s.startswith('**'):
            # 跳过一个 `**标签**：` 条目区域（含其续行与夹杂空行），直到结构性标记
            j = i + 1
            while j < n:
                nx = lines[j].strip()
                if not nx:
                    j += 1
                    continue
                if nx.startswith(('>', '#', '**', '---', '$$', '|')):
                    break
                j += 1
            i = j
            continue
        # 收集一段顶层散文
        j = i
        buf = []
        while j < n:
            cur = lines[j].strip()
            if not cur or cur.startswith(('>', '#', '$$', '---', '|', '**')):
                break
            buf.append(cur)
            j += 1
        if buf:
            text = ' '.join(buf)
            # 含公式的段落 = 内容承载的描述性内容，豁免长散文闸门（Tier 2）
            if _para_has_math(text):
                i = j
                continue
            if len(text) > VERBOSE_PARA_CHARS:
                out.append(f"  x L{i+1}: 顶层散文段过长（{len(text)} 字，疑似整段照抄非核心内容）"
                           f"— 动机/导语须精简表述但保留公式与概念(Tier 2)：{text[:60]}…")
        i = j
    return out


def check_verbose_proofs(lines):
    """证明/注记/解答块引用过长且未分条（Tier 3 闸门）。

    ⚠️ 已用 `1. 2. 3. …` / `（1）（2）` / `(a)(b)` 等分条枚举的证明【步数不限】一律豁免——
    「1,2,3」只是示意，核心步骤按实际需数列出即可。只有「整段散文墙」式（无步骤标号且
    >700 字）的块才判违规。例 Example 的忠实陈述豁免，但其内 `> **解答/证明**：` 子块同样受约束。
    """
    out = []
    n = len(lines)
    i = 0
    while i < n:
        ln = lines[i]
        if PROOF_OPEN_RE.search(ln):
            j = i
            buf = []
            while j < n:
                cur = lines[j].strip()
                if cur.startswith('>'):
                    tail = cur[1:].strip() if len(cur) > 1 else ''
                    buf.append(tail)
                    j += 1
                elif cur == '':
                    k = j + 1
                    while k < n and lines[k].strip() == '':
                        k += 1
                    if k < n and lines[k].strip().startswith('>'):
                        j = k
                        continue
                    break
                else:
                    break
            # 已分条枚举（步数不限）→ 豁免，不计入违规
            if _is_enumerated(buf):
                i = j
                continue
            text = ' '.join(buf)
            if len(text) > VERBOSE_PROOF_CHARS:
                out.append(f"  x L{i+1}: 证明/注记/解答块过长且未分条（{len(text)} 字，疑似逐段翻译原书 proof）"
                           f"— 须压成核心步骤 1. 2. 3. …（步数按实际需数，Tier 3）：{text[:60]}…")
            i = j
            continue
        i += 1
    return out



def check_extra_items(md_lines, ext_dir, ch):
    """编造条目：md 出现、但结构契约编号项清单中没有的编号条目（无中生有结构）。"""
    _, item_keys = _load_contract(ext_dir, ch)
    if not item_keys:
        return []
    out = []
    for i, ln in enumerate(md_lines):
        m = ITEM_LABEL_RE.match(ln)
        if m and m.group(1) not in item_keys:
            # 排除练习标签（以 Exercise 开头不在此正则范围，这里仅数字条目）
            out.append(f"  x L{i+1}: 编造条目（契约无此编号，属无中生有结构，须删除或改为散文/备注）— {ln.strip()[:78]}")
    return out


class PLayer(VerifyLayer):
    """P-LAYER — 内容/结构反回归闸门（BLOCKING, 不可 --fix）。"""

    code = 'P'
    name = 'verbose-gates'
    order = 16
    fix_order = 99          # 不参与自动修复
    auto_fixable = False

    def run(self, ctx):
        try:
            lines = ctx.read_md_lines()
        except Exception:
            return LayerResult(code=self.code, metadata={
                'p_exer_block': [], 'p_noise': [], 'p_bare_item': [], 'p_missing_sec': [],
                'p_extra_item': [], 'p_verbose': [], 'p_proof_verbose': [],
            })
        exer = check_exer_blocks(lines)
        noise = check_noise(lines)
        bare = check_bare_items(lines, ctx.config.primary_type)
        missing = check_missing_sections(lines, ctx.ext_dir, ctx.ch,
                                         ctx.config.section_numbers)
        extra = check_extra_items(lines, ctx.ext_dir, ctx.ch)
        verbose = check_verbose_paragraphs(lines)
        verbose_proof = check_verbose_proofs(lines)
        return LayerResult(code=self.code, metadata={
            'p_exer_block': exer,
            'p_noise': noise,
            'p_bare_item': bare,
            'p_missing_sec': missing,
            'p_extra_item': extra,
            'p_verbose': verbose,
            'p_proof_verbose': verbose_proof,
        })
