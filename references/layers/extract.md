# EXTRACT 层 — 数据 provider

> 本文件是 **EXTRACT 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
提供原始 JSON 数据（提取条目 / 键集），是后续所有层的输入源；必跑、永不可禁用。

## 语义与检查内容
- 扫描 `_extract` 的 `page_*.json`，填 `ctx.items` / `ctx.entry_keys` / `ctx.all_keys`。
- 算 `ignored_hit` **第一段（stage1）** 写入 `ctx`（最终值由 B 层第二段回写，见下）。
- 必须原样 port 英文书分支（`ctx.config.ordinal == ORDINAL_EN`：按章过滤前向引用、key 规范化成中文形式；md 侧 `entry_keys`/`all_keys` 限制到当前章）。
- 三段逻辑（three-level / two-level / en）必须完整搬运，否则 EN 书整体漂移。

## 阻断性 / 可修复
- 本身不是 pass/fail 判定层，但 `extract_dir` 缺失 / 无 `page_*.json` → 数据缺失 → FAIL。
- **永不可禁用**（manager 特判 `code != 'EXTRACT'`）。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
items
entry_keys
```

## 实现（`verify/layers/extract_layer.py`）
- `code = 'EXTRACT'`，`order = 0`，`auto_fixable = False`。
- `all_keys` 为新增键、**不进入旧字节契约**（不影响 `print_result` 输出）。
- `ignored_hit` 两段式：EXTRACT 算 stage1 → B 层在产出 `blocking` 后做第二段 regex 抑制并回写最终 `ignored_hit`（manager 按 `order` 合并、B 覆盖 EXTRACT）。禁止只由 EXTRACT 一次性算完。
