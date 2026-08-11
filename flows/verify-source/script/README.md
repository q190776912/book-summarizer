# flows\verify-source\script\README.md

> 本流程（`verify-source`）是**薄壳**，不持有任何校验代码。
> 全部校验逻辑在通用 [`verify`](../../../verify) 流程中。

## 复用关系
- `verify-source` 在 Stage 4 把通用 `verify` 指向「源语言总结目录」。
- 真实代码入口：`../../../verify/script/verify_chapter.py`（`--all` / `--fix`）。
- 校验层实现、注册表、`--fix` 范围：见 `../../../verify/layers`。
- 各包按名互相 import，由 `../../../lib/boot.py` 在入口处统一注入 `sys.path`（见 SKILL.md「代码位置」）。
