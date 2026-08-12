# Flow: extract（提取 / Stage 1）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
把 PDF 放到本书专属目录，启动**后台**文本提取流水线，并在提取进行中**并行**轮询落盘页码，对已稳定页做 MM Repair；文本提取全部完成后，依次跑 **config 子流程**（生成 `verify_config.json`）、**figure_detection 子流程**（图检测 + 分配），最后跑 **structure 子流程**（生成全书每章 `ch<N>_structure.json`）。本阶段最终产出修复后的 `page_*.json` + `figure_index.json` + 全书每章 `ch<N>_structure.json`（写作契约 + verify 基准合一），**不做任何校验**。
## 前置
- `prep` 完成，环境 OK。
- 已知待提取 PDF 的路径 `P`（工作目录由 Step 1 的「目录决策」按分支 A–D 自动确定，必要时归一目录；不要求 PDF 预先就位于 `D:\study\book\<书名>\`）。

## 步骤（有序）

1. **归位 PDF（目录决策）**

   根据「已知 PDF 路径」确定**工作目录**（记为 `<book_dir>`），作为 `_extract/` 与后续所有产物的落位目录。目录决策**只为提取确定目录**：除分支 C / D 明确要求归一目录外，不移动已就位的 PDF。

   **目录决策（给定 PDF 路径 `P`，其所在目录为 `D`，文件名去扩展名为 `N`）**
   - **分支 A — 已有 `_extract`**：若 `D` 内已存在 `_extract/` → 工作目录 = `D`，**直接在 `D` 提取，不移动 PDF、不新建目录**。
   - **分支 B — 无 `_extract`，且目录名 ≈ PDF 名（或译名对应）**：若 `D` 的目录名与 `N` 相似（含译名对应，如目录 `Evans 偏微分方程` 对应 PDF `Evans-PDE.pdf`），或 `D` 本身即以书名命名 → 工作目录 = `D`，**在当前目录提取，不新建目录、不移动 PDF**。
   - **分支 C — 无 `_extract`，且目录名与 PDF 名差别较大**：在 `D` 内新建目录 `D/<N>/`，把 PDF 移入 `D/<N>/<N>.pdf` → 工作目录 = `D/<N>`。
   - **分支 D — 上下册 / 多册书**：在 `D` 内按书名新建统一目录 `D/<书名>/`，其下再分册子目录（如 `D/<书名>/上册/`、`D/<书名>/下册/`，或 `册一/册二/…`）；把各册 PDF 分别放入对应册目录（如 `D/<书名>/上册/上册.pdf`）。逐册提取：每册工作目录为 `D/<书名>/<册>/`，前一册 `PIPELINE OK` 后再启动下一册（见本阶段规则2 多册串行）。

   > 约定：提取输出 `_extract/` 始终建在「工作目录」同级（即 `<book_dir>/_extract/`）；`<书名>` 即最终确定的工作目录名。若 `<book_dir>` 不在 `D:\study\book\` 下，提取与产物仍只在 `<book_dir>` 内进行，不影响其它书籍。

2. **启动后台文本提取（启动前禁止做其他事）**

   - 归位完成后启动后台**文本**提取：只需传已确定的 PDF（如 `D/<N>/<N>.pdf` 或 `D/<书名>/<册>/<册>.pdf`），提取**范围**默认取全本（无需传任何页数）；三种启动形态（PowerShell `Start-Process` / `launch_pipeline.sh` / 直接 `python`）与 PATH 设置、范围参数说明见下方「启动方式」。若只想提取某一段，可加 `--start N` / `--end N`（见「启动方式」的范围说明）。启动后程序内部的执行流程（断点续跑 + 分批 MFD→MFR→OCR，**纯文本、不含图检测**）见子流程 [`extract/pipeline`](pipeline/pipeline.md)。
   - 启动后**立即转 Step 3 轮询、不等待**（并行强制规则见本阶段规则1）。

3. **主 Agent 进入轮询循环（强制并行，见本阶段规则1）**
   ```
   total_chapters = len(chapter_map)
   chapter_map_ready = False
   while True:
       1. current_max_page = max(现有 _extract/page_*.json 的页码)
       2. if not chapter_map_ready and current_max_page >= 5:
            从目录页读章名与书页码 → 写 chapter_map.json（见子流程 [`extract/chapter_map`](chapter_map/chapter_map.md)）；chapter_map_ready = True
       3. 若 current_max_page 自上次 MM audit 以来增长（建议新增 ≥1 稳定批次，如 50 页；或后台提取已结束）：
            对"新增稳定落盘区间"跑 MM Repair 完整链路（见子流程 [`extract/mm_repair`](mm_repair/mm_repair.md)）
   ```
   - **提取与 MM 修复门可并行**：MM Repair 只针对已落盘页码，绝不与提取进程写同一文件冲突。
   - **视觉审读是瓶颈**：每多一个稳定批次，主 Agent 必须立即读 `page_NNN_sheet.png` 做视觉识别，可拆给多个子代理并行。

4. **文本提取 100% 完成后 → 跑 config 子流程（生成书级配置）**
   - 当后台文本提取结束、`_extraction_done.json` 存在（所有 `page_*.json` 落盘并经 MM Repair）后，运行 **config 子流程** [`extract/config_setting`](config_setting/config_setting.md)：依据 `page_*.json` 一次性生成 `_extract/verify_config.json`（编号形态 / 语言 / `formula` map / `figure.labels`）。
   - 🔴 **图检测之前必须完成此步**：图检测严格读 `figure.labels`，未配置则退化默认前缀，自定义图号书（Scheme / Illustration 等）会漏识。

5. **config 完成后 → 跑 figure_detection 子流程（图检测 + 分配）**
   - 运行 **figure_detection 子流程** [`extract/figure_detection`](figure_detection/figure_detection.md)：全本书 DocLayout-YOLO 检测 + `图X.X.X` 分配，产出 `figure_detect.json` + `figure_index.json` + `figure/` 裁剪图。书若无图可跳过本步。

6. **figure_detection 完成后 → 跑 structure 子流程（统一结构骨架，全书批量）**
   - 运行 **structure 子流程** [`extract/structure`](structure/structure.md)：生成单一 `ch<N>_structure.json` 树（章节 → 条目/练习递归，含 `key`/`type`/`name`/页码），作为 write-source 的写作契约与 verify 的编号项基准（合一）。文本提取 100% 且 config 已出 `verify_config.json` 后批量跑：
   ```powershell
   python flows/extract/structure/script/build_structure <extract_dir>
   # 不传 <ch> 即全书；也可指定章：build_structure.py <extract_dir> 1 2 3
   ```
   - 至此 extract 阶段完成：`page_*.json` + `figure_index.json` + 全书每章 `ch<N>_structure.json` 均已就绪，供 write-source 消费、verify 读取。

## 启动方式（后台提取启动逻辑，含启动脚本）

> 必须在 `pdfextract` conda 环境下运行（含 torch / fitz / paddle / PDF-Extract-Kit），PATH 要带上 torch 的 `lib` 与 nvidia cu12 bin（`cudnn\bin` 须故意留空，避免与 paddle 的 cudnn DLL 冲突，见 `extract_book.py` 顶部说明）。提取**范围**由脚本从 PDF 自动取全本（`fitz.open(pdf).page_count`，与 `extract_book.py` 第 449 行一致），**无需用户手填任何页数**。仅当要提取全本中的某一段时，才用 `--start N` / `--end N` 限定。三种启动形态等价，任选其一。

**提取范围（`--start` / `--end`，均可省略）**
- 都不给 → 提取全本（start=1，end=PDF 自动识别总页数）。
- 只给 `--end E` → 提取 `1..E`（开始页默认为 1，即"单纯传结束页"语义）。
- 只给 `--start S` → 提取 `S..(自动总页)`。
- `--start S --end E` → 提取精确的 `S..E` 段。
- 断点续跑仍生效：实际起点 = `max(--start, 已提取最大页+1)`（`--force` 时强制从 1 重跑）。

**形态 A — `launch_pipeline.sh`（推荐，`nohup` 后台 + 自动设 CUDA PATH）**
```bash
bash launch_pipeline.sh "D:/study/book/<书名>/<书名>.pdf"                # 全本，页数自动识别
bash launch_pipeline.sh "D:/study/book/<书名>/<书名>.pdf" --end 320       # 仅提取前 320 页
bash launch_pipeline.sh "D:/study/book/<书名>/<书名>.pdf" --start 100 --end 200  # 提取 100–200
bash launch_pipeline.sh "D:/study/book/<书名>/<书名>.pdf" --force         # 从头重跑
```
- 脚本内部 `nohup … &` 脱离终端；日志写 `<pdf_parent>/_extract/extract_pipeline.log`。`--start`/`--end` 均可省略，省略即取全本。

**形态 B — 直接 `python`（手动设 PATH）**
```bash
D:/anaconda3/envs/pdfextract/python.exe flows/extract/pipeline/script/extract_pipeline \
    "D:/study/book/<书名>/<书名>.pdf"
# 等价于：python extract_pipeline.py <pdf> [--start N] [--end N] [--force] [--deskew auto|off|force]
```
- 其余开关：`--force`（从头）/`--deskew auto|off|force`（纠斜）。范围用 `--start`/`--end` 限定，不给则全本。图检测单独由 figure_detection 子流程负责，此处不传图相关开关。

**形态 C — PowerShell `Start-Process`（中文路径安全，Windows）**
```powershell
# 1) 设 PATH（含 torch lib + nvidia cu12 bin；故意不含 cudnn\bin）
$env:Path = "D:\anaconda3\envs\pdfextract\lib\site-packages\torch\lib;" +
            "D:\anaconda3\envs\pdfextract\Library\bin;" +
            "D:\anaconda3\envs\pdfextract\Scripts;D:\anaconda3\envs\pdfextract;" + $env:Path
# 2) 归位 PDF（Move-Item 而非 Copy-Item，确保仅此一份）
if (-not (Test-Path -LiteralPath "D:\study\book\<书名>\<书名>.pdf")) {
    Move-Item -LiteralPath "<原路径>" -Destination "D:\study\book\<书名>\<书名>.pdf" -Force
}
# 3) 后台静默启动（仅传 PDF，范围默认全本；要限定段可加 "--start"/"--end" 元素）
$proc = Start-Process -WindowStyle Hidden -PassThru `
    -FilePath "D:\anaconda3\envs\pdfextract\python.exe" `
    -ArgumentList @("flows/extract/pipeline/script/extract_pipeline",
                    "D:\study\book\<书名>\<书名>.pdf")
# 取 PID 便于跟踪：$proc.Id
```
- 中文 / 含空格路径安全（用 `-LiteralPath` 与带引号 `ArgumentList`）；只传 PDF 即全本，范围由脚本内 `fitz` 自动识别。

**启动后验证**：看 `<pdf_parent>/_extract/extract_pipeline.log` 首行应为 `--end omitted: using auto-detected PDF total=N as end`（或 `Using --end=N` / `--end=… exceeds PDF total … clamped` 等），随后出现 `Models loaded. Starting batch loop.` 即正常开工。

## 本阶段规则（🔴 内联）

- **规则1 防停滞（最高优先级）**：启动任何后台任务后，**主 Agent 不得停手等用户**——
  - ❌ 不得 `TaskOutput(block=True)` 干等后台；
  - ❌ 不得"等完成通知才推进"；
  - ❌ 更不得结束回合说"等你看完再聊 / 等通知我继续"。
  - ✅ 立即继续做可并行工作（轮询落盘页做 MM Repair）；若确实无任何可并行工作，则 `TaskOutput(block=True)` **原地**等结果、同一回合内继续推进。
- **规则2 — 多册文档：强制逐册串行提取**（显存安全），前一册 `PIPELINE OK` + 显存回落后才启动下一册。

## 出口条件
- 出口：全书页面提取 100% 且每页过 MM Repair，config + figure_detection + structure 子流程均已跑完，产出 `page_*.json` + `figure_index.json` + 全书每章 `ch<N>_structure.json`（写作契约 + verify 基准合一）。

## 相关代码（路径相对 skill 根目录）
- `flows/extract/pipeline/script/extract_pipeline`：后台**文本**流水线驱动（自动断点续跑，纯文本提取）。参数：`<pdf> [--start N] [--end N] [--force] [--deskew …]`；`--end` 省略时取 PDF 自动识别总页（全本），`--start` 默认 1；每批 50 页；自动续跑；一批失败即停。图检测不在本脚本内。
- `launch_pipeline.sh`：bash 启动器（空格路径安全）。
- `../../data/chapter_map/chapter_map.py`（数据结构见 [data/chapter_map/chapter_map.md](../../data/chapter_map/chapter_map.md)）：chapter_map 模板工具。
- `flows/extract/structure/script/build_structure`：统一结构骨架生成（structure 子流程，Step 6），生成全书每章 `ch<N>_structure.json`。
- `flows/extract/structure/script/scan_skeleton`：章节/练习（`SEC`/`EXER`）扫描，build_structure 的内部依赖（不再作为独立子流程暴露）。
- `flows/extract/structure/script/extract_items` + 变体（`extract_items_en` / `_gm` / `_hom` / `_kt` / `_vakil`）：编号项抽取，按 `ordinal` 被 build_structure 调用（内部依赖）。

## 子流程
- [`extract/pipeline`](pipeline/pipeline.md) — 后台**文本**提取流水线（Step 2 启动：断点续跑 + 分批 MFD→MFR→OCR；不含图检测）
- [`extract/chapter_map`](chapter_map/chapter_map.md) — 建章节映射
- [`extract/mm_repair`](mm_repair/mm_repair.md) — MM Repair 链路（Step 2 轮询）
- [`extract/config_setting`](config_setting/config_setting.md) — 书级配置生成（Step 3，图检测之前）
- [`extract/figure_detection`](figure_detection/figure_detection.md) — 图检测 + 分配（Step 4，config 之后）
- [`extract/structure`](structure/structure.md) — 统一结构骨架（Step 6，生成 `ch<N>_structure.json`；写作契约 + verify 基准合一）
