# F 层 — FIGURE VALIDITY

> 本文件是 **F 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
图有效性：裁剪图能否正常解码。

## 语义与检查内容
- 用 `np.fromfile` + `cv2.imdecode` 逐一打开裁剪图。
- **INVALID（阻断 FAIL）**：缺失文件 / 无法解码 / 单边 <20px。
- **SUSPICIOUS（仅 WARN）**：近空白（灰度方差 <50，疑似误检文字块）。

## 阻断性 / 可修复
- 有图时 `fig_invalid` 非空 → 阻断 FAIL。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
fig_invalid
fig_invalid_warn
```

## 实现（`verify/layers/f_layer.py`）
- `code = 'F'`，`order = 6`，`auto_fixable = False`。
- 与 E 同前提（无 `figure_index.json` 则 SKIP）。底层返回 None 必须 emit 空列表。
