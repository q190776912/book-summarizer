> 🔴 **本文件是该领域规则的唯一权威详细说明（SSOT）**。`SKILL.md` 与代码注释只引用此处、不重复描述；新增/修改该领域规则只改本文件。

# PDF-Extract-Kit Environment Setup (conda `pdfextract`)

> 本文件集中放**安装 / 排障**类参考（CUDA-cudnn 对齐、conda 环境、权重路径、启动器）。日常"总结一章"的流程不需要读它；只在**首次装环境**或**遇到 `WinError 127/193` 等 CUDA/cudnn 报错**时查阅。SKILL.md 中对应位置保留指针。

> **⚠️ All extraction steps MUST run inside the `pdfextract` conda env**（环境名/路径见 `user_config.json`，可被 `BKS_CONDA_ENV_NAME` / `BKS_CONDA_ENV_PATH` 覆盖）。Never run the extraction scripts with the base/system Python, which has its own broken paddle and no torch GPU.

This skill uses **PDF-Extract-Kit** for formula detection (MFD), formula recognition (MFR → LaTeX) and text OCR, all on GPU. The verified working environment is a conda env on a CUDA 12.9 machine (e.g. RTX 5060, Compute Capability 12.0, Driver API 13.1).

## 配置与路径（参数化，见 `user_config.json`）

所有机器特定路径集中在 skill 根目录 `user_config.json`（缺失时回退到提交的 `user_config.example.json`，也可用 `BKS_*` 环境变量覆盖）。脚本不硬编码任何路径；权重子路径由 `lib/user_config.py::weight_paths()` 从 `model_root` 派生。下文用 `<key>` 表示 config 取值：

| 配置项（user_config 键） | 含义 |
|--------------------------|------|
| `corpus_root` | 书库根目录（目录契约 `<corpus_root>\<书名>\`，PDF 必须放 `<书名>\<书名>.pdf`） |
| `model_root` | PDF-Extract-Kit 根目录（克隆源码处；权重全部落其下，见「Model weights」） |
| `conda.env_name` | 提取用 conda 环境名（默认 `pdfextract`） |
| `conda.env_path` | 该环境的绝对路径，如 `<anaconda>/envs/pdfextract`（脚本用其 `python.exe`） |
| `paddleocr_cache` | PaddleOCR 权重缓存（OCR 权重缺失时的拷贝来源，见「Model weights」） |

| 派生路径（`weight_paths()` 产出，勿手改） | 用途 |
|------|------|
| `<model_root>/pdf_extract_kit` | PDF-Extract-Kit 包（`sys.path` 注入点） |
| `<model_root>/models/models/opendatalab--PDF-Extract-Kit/snapshots/master/models/MFD/models/MFD/YOLO/yolo_v8_ft.pt` | MFD 权重 |
| `<model_root>/models/MFR/unimernet_tiny` | MFR 权重（需含 `pytorch_model.pth`） |
| `<model_root>/pdf_extract_kit/configs/unimernet.yaml` | MFR 配置（脚本用**绝对路径**） |
| `<model_root>/models/OCR/PaddleOCR/det/ch_PP-OCRv4_det` | OCR 检测权重 |
| `<model_root>/models/OCR/PaddleOCR/rec/ch_PP-OCRv4_rec` | OCR 识别权重 |
| `<model_root>/models/Layout/YOLO/doclayout_yolo_ft.pt` | DocLayout-YOLO 权重（图片提取 `flows/script/extract_figures` 用） |

| 其他位置 | 路径 |
|----------|------|
| Skill 脚本目录 | 任意位置均可（含 `flows/` · `verify/` · `config/` · `tools/`）；路径自举：各脚本经 `lib/boot.py` 向上定位 `SKILL.md` 所在根，无需手改硬编码 |
| 每书总结目录 | `<corpus_root>\<书名>\` — markdown 章节文件在此 |
| 每书提取 JSON | `<corpus_root>\<书名>\_extract\page_*.json` |

## ⚠️ Critical: torch and paddle MUST share the same CUDA minor version

PDF-Extract-Kit loads **torch** (MFD + MFR) and **paddle** (OCR) in the **same Python process**. Both frameworks bundle their own copies of `cudnn64_9.dll` / `cublas64_12.dll` with the same filename but different internal versions. If their CUDA minor versions differ, the second framework to import grabs the wrong copy → `WinError 127/193` ("Error loading cublas64_12.dll / cudnn_cnn64_9.dll").

**Fix: align torch's CUDA build to paddle's.** Paddle 3.2.2 (cu129 wheel) is built against **CUDA 12.9** (`paddle.version.cuda() == 12.9`, `cudnn == 9.9.0`). Therefore torch MUST be the **cu129** build, NOT cu130/cu126:

```
# CORRECT — torch cu129 matches paddle's CUDA 12.9
pip install torch==2.8.0+cu129 torchvision==0.24.0+cu129 --index-url https://download.pytorch.org/whl/cu129

# WRONG (causes the DLL conflict above):
#   torch==2.13.0+cu126   ← torch CUDA 12.6 ≠ paddle 12.9
#   torch==2.13.0+cu130   ← torch CUDA 13.0 ≠ paddle 12.9
```

After installing, verify both in the SAME process report matching CUDA 12.9:
```
conda run -n pdfextract python -c "import torch,paddle; print(torch.__version__, torch.backends.cudnn.version(), '|', paddle.version.cuda(), paddle.version.cudnn())"
# expected: 2.8.0+cu129 91002 | 12.9 9.9.0
```

## Verified environment setup（`pdfextract` conda env）

```
# create env
conda create -n pdfextract python=3.10
conda activate pdfextract

# torch GPU build — MUST be cu129 to match paddle 3.2.2 (CUDA 12.9)
pip install torch==2.8.0+cu129 torchvision==0.24.0+cu129 --index-url https://download.pytorch.org/whl/cu129

# core deps (official PDF-Extract-Kit requirements)
pip install omegaconf matplotlib PyMuPDF ultralytics doclayout-yolo "unimernet==0.2.3" paddleocr==2.7.3 struct-eqtable lmdeploy

# transformers/tokenizers: PDF-Extract-Kit's tokenizer.json is old-format; 0.19 crashes,
# 0.15 is rejected by transformers==4.42.4. Use this combo (verified):
pip install "transformers==4.45.2" "tokenizers==0.20.3"

# PaddleOCR GPU build (paddlepaddle_gpu, NOT the CPU-only paddlepaddle)
pip uninstall -y paddlepaddle paddlepaddle_gpu
pip install paddlepaddle_gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
```

## PDF-Extract-Kit 源码与权重（ModelScope 主源）

```
git clone https://github.com/opendatalab/PDF-Extract-Kit.git  <model_root>
```
权重从 ModelScope 仓库 `opendatalab/pdf-extract-kit-1.0` 拉取（HF 在部分网络不可达），落位即上文「派生路径」表（MFD / MFR / OCR / Layout 四组）。各权重的结构要求见「Model weights」。

## ⚠️ Critical: the `nvidia/cudnn/bin` folder MUST be EMPTY (paddle reuses torch's cudnn)

This is the single most important, non-obvious requirement. PDF-Extract-Kit loads **torch** and **paddle** in the same process; both ship a `cudnn64_9.dll` with the same filename but different internal builds. If paddle's own `nvidia/cudnn/bin/*.dll` files are present, paddle loads them and then fails on a cross-dependency (`cudnn_engines_precompiled64_9.dll` / `WinError 127`). The working setup is the opposite:

- **`<conda.env_path>\lib\site-packages\nvidia\cudnn\bin\` must contain NO `.dll` files.** With that folder empty, paddle cannot find its own cudnn there and automatically falls back to the **single copy inside `torch\lib\`**, so both frameworks share ONE cudnn → no collision. (Verified: with the folder empty, `INIT OK` + `PIPELINE OK`; populating it breaks the run.)
- The other nvidia cu12 runtime folders (`cublas\bin`, `cuda_runtime\bin`, `cufft\bin`, `curand\bin`, `cusolver\bin`, `cusparse\bin`, `nvjitlink\bin`) DO need their DLLs and should be left intact.
- The `nvidia-cudnn-cu12` pip package may be installed, but its `bin/*.dll` files must be moved out (keep them in a sibling backup folder, e.g. `nvidia\cudnn_bin_bak\`, so you can restore if needed).
- **Uninstall any `*-cu13` nvidia packages** if present — they drop `cublas64_13.dll` etc. into the same `nvidia/*/bin` folders and cause version clashes:
  ```
  pip uninstall -y nvidia-cublas-cu13 nvidia-cuda-runtime-cu13 nvidia-cudnn-cu13 nvidia-cufft-cu13 nvidia-curand-cu13 nvidia-cusolver-cu13 nvidia-cusparse-cu13 nvidia-nvjitlink-cu13
  ```
- Also keep the system CUDA path (`C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.x\bin`) OUT of the run's manual `PATH`, since it can shadow the cu12 runtime. The run launcher below handles PATH correctly.

## 启动提取（Windows）

首选 skill 自带的 **`launch_pipeline.sh`**（Git-Bash 运行，自动解析 `<conda.env_path>` 并设置 CUDA PATH）：

```bash
bash launch_pipeline.sh "<corpus_root>/<书名>/<书名>.pdf"          # 全本，页数自动识别
bash launch_pipeline.sh "<corpus_root>/<书名>/<书名>.pdf" --end 320 # 仅提取前 320 页
```

若机器无 Git-Bash / bash（`C:\Windows\system32\bash.exe` 是 WSL 启动器且未装发行版），改用 `flows/extract/extract.md` 的**统一 PowerShell 启动写法**（直接 `Start-Process python.exe`，不经 `cmd /c`）——中文路径 / 括号文件名实测安全；避免 `cmd /c` 包命令串与 `.bat`/`.ps1` 启动器（坑详见该文档「⚠️ Windows 启动失败模式」）。

`.bat` 启动器仅作 PATH 设置逻辑参考（某些 cmd 环境可运行）：

```bat
@echo off
setlocal
set PEK=<model_root>
set ENV=<conda.env_path>
set NV=%ENV%\lib\site-packages\nvidia
set PATH=%ENV%\lib\site-packages\torch\lib;^
%NV%\cublas\bin;%NV%\cuda_runtime\bin;%NV%\cufft\bin;^
%NV%\curand\bin;%NV%\cusolver\bin;%NV%\cusparse\bin;%NV%\nvjitlink\bin;^
%ENV%\Library\bin;%ENV%\Scripts;%ENV%;%PATH%
call %ENV%\Scripts\activate.bat
python %~dp0%1
endlocal
```

> **Note**: intentionally omit `%NV%\cudnn\bin` from PATH — that folder must stay empty so paddle reuses torch's cudnn (see the rule above).

Verify runtime (run inside `pdfextract`):
```
conda run -n pdfextract python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
conda run -n pdfextract python -c "import unimernet, paddle, paddleocr, struct_eqtable; print('deps OK')"
```

## Model weights（落位 = 上文「派生路径」表）

- **MFD** (`yolo_v8_ft.pt`): `<model_root>\models\models\opendatalab--PDF-Extract-Kit\snapshots\master\models\MFD\models\MFD\YOLO\yolo_v8_ft.pt`
- **MFR** (`unimernet_tiny`): `<model_root>\models\MFR\unimernet_tiny` — must contain `pytorch_model.pth` (the official `unimernet.py` hardcodes this filename). For the **full UniMERNet** model the weight is `pytorch_model.bin`; create a hardlink `pytorch_model.pth` → `pytorch_model.bin` (same pickle format). Full model config is 1024-dim; unimernet 0.2.3 default builds 512-dim, so prefer `unimernet_tiny` unless you specifically need the full model and adjust dimensions. MFR config file (pass as `cfg_path`): `<model_root>\pdf_extract_kit\configs\unimernet.yaml` (**absolute path**).
- **OCR** (PaddleOCR PP-OCRv4): detection `<model_root>\models\OCR\PaddleOCR\det\ch_PP-OCRv4_det`, recognition `<model_root>\models\OCR\PaddleOCR\rec\ch_PP-OCRv4_rec`. If missing, copy from the PaddleOCR cache (`paddleocr_cache`):
  ```
  <paddleocr_cache>\whl\det\ch\ch_PP-OCRv4_det_infer  ->  <model_root>\models\OCR\PaddleOCR\det\ch_PP-OCRv4_det
  <paddleocr_cache>\whl\rec\ch\ch_PP-OCRv4_rec_infer  ->  <model_root>\models\OCR\PaddleOCR\rec\ch_PP-OCRv4_rec
  ```

> **Note on `tasks/__init__.py`**: PDF-Extract-Kit unconditionally imports all tasks (incl. OCR/table) at package import. That requires `paddleocr`, `struct_eqtable`, etc. to be installed — which they are in the setup above. Do NOT comment out those imports; instead install the deps. Torch (cu129) and paddle (cu129/3.2.2) load in the **same process** and coexist because (a) their CUDA minor versions match (see the CUDA alignment rule) and (b) `nvidia/cudnn/bin` is kept empty so paddle reuses torch's single cudnn copy (see the cudnn-empty rule). If you see `WinError 127/193` on `cublas64_12.dll` / `cudnn_cnn64_9.dll`, check: torch is cu129 (not cu126/cu130), no `*-cu13` nvidia packages remain, and `nvidia/cudnn/bin` is empty.