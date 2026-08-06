# 分隔符通配 + 正则去重 重构设计方案

> 作者：Bob（架构师） · 类型：**重构（refactor）**，非新功能
> 范围：`verify/key_parse.py`、`verify/layers/b_layer.py`、`verify/layers/extract_layer.py`、`extract/extract_items*.py`
> 硬约束（来自 team-lead）：不改坏三书回归（Kreyszig 11/11、Koopman 40/40、Apostol 28/28）；保留 `levels`/`scope`/`separate_types`(`SEP_COMBINED=0`/`SEP_PER_TYPE=1`，判定用 `==`)/`known_gaps`/分组逻辑；保留 label-first / number-first 识别逻辑。

---

## 1. 共享 lib 方案

### 1.1 文件归属决策：**新建 `verify/regexlib.py`，由 `key_parse.py` 重新导出**

| 候选 | 结论 | 理由 |
|------|------|------|
| 复用 `key_parse.py` 作为唯一归宿 | ❌ 不单独成立 | `key_parse.py` 还承载 label canon map、各 scheme 正则、业务语义，塞入"分隔符原语"会让它更臃肿，且本次只动"分隔符" |
| **新建 `verify/regexlib.py` + `key_parse.py` 重新导出** | ✅ **采用** | ① 单一真理源，满足"公用正则抽 lib"；② `regexlib` 仅依赖 `re`（无 cv2/torch），可独立 import，契合 `key_parse` 既有的"standalone"契约；③ `key_parse` 重新导出全部既有公共名 → 所有现调用方**零改动**（见下方调用方清单），回归风险最低 |

**调用方零改动清单**（grep 确认）：`verify/layers/b_layer.py`、`verify/layers/extract_layer.py`、`verify/layers/d_layer.py`(用 `GM_SEC_RE/GM_ENTRY_RE`)、`verify/layers/a_layer.py`(用 `sortkey`)、`verify/manage_ignore.py`、`verify/ignore_files.py`(用 `normkey`)、`extract/extract_items_gm.py`(用 `GM_*_RE/gm_head_label/_canon_label`)。全部仍 `from verify.key_parse import ...`，名字不变。

**依赖方向（避免循环）**：`regexlib`（最底层，纯分隔符原语，**不含 label 知识**）← `key_parse`（高层，label 集合 + scheme 正则 + `canon_token`/`normkey`，从 regexlib 引入 SEP 并重新导出）← 各 layer / extractor。

### 1.2 公共 API 草案（`verify/regexlib.py`）

```python
# --- 分隔符类（团队要求全集，不含 * / 数字 / 字母）---
SEP_WIDE = r'[.\-–·/：:～~_＋+，,;；、．－〜\s]'   # 用于 split/canon（输入已被边界限定）
SEP_TIGHT = r'[.\-–·/．－〜]'                       # 现 b_layer._SEP 原样，用于"匹配型"正则，防 over-match
SEP = SEP_TIGHT                                    # 别名：各 scheme 共享正则均由此构造

SEP_SPLIT_RE = re.compile(SEP_WIDE + '+')           # 带 + 量词，re.split 后过滤空串

def canon_sep(s: str) -> str:
    """任意分隔符 run → 单个 '.'，去首尾、合并重号。'4--11..5' → '4.11.5'"""

_NUMPATH_RE = re.compile(r'(\d+(?:' + SEP + r'\d+){0,2})')   # 仅数字部分
def canon_token_numeric(s: str) -> str:
    """只归一 token 里数字部分的分离符，保留 label 原文。
       'Theorem 12-3'→'Theorem 12.3'，'定理 4·11-5'→'定理 4.11.5'（供 known_gaps 比对）"""

@lru_cache(maxsize=16)
def build_numpath_regexes(levels):
    """返回 (exact, cap, label_first, num_first)，与现 b_layer._numpath_regexes 等价，
       但用 SEP 构造 → 匹配行为不变；levels 驱动组件数"""

def split_numpath(s: str, levels: int):
    """现 b_layer._split_numpath：exact 匹配(按 levels 校验组件数) →
       re.split(SEP_SPLIT_RE, s) 过滤空串 → int 列表；否则 None"""

# --- 各 scheme 共享编译正则（均由 SEP 构造，保证一致）---
KEY_RE      = re.compile(r'(\d+)\.(\d+)' + SEP + r'(\d+)')
ENTRY_RE    = re.compile(r'\*\*[^*]*?(\d+\.\d+' + SEP + r'\d+)[^*]*\*+')
ROMAN_KEY_RE= re.compile(r'([IVXLCDM]+)\.(\d+)' + SEP + r'(\d+)')
ENTRY_RE_ROMAN = ...   # 同上，label + ROMAN
PROSE_RE_ROMAN  = ...
ENTRY_RE_2   = re.compile(r'\*\*(定义|定理|...)\s*(\d+)' + SEP + r'(\d+)\s*[.．]?\s*\*+')  # 原仅 \.
PROSE_RE_2   = re.compile(r'(定义|定理|...)\s*(\d+)' + SEP + r'(\d+)')
ENTRY_RE_EN / PROSE_RE_EN / ENTRY_RE_EN_C / PROSE_RE_EN_C  # (\d+)\.(\d+) → (\d+)' + SEP + r'(\d+)'
FR_ENTRY_RE / FR_PROSE_RE  # 同上
GM_SEC_RE / GM_ENTRY_RE / GM_LABELED_RE / GM_HEAD_LABEL_RE  # 用 SEP 替换 [.．]/[.．、]/可选\.?
```

`key_parse.py` 在引入上述原语后，再提供**需要 label 知识**的 API 并重新导出全部旧名：

```python
from verify.regexlib import (SEP, SEP_TIGHT, SEP_WIDE, SEP_SPLIT_RE,
                             canon_sep, canon_token_numeric,
                             build_numpath_regexes, split_numpath,
                             KEY_RE, ENTRY_RE, ROMAN_KEY_RE, ENTRY_RE_ROMAN,
                             PROSE_RE_ROMAN, ENTRY_RE_2, PROSE_RE_2,
                             ENTRY_RE_EN, PROSE_RE_EN, ENTRY_RE_EN_C, PROSE_RE_EN_C,
                             FR_ENTRY_RE, FR_PROSE_RE, GM_SEC_RE, GM_ENTRY_RE,
                             GM_LABELED_RE, GM_HEAD_LABEL_RE)

def canon_token(s: str) -> str:
    """带可选 label 前缀时只归一数字部分 → 'LABEL C.S.N' 或 'C.S.N'（全 label 归一版）"""

def normkey(s: str) -> str:
    """改为：canon_sep(s) 后，若 3 组件则 'C.S-N'，否则原样。
       wildcard 感知（'4·11·5'→'4.11-5'），对既有点/ dash 键行为不变"""
```

### 1.3 关键设计决策

1. **双分隔符集**：匹配型正则（`KEY_RE`/`ENTRY_RE`/`PROSE_*`/`_numpath_regexes`/`_BOOK_LABEL_RES`）统一用 `SEP_TIGHT`（= 现 b_layer 的 `[.\-–·/．－〜]`，**不含** 空格/逗号/冒号）；`SEP_WIDE` + `SEP_SPLIT_RE` 只用于 `re.split` 与 `canon_sep`/`canon_token_numeric`（这些场景输入已被边界/anchor 限定）。→ 既满足团队"通配覆盖全集"的诉求，又规避 unanchored `finditer` 吞掉 `"1, 2, 3"`/`"Eq. 2.3"` 等散文数字（**over-match 对策**，见 §3）。
2. **`present_md` 末级保持 dash（`C.S-N`）**：不改动其分隔符形态，因此既有 `present_md` ↔ `BLayer.run` 的 `bkeys`（`f"{sec}-{n}"`）dash 比对耦合**天然保持有效**，无需两端各做归一（约束 #4）。
3. **`known_gaps` 通配**：`b_layer` 的 `_norm_sep`/`_SEP_BETWEEN_DIGITS` 整体由 `canon_token_numeric` 替代；用户写 `"Theorem 12.3"` 或 `"Theorem 12-3"`、emit 出 dash 形态，三者经同一 `canon_token_numeric` 归一后一致比对（约束 #5）。
4. **`split` 健壮性**：5 处 `re.split(_SEP, s)` 改为 `re.split(SEP_SPLIT_RE, s)` 并过滤空串 → 消除连续分隔符（`4..11--5`）产生 `''` 导致 `int()` 崩溃的隐患（b_layer L108/191/204/209/235）。

---

## 2. 任务分解清单（有序、标注依赖）

> 约定：`SEP`=`SEP_TIGHT`。每个任务给出**具体改动点 + 行号**。

### T01 — 新建 `verify/regexlib.py` 共享分隔符原语库  【P0，无依赖】
- 新建文件 `verify/regexlib.py`，落地 §1.2 全部符号：`SEP`/`SEP_TIGHT`/`SEP_WIDE`/`SEP_SPLIT_RE`/`canon_sep`/`canon_token_numeric`/`build_numpath_regexes`/`split_numpath` + 各 scheme 共享编译正则（`KEY_RE`/`ENTRY_RE`/`ROMAN_KEY_RE`/`ENTRY_RE_ROMAN`/`PROSE_RE_ROMAN`/`ENTRY_RE_2`/`PROSE_RE_2`/`ENTRY_RE_EN`/`PROSE_RE_EN`/`ENTRY_RE_EN_C`/`PROSE_RE_EN_C`/`FR_ENTRY_RE`/`FR_PROSE_RE`/`GM_SEC_RE`/`GM_ENTRY_RE`/`GM_LABELED_RE`/`GM_HEAD_LABEL_RE`）。
- 纯 `re`、无重依赖，可独立 import。

### T02 — `verify/key_parse.py` 改造：引入 regexlib + 通配正则 + `normkey`  【P0，依赖 T01】
- 顶部 `from verify.regexlib import ...`（见 §1.2），**删除**本文件内手写的 `KEY_RE`/`ENTRY_RE`/`ROMAN_KEY_RE`/`ENTRY_RE_ROMAN`/`PROSE_RE_ROMAN`/`ENTRY_RE_2`/`PROSE_RE_2`/`ENTRY_RE_EN`/`PROSE_RE_EN`/`ENTRY_RE_EN_C`/`PROSE_RE_EN_C`/`FR_ENTRY_RE`/`FR_PROSE_RE`/`GM_SEC_RE`/`GM_ENTRY_RE`/`GM_LABELED_RE`/`GM_HEAD_LABEL_RE` 定义（改为从 regexlib 引入后**重新导出**，保持公共名不变）。
- L32 `KEY_RE`：`[\.\-]` → `SEP`（已由 regexlib 完成，本任务仅确认引用）。
- L34 `ENTRY_RE`：`[.\-]` → `SEP`。
- L25/27 `FR_ENTRY_RE`/`FR_PROSE_RE`：`(\d+)\.(\d+)` → `(\d+)' + SEP + r'(\d+)`（通配，原仅点号）。
- L41-47 `ENTRY_RE_2`/`PROSE_RE_2`：同上通配。
- L90-104 `ENTRY_RE_EN`/`PROSE_RE_EN`/`ENTRY_RE_EN_C`/`PROSE_RE_EN_C`：`(\d+)\.(\d+)` → 通配（en 书用点号，仍匹配，无回归）。
- L109-113 `ROMAN_KEY_RE`/`ENTRY_RE_ROMAN`/`PROSE_RE_ROMAN`：`[\.\-]` → `SEP`。
- L124 `GM_SEC_RE`：`[.．、]?` → `SEP + '?'`（或保留 `?`，用 SEP 替换字符类）。
- L125 `GM_ENTRY_RE`：`[.．]` → `SEP`。
- L127 `GM_LABELED_RE`：可选 `\.?` → `SEP + '?'`（两处）。
- **L49-54 `normkey` 重写**：`s.split('.')` → `canon_sep(s)` 后按组件数处理（3 组件→`C.S-N`，否则原样）；wildcard 感知，对点/dash 键行为不变。
- 新增 `canon_token`（全 label 归一版，供未来/可选使用）。
- 验证：本文件 import 自检 + `python -c "from verify.key_parse import KEY_RE, normkey, GM_LABELED_RE"` 通过。

### T03 — `verify/layers/b_layer.py` 改造：去重 + 健壮性（不改分级/分组/label-first）  【P0，依赖 T01】
- L42 `_SEP = r'[.\-–·/．－〜]'` → 删除，改 `from verify.regexlib import SEP, SEP_SPLIT_RE, canon_token_numeric, split_numpath, build_numpath_regexes`（与现字符集一致 → 匹配行为不变）。
- L51-63 `_numpath_regexes`：逻辑原样迁入 `regexlib.build_numpath_regexes`；本文件改为调用（L58 `numpath` 用 `SEP` 已由 regexlib 提供）。
- L92-94 `_SEP_BETWEEN_DIGITS`/`_norm_sep` → 删除，改用 `regexlib.canon_token_numeric`。
- L101-109 `_split_numpath` → 改为调用 `regexlib.split_numpath`（内部已用 `SEP_SPLIT_RE` + 过滤空串）。
- L108/191/204/209/235 共 5 处 `re.split(_SEP, s)` → `re.split(SEP_SPLIT_RE, s)` 并过滤空串（健壮性修复）。
- L485 `present_md` key、L526 `emit` 的 `full`、L306 尾部 `full`：**保持 `C.S-N` dash 形态不变**（耦合安全，见 §1.3.2）。可选：抽出 `md_item_key(prefix_str, item_num)` 助手统一三处构造，防未来漂移。
- L501/529-530 `known = {_norm_sep(x)...}` / `_norm_sep(token)...` → 全部替换为 `canon_token_numeric(...)`（raw 与 canon-label 两种形态分别归一后比对，逻辑同现）。
- L575/L595 `bkeys` 构造（`f"{sec}-{n}"` / `f"{sec}{n.strip()}"`）保持 dash 形式不变。
- **严禁改动**：`SEP_COMBINED`/`SEP_PER_TYPE` 常量、`from_dict` 的 `==` 判定、`group_prefix_len`、label-first/number-first 分支、`_is_header_boundary`/`_after_label_boundary`（本轮不动，见 §4）。

### T04 — `verify/layers/extract_layer.py` 改造：通配匹配型正则  【P0，依赖 T01】
- 顶部新增 `from verify.regexlib import SEP`（或 `SEP_TIGHT`）。
- L62-66 `_BOOK_LABEL_RES`（3 条）：`[.\-]`（L63/L65）→ `SEP`；保持 `^` 锚定（跨引用已被锚定排除）。
- L143 `mark_re`：`(\d+)\.(\d+)[.\-](\d+)` → `(\d+)\.(\d+)' + SEP + r'(\d+)`。
- L156 `re.search(r'(\d+)\.(\d+)-(\d+)', it['key'])`：解析 extractor 自有 dash 键，行为不变；可选改为 `canon_token_numeric` 以兼容其他分隔符（P2，非必须）。

### T05 — `extract/extract_items*.py` 改造：抽取侧分隔符通配（含可选清理）  【P1，依赖 T01】
- `extract/extract_items.py`：
  - L139 `lab_re`：`[\.\·]` → `SEP`（two-level `定义4·1` 也能抽）。
  - L282 `num_re`：`[\.\-\·\，\s]` → 用 `SEP_WIDE`（OCR 噪声含空格/逗号，抽取侧本就该宽）→ 等价于现行为且 wildcard 更全。
  - L303 `fallback_re`：`[\s_\-\·]` → 用 `SEP_WIDE`。
- `extract/extract_items_en.py`：
  - L13-16 `EN_LAB_RE`：`(\d+)\s*\.\s*(\d+)` → `(\d+)' + SEP + r'(\d+)`（en 书用点号仍匹配，通配其他分隔符）。
- `extract/extract_items_gm.py`：
  - `GM_OCR_ITEM_RE`(L93) `^(\d{1,3})\.\s*`、`GM_OCR_SEC_RE`(L85) `^...(\d{1,2})\.\s+`：结构性标题固定用点，可保留 `\.`；其共享 `GM_LABELED_RE`/`GM_HEAD_LABEL_RE` 已在 T02 经 regexlib 通配。**本轮建议保留 `.`，仅记录。**
- **额外汇总（建议本轮一并或作为 follow-up，P2）**：`extract/scan_items.py`(L63-67 `lab_re`/`sec_re`/`ex_re` 的 `[\.\·]`)、`extract/b_layer.py`(L26 `num_re` 的 `[\.\-\·\，\s]`) 同样写死分隔符，属"校验相关正则重复定义"，应一并改引用 `regexlib.SEP`/`SEP_WIDE` 以彻底完成"抽 lib"。**不阻塞三书回归，但建议纳入同 PR 以免遗漏。**

---

## 3. 回归与风险计划

### 3.1 必跑回归（命令形如，QA 自动定位带 `verify_config.json` 的书）
```
D:/anaconda3/envs/pdfextract/python.exe -m verify.verify_chapter --all <book>/_extract <book根目录>
```
| 书 | scheme | 期望 | 本次相关点 |
|----|--------|------|-----------|
| Kreyszig | three-level | **11/11 PASS** | `KEY_RE`/`ENTRY_RE`/`normkey`/`_BOOK_LABEL_RES`/`mark_re` 用 SEP_TIGHT=现 `[\.\-]` 超集，点/dash 仍匹配；`split` 更健壮 |
| Koopman | en (two-level) | **40/40 PASS** | `ENTRY_RE_EN_C`/`PROSE_RE_EN_C` 由 `\.`→`SEP`，点号仍匹配；`EN_LAB_RE` 同理 |
| analytic-number-theory (Apostol, `D:/study/book/analytic-number-theory`) | en (two-level) | **28 文件全 PASS** | 同上；注意目录为 `D:/study/book/...` |

> 额外建议：跑完三书后，抽查 1 本含 `ignore_keys`/`known_gaps` 的书，确认抑制行为未变。

### 3.2 over-match 风险与对策
- **风险**：若把团队要求的全集（`SEP_WIDE` 含空格/逗号/冒号）直接用于 `keys_in_md` 的 unanchored `finditer` 正则（`KEY_RE`/`PROSE_*`），散文如 `"1, 2, 3"`、`"Eq. 2.3"`、日期 `"2024.1.3"` 可能被误捕为编号键 → `all_keys` 膨胀 → A 层 `extra` 误报 / B 层新分组。
- **对策（已写入设计）**：匹配型正则统一用 `SEP_TIGHT`（= 现 b_layer 集，仅含真实数字间分隔符），`SEP_WIDE` 只用于 `re.split`/`canon_sep`（输入已被 anchor/边界限定，无散文吞号风险）。三书 md 中无空格/逗号分隔的真实编号，故 `finditer` 超集匹配不会新增误捕。
- **验证**：回归后对比改动前后 `all_keys` 集合差异应为空（或仅多捕获原先因 `·`/空格漏匹配的正确键——属正向修复）。

### 3.3 `present_md` ↔ `bkeys` 比对耦合（约束 #4）
- 决策：**保持两端 dash 形态不变**。理由：`present_md` 键由解析出的 `comps` 经 `C.S-N` 构造（与 .md 原书写法无关，恒为 dash）；`BLayer.run` 的 `bkeys` 亦为 dash（`f"{sec}-{n}"`）。故 `<=` 抑制比对逻辑无需改动即有效。
- 加固：T03 可选抽出 `md_item_key()` 助手统一 L485/L526/L306 三处构造，防止未来某处改分隔符导致耦合失效。

### 3.4 `normkey` 改造对 A 层比对的影响（约束：指出是否影响）
- A 层（`a_layer.py`）不吃 `normkey` 直接，而是消费 `ctx.extracted`/`ctx.all_keys`/`ctx.entry_keys`（均在 `extract_layer` 构建）。`normkey` 经 `keys_in_md`(three-level 分支) 与 `manage_ignore`/`ignore_files`(ignore 键归一) 间接影响这些集合。
- **three-level（Kreyszig）**：旧 `normkey("4.11-5")`→`"4.11-5"`，新 `canon_sep`→`"4.11.5"`→3 组件→`"4.11-5"`，**完全相同**，零影响。
- **en（Koopman/Apostol）**：`ENTRY_RE_EN_C` 现用 `\.`，新用 `SEP`；点号仍匹配，且若 md 出现 `Definition 1·2` 也能捕获（正向）。
- **唯一行为变化点**：md 用 `·`/空格 等旧 `normkey` 不处理的分离符时，新 `normkey` 会归一为 dash → 与 extractor 的 dash 键匹配 → **减少 false-missing（正向）**。
- **ignore_keys 次级影响**：`manage_ignore`/`ignore_files` 用 `normkey` 归一 ignore 键。旧对 two-level dash 键 `"4-1"` 不归一（保留 `"4-1"`），新→`"4.1"`；但 two-level extractor 键为 `"定义1.1"`(含 label+点)，格式本就不同，故实际无交互。建议回归后抽查 ignore 行为确认。

---

## 4. 待明确事项（需用户拍板）

1. **是否把 `key_parse.py` 重命名为更贴切的名字**（如 `keyparse.py` / 保留）？本次设计**不重命名**（避免牵连所有 import 与文档引用），但如想顺手规范化可一并做——需同步改 7 处 import 与 `references/verification.md` 等文档。
2. **`_is_header_boundary` / `_after_label_boundary` 的终止符集合**（b_layer L121/L139）是否也通配？当前用写死集合，未知标点已默认归为边界（优先级低）。本轮**建议不动**（属"条目 vs 引用"判定，非"分隔符匹配"，且改动有引入误报风险）。若要做，应单独评估。
3. **`extract/scan_items.py` 与 `extract/b_layer.py`**（T05 额外汇总）是否纳入本轮 PR，还是留作 follow-up？前者是连续性扫描、后者是抽取侧缺号恢复，均含写死分隔符，彻底"抽 lib"应覆盖；但二者均未在三书核心回归路径上，可独立验证。
4. **`SEP_WIDE` 是否要含全角逗号 `，`**：当前列了 `,`(半角) 与 `、`(顿号)，未列全角逗号 `，`。建议补 `，`（中文散文常见），但需确认不会与 `SEP_TIGHT` 外的匹配型正则误用——重申：匹配型只用 `SEP_TIGHT`，`SEP_WIDE` 仅 split/canon，故加 `，` 安全。请确认。

---

## 5. 补完：d_layer.py + GM_SEP 通配（用户复查触发）

> 实际落地位置为 **`lib/regexlib.py`**（非本方案初稿写的 `verify/regexlib.py` —— 用户明确 lib 应放 skill 的 `lib/` 目录），并新增了 `SEP_NUMERIC`（提取器数字匹配器专用，排除冒号/加/分号/顿号/斜杠以免误读小数/公式/日期，补全角 `．`/`－` OCR 变体）。

### 5.1 范围纠正
- 初稿范围漏了 **`verify/layers/d_layer.py`** —— D 层在源/raw JSON 里匹配 `C.S-N` 引用的 6 个 `(\d+)\.(\d+)` 字面点 + `D_ITEM_RE` 的 `[.\-·]`，全部为写死标点。用户复查时本以为在 `registry.py`（实际 registry 干净、无任何 `re.compile`），真凶是同目录的 `d_layer.py`。
- `key_parse.py` 的 **`GM_SEP`** 初稿保留为独立写死一份，本次改为从 `SEP_TIGHT` 派生：`GM_SEP = SEP_TIGHT[:-1] + r'、]'`（保留 GM 专用 `、`）。

### 5.2 改动点（相对初稿）
- `verify/layers/d_layer.py`：顶部 `from lib.regexlib import SEP_TIGHT`；`D_SEC_HEAD_A/B/C`、`D_ITEM_RE`、`D_MD_SEC_RE`、`D_MD_NESTED_SEC_RE` 六个正则的全部 `\.` 与 `[.\-·]` → `SEP_TIGHT` 拼接（SEP_TIGHT 不含空白，`D_ITEM_RE` 的「no space sep -> no chain misread」意图保留）。
- `verify/key_parse.py`：`GM_SEP` 改写为派生式。

### 5.3 「非 bug」澄清（避免误改）
下游 `verify/layers/b_layer.py`、`extract/scan_items.py`、`extract/extract_items*.py`、`extract/b_layer.py`、`gen_contract.py` 等大量 `key.split('.')` / `split('-')` / `split(':')` 是解析**已归一化的 canonical `C.S-N` key**（提取器匹配时用通配抓数字组分、存 key 时归一成字面 `.`/`-`），不是写死标点匹配 —— 通配只在匹配阶段发生。这些 split **不应**改为通配，否则会破坏 canonical key 契约。

### 5.4 验证
import smoke test（含 d_layer）→ `IMPORTS OK`；3 书本轮回归预期与改动前一致。
