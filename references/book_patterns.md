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

```
读 TOC / 抽一页原文，看编号长什么样？
│
├─ 编号形如  定义1.1 / 定理1.1 / 引理1.2 …（只有 章.号 两级，且 定理族共用一个连续号）
│     → 两级 + 双计数器（周民强型）
│     → 在 <book>/_extract/verify_config.json 设 "ordinal": 2
│     → 写章后用 extract/scan_items.py 做连续性核验
│
├─ 编号形如  1.1-2 / 3.2-7（三级 章.节-号）
│     → 默认 three-level，无需配置
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
