# S 层 — SECTION BOUNDARY（section_boundary）

> 本文件是 **S 层** 的唯一权威详情（SSOT）。语义 / 判据 / 阈值 / 实现只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **注册机制**：脚本 `verify/section_boundary/script/section_boundary.py`，由 `verify/script/register_all.py` 按裸名扫描 `verify/*/script/` 自动发现并注册。`code = 'S'`，`order = 2`，`auto_fixable = False`。

```contract-keys
section_boundary_findings
section_boundary_stats
```

## 目的

检测**章节边界内容错位**——上一节的正文尾巴被挂到下一节标题之后、下一节的
开头被留在上一节末尾、同一段内容在边界两侧各出现一次。根因是**按页 / 按单元
切分**时把印刷页边界当成了节边界：

- 节头落在一页中间，切分脚本按页切断，于是「上一节最后一段」和「下一节的
  标题」一起进了下一页的单元；
- 或反过来，下一节的开头正文留在上一单元，标题单独进了下一单元；
- 或者同一段文本在两侧各落一份（常见于结构化证明块 + 普通正文）。

这类缺陷**D 层看不见**（节头都在、节号连续），**B 层也看不见**（条目编号
没有跳号），但读者会在新节标题下先读到上一节的结尾，理解顺序被打断。S 层
补的就是这条缝隙。本层只报 **WARN、非阻断**：边界错位通常是单元/manifest
层面的搬移问题，自动改写风险高，须人工确认后整块修复。

## 前置

- 待校验语言的交付 md 已生成（合并稿或按节拆分文件均可）。
- 页面几何信号是**可选证据**：`_extract/page_*.json` 与分章契约
  `_extract/book_structure/{chN,appendixX}.json` 存在时才启用；缺失时只跑
  文本信号，不报错、不猜测。
- 本层对书名 / 语言 / 编号风格无假设：`## § 1.2 Title`、`## 1.2 Title`
  以及无编号标题都接受；一级标题（章名）与以条目标签开头的标题
  （`### Theorem 1.2`）不作为节边界。

## 步骤 / 判据

对每个节 / 小节标题，取「上一节正文块」与「本节正文块」，依次跑：

### 文本信号（任何书）

| kind | 判据 |
|------|------|
| `split_sentence` | 上一块末尾没有终止标点，且下一块以小写词 / 逗号 / 数学片段开头，或上一块以 `,;:=` 等开启符结尾 → 句子被节头切断 |
| `heading_late` | 节标题的粗体 run-in（`**Title.** 正文…`）出现在节头之前，且其后已有 ≥120 字正文 |
| `heading_early` | 节头之后先出现别的条目 / 证明，之后才出现本节自己的 run-in 标题（且前面 ≥80 字） |
| `lowercase_start` | 节头后第一段以小写字母开头（英文） |
| `backref_opening` | 节头后第一段以 `Thus / Therefore / 因此 / 所以 …` 等回指词开头 |
| `math_fragment` | 节头后第一段是 `$…$ be/with/and…` 形式，说明句子从中间开始 |
| `dup_prev` | 节头后第一段（≥40 字）与上一节文本 ≥90% 相同 |
| `dup_earlier` | 节头后第一段（≥80 字）与更早章节文本 ≥80% 相同 |
| `dup_across` | 节头后连续 1–3 块（合计 ≥200 字）与上一节文本 ≥62% 相同 |
| `dup_within` | 同一节内两块（各 ≥100 字）相似度 ≥0.9 |
| `orphan_proof` | 节头后开头就是证明块，且前面没有条目陈述 |
| `late_start` | 节头后先出现条目 / 证明，≥120 字后才出现明确导语（`In this section` / `本节…`） |
| `stranded_item` | 节头后第一个条目的编号不大于上一节同层级最大编号 |
| `dup_heading` | 同一章内标题重复 |

阈值常量集中在 `lib/section_boundary.py`；`_title_match` 只做**整词**
相等 / 前缀匹配，绝不做子串匹配（`Linear Equations` 不得命中
`Quasilinear Equations`）。

### 页面几何信号（有 page JSON 时）

把上述「上一块 / 下一块」的文本回查到 PDF 页面文本块坐标：

1. 只在章契约页范围内读 `page_*.json`；`y < 140` 的块视为运行页眉 /
   页码，**不参与匹配**。
2. 节标题按归一化文本**精确匹配**（允许末尾 ≤6 字符的 OCR 残差）。
3. 若节头后第一块的印刷位置在节头**之前** → `heading_early`。
4. 若节头前最后一块的印刷位置在节头**之后** → `heading_late`。
5. `desc` 单元可能把多个印刷段焊成一块：整块头部匹配在节头前不代表块尾
   也在节头前，故再取块尾 160/100/60 字（含去数学后的文本）回查；块尾
   印在节头之后 → `heading_late`（「焊死的下一节开头」信号）。

匹配不到页面块 = 没有证据，直接跳过；绝不因为查不到就报问题。

## 本阶段规则

- **只报 WARN，不阻断**：finding 进 `section_boundary_findings`，不增加
  `problems`，不改变 PASS/FAIL。`section_boundary_stats` 一并落盘
  （`verify_detail` 旁路），便于批量排查。
- **检测不是修复**：边界错位应按「整块搬移」修复——把上一节尾巴搬回上一
  单元，或把下一节开头搬进下一单元；改单元文件后必须同步该章
  `units*/manifest.json` 并重跑 `sync_delivery_from_units.py` /
  `resync_src_hash.py`。禁止直接手改交付 md 后再让 manifest 漂移。
- **页面几何只做证据**：节头匹配不到、页面 JSON 缺失、语言不同，都不构成
  报错理由；文本信号仍然独立生效。
- **可重复**：本层不写任何文件，不修改 `ctx`，同样输入必得同样输出。

## 出口条件

- 本层无阻断出口：`section_boundary_findings` 为空表示未发现边界错位；
  非空时按 WARN 处理，由人工确认后修复。
- `section_boundary_stats` 必须始终可审计：`files` / `lines` / `headings` /
  `findings` / `high` / `page_geometry` 六项齐全。读不到交付 md 时本层
  fail-closed 抛错（无证据不得静音成 PASS）。

## 相关代码（路径相对 skill 根目录）

- `lib/section_boundary.py`：检测核心（文本信号 + `PageCtx` 页面几何 +
  章文件发现 / 合并行号 → 真实文件行号映射）。
- `verify/section_boundary/script/section_boundary.py`：`VerifyLayer` 适配器。
- `tools/audit_section_boundary.py`：只读审计 CLI（全书 / 单章 / 单语言，
  可输出 JSON）。
- `verify/tests/test_section_boundary.py`：判据测试。

## 子流程

- 无。本层不调用其它校验层，也不被其它层调用。
