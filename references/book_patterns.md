> 🔴 **本文件是该领域规则的唯一权威详细说明（SSOT）**。`SKILL.md` 与代码注释只引用此处、不重复描述；新增/修改该领域规则只改本文件。

# 编号体系与 OCR 怪象参考（book_patterns）

本文件记录 skill 在总结不同教材时遇到的**非标准编号体系**与 **OCR 怪象**，
以及对应的处理决策。遇到新的书时先对照「判定树」，确定编号模式（ordinal），
可避免大量假阳性（phantom key）误报。

---

## 1. 两级编号 + 双计数器（周民强《实变函数论》第三版）

### 体系特征
| 类别 | 计数方式 | 书写示例 | .md 写法 |
|---|---|---|---|
| 定义 | **独立**每章计数 | 定义1.1, 定义1.2, …, 定义1.33 | `**定义1.1**：` |
| 定理/引理/推论/命题 | **共用一个连续计数器** | 定理1.1, 引理1.2, 推论1.3, …, 命题…（1.1–1.27 连续无缺） | `**定理1.1**：` |
| 例 | **按节各自重编** | §5.1 内 例1, 例2, …；§5.2 内又从 例1 起 | `> **例1**：` |

与 skill 默认的**三级** `章.节-号`（N.S-N）正则**完全不兼容**：
三级正则会把公式碎片 / 集合枚举误读成 `1.1-1`、`1.2-3`、`1.3-5` 之类的
负偏移幻影键（例如把 `((1-1.1+1))` 读成 `1.1-1`，把 `{1，2，3，4，5}不是A的真子集`
读成 `1.2-3`）。这些键永远不会出现在 .md 中，于是 `verify/verify_chapter.py`
把它们报成永远无法消除的 `TRULY MISSING`。

### 处理决策（已内置到 skill）
- `extract/extract_items.py` 对两级书按 `ordinal` 路由（`<book>/_extract/verify_config.json` 设 `"ordinal": 2`）：直接按 `标签 章.号` 提取，
  产出 `定义1.1`、`定理1.1` 等键，**不再使用三级 N.S-N 正则**，从根本上杜绝幻影键（命令行亦可显式 `extract/extract_items.py 1 20 82 _extract --ordinal 2`）。
- `verify/verify_chapter.py` 的 `keys_in_md` 同样支持两级：解析 `**定义1.1**：` 等 bold 键；
  编号模式由 `<book>/_extract/verify_config.json` 的 `ordinal` 决定，`--all` 时自动启用。
- **例的完整性**不进 `extract_items`/`verify` 的 A/B 层（例按节重编、跨节重复），
  交给专门的 `extract/scan_items.py` 做独立连续性核验。

### 命令
```bash
# 提取（两级；ordinal 也可在 verify_config.json 里设，无需命令行）
python extract/extract_items.py 1 20 82 _extract --ordinal 2
# 校验（两级，全书；ordinal 来自 verify_config.json）
python verify/verify_chapter.py --all _extract <book_dir>
# 独立连续性核验（权威）
python extract/scan_items.py 1 20 82 _extract
```

---

## 2. OCR 对 `§` 的漏识

本项目实测到的现象：

| 真值 | OCR 误读 | 出现位置 | 处理 |
|---|---|---|---|
| §1.6 | `81.6` | Ch1 尾部 | D 层 `D_SEC_HEAD_A` 已容忍 `8` 前缀；scan_items 的 sec_re 容忍 `(?:§\|8)?` |
| §2.5 | `S2.5` | Ch2 | D 层 `D_SEC_HEAD_A` 容忍 `8`；scan_items 的 sec_re 容忍 `(?:§\|S)?` |
| 普通 § | `§ 6.6`（中间有空格）| 多章 | D 层 `D_SEC_HEAD_C` 处理短块 |

> 注意：`extract/scan_items.py` 的 `sec_re` 只容错 `§/S/8` 三种开头；若某节在扫描输出中
> 缺失，先用 `--verbose` 看原始文本，再人工确认是否又是一种新的 OCR 变形。

---

## 3. 三级编号（默认，大多数书）

`章.节-号`（N.S-N），例如 `1.1-2`、`3.2-7`。这是 `extract/extract_items.py` 的默认
编号模式（`ordinal=3`，三级），`verify/verify_chapter.py` 也默认三级。绝大多数教材（含英文书）
属此类，无需任何额外配置。

---

## 4. 判定树：遇到新书先看编号

> 🔴 **`verify_config.json` 是校验的硬性前置（规则 H），但生成时机在「源语言全部初稿完成后」**：先写完**源语言**全部章节初稿（规则 E 阶段 1），再依据**源语言版** `.md` 生成 `<book>/_extract/verify_config.json`（至少含 `ordinal`），然后才批量校验（阶段 3）。**翻译派生版不参与配置生成。** 文件存在但缺 `ordinal` 会令 `verify_chapter.py` / `scan_skeleton.py` 直接报错（exit 2）；文件缺失仅警告并沿用默认 ordinal=3（写初稿阶段可继续，存量书兼容）。可用 `python verify/make_config.py <extract_dir>` 半自动探测 + 人工核对生成起始配置。**🚫 禁止「写完一章就校验一章」**——配置与校验统一在源语言初稿全部完成后批量进行。

```
读 TOC / 抽一页原文，看编号长什么样？（判定树只用于确定 ordinal，配置在源语言初稿全部完成后统一生成）
│
├─ 编号形如  定义1.1 / 定理1.1 / 引理1.2 …（只有 章.号 两级，且 定理族共用一个连续号）
│     → 两级 + 双计数器（周民强型）
│     → 源语言初稿全部完成后，在 verify_config.json 设 "ordinal": 2
│     → 批量校验后用 extract/scan_items.py 做连续性核验
│
├─ 编号形如  1.1-2 / 3.2-7（三级 章.节-号）
│     → 默认 three-level
│     → 源语言初稿全部完成后，在 verify_config.json 设 "ordinal": 3（默认可不写，但仍建议显式）
│
├─ 英文书编号形如  Theorem 1.2 / Lemma 3.4（EN 两级，无章号位）
│     → 源语言初稿全部完成后，在 verify_config.json 设 "ordinal": 4
│
├─ 罗马数字章号  I.2.3 / II.1.1 …（章号是 I/II/III…）
│     → 源语言初稿全部完成后，在 verify_config.json 设 "ordinal": 5
│
├─ Gelfand–Manin 风格  §2 标题 + 条目从 1 起号（gm，两级、章内本地）
│     → 源语言初稿全部完成后，在 verify_config.json 设 "ordinal": 6
│
├─ Fraleigh 风格  按节编号、无章号位（fraleigh，两级）
│     → 源语言初稿全部完成后，在 verify_config.json 设 "ordinal": 7
│
└─ 不确定 / 跑 verify 出现负偏移的 "1.x-y"（x、y 比真实条目小很多）
      → 几乎肯定是三级正则误吃公式/枚举
      → 先用 extract/scan_items.py 或人工核对确认真实条目齐全
      → 若确为两级书：设 ordinal=2（两级）
      → 若确为三级书但有几个真·OCR 噪点：用 --ignore 登记
        （写入 _extract/ignore_ch{N}.json，附 ignore_ch{N}.md 举证）
```

---

## 5. `--ignore` 噪声键登记规范

仅用于**已确认是 OCR 乱码 / 公式碎片**、且无法修复的交叉引用键。它**只影响 A/B 层**，
**不影响 C 层 KaTeX 与 D 层整节校验**（安全性由 `verify/verify_chapter.py` 保证）。

- 文件：`_extract/ignore_ch{N}.json`，内容 JSON 列表或字典：
  ```json
  ["1.1-1", "1.2-3", "1.3-5"]
  ```
  或带理由的字典：
  ```json
  {"1.1-1": "公式碎片 ((1-1.1+1)) 误读", "1.2-3": "集合枚举 {1,2,3,4,5}"}
  ```
- 配套写 `ignore_ch{N}.md`：贴出原始文本片段，证明这些键是噪声而非漏写条目。
- `verify/verify_chapter.py` 会自动合并 `ignore_ch{N}.json`，无需手动传 `--ignore`。

---

## 6. 书级配置与小节层级（verify_config.json）

> 🔴 **本规则由 SKILL.md「规则 H」强制前置**：`verify_config.json` 配置（ordinal / section_types / section_depths / language）由**源语言**内容派生，是 `verify` 的硬性前置。配置在**源语言全部初稿完成后**（规则 E 阶段 2）依据**源语言版** `.md` 生成，至少含 `ordinal`；**翻译版不参与配置生成**。写初稿阶段（阶段 1）不要求配置就位（scan_skeleton 遇缺失仅告警 + 默认 ordinal=3），但任何 `verify` 跑起来前配置必须完整。

### 6.1 `ordinal` —— 必填（1–7）

`ordinal` 是编号风格选择器（整数编码，见 `lib/config.py` 的 `ORDINAL_*` 常量）。它是**必填**字段；文件存在但缺 `ordinal` 会令 `verify_chapter.py` / `scan_skeleton.py` 直接报 `[CONFIG]` 错误并 exit 2。判定树（§4）每个分支都对应一个 `ordinal` 值：

| 编号形态 | `ordinal` | 说明 |
|---|---|---|
| 两级 + 双计数器（周民强型） | `2` | 定义1.1 / 定理1.1 共用连续号 |
| 三级 章.节-号（默认） | `3` | 1.1-2 / 3.2-7 |
| EN 两级（Theorem 1.2） | `4` | 无章号位 |
| 罗马数字章号（I.2.3） | `5` | 章号为 I/II/III… |
| gm（§2 + 章内本地号） | `6` | Gelfand–Manin 风格 |
| fraleigh（按节编号） | `7` | 无章号位 |

### 6.2 `section_types` / `section_depths` —— 仅四级（及更深）书显式声明

绝大多数书**不需要**手写这两个字段：省略时由 `ordinal` 自动反推（见下表的「默认反推」），D 层据此校验小节层级连续性。`from_dict` 还会兜底清洗（长度不等 / 含 <1 / 含非法角色码 → 回退到反推值）。

**只有在书的小节层级深于 `ordinal` 默认反推时**，才需在 `verify_config.json` 显式声明。典型例子：四级子小节书（编号形如 `1.1.1.1`），其 `ordinal=3`（三级默认反推只到 1.1.1），要校验到第四级必须手写：

```json
{
  "ordinal": 3,
  "section_types": [1, 2, 3, 4],
  "section_depths": [1, 2, 3, 4]
}
```

反推表（`ordinal` → 默认 `section_types` / `section_depths`，即 D 层默认校验层级）：

| `ordinal` | 名称 | 默认 `section_types` | 默认 `section_depths` |
|---|---|---|---|
| 1 | single | `[1]` | `[1]` |
| 2 | two_level | `[1, 2]` | `[1, 2]` |
| 3 | three_level | `[1, 2, 3]` | `[1, 2, 3]` |
| 4 | en | `[1, 2]` | `[1, 2]` |
| 5 | roman | `[1, 2, 3]` | `[1, 2, 3]` |
| 6 | gm | `[1, 2]` | `[1, 2]` |
| 7 | fraleigh | `[1, 2]` | `[1, 2]` |

> 角色码 `section_types` ∈ `{1=章, 2=节, 3=小节, 4=子小节}`；`section_depths` 与 `section_types` 等长、各分量 ≥1、且 `section_depths[0]==1`。若显式给出但不合法（长度不等 / 含 <1 / 含非法角色码 / 首分量非 1），`require_complete()` 会直接报 `[CONFIG]` 硬错误。
>
> ⚠️ 存量书（无 `verify_config.json`）跑 `verify` / `scan_skeleton` 只会有 WARNING 并沿用默认 ordinal=3，不阻断；新流程之所以允许沿用默认，是为了**不误伤存量书**，但规则 H 要求**新建书必须显式填写**，不得依赖静默默认值。

### 6.3 生成 / 校验工具

- `python verify/make_config.py <extract_dir>` —— best-effort 生成起始配置（判定不清时仍以本判定树为准，人工核对）。
- `verify_chapter.py` / `scan_skeleton.py` 入口均经 `ConfigLoader.require_complete()` 校验完整性（规则 H 主防线在**工作流规则**，不在单脚本行为上）。
