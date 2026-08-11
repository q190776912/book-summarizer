> 🔴 **本文件是该领域规则的唯一权威详细说明（SSOT）**。`SKILL.md` 与代码注释只引用此处、不重复描述；新增/修改该领域规则只改本文件。

# PDF-Extract-Kit Environment Setup (conda `pdfextract`)

> 本文件从 `SKILL.md` 的 `## Prerequisite` 段外移而来，集中放**安装 / 排障**类参考（CUDA-cudnn 对齐、conda 环境、权重绝对路径、启动器）。日常"总结一章"的流程不需要读它；只在**首次装环境**或**遇到 `WinError 127/193` 等 CUDA/cudnn 报错**时查阅。SKILL.md 中对应位置保留指针。

> **⚠️ All extraction steps MUST run inside the `pdfextract` conda env** (`conda activate pdfextract` before any python call). Never run the extraction scripts with the base/system Python (e.g. `C:\Program Files\Python313`), which has its own broken paddle and no torch GPU.

This skill uses **PDF-Extract-Kit** for formula detection (MFD), formula recognition (MFR → LaTeX) and text OCR, all on GPU. The verified working environment is a conda env named `pdfextract` on a CUDA 12.9 machine (e.g. RTX 5060, Compute Capability 12.0, Driver API 13.1).

## Reference paths (this machine)

All absolute paths used by the extraction scripts. Adjust only if you relocate the env / models.

| Purpose | Path |
|---------|------|
| Conda env root | `D:\anaconda3\envs\pdfextract` |
| Python executable | `D:\anaconda3\envs\pdfextract\python.exe` |
| Conda activate script | `D:\anaconda3\envs\pdfextract\Scripts\activate.bat` |
| nvidia cu12 runtime (under env) | `D:\anaconda3\envs\pdfextract\lib\site-packages\nvidia\` (subdirs `cublas\bin`, `cuda_runtime\bin`, `cudnn\bin`, `cufft\bin`, `curand\bin`, `cusolver\bin`, `cusparse\bin`, `nvjitlink\bin`) |
| **cudnn bin must be EMPTY** | `D:\anaconda3\envs\pdfextract\lib\site-packages\nvidia\cudnn\bin\` (0 `.dll` files) |
| torch's bundled cudnn (the copy paddle reuses) | `D:\anaconda3\envs\pdfextract\lib\site-packages\torch\lib\` |
| PDF-Extract-Kit root | `D:\study\model\PDF-Extract-Kit` |
| PDF-Extract-Kit package | `D:\study\model\PDF-Extract-Kit\pdf_extract_kit` |
| MFD weight (`yolo_v8_ft.pt`) | `D:\study\model\PDF-Extract-Kit\models\models\opendatalab--PDF-Extract-Kit\snapshots\master\models\MFD\models\MFD\YOLO\yolo_v8_ft.pt` |
| MFR weight (`unimernet_tiny`) | `D:\study\model\PDF-Extract-Kit\models\MFR\unimernet_tiny` (needs `pytorch_model.pth`) |
| MFR config (`unimernet.yaml`) | `D:\study\model\PDF-Extract-Kit\pdf_extract_kit\configs\unimernet.yaml` (use **absolute** path in scripts) |
| OCR detection weight | `D:\study\model\PDF-Extract-Kit\models\OCR\PaddleOCR\det\ch_PP-OCRv4_det` |
| OCR recognition weight | `D:\study\model\PDF-Extract-Kit\models\OCR\PaddleOCR\rec\ch_PP-OCRv4_rec` |
| DocLayout-YOLO weight (`doclayout_yolo_ft.pt`) | `D:\study\model\PDF-Extract-Kit\models\Layout\YOLO\doclayout_yolo_ft.pt`（图片提取 `flows/script/figure/extract_figures` 用；从 ModelScope `opendatalab/pdf-extract-kit-1.0` 拉，HF 此环境不可达） |
| Summary folder (per book) | `D:\study\book\<书名>\` — the markdown chapter files live here. |
| Extracted JSON (per-page) | `D:\study\book\<书名>\_extract\page_*.json` — directly in `_extract\` |
| Skill scripts directory | `C:\Users\ye190\.workbuddy\skills\book-summarizer\` |

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

## Verified environment setup (`pdfextract` conda env)

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

## ⚠️ Critical: the `nvidia/cudnn/bin` folder MUST be EMPTY (paddle reuses torch's cudnn)

This is the single most important, non-obvious requirement. PDF-Extract-Kit loads **torch** and **paddle** in the same process; both ship a `cudnn64_9.dll` with the same filename but different internal builds. If paddle's own `nvidia/cudnn/bin/*.dll` files are present, paddle loads them and then fails on a cross-dependency (`cudnn_engines_precompiled64_9.dll` / `WinError 127`). The working setup is the opposite:

- **`D:\anaconda3\envs\pdfextract\lib\site-packages\nvidia\cudnn\bin\` must contain NO `.dll` files.** With that folder empty, paddle cannot find its own cudnn there and automatically falls back to the **single copy inside `torch\lib\`**, so both frameworks share ONE cudnn → no collision. (Verified: with the folder empty, `INIT OK` + `PIPELINE OK`; populating it breaks the run.)
- The other nvidia cu12 runtime folders (`cublas\bin`, `cuda_runtime\bin`, `cufft\bin`, `curand\bin`, `cusolver\bin`, `cusparse\bin`, `nvjitlink\bin`) DO need their DLLs and should be left intact.
- The `nvidia-cudnn-cu12` pip package may be installed, but its `bin/*.dll` files must be moved out (keep them in a sibling backup folder, e.g. `nvidia\cudnn_bin_bak\`, so you can restore if needed).
- **Uninstall any `*-cu13` nvidia packages** if present — they drop `cublas64_13.dll` etc. into the same `nvidia/*/bin` folders and cause version clashes:
  ```
  pip uninstall -y nvidia-cublas-cu13 nvidia-cuda-runtime-cu13 nvidia-cudnn-cu13 nvidia-cufft-cu13 nvidia-curand-cu13 nvidia-cusolver-cu13 nvidia-cusparse-cu13 nvidia-nvjitlink-cu13
  ```
- Also keep the system CUDA v13.1 path (`C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.1\bin`) OUT of the run's manual `PATH`, since it can shadow the cu12 runtime. The run launcher below handles PATH correctly.

## Recommended run launcher

> **本环境改用 `launch_pipeline.sh`**（skill 自带的 bash 脚本）：`.bat` 启动器仅适用于能直接运行 `.bat` 的 Windows cmd 环境；本环境的安全策略会拦截 `Start-Process`/`.bat`，且空格路径静默失败。下面 `.bat` 仅作 PATH 设置逻辑的参考。

Launch extraction scripts through a small `.bat` that sets PATH to `torch\lib` + the nvidia cu12 bins first, then calls the env's python. (历史上的 `run_extract.bat` 已退役至 `_retired/`；首选 skill 自带的 `launch_pipeline.sh`。) Example launcher placed next to the script:

```bat
@echo off
setlocal
set PEK=D:\study\model\PDF-Extract-Kit
set ENV=D:\anaconda3\envs\pdfextract
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

## Model weights (absolute paths — see Reference paths table above)

- **MFD** (`yolo_v8_ft.pt`): `D:\study\model\PDF-Extract-Kit\models\models\opendatalab--PDF-Extract-Kit\snapshots\master\models\MFD\models\MFD\YOLO\yolo_v8_ft.pt`
- **MFR** (`unimernet_tiny`): `D:\study\model\PDF-Extract-Kit\models\MFR\unimernet_tiny` — must contain `pytorch_model.pth` (the official `unimernet.py` hardcodes this filename). For the **full UniMERNet** model the weight is `pytorch_model.bin`; create a hardlink `pytorch_model.pth` → `pytorch_model.bin` (same pickle format). Full model config is 1024-dim; unimernet 0.2.3 default builds 512-dim, so prefer `unimernet_tiny` unless you specifically need the full model and adjust dimensions. MFR config file (pass as `cfg_path`): `D:\study\model\PDF-Extract-Kit\pdf_extract_kit\configs\unimernet.yaml` (**absolute path**).
- **OCR** (PaddleOCR PP-OCRv4): detection `D:\study\model\PDF-Extract-Kit\models\OCR\PaddleOCR\det\ch_PP-OCRv4_det`, recognition `D:\study\model\PDF-Extract-Kit\models\OCR\PaddleOCR\rec\ch_PP-OCRv4_rec`. If missing, copy from the PaddleOCR cache:
  ```
  C:\Users\ye190\.paddleocr\whl\det\ch\ch_PP-OCRv4_det_infer  ->  D:\study\model\PDF-Extract-Kit\models\OCR\PaddleOCR\det\ch_PP-OCRv4_det
  C:\Users\ye190\.paddleocr\whl\rec\ch\ch_PP-OCRv4_rec_infer  ->  D:\study\model\PDF-Extract-Kit\models\OCR\PaddleOCR\rec\ch_PP-OCRv4_rec
  ```

> **Note on `tasks/__init__.py`**: PDF-Extract-Kit unconditionally imports all tasks (incl. OCR/table) at package import. That requires `paddleocr`, `struct_eqtable`, etc. to be installed — which they are in the setup above. Do NOT comment out those imports; instead install the deps. Torch (cu129) and paddle (cu129/3.2.2) load in the **same process** and coexist because (a) their CUDA minor versions match (see the CUDA alignment rule) and (b) `nvidia/cudnn/bin` is kept empty so paddle reuses torch's single cudnn copy (see the cudnn-empty rule). If you see `WinError 127/193` on `cublas64_12.dll` / `cudnn_cnn64_9.dll`, check: torch is cu129 (not cu126/cu130), no `*-cu13` nvidia packages remain, and `nvidia/cudnn/bin` is empty.
