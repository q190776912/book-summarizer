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
    write_source → derive）；
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
- `flows/extract/structure/script/build_structure.py`：启动前要求 `_extraction_done.json`
  （同时覆盖其 Evans 字母章号降级分支）。
- `verify/script/verify_chapter.py`：经 `ConfigLoader` 要求 `_extraction_done.json`，
  并额外要求 `book_structure.json` 存在（verify 的编号项基准）。

### 4. 证明戳（provenance）
- `make_config.py` 生成的 `verify_config.json` 带 `_provenance.generated_by ==
  "make_config.py"`。`ConfigLoader` 据此 + `_extraction_done.json` 双重识别"合法来源"，
  手写文件无此戳即被拒。

## 规范流程顺序（单一真源：flows/_flow_contract.py 的 FLOW_ORDER）

```
prep:            [env]
extract:         [place_pdf, extract_text, mm_repair,
                  config, figure_detection, structure]
write_source:    [write_chapters, embed_figures, verify_source]
derive:          [translate, verify_cn]
```

> `config` 步骤包含两件事（见 config_setting.md）：① 建章节映射
> `chapter_map.json`（MM Repair 完成后统一生成，只建一次）；② `make_config.py`
> 生成 `verify_config.json`。旧 `extract.chapter_map` 独立步骤已并入 `config`。

## 每步"完成"的判据（物理证据，见 flows/_flow_contract.py）

不看账本、只看磁盘产物：
- `extract_text`：`page_*.json` 连续落盘 1..N 无空洞。
- `mm_repair`：`_extraction_done.json` 存在 **且** manifest 条目全 resolved **且**
  每页 `page_*.json` 有 `mm_repaired/mm_reviewed/mm_converted` 标记（legacy 缺
  marker 时回退物理核对）。
- `config`：`chapter_map.json` 存在且含章节 **且** `verify_config.json` 存在且
  含 `ordinal` 数组。
- `figure_detection`：`figure_index.json` 存在。
- `structure`：`book_structure.json` 存在且含章节节点。
- `write_chapters`：已写源语言章数 == chapter_map 章数。
- `verify_source` / `verify_cn`：agent 跑 `verify_chapter.py --all` 确认 `exit 0`。

## 标准工作流（agent 必须遵守）

```bash
# 1) 看当前进度 / 下一个可执行步骤
python tools/flow_runner.py status <book_dir>
python tools/flow_runner.py next   <book_dir>

# 2) scripted 步（extract_text/config/figure/structure/embed/verify）直接 run：
python tools/flow_runner.py run <book_dir> extract config --pdf "<pdf>"

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
- ❌ 手填 `_extract/.flow_gate.json` 账本（仅 `flow_runner` 经证据复核后写）。
- ❌ 把"文本 100% 落盘 / Pipeline finished 日志 / 后台进程结束"当作"MM Repair 完成"。
