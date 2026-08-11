# Flow: derive-translate（派生并校验翻译版 / Stage 5）

> 统一模板：目的 / 触发 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
据**已校验的源语言版**派生翻译版（英文书 → 中文 `第N章_*.md`），再对翻译版跑批量校验至 PASS。

## 触发
- `verify` 流程（源语言版）全部章节 `verify PASS + KaTeX OK` 后。

## 前置
- 源语言全部章节已校验通过（`verify PASS + KaTeX OK`），是派生翻译版的**唯一蓝本**。
- 🔴 **修复方向严格单向（最高优先级）**：任何返工 / 修复都先修源语言 → 源语言彻底修复完成（复验 PASS + KaTeX OK）→ 再据已修定源语言同步更新翻译语言。绝不允许翻译语言先于源语言动手，或两边各修各的导致分叉。

## 步骤（有序）
1. 以已校验源语言版为唯一蓝本，**逐条翻译**出翻译版：条目 / 编号 / 公式 / 图片位置必须 1:1 对应，不得增删或自行发挥；中文版首现术语照旧标 `(English)`。
2. 对翻译版跑格式后处理（`wrap_examples_bq` / `fmt_proofs` / `fix_katex` / `check_katex`）与嵌图（Step 3.5）。
3. 批量校验翻译版：
   ```powershell
   python verify/script/verify_chapter.py --all <extract_dir> <book_dir>   # 针对翻译版
   ```
   未过则 `--fix` 修复 + 重验，至多 2 次仍不过继续修，**严禁停下来问用户**。
4. 中英两版必须 1:1 同构；源语言修补后翻译版须同步修补（单向：先英后中）。

## 本阶段规则（🔴 内联）
- **规则1 — 源语言优先**：中文版是英文版的**派生**，不是平行独立文件。英文书每章顺序：先写英文源版 → 完全校验 / 修复至 PASS → 再据已校验英文版逐条翻译中文版。
- **🚫 禁止「只有中文、没有英文」**：目录下只有 `第N章_*.md` 而无对应 `ChapterN_*.md`，说明流程从根上错，该章（及依赖它的后续章）必须重做。中文总结的存在**以英文源版存在且校验通过为前提**。
- **中英两版 1:1 同构**：条目、编号、公式、图片位置逐一对应，不得增删或自行发挥。
- **修复严格单向**：先修源语言（英文版）→ 源语言彻底修复完成（复验 PASS + KaTeX OK）→ 再据这份已修定源语言同步更新翻译语言（中文版）。翻译语言总结必须始终以源语言为唯一蓝本、保持一致。

## 出口条件（全书完成）
- 出口：**源语言 + 翻译版章数 == `chapter_map` 总章数，且两版均 `verify PASS + KaTeX OK`**。唯一退出条件：`已写章数 == chapter_map 总章数`。

## 相关代码（路径相对 skill 根目录）
- `../../verify/script/verify_chapter.py`：`--all` 校验翻译版。
- `flows/write-source/format/script/format/*` + `flows/script/figure/embed_figures`：翻译版格式后处理与嵌图（同 `write-source`）。

## 子流程
- 写作 / 格式 / 嵌图规则见 [`write-source`](../write-source/write-source.md) 及其子流程。
- 校验层见 [`../../verify/verify.md`](../../verify/verify.md)（各层 SSOT 总入口）。
