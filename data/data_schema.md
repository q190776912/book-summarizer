# 中间产物 JSON 索引（`.`）

`.` 下每个中间产物 JSON **独占一个目录**：内含 `<json_name>.md`（数据结构说明）
与 `<json_name>.py`（模型类，继承 `lib/json_data.py` 基类）。脚本分两类：

- **构造器**（产生该 JSON）：就在对应目录的 `<json_name>.py`，CLI 直接写盘。
- **流程 / 校验脚本**（消费或校验该 JSON，不产新 JSON）：留在 `../verify/formula-manifest/script`
  或对应 `../flows` 阶段，**不在** `.`。

## 目录清单（含 in-skill 构造器）

| JSON | 目录 | 模型类（继承 `JsonData`） | 性质 |
|------|------|--------|------|
| `chapter_map.json` | [chapter_map/](chapter_map) | `ChapterMap` | 构造器 |
| `figure_index.json` | [figure_index/](figure_index) | `FigureIndex` | 构造器（同时产出 `figure_embed_overrides.json`） |
| `figure_embed_overrides.json` | [figure_embed_overrides/](figure_embed_overrides) | `FigureEmbedOverrides` | 构造器（由 `figure_index` 生成器写入） |
| `*_formulas.json` | [formula_manifest/](formula_manifest) | `FormulaManifest` | 构造器 |
| `book_chN_formulas.json` | [build_book_manifest/](build_book_manifest) | `BookFormulaIndex` | 构造器 |
| `*_filled.json` | [fill_book_labels/](fill_book_labels) | `FormulaFill` | 构造器 |
| `repairs.json` | [repairs/](repairs) | `Repairs` | 构造器 |

## 外部 / 流程产物（无 in-skill 构造器）

| JSON | 目录 | 说明 |
|------|------|------|
| `page_*.json` | [page_json/](page_json) | OCR 工具（PDF-Extract-Kit 等）产出，in-skill 只消费 |
| `figure_detect.json` | [figure_detect/](figure_detect) | 外部检测器产出，被 `figure_index` 生成器消费 |
| `fig_noise.json` | [figure_noise/](figure_noise) | 噪声标注，无 in-skill 构造器 |
| `ch<N>_extract.json` | [ch_extract/](ch_extract) | `flows` 中 `extract_items*` 产出 |

## 基类

`lib/json_data.py` 定义 `JsonData`：提供 `to_dict()` / `dump()` / `load()` /
`from_dict()` 通用序列化契约。每个 JSON 模型类继承它，并各自实现构造函数
（`default` / `from_dict` / `build` / `merge` / `from_markdown` 等）与字段。

> 边界：`../config` 是**配置型** JSON（如 `verify_config.json`），与 `.` 的中间产物
> JSON 平行；其文档与脚本见 [`../config/config_schema.md`](../config/config_schema.md)。
