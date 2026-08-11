# katex-validation 层（C · `katex_validation`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="C"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`katex-validation`（`katex_validation`）。

## 目的

## 一句话目的
运行 `../../../flows/write-source/format/script/format/check_katex.py` 真实 KaTeX 渲染，抓出渲染失败。
## 触发

由 `verify` 总流程（见 [`../../verify.md`](../../verify.md) 与注册表 [`..`](.)）
按 `order` 自动调度；亦可被其他消费者（如 `../../../flows/verify-source`、`../../../flows/derive-translate`
或外部 skill）单独引用本子流程，针对单章 / 单文件运行该校验层。

## 前置

- `<book>/_extract/verify_config.json` 完整合法（config_setting 流程 规则1）。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

## 语义与检查内容
- 调用 `../../../flows/write-source/format/script/format/check_katex.py`（内部 `katex_validate.js` 真实渲染），抓非法命令、括号不配对等真正语法错误。
- 具体禁忌清单（转义定界符 `$$`、缺空行、行内 `$` 未配对、不支持宏、嵌套块引用 `> > $$` 等）由 `../../../flows/write-source/format/script/format/check_katex.py` 真实渲染核对（详见本文件「实现」段）。
- `check_katex.py --fix` 可自动修正前几项（转义定界符、单行展示公式、缺空行、嵌套块引用展示公式）；其余需手动。
## 本阶段规则

## 阻断性 / 可修复
- `katex_errors` 非空 → 阻断 FAIL。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；不可 `--fix`，须回写作阶段修正。

## 相关代码

- 实现：`script/katex_validation.py`
  - `code="C"`，`order=4`，`auto_fixable=False`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
katex_errors
katex_lines
```

## 实现备注

## 实现（`script/katex_validation.py`）
- `code = 'C'`，`order = 4`，`auto_fixable = False`（KaTeX 修复由 `check_katex.py --fix` 单独做，不经 verify manager 的 `fix`）。
- 通过 `subprocess` 调 `../../../flows/write-source/format/script/format/check_katex.py`。
