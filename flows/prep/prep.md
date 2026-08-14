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
3. 安装 KaTeX 真渲染依赖（F 层公式校验必需；缺失时公式真渲染被跳过，仅走正则启发式并显式告警）：
   ```bash
   cd "<skill根>"
   npm install katex --no-save --no-audit --no-fund
   ```
   - 安装位置：**技能根 `node_modules/katex`**（`katex_render.py` 的 `_find_node_modules()` 第一候选即为
     技能根 `node_modules`）；node 也会从 `katex_validate.js` 所在目录向上回溯到技能根 `node_modules`，
     故装在技能根即可被原生解析。
   - 缺少该依赖时，`verify` 的 F 层不会静默放过：`katex_render.py` 会打印
     `[render] katex node_modules missing … (heuristic-only fallback)` 告警，真实 LaTeX 语法错误
     **不被检查**，仅走正则启发式。务必确认 `<skill根>/node_modules/katex` 目录存在后再跑 verify。

## 本阶段规则
- 无硬性关卡；仅环境检查。若 `torch.cuda.is_available()` 为 `False`，**不要继续**，先修复环境（显存 / CUDA / 驱动）。

## 出口条件
- 出口：`cuda` 可用、环境就绪，且 `<skill根>/node_modules/katex` 存在（F 层真渲染可用）。

## 相关代码（路径相对 skill 根目录）
- 环境 / 模型绝对路径表见同目录 [`environment.md`](ref/environment.md)（SSOT）。

## 子流程
无。
