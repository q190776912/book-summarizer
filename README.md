# book-summarizer

把一本教材（本地 PDF）转化成**逐章结构化 markdown 笔记**：定义 / 定理 / 例题 + 证明梗概 + KaTeX 公式 + 插图，中英双版（中文书只出中文版，英文书出中英 1:1 同构双版），用于复习、参考或间隔重复。

## 能力一览

- PDF 文本提取（MFD 公式检测 → MFR 公式识别 → OCR 正文）→ MM Repair 修复 OCR 噪声
- 章节骨架扫描 + 编号条目抽取 + 内容挂载 → 分章契约 `book_structure/ch{N}.json`（写作契约）
- 按契约逐单元写源语言稿 →（英文书）逐单元翻译（1:1 同构闸）→ 拼接源+译两版 → 多层校验（结构 / 编号 / 格式 / KaTeX / 公式对账）至 PASS
- 图检测 + 分配（DocLayout-YOLO；图片经契约 image 块随单元继承，嵌图子流程已废弃）

## 前置要求（Windows）

| 组件 | 版本/说明 | 来源 |
|------|-----------|------|
| Windows + Git-Bash | 运行 `launch_pipeline.sh`（无 Git-Bash 时用 PowerShell 统一启动写法，见 `flows/extract/extract.md`） | git for windows |
| conda + Python 3.10 | 提取环境 | conda |
| NVIDIA GPU + 驱动 | CUDA 12.9（torch cu129 与 paddle cu129 必须同 minor，详见 `flows/prep/ref/environment.md`） | — |
| PDF-Extract-Kit 源码 | clone 到 `model_root` | github.com/opendatalab/PDF-Extract-Kit |
| 权重四组：MFD / MFR(unimernet_tiny) / OCR(PP-OCRv4) / Layout(doclayout_yolo_ft) | 落位 = `model_root` 下的固定子路径（`lib/user_config.py::weight_paths()` 派生，无需手配） | ModelScope `opendatalab/pdf-extract-kit-1.0`（HF 常不可达） |
| Node.js | `npm install katex --no-save`（prep 校验用） | — |

完整安装步骤（含 cudnn PATH 对齐、cudnn/bin 必须为空、各权重结构要求）见 **[`flows/prep/ref/environment.md`](flows/prep/ref/environment.md)**。

## 安装

1. 把本 skill 目录放入你的 AI 编程工具的 skills 路径（如 opencode 的 `~/.agents/skills/`；支持按目录加载 skill 的工具均可）。
2. 按 environment.md 建 conda 环境、拉权重（四组权重落位即自动生效，无需改脚本）。
3. **机器路径配置**（`user_config.json`，gitignored 不随仓库上传；缺失时回退到 `lib/user_config.py` 内置默认值，并可自动探测常见位置）：
   ```jsonc
   {
     "corpus_root": "D:/study/book",            // 书库根目录
     "model_root": "D:/study/model/PDF-Extract-Kit",  // PDF-Extract-Kit 源码根
     "conda": {
       "env_name": "pdfextract",
       "env_path": "D:/anaconda3/envs/pdfextract"
     },
     "paddleocr_cache": "C:/Users/<you>/.paddleocr"
   }
   ```
   首次使用时 Agent 会自动跑 `lib/user_config.py status` 探测依赖并**向你确认默认值**；依赖目录不存在时会先问你是否已有，没有则引导安装（流程见 SKILL.md「首次使用配置」）。
4. 环境变量覆盖（优先级：**env > `user_config.json` > 内置默认值**）：

   | 配置项 | env 变量 |
   |--------|----------|
   | corpus_root | `BKS_CORPUS_ROOT` |
   | model_root | `BKS_MODEL_ROOT` |
   | conda.env_name | `BKS_CONDA_ENV_NAME` |
   | conda.env_path | `BKS_CONDA_ENV_PATH` |
   | paddleocr_cache | `BKS_PADDLEOCR_CACHE` |

## 快速开始

```bash
# 1. 归位 PDF（目录契约：<corpus_root>/<书名>/<书名>.pdf）
# 2. 跑流程（严格顺序，flow_runner 机械把关）
python tools/flow_runner.py run "<corpus_root>/<书名>" prep env
python tools/flow_runner.py run "<corpus_root>/<书名>" extract place_pdf
python tools/flow_runner.py run "<corpus_root>/<书名>" extract extract_text   # 后台提取（Windows 用 PowerShell 启动写法，见 extract.md）
# ... extract.mm_repair → write_source: config → build_chapter_map（OCR 证据算章界）→ figure_detection → structure（完整性闸门）→ draft（拆分单元，每 item 一单元）
python tools/flow_runner.py run "<corpus_root>/<书名>" write_source config
python tools/flow_runner.py run "<corpus_root>/<书名>" write_source build_chapter_map
python tools/flow_runner.py run "<corpus_root>/<书名>" write_source figure_detection
python tools/flow_runner.py run "<corpus_root>/<书名>" write_source structure
python tools/flow_runner.py run "<corpus_root>/<书名>" write_source draft
# 3. 逐单元改好 →（仅英文书）逐单元翻译 → 拼接源+译两版 → 批量校验（一次覆盖两版）
python tools/flow_runner.py run "<corpus_root>/<书名>" write_source write_chapters
python tools/flow_runner.py run "<corpus_root>/<书名>" write_source translate_chapters   # 仅英文书
python tools/flow_runner.py run "<corpus_root>/<书名>" write_source merge_all
python tools/flow_runner.py run "<corpus_root>/<书名>" write_source verify_source
```

完整流程与每步规则见 **[`SKILL.md`](SKILL.md)**（Stage 0 → 2 主流程、写源硬闸、flow_gate 强制顺序）与 `flows/<stage>/<stage>.md`。

## 常见问题

- **`WinError 127/193`（cublas/cudnn DLL）**：torch 非 cu129 / 残留 `*-cu13` 包 / `nvidia/cudnn/bin` 非空，见 environment.md。
- **`bash` 不可用**（`C:\Windows\system32\bash.exe` 是 WSL 启动器未装发行版）：用 `flows/extract/extract.md` 统一 PowerShell 启动写法（`Start-Process python.exe`）。
- **HF 下载权重失败**：用 ModelScope `opendatalab/pdf-extract-kit-1.0`。
- **无 GPU**：CPU 可跑但极慢（`torch.cuda.is_available()` 为 False 时自动 CPU）。
- **launch_pipeline.sh 报"cannot resolve conda env path"**：PATH 里没有 python/py，或未配 `BKS_CONDA_ENV_PATH`。
- **输出语言**：中文书 → 仅中文；英文书 → 中英双版；其他语种 → 原文 + 中英。

## 架构速览

- `SKILL.md`：主流程（Stage 0 prep → 1 extract → 2 write-source（含 2026-09-03 内建的翻译单元化步骤））、目录契约、写源硬闸、flow_gate
- `flows/`：各阶段流程文档（统一模板：目的/前置/步骤/规则/出口/相关代码）与脚本
- `verify/`：通用校验引擎（多层语义校验，`verify/verify.md` 为编排权威）
- `config/`：书籍处理过程配置（`verify_config` 生成器、`ignore_chN` 忽略清单等）
- `data/`：中间产物 JSON 的模型类与结构说明（`data/data_schema.md`）
- `lib/`：公用库（`boot.py` 路径自举、`user_config.py` 配置加载、`normalize_math.py` 公式修复等）
- `tools/`：生产期格式化 CLI 工具 + `flow_runner.py` 流程推进器