# Sub-flow: extract / skeleton（结构骨架契约 / extract 末尾强制生成）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
**批量**为全书每一章生成"结构骨架"——按原书页码顺序列出全部 `SEC`（节标题）/ `ITEM`（编号条目）/ `EXER`（练习），作为**写作契约**（不是参考）。骨架在 extract 阶段一次性产出，write-source 阶段直接消费，无需每章临时生成。
## 前置
- 全书 `page_*.json` 已落盘且过 MM Repair（extract 主流程出口满足）。
- `verify_config.json` 已就绪（骨架的编号模式由 `ordinal` 自动判定；图检测是否完成不影响骨架）。

## 步骤（有序）
```powershell
python flows/extract/script/extract/scan_skeleton <extract_dir>
# 全书：不传 <ch> 即扫全部章；也可指定章：scan_skeleton.py <extract_dir> 1 2 3
# 编号模式（三级/两级/cn）由 <extract_dir>/verify_config.json 的 ordinal 自动判定，无需 --scheme
```
产出 `<extract_dir>/ch<N>_skeleton.txt`（每章一个），按原书页码顺序列出 `SEC` / `ITEM` / `EXER`，每条带页码与**印刷标题**。

## 本阶段规则（🔴 内联）
- **骨架是契约，不是参考**：
  - 有几个 `SEC` 就必须写几个 `## §N.M`，**顺序照抄**，一个不能少、不能颠倒；
  - 每个 `ITEM` 都必须在总结里落地；`EXER` 按 `../../write-source/format/ref/formatting.md` 习题规则处理（穿插习题原位保留，章末整块习题省略），故该类 `EXER` 不强制落地；
  - `ITEM` 行末印刷标题必须写进条目标签，不得丢弃；
  - 骨架里没有的编号，不许出现在总结里（无中生有）。
- **不能只靠 `ch<N>_items.txt`**：它只含 verifier 必备条目键，不含节标题 / 练习 / 印刷标题；只拿它写作必然漏节、乱序、丢标题。
- **写完后自查**：`grep -c '^## §' <md>` 应等于骨架 `SEC` 数；条目 / 练习编号集合应与骨架一致。

## 出口条件
- 出口：全书每章 `ch<N>_skeleton.txt` 已生成，作为 write-source 的写作契约采用。

## 相关代码（路径相对 skill 根目录）
- `flows/extract/script/extract/scan_skeleton`：骨架生成。

## 子流程
无。
