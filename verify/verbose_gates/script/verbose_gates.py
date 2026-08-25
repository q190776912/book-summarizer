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

# md 中的节标题（兼容 `## §1.2` / `## 1.2`（两级）与 `### §1.2.3`（三级）、
# `#### §1.2.3.4`（四级，子节规范写法，头部 # 数 = 嵌套层级）。
# 注意：契约（book_structure.json）的小节号支持任意层级（如 18.3.1 / 16.3.4.1），
# 故此处用 `(?:\.\d+)*` 而非 `(?:\.\d+)?`，且头部取 `#{2,4}` 而非 `##`，
# 否则三级小节号会被截断为两级、或三级 `###`/四级 `####` 标题根本不被扫描，
# 导致 p-layer-missing-sec 把真实存在的小节误报为缺失（回归：commit 5390e5d
# 把契约源切到 book_structure.json 后未同步放宽此正则）。
SEC_HEADING_RE = re.compile(r'^#{2,4}\s*§?\s*(\d+(?:\.\d+)*(?:-[A-Za-z])?)')
# 无编号小节（section_types 含 role 0 / depth 0，对应「原书小节无序号标」）专用：
# 要求 `§` 符号、编号可选。用于 unnumbered 书（如 Silverman）——闸门改用「按位置」
# 比对结构契约小节，不依赖 md 标题里的数字（详见 SKILL.md 写作规则：尊重原书编号）。
SEC_HEADING_RE_OPT = re.compile(r'^##\s*§\s*([\dA-Za-z][\d.\-A-Za-z]*)?')


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
        # Long lines (>120 chars) carrying a publisher/citation fragment inside
        # running prose (e.g. do Carmo citing "Princeton University Press,
        # 1957-1958" in a remark) are legitimate content, not header noise.
        if len(s) > 120:
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
    # every other style (single / two_level / en / roman / gm) uses
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
EXER_SEC_TITLE_RE = re.compile(r'(?:练习|习题|习)\s*\d*\s*$|[Ee]xercises?\b|[Pp]roblems?\b')


# 标题归一化（无序号标小节按标题匹配用）：去 LaTeX/标点/空白，保留字母数字与
# CJK，转小写。使 "Primes of the Form $N^2 + 1$" 与 "Primes of the Form N2 1" 可比对。
_LATEX_RE = re.compile(r'\$[^$]*\$')
_NONWORD_RE = re.compile(r'[^0-9a-zA-Z一-鿿]+')


def _norm_title(t):
    t = _LATEX_RE.sub(' ', t or '')
    t = _NONWORD_RE.sub(' ', t)
    return re.sub(r'\s+', ' ', t).strip().lower()


def _md_section_titles(md_lines):
    """提取 md 中 `## §` 小节的标题文本（跳过可选数字前缀）。"""
    titles = []
    for ln in md_lines:
        m = SEC_HEADING_RE_OPT.match(ln)
        if not m:
            continue
        rest = ln[m.end():].strip()
        rest = re.sub(r'^\d+(?:\.\d+)*\s*', '', rest).strip()  # 去残留数字前缀
        if rest:
            titles.append(rest)
    return titles


def _md_section_count(md_lines):
    """统计 md 中 `## §` 小节标题的数量（含空标题小节，如 Silverman 后段章节
    大量「## §」后直接跟定理的空标题小节）。用于「无编号小节」书的**数量**比对——
    标题子串匹配对双语互译标题不可行（见 check_missing_sections unnumbered 分支）。"""
    n = 0
    for ln in md_lines:
        if SEC_HEADING_RE_OPT.match(ln):
            n += 1
    return n


def _title_present(title, md_titles):
    """契约小节标题是否在 md 小节标题集合中（归一化相等或互含，容错微调）。"""
    tn = _norm_title(title)
    if not tn:
        return True
    for mt in md_titles:
        mn = _norm_title(mt)
        if tn == mn or tn in mn or mn in tn:
            return True
    return False


def _iter_nodes(node):
    """展平结构树（不含 chapter 自身），供契约加载使用。"""
    for k in node.get("sub_sec", []):
        yield k
        yield from _iter_nodes(k)


def _load_contract(ext_dir, ch):
    """返回 (sections, item_keys, letter_sub_pairs)。

    sections : list[(num, title)]，title 含印刷标题（用于习题节判定）。
    item_keys: set[str]，允许出现的编号项编号集合（仅 three-level 点分格式，
               与 md 侧 ITEM_LABEL_RE 对齐）。
    letter_sub_pairs: list[(sec_key, letter, title)]，契约声明的裸字母子块
               （section 节点 letter_subs 元数据；无则空表 → 字母子节闸不启用）。

    读取单文件书对象 book_structure.json（结构树）；
    旧书须先重跑 build_structure 生成该单文件。
    """
    sections, item_keys, letter_sub_pairs = [], set(), []
    bs = BookStructure.load(ext_dir)
    if bs is None:
        return sections, item_keys, letter_sub_pairs
    ch_node = bs.find_chapter(ch)
    if ch_node is None:
        return sections, item_keys, letter_sub_pairs
    for n in _iter_nodes(ch_node.to_dict()):
        t = n.get("type")
        if t == "section":
            key = str(n.get("key", ""))
            sections.append((key, str(n.get("name", ""))))
            for e in (n.get("letter_subs") or []):
                if e.get("key"):
                    letter_sub_pairs.append(
                        (key, str(e["key"]), str(e.get("name", ""))))
        elif t not in ("section", "chapter", "exercise"):
            k = str(n.get("key", ""))
            if re.match(r"^\d+\.\d+\.\d+$", k):
                item_keys.add(k)
    return sections, item_keys, letter_sub_pairs


def _norm_secnum(s):
    """Normalize a section-number token for comparison: dash/EN-dash/en-dot
    separators all collapse to '.' so contract keys printed as '1-1' (do Carmo)
    match md headings written `## §1.1`."""
    return re.sub(r'[.\-\u2013\u00b7\uff0e]+', '.', (s or '').strip())


# md 侧 token（全局节号书 / 字母子节）：
#   `## §12`      -> 数字节（首分量即节 id，全书全局编号）
#   `## §A`       -> 字母节（附录章）
#   `### §12.A`   -> 投影式字母子节（历史写法，显式父节优先）
#   `### §A`      -> 纯字母子节（Karlin 体例，父节靠位置）
_GLOBAL_SEC_TOKEN_RE = re.compile(r'^#{2,6}\s*§\s*(\d+(?:[.\u00b7]\d+)*)')
_LETTER_TOKEN_RE = re.compile(r'^#{2,6}\s*§\s*(?:(\d{1,2})[.\u00b7]\s*)?([A-Z])(?![A-Za-z])')


def _md_global_section_ids(md_lines):
    """md 已写的节 id 集合：数字节取完整序标串（'12'），字母节取字母（'A'）。"""
    ids = set()
    for ln in md_lines:
        m = _GLOBAL_SEC_TOKEN_RE.match(ln.strip())
        if m:
            ids.add(m.group(1).replace('\u00b7', '.'))
            continue
        m = re.match(r'^#{2,6}\s*§\s*([A-Z])(?![A-Za-z])', ln.strip())
        if m:
            ids.add(m.group(1))
    return ids


def _md_letter_sub_pairs(md_lines):
    """md 已写的字母子节 (parent_sec_str, 'A') 对；显式 N（`### §12.A`）优先，
    否则挂在最近一个数字节下（`### §A` 位置定父）。"""
    out = set()
    cur = None
    for ln in md_lines:
        s = ln.strip()
        m = re.match(r'^#{2,6}\s*§\s*(\d+(?:[.\u00b7]\d+)*)', s)
        if m:
            cur = m.group(1).split('.')[0]
            continue
        m = _LETTER_TOKEN_RE.match(s)
        if m:
            parent = m.group(1) or cur
            if parent is not None:
                out.add((str(parent), m.group(2)))
    return out


def check_missing_sections(md_lines, ext_dir, ch, cfg=None):
    sections, item_keys, letter_sub_pairs = _load_contract(ext_dir, ch)
    if not sections and not letter_sub_pairs:
        return []
    # 习题专属节按规则可省略，不计入「骨架必写节」契约
    required = [(s, title) for (s, title) in sections
                if not EXER_SEC_TITLE_RE.search(title)]
    unnumbered = bool(cfg.sections_unnumbered) if cfg is not None else False

    out = []
    md_sec_ids = _md_global_section_ids(md_lines)
    if required and not unnumbered:
        # 标准书（带序标）：md `## §N` 的数字必须与契约编号逐一对齐。
        # 原 present/present_first 集合逻辑原样保留（§C.S 标准书 +
        # Fraleigh 型全局末级分量回退，零回归）；再并上 `_md_global_section_ids`
        # —— 全局单序标书（Arnold：契约 '12' ↔ md `## §12`）与附录字母节
        # （契约 'A' ↔ md `## §A`）由此命中。
        present = set()
        present_first = set()
        for ln in md_lines:
            m = SEC_HEADING_RE.match(ln)
            if m:
                num = _norm_secnum(m.group(1))
                present.add(num)
                # 首级分量（如 "26.1" -> "26"），用于兼容「全书全局编号」书
                # （Fraleigh 等：契约存 "6.26"，md 用 `## §26.1` —— 全局节号 26
                # 是 md 的首级分量、也是契约的末级分量）。该匹配为「附加」，
                # 不破坏标准书，仅对全局编号书放行 contract-last in present_first。
                present_first.add(num.split('.')[0])
        present |= md_sec_ids
        for s, title in required:
            ns = _norm_secnum(s)
            ok = (ns in present) or (ns.split('.')[-1] in present_first)
            if not ok:
                out.append(f"  x Ch{ch} §{s}: 结构契约要求此节，但 md 无对应 `## §{s}` 标题")
    elif required and unnumbered:
        # 无编号小节（section_types 含 role 0）：原书小节无数字序标（如 Silverman）。
        # 🔴 改用「数量」比对，不再按标题匹配：双语书（EN+CN）的 `## §` 标题是
        # 「互译」而非子串关系（EN "Solving ax+by=gcd(a,b) by the Euclidean
        # Algorithm" vs CN "用欧几里得算法 (Euclidean Algorithm) 解 ax+by=gcd(a,b)"），
        # 标题子串互含对双语根本不成立，按标题匹配必致一语言整批假阳缺节。
        # 数量比对是语言无关的：本书 EN/CN 各章 `## §` 数量逐章对齐（已核验全 47
        # 章一致），契约小节数 = EN md `## §` 数，故 EN/CN 校验同过。
        # 保持非对称语义：md 小节数 ≥ 契约数即通过（多出小节不报，原书 subsection
        # 可能多于稀疏契约）；仅当 md 小节数 < 契约数（漏写/合并）才报缺节。
        contract_count = len(sections)
        md_count = _md_section_count(md_lines)
        if md_count < contract_count:
            out = [f"  x Ch{ch}: 结构契约要求 {contract_count} 个 `## §` 小节，"
                   f"但 md 仅 {md_count} 个（可能漏写/合并小节）"]
            return out

    # 字母子节（role 5）：契约 letter_subs 声明的每个 (§N, A) 必须在 md 有对应标题
    if letter_sub_pairs:
        have = _md_letter_sub_pairs(md_lines)
        for sec_key, L, _t in sorted(letter_sub_pairs):
            if (str(sec_key), L) not in have:
                out.append(f"  x Ch{ch} §{sec_key}.{L}: 结构契约要求此字母子节，"
                           f"但 md 无对应 `## §{sec_key}.{L}` / `### §{L}` 标题")
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
           or s.startswith('---') or s.startswith('|') \
           or s.startswith(('<div', '</div', '<img')):
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
            if not cur or cur.startswith(('>', '#', '$$', '---', '|', '**', '<div', '</div', '<img')):
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
    _, item_keys, _ = _load_contract(ext_dir, ch)
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
                                         cfg=ctx.config)
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
