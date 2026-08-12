# data-provider 层（EXTRACT · `data_provider`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="EXTRACT"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`data-provider`（`data_provider`）。

## 目的

## 一句话目的
提供原始 JSON 数据（提取条目 / 键集），是后续所有层的输入源；必跑、永不可禁用。
## 前置

- `<book>/_extract/verify_config.json` 完整合法。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`。

## 步骤

## 语义与检查内容
- 扫描 `_extract` 的 `page_*.json`，填 `ctx.items` / `ctx.entry_keys` / `ctx.all_keys`。
- 算 `ignored_hit` **第一段（stage1）** 写入 `ctx`（最终值由 B 层第二段回写，见下）。
- 必须原样 port 英文书分支（`ctx.config.ordinal == ORDINAL_EN`：按章过滤前向引用、key 规范化成中文形式；md 侧 `entry_keys`/`all_keys` 限制到当前章）。
- 三段逻辑（three-level / two-level / en）必须完整搬运，否则 EN 书整体漂移。
## 本阶段规则

## 阻断性 / 可修复
- 本身不是 pass/fail 判定层，但 `extract_dir` 缺失 / 无 `page_*.json` → 数据缺失 → FAIL。
- **永不可禁用**（manager 特判 `code != 'EXTRACT'`）。
## 出口

- 数据缺失（`extract_dir` 无 `page_*.json`）→ FAIL；**永不可禁用**。

## 相关代码

- 实现：`script/data_provider.py`
  - `code="EXTRACT"`，`order=0`，`auto_fixable=False`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

数据 provider，被所有层依赖；无子流程。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
items
entry_keys
warnings
```

## 实现备注

## 实现（`script/data_provider.py`）
- `code = 'EXTRACT'`，`order = 0`，`auto_fixable = False`。
- `all_keys` 为新增键、**不进入旧字节契约**（不影响 `print_result` 输出）。
- `ignored_hit` 两段式：EXTRACT 算 stage1 → B 层在产出 `blocking` 后做第二段 regex 抑制并回写最终 `ignored_hit`（manager 按 `order` 合并、B 覆盖 EXTRACT）。禁止只由 EXTRACT 一次性算完。
