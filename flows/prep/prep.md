# Flow: prep（准备 / Stage 0）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
首次运行本 skill 前，确认 Python 环境与 GPU 模型就绪，避免提取阶段中途失败。
## 前置
无。

## 步骤
1. 激活提取环境：
   ```powershell
   conda activate pdfextract
   python -c "import torch; print(torch.cuda.is_available())"   # 必须为 True
   ```
2. 确认可用 Python 解释器与依赖（PyMuPDF / PaddleOCR / torch+CUDA）路径正确。

## 本阶段规则
- 无硬性关卡；仅环境检查。若 `torch.cuda.is_available()` 为 `False`，**不要继续**，先修复环境（显存 / CUDA / 驱动）。

## 出口条件
- 出口：`cuda` 可用、环境就绪。

## 相关代码（路径相对 skill 根目录）
- 环境 / 模型绝对路径表见同目录 [`environment.md`](ref/environment.md)（SSOT）。

## 子流程
无。
