# Flow Gate（流程强制顺序执行）—— book-summarizer 死命令机制

> **铁律**：上一步没做完，机械上不能进入下一步。任何跳步都会被闸控拦截，
> 不会"悄悄跑完但地基是错的"。本文件是该机制的**唯一权威说明**。

## 为什么需要它

`extract.md` / `config_setting.md` / `mm_repair.md` 里写满了 🔴 顺序规则
（"图检测前必须 config 先行"、"structure 为 extract 末尾"、"MM Repair 完成
才能 config"），但规则靠 agent 自觉遵守——一旦 agent 没在 gate 处停下、或用
**手写 config 绕过护栏**（真实事故：Fraleigh 的 `verify_config.json` 是 agent
绕过 `make_config` 护栏手搓的，导致 50 章全按错误基准被校验），全盘皆输。

本机制把"护栏"从**软提醒 / 退化默认**升级为**代码级硬拒绝 + 下游复核拒绝**，
让违规文件根本进不了下一阶段。

## 机制（四层）

### 1. 证明账本（ledger）
- 位置：`<extract_dir>/.flow_gate.json`（单卷书即 `<book_dir>/_extract/.flow_gate.json`）
- 内容：`{steps: { "<flow>.<step>": {done, ts, iso, evidence} }}`
- **仅 `flow_runner.py` 在证据复核通过后写 `done`**；任何脚本/agent 不得手填。
- 🔴 **上下册 / 多册书**：每册的 extract_dir 为 `<书目录>/_extract/<册>`，账本随之
  分册隔离；`flow_runner` 每册操作须传 `--extract <书目录>/_extract/<册>`（`status /
  next / verify / mark / run / bootstrap` 均支持），book_dir 仍传书级目录（.md 落位
  处）。

### 2. 顺序闸（flow_runner 编排器）
- `tools/flow_runner.py` 是推进任何步骤的**唯一 sanctioned 入口**。
- 进入 `flow X` 的 `step S` 前：
  - `require_flow_prereqs`：其上游 flow 的末步必须已完成（prep → extract →
    write_source）；
  - `require_ordered`：`flow X` 内 `S` 之前的所有步骤必须已 `done`。
- 二者任一不满足 → 抛 `FlowGateError`，**硬拒绝，禁止跳步**。

### 3. 关键加载器 self-assert（防御纵深）
即使 agent 忘了走 flow_runner、**直接调用脚本**，以下入口也会在启动时 self-
assert 上游完成，照样被挡：
- `config/verify_config/make_config.py`：缺 `_extraction_done.json` → **硬退出、绝不写
  退化默认文件**（关掉"绕过护栏"的后门）。
- `config/verify_config/verify_config.py` 的 `ConfigLoader`：加载 `verify_config.json`
  时要求 `_extraction_done.json` 存在，否则 `ConfigError` BLOCKED——**手写 config
  再也无法被下游消费**。
- `flows/extract/mm_repair/script/mm_repair_apply.py`：仅在「条目全 resolved + 每页
  有 mm 标记」**真完成时**写出 `_extraction_done.json`；否则告警不写（杜绝手 touch
  假绿 / "apply 已跑但大量未修"被当完成）。
- `flows/write-source/structure/script/build_structure.py`：启动前要求 `_extraction_done.json`
  （同时覆盖其 Evans 字母章号降级分支）。
- `verify/script/verify_chapter.py`：经 `ConfigLoader` 要求 `_extraction_done.json`，
  并额外要求分章契约 `book_structure/` 下至少一章（verify 的编号项基准；旧版全书单文件已废弃）。

### 4. 证明戳（provenance）
- `make_config.py` 生成的 `verify_config.json` 带 `_provenance.generated_by ==
  "make_config.py"`。`ConfigLoader` 据此 + `_extraction_done.json` 双重识别"合法来源"，
  手写文件无此戳即被拒。

## 规范流程顺序（单一真源：flows/_flow_contract.py 的 FLOW_ORDER）

```
prep:            [env]
extract:         [place_pdf, extract_text, mm_repair]
write_source:    [config, build_chapter_map, figure_detection, structure,
                  draft, write_chapters, translate_chapters,
                  merge_all, verify_source]
```

> `config` 步骤包含两件事（见 config_setting.md）：① 建章节映射
> `chapter_map.json`（MM Repair 完成后统一生成，只建一次）；② `make_config.py`
> 生成 `verify_config.json`。旧 `extract.chapter_map` 独立步骤已并入 `config`。
> 🔴 **`build_chapter_map` 一步生成正确页码（代替旧的两步法）**：chapter_map 由
> agent 只填结构（章号 + 中/英章名 + 附录标记），再经
> `python tools/flow_runner.py run <book_dir> write_source build_chapter_map`
> 从 OCR 证据自动算出每章 `start`/`end` 写回，并产出 `chapter_map.build_report.md`
> 供 agent 判断。不再有独立的"校验脚本闸步"；agent 对报告的判断是强制环节
> （UNDTECTED 章手动补正后重跑），全章 `start`/`end` 非 null 才放行后续步骤。

## 每步"完成"的判据（物理证据，见 flows/_flow_contract.py）

不看账本、只看磁盘产物：
- `extract_text`：`page_*.json` 连续落盘 1..N 无空洞。
- `mm_repair`：`_extraction_done.json` 存在 **且** manifest 条目全 resolved **且**
  每页 `page_*.json` 有 `mm_repaired/mm_reviewed/mm_converted` 标记（legacy 缺
  marker 时回退物理核对）。
- `config`：`chapter_map.json` 存在且含章节 **且** `verify_config.json` 存在且
  含 `ordinal` 数组。
- `build_chapter_map`：`tools/build_chapter_map.py` 一步生成正确页码后，`chapter_map.json`
  全章 `start`/`end` 均非 null **且** `chapter_map.build_report.md` 已生成（证明生成器
  已跑、agent 有报告可判）。任一章 `start`/`end` 仍空（UNDTECTED 未补正）禁止 mark，
  figure/structure 等下游步骤的顺序闸随之硬拒；agent 对报告的判断是强制环节。
- `figure_detection`：`figure_index.json` 存在。
- `structure`：`chapter_map` 全部章节均有分章骨架 `book_structure/ch{N}.json`（附录 `appendix{X}.json`）**且** 每章完整性报告 `completeness_reports/ch{N}_*.json` 的 `gate.passed == true`（🔴 structure.md 第 2–4 步闸门）。
- `draft`：每章 `book_structure/ch{N}.json`（附录 `appendix{X}.json`）+ `units/ch{N}/manifest.json` 齐备且 manifest 不早于契约（内容化分章契约 + 每 item 一单元拆分；内容完整性闸门 `check_content_completeness.py` PASS）。
- `write_chapters`：每章「逐单元改好 + 门控通过」机械核对（🔴 2026-08-31 重构 / 2026-09-03 拼接移出，脱离单元 / 门控未过 = 硬拒）——每章单元门控通过：`units/ch{N}/` 中每个单元文件存在、首行 DONE、**单元级质量校验通过**（= 每个编号项都改对、一个不漏，`gate_units.py` 判定；2026-09-01 起判断标准是「写对」而非「重写」，check_unit_quality.py 全部引用 verify 已有检测：`check_katex.check_display_math_closure`（$$ 闭合）/ `katex_heuristics`（裸命令·裸 Unicode 字符·裸箭头）/ `verbose_gates.check_verbose_proofs`（证明过长）/ `struct_labels`（结构标签）/ `format_verify.check_example_blockquote_lines`（example blockquote）/ OCR 残留薄封装）。最终 md 存在 + 契约骨架节 / 编号项在位核对移至 `merge_all` 步。
- `translate_chapters`：① 翻译清单已初始化（`units-translate/ch{N}/manifest.json`，翻译步内 `init_translate_units.py` 生成——元数据 + src_hash，不复制正文；中文源书自动跳过）；② 翻译单元门控通过（`gate_units --units-dir units-translate`，缺文件/未译/质量差即拒）；③ `check_translate_parity.py` 1:1 同构闸通过（单元序列 / \tag / 图片 / 编号项标签与源单元逐一相等）。
- `merge_all`：每章源语言 + 翻译语言两组最终 md 存在（`merge_units.py --all` 产物），且结构契约全部 section 名 + 编号项 `name` 在两组 md 中在位（漏项当场拦截）。中文源书只要求源语言（中文）一组。
- `draft` 证据补充：内容完整性闸门（`verify/script/check_content_completeness.py`）PASS——描述信息 / 证明 / 图片 / 文字公式块齐备。
- `verify_source`：流程末步，`verify_chapter.py --all` 对**源语言 + 翻译语言两组 md** 确认 `exit 0`（`verify PASS + KaTeX OK`；中文源书只有一组中文 md）。🔴 **仅按章数自报或仅跑过 `write_chapters` 不算通过**。

> **适用范围**：翻译步骤（`translate_chapters`）**仅适用于英文书**（源=英文 `ChapterN_*.md` → 翻译中文）。**中文书无翻译阶段**：翻译证据自动跳过，`write_source` 全部步骤完成即为全书完成（中文书源=`第N章_*.md`，无独立翻译版）。

## 标准工作流（agent 必须遵守）

```bash
# 1) 看当前进度 / 下一个可执行步骤
python tools/flow_runner.py status <book_dir>
python tools/flow_runner.py next   <book_dir>

# 2) scripted 步（extract_text / write_source 的
#    config/figure/structure/draft/verify）直接 run：
python tools/flow_runner.py run <book_dir> write_source config --pdf "<pdf>"
python tools/flow_runner.py run <book_dir> write_source draft

# 3) agent 步（mm_repair 视觉 / 写作 / 翻译）按 flow 文档做完后：
python tools/flow_runner.py verify <book_dir> extract mm_repair   # 证据复核
python tools/flow_runner.py mark   <book_dir> extract mm_repair   # 落账

# 4) 历史已合规完成之书一次性回填（依据物理证据，绝不伪造）：
python tools/flow_runner.py bootstrap <book_dir>
```

## ❌ 禁止清单（违反 = 违规，全盘风险）

- ❌ 在 `_extraction_done.json` 不存在时跑 `make_config.py` / `build_structure.py` /
  `verify_chapter.py`（它们会硬拒，但你**不应试图绕过**）。
- ❌ 手写 / 手改 `verify_config.json` 充当总结地基（无 `_provenance` 戳，下游必拒）。
- ❌ 提前手 touch `_extraction_done.json` 冒充 MM Repair 完成（它只能由
  `mm_repair_apply.py` 真完成写出，或 `bootstrap` 依物理证据补写）。
- ❌ 跳步：未跑完本 flow 前置步骤就进下一步（顺序闸硬拒）。
- ❌ **跳过单元粒度直接凭整章 md 翻译**，或**未过同构闸（`check_translate_parity.py`）就拼接翻译版**（翻译闸详见 [`write-source`](write-source/write-source.md) 步骤 6）。
- ❌ 手填 `_extract/.flow_gate.json` 账本（仅 `flow_runner` 经证据复核后写）。
- ❌ 把"文本 100% 落盘 / Pipeline finished 日志 / 后台进程结束"当作"MM Repair 完成"。
