# Sub-flow: extract / items（编号项清单 / extract 末尾强制生成）

> 统一模板：目的 / 触发 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
在文本提取 100% 完成、config 与 figure_detection 之后，**批量**为全书每一章枚举"编号项清单"——所有带编号的条目（定义 / 定理 / 引理 / 推论 / 命题 / 例 等）的 `键 / 标签 / 页码` 列表。它是 verify 阶段 data_provider 层判定「条目齐全、无缺失、无重复」的权威基准，也是 write-source 写章时与骨架交叉核对的清单。

## 触发
- `extract` 流程第 6 步（skeleton 之后，最终步骤）：config + figure_detection 完成后，批量枚举全书编号项。

## 前置
- 全书 `page_*.json` 已落盘且过 MM Repair。
- `verify_config.json` 已由 config 子流程生成（编号模式 `ordinal` 决定抽哪条路径）。

## 步骤（有序）
1. **主抽取器 `extract_items.py`**（三级 `N.S-N` 默认；内部按 `ordinal` 自动选路到 two_level / fraleigh / gm / 英文 `extract_items_en` 等变体）：
   ```powershell
   python flows/extract/script/extract/extract_items <ch> <start> <end> <extract_dir> > <extract_dir>/ch<ch>_items.txt
   # 英文书：python extract_items.py --lang en <start> <end> <extract_dir>
   ```
   逐章枚举所有编号条目（`键 / 标签 / 页码 / 文本`），重定向为 `ch<N>_items.txt`。
2. **两级数书专用扫描 `scan_items.py`**：对采用「定义自有计数器 + 定理族共享计数器 + 例按节重编号」的书（如 周民强《实变函数论》），三级 `N.S-N` 正则会造出伪键，须用 `scan_items.py` 独立扫描并核对连续性缺口：
   ```powershell
   python flows/extract/script/extract/scan_items <ch> <start> <end> <extract_dir>
   ```

## 本阶段规则（🔴 内联）
- **编号项类型必须真实匹配，禁止强制归入 `uncat`**（呼应 `config_setting` 规则5）：未匹配上的类型不得硬塞近似类型或临时 hack；agent 找不到匹配时可增量引入新类型（在 `ordinal` 新增 `type` 码 + `name`，必要时加脚本并登记 `../../../lib/boot.py` 与 `verify.md` 注册表）。
- **两级书走 `scan_items.py`，不强行三级 `extract_items` 模式**：否则 `1.1-1` 之类会被正则在公式 / 枚举片段里造出永不匹配的伪键。
- **清单是 verify 的权威基准**：verify 阶段 data_provider 层直接复用 `extract_items()` 重新派生，与本书目清单同源；write-source 写章前应与 `ch<N>_items.txt` 交叉核对，确保无遗漏。
- **B 层断号由 `b_layer.recover_missing_items` 兜底**：扫描遇边界 / 尾部残页时自动重扫修复，产出 `BLOCKING` 阻断项须先解决再写作（见 `verify` 层 B）。

## 出口条件
- 出口：全书每章编号项已枚举（`<extract_dir>/ch<N>_items.txt` 或 scan_items 报告），作为 verify 基准与 write-source 核对清单。

## 相关代码（路径相对 skill 根目录）
- `flows/extract/script/extract/extract_items`：主抽取器（三级默认，含 two_level / fraleigh 选路）。
- `flows/extract/script/extract/extract_items_en` / `extract_items_gm.py` / `extract_items_hom.py` / `extract_items_kt.py` / `extract_items_vakil.py`：各体例变体。
- `flows/extract/script/extract/scan_items`：两级书独立完整性扫描。
- `flows/extract/script/extract/b_layer`：`recover_missing_items` 断号修复。

## 子流程
无。
