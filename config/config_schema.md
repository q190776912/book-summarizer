# 配置文件说明（Config Files · 索引）

> 本目录 `.` 是**公用配置文档与脚本**的根：集中说明本书摘要流程用到的各个**配置文件**的格式，并提供生成 / 维护这些配置的**脚本**。每个配置文件有独立的说明文档（下方列表），各流程（`config_setting`、`verify` 等）通过引用对应文档来使用配置说明与脚本，不在流程内部重复定义。

## 本书用到的配置文件

| 配置文件 | 作用 | 生成 / 维护 | 说明文档 |
|---------|------|------------|------|
| `verify_config.json` | 书级配置：编号形态 `ordinal`、语言 `language`、公式序标 `formula`、图序标体例 `figure.labels`、忽略章节 `ignore` 等；`verify_chapter.py` / `flows/extract/script/extract/scan_skeleton` 的**唯一配置源** | `verify_config/make_config.py` 半自动生成，或手填 | [`verify_config/verify_config.md`](./verify_config/verify_config.md) |
| `figure_embed_overrides.json` | 图嵌入锚点覆盖（图注无条目号时手动指定精确锚点） | `build_figure_index.py`（`../data/figure_index`）自动产出骨架，或手填 | [`figure_embed_overrides.md`](../data/figure_embed_overrides/figure_embed_overrides.md) |
| `ignore_ch{N}.json` / `ignore_fig_ch{N}.json` | 每章 verify 忽略键（条目级）/ 图片噪声豁免键（图片级） | 手填（`--ignore` / `--ignore-figure`）或 `ignore_chN/manage_ignore.py` | [`ignore_chN/ignore_chN.md`](./ignore_chN/ignore_chN.md) |
| `manual_overrides_ch{N}.json` | 每章抽取覆盖（OCR 漏识条目的人工补写登记，解除 B 层序列缺口 BLOCKING） | 手填（`flows/extract/script/extract/extract_items --manual`） | [`manual_overrides_chN/manual_overrides_chN.md`](./manual_overrides_chN/manual_overrides_chN.md) |
| `figure_manual_chN.json` | 手动补图声明（DocLayout-YOLO 漏判的图的位置 / 旋转 / 图注） | 手填（`figure_manual_chN/apply_manual_figures.py`） | [`figure_manual_chN/figure_manual_chN.md`](./figure_manual_chN/figure_manual_chN.md) |

> 其余配置（如 MM Repair 的中间结果）直接写入 `page_*.json`，不单独成文件。
> 流水线**中间产物**（非配置）：`figure_index.json` / `figure_detect.json` / `chapter_map.json` / `repairs.json` / `manifest.json` / `page_*.json` 等由提取/图片/修复步骤自动生成，其字段说明随各自流程文档，不在此集中。

## 相关脚本（按 JSON 分目录）

每个配置 JSON 独占一个目录，内含 `<json_name>.md`（文档）+ 模型 / 实例化脚本：

- `verify_config`：`verify_config.py`（模型 `BookConfig` / `GroupConfig` / `ChapterInfo` / `ConfigLoader`）+ `make_config.py`（半自动生成 `verify_config.json`）+ `tests/`（回归测试）。
- `ignore_chN`：`ignore_chN.md`（文档）+ `manage_ignore.py`（交互式登记 / 检视 `ignore_ch{N}.json`）。
- `figure_manual_chN`：`figure_manual_chN.md`（文档）+ `apply_manual_figures.py`（读取 `figure_manual_chN.json` 并写回 `figure_index.json`）。
- `manual_overrides_chN`：`manual_overrides_chN.md`（文档，仅手填；由 `flows/extract/script/extract/extract_items --manual` 加载合并）。

## 历史参考

- `ref/_archived_verify_config_schema.md`：早期 schema 设计分解（已归档，仅供回溯）。
