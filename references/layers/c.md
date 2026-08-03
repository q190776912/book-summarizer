# C 层 — KATEX ERRORS

> 本文件是 **C 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
运行 `format/check_katex.py` 真实 KaTeX 渲染，抓出渲染失败。

## 语义与检查内容
- 调用 `format/check_katex.py`（内部 `katex_validate.js` 真实渲染），抓非法命令、括号不配对等真正语法错误。
- 具体禁忌清单（转义定界符 `$$`、缺空行、行内 `$` 未配对、不支持宏、嵌套块引用 `> > $$` 等）见 [`../formatting.md`](../formatting.md) 的 KaTeX 规则。
- `check_katex.py --fix` 可自动修正前几项（转义定界符、单行展示公式、缺空行、嵌套块引用展示公式）；其余需手动。

## 阻断性 / 可修复
- `katex_errors` 非空 → 阻断 FAIL。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
katex_errors
katex_lines
```

## 实现（`verify/layers/c_layer.py`）
- `code = 'C'`，`order = 4`，`auto_fixable = False`（KaTeX 修复由 `check_katex.py --fix` 单独做，不经 verify manager 的 `fix`）。
- 通过 `subprocess` 调 `format/check_katex.py`。
