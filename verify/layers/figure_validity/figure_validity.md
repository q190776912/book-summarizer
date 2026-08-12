# figure-validity 层（F · `figure_validity`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="F"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`figure-validity`（`figure_validity`）。

## 目的

## 一句话目的
图有效性：裁剪图能否正常解码。
## 前置

- `<book>/_extract/verify_config.json` 完整合法。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

## 语义与检查内容
- 用 `np.fromfile` + `cv2.imdecode` 逐一打开裁剪图。
- **INVALID（阻断 FAIL）**：缺失文件 / 无法解码 / 单边 <20px。
- **SUSPICIOUS（仅 WARN）**：近空白（灰度方差 <50，疑似误检文字块）。
## 本阶段规则

## 阻断性 / 可修复
- 有图时 `fig_invalid` 非空 → 阻断 FAIL。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；不可 `--fix`，须回写作阶段修正。

## 相关代码

- 实现：`script/figure_validity.py`
  - `code="F"`，`order=6`，`auto_fixable=False`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
fig_invalid
fig_invalid_warn
```

## 实现备注

## 实现（`script/figure_validity.py`）
- `code = 'F'`，`order = 6`，`auto_fixable = False`。
- 与 E 同前提（无 `figure_index.json` 则 SKIP）。底层返回 None 必须 emit 空列表。
