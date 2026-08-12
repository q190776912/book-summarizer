# Flow: verify-source（校验源语言总结 / 薄壳，引用 verify 流程）

> 本流程是 [`verify`](../../verify/verify.md) 公用流程的**薄壳**。
> 校验逻辑本身**语言无关**——源语言总结与翻译语言总结共用同一套 `verify` 校验层。
> 本流程仅把 `verify` 指向"源语言总结目录"，不含任何独立校验代码。

## 目的
源语言全部初稿写完后，调用通用 `verify` 流程**一次性批量校验源语言全部章节**，直至 `verify PASS + KaTeX OK`。
## 前置
- 源语言全部章节初稿写完（合并文件 `ChapterN_*.md` 或按节拆分的 `ChapterN_M...` 文件）。
- `_extract/verify_config.json` 完整合法（含 `formula` map 若书有公式）。

## 步骤（有序）
1. **🔴 Q 层前置（若书有公式）**：确认 `verify_config.json` 含 `"formula"` map；缺失则按书实际公式编号推导写入。详见 [`verify` 流程步骤 1](../../verify/verify.md)。
2. 批量校验源语言目录（直接复用通用 `verify`）：
   ```powershell
   python verify/script/verify_chapter.py --all <extract_dir> <book_dir>   # exit 0 才算源语言通过
   ```
3. 未过则用 `--fix` 自动修复其中可修复层，再不带 `--fix` 复验确认 `exit 0`；至多 2 次仍不过则继续修，**严禁停下来问用户**。
4. 校验层语义 / 顺序 / `--fix` 范围见 `../../verify/verify.md`（SSOT）。
5. （可选）公式 manifest 保真对账见 [`../../verify/formula-manifest`](../../verify/formula-manifest/formula-manifest.md)。

## 本阶段规则
- 所有批量纪律 / `--all` 自动发现 / 失败处理与通用 `verify` 流程**完全一致**（见 [`verify` 流程本阶段规则](../../verify/verify.md)）。
- 🔴 **修复方向严格单向（最高优先级）**：源语言先于翻译语言。任何返工先修源语言 → 源语言彻底修复完成（复验 PASS + KaTeX OK）→ 再据已修定源语言同步更新翻译语言。

## 出口条件
- 出口：`verify_chapter.py --all` 对源语言**全部章节 `exit 0`**（`verify PASS + KaTeX OK`）。

## 相关代码
- 无本流程独立代码；全部复用 [`../../verify`](../../verify)。
- 校验入口：`../../verify/script/verify_chapter.py`。

## 子流程
- 全部委托给 [`verify`](../../verify/verify.md) 及其子流程 `layers` / `formula-manifest`。
