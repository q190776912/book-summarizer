# Flow: extract（提取 / Stage 1）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
把 PDF 放到本书专属目录，启动**后台**文本提取流水线，并在提取进行中**并行**轮询落盘页码，对已稳定页做 MM Repair；文本提取全部完成后，依次跑 **config 子流程**（生成 `verify_config.json`）、**figure_detection 子流程**（图检测 + 分配），最后跑 **structure 子流程**（生成全书单一的 `book_structure.json` 书对象）。本阶段最终产出修复后的 `page_*.json` + `figure_index.json` + 全书单一的 `book_structure.json`（写作契约 + verify 基准合一），**不做任何校验**。
## 前置
- `prep` 完成，环境 OK。
- 已知待提取 PDF 的路径 `P`（工作目录由 Step 1 的「目录决策」按分支 A–D 自动确定，必要时归一目录；不要求 PDF 预先就位于 `<corpus_root>\<书名>\`）。

## 步骤（有序）

1. **归位 PDF（目录决策）**

   根据「已知 PDF 路径」确定**工作目录**（记为 `<book_dir>`），作为 `_extract/` 与后续所有产物的落位目录。目录决策**只为提取确定目录**：除分支 C / D 明确要求归一目录外，不移动已就位的 PDF。

   **目录决策（给定 PDF 路径 `P`，其所在目录为 `D`，文件名去扩展名为 `N`）**
   - **分支 A — 已有 `_extract`**：若 `D` 内已存在 `_extract/` → 工作目录 = `D`，**直接在 `D` 提取，不移动 PDF、不新建目录**。
   - **分支 B — 无 `_extract`，且目录名 ≈ PDF 名（或译名对应）**：若 `D` 的目录名与 `N` 相似（含译名对应，如目录 `Evans 偏微分方程` 对应 PDF `Evans-PDE.pdf`），或 `D` 本身即以书名命名 → 工作目录 = `D`，**在当前目录提取，不新建目录、不移动 PDF**。
   - **分支 C — 无 `_extract`，且目录名与 PDF 名差别较大**：在 `D` 内新建目录 `D/<N>/`，把 PDF 移入 `D/<N>/<N>.pdf` → 工作目录 = `D/<N>`。
   - **分支 D — 上下册 / 多册书**：在 `D` 内按书名新建统一目录 `D/<书名>/`，其下再分册子目录（如 `D/<书名>/上册/`、`D/<书名>/下册/`，或 `册一/册二/…`）；把各册 PDF 分别放入对应册目录（如 `D/<书名>/上册/上册.pdf`）。逐册提取：每册工作目录为 `D/<书名>/<册>/`，前一册 `PIPELINE OK` 后再启动下一册（见本阶段规则2 多册串行）。

   > 约定：提取输出 `_extract/` 始终建在「工作目录」同级（即 `<book_dir>/_extract/`）；`<书名>` 即最终确定的工作目录名。若 `<book_dir>` 不在 `<corpus_root>\` 下，提取与产物仍只在 `<book_dir>` 内进行，不影响其它书籍。

2. **启动后台文本提取（启动前禁止做其他事）**

   - 归位完成后启动后台**文本**提取：只需传已确定的 PDF（如 `D/<N>/<N>.pdf` 或 `D/<书名>/<册>/<册>.pdf`），提取**范围**默认取全本（无需传任何页数）；三种启动形态（PowerShell `Start-Process` / `launch_pipeline.sh` / 直接 `python`）与 PATH 设置、范围参数说明见下方「启动方式」。若只想提取某一段，可加 `--start N` / `--end N`（见「启动方式」的范围说明）。启动后程序内部的执行流程（断点续跑 + 分批 MFD→MFR→OCR，**纯文本、不含图检测**）见子流程 [`extract/pipeline`](pipeline/pipeline.md)。
   - 启动后**立即转 Step 3 轮询、不等待**（并行强制规则见本阶段规则1）。

3. **主 Agent 进入轮询循环（强制并行，见本阶段规则1）**
```
   while True:
       0. 健康检查（每轮先做）：确认后台提取进程仍存活 ——
          `tasklist` 中应有 pdfextract 的 `python.exe` 进程，且 `extract_pipeline.log`
           末尾无 `Batch N–M FAILED` / `Pipeline finished` / `Traceback`。
           若进程已不在 或 日志出现失败 → **立即排查原因**（读 `extract_pipeline.log`
           与对应 `batch_*.log` 末段定位异常并修复），随后**直接重启流水线**
           （脚本支持断点续跑，会从已落盘最大页+1 续跑，无需 --force）；
           修复前不要继续推进后续步骤。
       1. current_max_page = max(现有 _extract/page_*.json 的页码)
       2. 若 current_max_page 自上次 MM audit 以来增长（建议新增 ≥1 稳定批次，如 50 页；或后台提取已结束）：
            对"新增稳定落盘区间"跑 MM Repair 完整链路（见子流程 [`extract/mm_repair`](mm_repair/mm_repair.md)）
   ```
   - ⚠️ **流水线在首个批次失败时即整体停止**（日志 `Stopping due to batch failure`），**不会自动重试**；若不及时监控，会"静默死掉、0 页落盘"。因此每轮轮询**必须先做步骤 0 健康检查**，发现死掉立即排查+重启，绝不能在"以为还在跑"的状态下一步步空转。
   - **提取与 MM 修复门可并行**：MM Repair 只针对已落盘页码，绝不与提取进程写同一文件冲突。
   - **视觉审读是瓶颈**：每多一个稳定批次，主 Agent 必须立即读 `page_NNN_sheet.png` 做视觉识别，可拆给多个子代理并行。

4. **MM Repair 完成后 → 跑 config 子流程（chapter_map + 书级配置）**
   - 🔴 **真正的门控是「MM Repair 完成」，不是「文本 100% 落盘」**：主 Agent 必须跑完 Step 3 轮询循环——即文本提取 100% **且**全部稳定批次经 MM Repair（模式 A 视觉审读 + 模式 B 自动补偿）已 `mm_repair_apply` 写回 `page_*.json`——之后，才运行 **config 子流程** [`extract/config_setting`](config_setting/config_setting.md)：先建章节映射 `_extract/chapter_map.json`（步骤 1，全书只此一份、不重复生成），再依据 `page_*.json` 一次性生成 `_extract/verify_config.json`（编号形态 / 语言 / `formula` map / `ordinal` 里的 Figure 组）。`formula` map 与乱码文本依赖模式 A 校正后的 `page_*.json`；仅观察到文本 100% 落盘（或后台 `Pipeline finished.` 日志 / 仅靠 `_extraction_done.json` 存在）就提前跑 config，会得到基于未修复页的错误配置。
   - `_extraction_done.json` 是本阶段收尾**由主 Agent 在 MM Repair 完成后**写出的完成标记（不是后台文本流水线发出的中间信号）；它的存在应等价于「MM Repair 完成」，若它早于模式 A 写出则属误用（参见 Kreyszig 书 `_extraction_done.json` 的 `sample_pending` 反例）。
   - 🔴 **图检测之前必须完成此步**：图检测严格读 `ordinal` 的 Figure 组（图号前缀 `name` + 段数 `type`），缺 Figure 组则退化默认前缀，自定义图号书（Scheme / Illustration 等）会漏识。

5. **config 完成后 → 跑 figure_detection 子流程（图检测 + 分配）**
   - 运行 **figure_detection 子流程** [`extract/figure_detection`](figure_detection/figure_detection.md)：全本书 DocLayout-YOLO 检测 + `图X.X.X` 分配，产出 `figure_detect.json` + `figure_index.json` + `figure/` 裁剪图。书若无图可跳过本步。

6. **figure_detection 完成后 → 跑 structure 子流程（统一结构骨架，全书批量）**
   - 运行 **structure 子流程** [`extract/structure`](structure/structure.md)：生成单一 `book_structure.json` 书对象（章节 → 条目/练习递归，`sub_sec` 内按章顺序嵌套，含 `key`/`type`/`name`/页码），作为 write-source 的写作契约与 verify 的编号项基准（合一）。文本提取 100% 且 config 已出 `verify_config.json` 后批量跑：
   ```powershell
   python flows/extract/structure/script/build_structure <extract_dir>
   # 不传 <ch> 即全书；也可指定章：build_structure.py <extract_dir> 1 2 3
   ```
   - 至此 extract 阶段完成：`page_*.json` + `figure_index.json` + 全书单一的 `book_structure.json` 均已就绪，供 write-source 消费、verify 读取。

## 启动方式（统一 PowerShell 后台启动，唯一写法）

> 统一用 **PowerShell `Start-Process` 后台启动**（中文 / 空格 / 括号路径实测安全）。Linux / Git Bash 环境才用 `launch_pipeline.sh`（行为等价，见下）。必须在 `pdfextract` conda 环境下运行（含 torch / fitz / paddle / PDF-Extract-Kit），PATH 要带上 torch 的 `lib` 与 nvidia cu12 bin（`cudnn\bin` 须故意留空，避免与 paddle 的 cudnn DLL 冲突，见 `extract_book.py` 顶部说明）。提取**范围**由脚本从 PDF 自动取全本（`fitz.open(pdf).page_count`），**无需用户手填任何页数**；仅当要提取全本中的某一段时，才用 `--start N` / `--end N` 限定。

**提取范围（`--start` / `--end`，均可省略）**
- 都不给 → 提取全本（start=1，end=PDF 自动识别总页数）。
- 只给 `--end E` → 提取 `1..E`（开始页默认为 1，即"单纯传结束页"语义）。
- 只给 `--start S` → 提取 `S..(自动总页)`。
- `--start S --end E` → 提取精确的 `S..E` 段。
- 断点续跑仍生效：实际起点 = `max(--start, 已提取最大页+1)`（`--force` 时强制从 1 重跑）。

**统一启动（Windows 唯一写法）**
```powershell
# 1) 设 PATH（torch lib + nvidia cu12 bin；故意不含 cudnn\bin）
$env:Path = "<conda.env_path>\lib\site-packages\torch\lib;" +
            "<conda.env_path>\lib\site-packages\nvidia\cublas\bin;" +
            "<conda.env_path>\lib\site-packages\nvidia\cuda_runtime\bin;" +
            "<conda.env_path>\lib\site-packages\nvidia\cufft\bin;" +
            "<conda.env_path>\lib\site-packages\nvidia\curand\bin;" +
            "<conda.env_path>\lib\site-packages\nvidia\cusolver\bin;" +
            "<conda.env_path>\lib\site-packages\nvidia\cusparse\bin;" +
            "<conda.env_path>\lib\site-packages\nvidia\nvjitlink\bin;" +
            "<conda.env_path>\Library\bin;" +
            "<conda.env_path>\Scripts;<conda.env_path>;" + $env:Path
# 2) 归位 PDF（Move-Item 而非 Copy-Item，确保仅此一份）
if (-not (Test-Path -LiteralPath "<corpus_root>\<书名>\<书名>.pdf")) {
    Move-Item -LiteralPath "<原路径>" -Destination "<corpus_root>\<书名>\<书名>.pdf" -Force
}
# 3) 拼整条命令行：所有参数统一用 [char]34 双引号包住（数值 token 可不加）
$q = [string][char]34
$cmd = $q + "<skill根>\flows\extract\pipeline\script\extract_pipeline.py" + $q + " " + `
       $q + "<corpus_root>\<书名>\<书名>.pdf" + $q
#     要限定段时在末尾追加，如：$cmd += " " + $q + "--start" + $q + " " + $q + "100" + $q
# 4) 后台静默启动（子进程独立于本终端，窗口关闭不影响）
$proc = Start-Process -WindowStyle Hidden -PassThru `
    -FilePath "<conda.env_path>\python.exe" `
    -ArgumentList $cmd
Write-Output ("PID: " + $proc.Id)   # 取 PID 便于跟踪
```
- 🔴 **为什么必须这样写**：PS 5.1 的 `Start-Process -ArgumentList` 对**数组**元素会自行二次加引号 / 拆引号——`@($script, '"path with space.pdf"')` 时好时坏（实测多空格参数被劈开，argparse 报 `unrecognized arguments: to representation theory\...`，进程静默退出、日志不创建）；**传单个字符串则原样透传**，引号完全由自己控制 → 唯一可靠写法。
- 只传 PDF 即全本；`--start` / `--end` 为不含空格的简单 token，可不加引号（加了也无害）。
- `flow_runner run extract extract_text` 的命令模板是 `bash launch_pipeline.sh`，Windows 无 bash 时必然失败 → 启动一律用上方写法，全部页落盘后再 `flow_runner verify + mark extract extract_text` 落账。

**bash 环境（Linux / Git Bash，非 Windows）**
```bash
bash launch_pipeline.sh "<corpus_root>/<书名>/<书名>.pdf"                # 全本，页数自动识别
bash launch_pipeline.sh "<corpus_root>/<书名>/<书名>.pdf" --end 320       # 仅提取前 320 页
bash launch_pipeline.sh "<corpus_root>/<书名>/<书名>.pdf" --start 100 --end 200  # 提取 100–200
bash launch_pipeline.sh "<corpus_root>/<书名>/<书名>.pdf" --force         # 从头重跑
```
- 脚本内部 `nohup … &` 脱离终端 + 自动设 CUDA PATH；日志同样写 `<pdf_parent>/_extract/extract_pipeline.log`。

**前台直跑（仅调试用，看实时输出）**
```powershell
& "<conda.env_path>\python.exe" "<skill根>\flows\extract\pipeline\script\extract_pipeline.py" "<corpus_root>\<书名>\<书名>.pdf"
```
- `&` 调用符对引号处理正确（与 `Start-Process` 的数组行为不同）；会阻塞终端，仅供排障，不用于正式启动。

**⚠️ Windows 启动失败模式（本机实测，别再踩）**
- 🔴 **`bash` 不可用**：本机 `C:\Windows\system32\bash.exe` 是 WSL 启动器但**未装任何发行版**（`execvpe(/bin/bash) failed`），也无 Git Bash → `launch_pipeline.sh` 与 `flow_runner run extract extract_text` 必然失败，启动只用上方统一写法。
- 🔴 **别用 `cmd /c` 包整条命令串**：PS 5.1 `Start-Process -ArgumentList @('/c', $cmdline)` 对「以引号开头」的命令串会二次加引号 → cmd 解析失败：表现为 cmd 立即退出 `code=1`、**日志文件根本不会创建**（连空文件都没有）。形如 `echo hello > "log"`（引号在中间）没事；`"python.exe" "script" "pdf" > "log"`（引号开头）必挂。
- 🔴 **别写 `.bat` / `.ps1` 启动器文件**：cmd 按 OEM 代码页（中文系统 = GBK/936）读 `.bat`，PS 5.1 无 BOM 时按 ANSI 读 `.ps1`；UTF-8 写入（write 工具默认）的中文路径全部乱码 → `系统找不到指定的路径` / `文件名、目录名或卷标语法不正确`，日志同样不会创建。即使改写 GBK，LF-only 行尾也可能触发解析错误。
- 🔴 **禁止并发多开**：同一本书同时跑两个 `extract_pipeline.py` 会互写 `page_*.json`；启动前先确认无残留实例（`Get-CimInstance Win32_Process -Filter "Name='python.exe'"` 看 CommandLine）。
- ✅ 统一写法实测通过：中文路径、括号文件名（如 `遍历论+(孙文祥)+(Z-Library).pdf`）均安全；首启失败时加 `-RedirectStandardError "<extract>\pipeline_stderr.txt"` 抓取 argparse 报错。

**启动后验证**：看 `<pdf_parent>/_extract/extract_pipeline.log` 首行应为 `--end omitted: using auto-detected PDF total=N as end`（或 `Using --end=N` / `--end=… exceeds PDF total … clamped` 等），随后出现 `Models loaded. Starting batch loop.` 即正常开工。日志未创建 = 进程在 argparse 阶段就退出（多半是引号问题），按上面失败模式排查。

## 本阶段规则（🔴 内联）

- **规则1 防停滞（最高优先级）**：启动任何后台任务后，**主 Agent 不得停手等用户**——
  - ❌ 不得 `TaskOutput(block=True)` 干等后台；
  - ❌ 不得"等完成通知才推进"；
  - ❌ 更不得结束回合说"等你看完再聊 / 等通知我继续"。
  - ✅ 立即继续做可并行工作（轮询落盘页做 MM Repair）；若确实无任何可并行工作，则 `TaskOutput(block=True)` **原地**等结果、同一回合内继续推进。
- **规则2 — 多册文档：强制逐册串行提取**（显存安全），前一册 `PIPELINE OK` + 显存回落后才启动下一册。

## 出口条件
- 出口：全书页面提取 100% 且每页过 MM Repair，config + figure_detection + structure 子流程均已跑完，产出 `page_*.json` + `figure_index.json` + 全书单一的 `book_structure.json`（写作契约 + verify 基准合一）。

## 🔒 阶段门控（flow_gate 强制顺序，死命令）

本 flow 的 Step 1→6 是**硬有序**，且作为 `flows/_flow_gate.md` 定义的 `extract`
flow 被顺序闸守护。机制要点（完整见 [`flows/_flow_gate.md`](../_flow_gate.md)）：

- **顺序铁律**：`extract_text → mm_repair → config（含 chapter_map 建映射）→ figure_detection →
  structure` 依次进行；任一步未完成，下一步被 flow_runner 顺序闸 + 下游加载器双拦截。
- 🔴 **`_extraction_done.json` 是 MM Repair 真完成的唯一标记**：只能由
  `mm_repair_apply.py` 在「条目全 resolved + 每页有 mm 标记」时写出。本 flow 的
  Step 4（config）/ Step 5（figure）/ Step 6（structure）都依赖它——`make_config.py`
  缺它硬拒、`build_structure.py` 缺它硬拒、`ConfigLoader` 缺它拒绝加载 config。
- ❌ **禁止清单（本 flow 特别相关）**：
  - ❌ 在 `_extraction_done.json` 不存在时跑 `make_config.py` / `build_structure.py`
    （会硬拒；你不应试图绕过）。
  - ❌ 手写 / 手改 `verify_config.json` 充当 config（无 `_provenance` 戳，下游必拒）——
    这是 Fraleigh 事故的真实根因，绝不再犯。
  - ❌ 提前手 touch `_extraction_done.json` 冒充 MM Repair 完成。
  - ❌ 把"文本 100% 落盘 / Pipeline finished / 后台进程结束"当作"MM Repair 完成"。
- 推进步骤走 `python tools/flow_runner.py run <book_dir> extract <step>`；agent 步
  （mm_repair 视觉）做完用 `verify` 复核 + `mark` 落账。历史书一次性回填用
  `python tools/flow_runner.py bootstrap <book_dir>`（依物理证据，绝不伪造）。

## 相关代码（路径相对 skill 根目录）
- `flows/extract/pipeline/script/extract_pipeline.py`：后台**文本**流水线驱动（自动断点续跑，纯文本提取）。参数：`<pdf> [--start N] [--end N] [--force] [--deskew …]`；`--end` 省略时取 PDF 自动识别总页（全本），`--start` 默认 1；每批 50 页；自动续跑；一批失败即停。图检测不在本脚本内。
- `launch_pipeline.sh`：bash 启动器（空格路径安全）。
- `../../data/chapter_map/chapter_map.py`（数据结构见 [data/chapter_map/chapter_map.md](../../data/chapter_map/chapter_map.md)）：chapter_map 模板工具。
- `flows/extract/structure/script/build_structure`：统一结构骨架生成（structure 子流程，Step 6），生成全书单一的 `book_structure.json` 书对象。
- `flows/extract/structure/script/scan_skeleton`：章节/练习（`SEC`/`EXER`）扫描，build_structure 的内部依赖（不再作为独立子流程暴露）。
- `flows/extract/structure/script/extract_items` + 变体（`extract_items_en` / `_gm` / `_hom` / `_kt` / `_vakil`）：编号项抽取，按 `ordinal` 被 build_structure 调用（内部依赖）。

## 子流程
- [`extract/pipeline`](pipeline/pipeline.md) — 后台**文本**提取流水线（Step 2 启动：断点续跑 + 分批 MFD→MFR→OCR；不含图检测）
- [`extract/mm_repair`](mm_repair/mm_repair.md) — MM Repair 链路（Step 2 轮询）
- [`extract/config_setting`](config_setting/config_setting.md) — chapter_map 建映射 + 书级配置生成（Step 4，MM Repair 之后、图检测之前）
- [`extract/figure_detection`](figure_detection/figure_detection.md) — 图检测 + 分配（Step 5，config 之后）
- [`extract/structure`](structure/structure.md) — 统一结构骨架（Step 6，生成 `book_structure.json` 书对象；写作契约 + verify 基准合一）
