# book-summarizer 公用化改造方案（评审稿）

目标：让 skill 可在其他用户的 Windows 机器上直接安装使用。现状已具备良好基础（`lib/boot.py` 自举、`data/` 契约目录、CI 冒烟测试），核心问题只有三类：**用户特定硬编码路径**、**无集中依赖清单**、**README 空壳**。

已确认的决策：
- 配置放 **skill 根目录** `user_config.json`（`config/` 目录是"书籍处理过程配置"（verify_config / ignore_chN），不混用）
- 环境变量可覆盖（脚本直接调用场景）
- **仅支持 Windows**
- 书库目录**契约固定**（`<书名>\<书名>.pdf`），只参数化根路径

---

## 1. 配置设计

### 1.1 配置文件：`user_config.json`（skill 根目录）

```jsonc
{
  "corpus_root": "D:/study/book",
  "model_root": "D:/study/model/PDF-Extract-Kit",
  "conda": {
    "env_name": "pdfextract",
    "env_path": "D:/anaconda3/envs/pdfextract"
  },
  "paddleocr_cache": "C:/Users/<user>/.paddleocr"
}
```

- `corpus_root`：书库根（目录契约 `<corpus_root>\<书名>\` 不变）
- `model_root`：PDF-Extract-Kit 根目录，**各权重路径由它派生**（见 1.3），用户无需逐项配置
- `conda`：提取用 Python 环境
- `paddleocr_cache`：仅文档/校验用（det/rec 权重缺失时的拷贝来源）

### 1.2 优先级与环境变量覆盖

读取优先级：**env 变量 > user_config.json > 内置默认值**。env 变量名统一前缀 `BKS_`：

| 配置项 | env 变量 |
|--------|----------|
| corpus_root | `BKS_CORPUS_ROOT` |
| model_root | `BKS_MODEL_ROOT` |
| conda.env_name | `BKS_CONDA_ENV_NAME` |
| conda.env_path | `BKS_CONDA_ENV_PATH` |
| paddleocr_cache | `BKS_PADDLEOCR_CACHE` |

内置默认值 = 作者机器当前值（`D:/study/book` 等），保证仓库克隆后不配也能跑（作者习惯）；但**缺失必报错**的场景（如 make_config 缺 `_extraction_done.json`）保持 fail-fast 原则——config 缺失时不猜路径，报错指向 README 安装章节。

### 1.3 派生权重路径（由 model_root 派生，不单独配置）

| 用途 | 派生路径 |
|------|----------|
| MFD 权重 | `<model_root>/models/models/opendatalab--PDF-Extract-Kit/snapshots/master/models/MFD/models/MFD/YOLO/yolo_v8_ft.pt` |
| MFR 目录 | `<model_root>/models/MFR/unimernet_tiny` |
| MFR 配置 | `<model_root>/pdf_extract_kit/configs/unimernet.yaml` |
| OCR det | `<model_root>/models/OCR/PaddleOCR/det/ch_PP-OCRv4_det` |
| OCR rec | `<model_root>/models/OCR/PaddleOCR/rec/ch_PP-OCRv4_rec` |
| Layout | `<model_root>/models/Layout/YOLO/doclayout_yolo_ft.pt` |

### 1.4 实现：`lib/user_config.py`（新建）

- `load()`：合并 env + json + defaults，返回命名空间对象
- 提供 `model_root()` 派生权重路径的辅助函数
- **只读缓存**（多次调用不重读文件）；文件不存在且 env 未给 → 用 defaults + 打印警告
- 注意：`lib/boot.py` 的 `setup()` 先于 config 加载执行（config 读取不依赖 boot，但被 boot 注入路径的模块可用）

---

## 2. 逐文件改造清单

### 2.1 代码文件（改）

| 文件 | 现状 | 改法 |
|------|------|------|
| `flows/extract/pipeline/script/extract_book.py` | 7 处 `D:\study\model\...` 权重硬编码（:64-71） | 改用 `lib/user_config` 派生路径 |
| `flows/script/extract_figures.py` | `DEFAULT_WEIGHTS = D:\study\model\...doclayout_yolo_ft.pt`（:118） | 同上 |
| `launch_pipeline.sh` | `ENV="D:/anaconda3/envs/pdfextract"`（:16）+ CUDA PATH hack | env_path 从 `BKS_CONDA_ENV_PATH` / config 解析；PATH hack 逻辑保留但基于 env_path 拼装；注释说明这是本机调优项 |
| `verify/script/review_tool.py` | `PY = D:\anaconda3\envs\pdfextract\python.exe`（:25） | 从 config 读 |
| `flows/_flow_contract.py` | prep 检查硬编码 `conda activate pdfextract`（:44） | env_name 从 config 读 |
| `config/ignore_chN/manage_ignore.py` | 帮助文本示例路径 `D:\study\book\...`（:28） | 改为 `<corpus_root>\...` 占位 |
| `config/verify_config/tests/test_config_complete.py`、`test_q_layer_formula_regression.py` | `CORPUS_ROOT = D:\study\book`（:79 / :75） | 改为从 config 读或指向 `verify/tests/fixtures/` 独立 fixture |

### 2.2 代码文件（清理，不接 config）

| 文件 | 处理 |
|------|------|
| `tools/_audit_verify_config_depth.py`、`tools/_fix_verify_config_depth.py`、`tools/_validate_verify_config_load.py` | 均硬编码 `D:/study/book` 且属 `_` 前缀一次性诊断工具。按 SKILL.md「tools/ 只放通用工具」规则**删除**（或移入对应书 `_extract/`），不留公用仓库 |
| `tools/_chapter_items.txt`、`tools/_ch0_dump.txt` | `_*.txt` 已在 .gitignore，确认不进仓库即可 |

### 2.3 文档文件（改）

| 文件 | 改法 |
|------|------|
| `SKILL.md` | 目录契约 `D:\study\book\<书名>` → `<corpus_root>\<书名>`，注明"corpus_root 见 README 配置"；顺手修正「核心脚本速查」旁 `lib/config.py` 的不实引用（该文件当前不存在，SKILL.md:93 提到它，改为实际存在的 `lib/util.py` / `lib/flow_gate.py` 等；另由本次新增 `lib/user_config.py` 承接配置职责） |
| `flows/extract/extract.md` | 分支 A–D 的 `D:\study\book` 示例（:9,23,81-84,91,103-104,110）→ `<corpus_root>` 占位 |
| `flows/extract/pipeline/pipeline.md` | 权重路径引用（:21,61）→ 参数化说明 |
| `flows/prep/ref/environment.md` | 从"本机备忘"改写为"安装指引"：参数化所有路径 + 保留 ModelScope 下载源说明 + cudnn PATH hack 注明为可选调优 |

### 2.4 新增文件

| 文件 | 内容 |
|------|------|
| `user_config.json`（gitignore，**不随仓库上传**） | 用户实际配置；首次使用由 Agent 探测 + 询问后写入 |
| `lib/user_config.py` | 1.4 所述加载器 + 自动探测（`discover()` / `missing()` / `status` CLI） |
| `docs/install.md` | 安装依赖表 + 权重下载 + 环境验证（或并入 README） |

> 终稿调整：`user_config.example.json` 取消，内置默认值（作者机器值）写进 `lib/user_config.py` 的 `_DEFAULTS`；配置文件名统一为 `user_config.json`；依赖目录先自动探测（`discover` 常见位置），探测不到才询问用户"是否已有目录 → 没有则引导安装"。

### 2.5 .gitignore / CI

- `.gitignore` 增加 `user_config.json`
- `verify-smoke.yml` 无需改动（只跑纯 Python 校验层，无 GPU/权重依赖）；确认新增 `lib/user_config.py` 不影响 boot 注入与冒烟

---

## 3. 依赖表（写入文档）

| 组件 | 用途 | 来源 | 备注 |
|------|------|------|------|
| conda + Python 3.10+ | 基础环境 | conda | 现有 pycache 出现 3.10/3.13，建议文档锁定 3.10（torch/paddle 兼容最稳） |
| PyTorch + CUDA | MFR/MFD 推理 | pip（官方源） | 需 GPU；CPU 可用但慢 |
| PDF-Extract-Kit（源码） | 提取引擎 | GitHub 源码 clone 到 model_root | `pdf_extract_kit` 包 + configs |
| 权重：MFD `yolo_v8_ft.pt` | 公式检测 | ModelScope `opendatalab/pdf-extract-kit-1.0`（HF 此环境不可达，文档以 ModelScope 为主源） | 落位见 1.3 派生路径 |
| 权重：MFR `unimernet_tiny` | 公式识别 | 同上 | 需含 `pytorch_model.pth`；全量模型需 hardlink + 调维度，文档注明用 tiny |
| 权重：OCR `ch_PP-OCRv4_det/rec` | 文本识别 | 同上 / PaddleOCR 缓存 | |
| 权重：`doclayout_yolo_ft.pt` | 图片/版式检测 | 同上 | 图提取用 |
| PaddleOCR（pip） | OCR 依赖 | PDF-Extract-Kit 依赖链 | |
| Git-Bash | 启动后台提取 | git for windows | `launch_pipeline.sh` 依赖；.bat/.ps1 因安全策略/空格路径不可用 |

---

## 4. README 大纲（重写）

1. 简介 + 能力一览（PDF → 逐章 markdown，定义/定理/例题 + KaTeX + 嵌图）
2. 安装：前置依赖表（上表）→ 权重下载 → `user_config.json` 配置
3. 快速开始：一条命令示例（`flow_runner run` / `launch_pipeline.sh`）
4. 目录契约说明
5. 环境变量覆盖表
6. 常见问题（cudnn PATH、HF 不可达、CPU 无 GPU、中文书 vs 英文书输出语言）
7. 架构速览（指向 SKILL.md / flows / verify 文档）

---

## 5. 待决问题

1. ~~**gm 体例书例外**~~（已结案）：gm = Gelfand–Manin《Methods of Homological Algebra》一类把条目印成小节标题的排印体例，对应 `ORDINAL_GM = 6`。已核查书库：**无任何书实际启用 type 6/5**，属休眠的通用能力，且有测试覆盖。决定：**保留内置，不抽配置项**，公用后对普通用户无副作用。
2. **`verify/section_continuity` 等对「中英 1:1 同构」的强制**：这是该 skill 核心卖点，保持默认不变。
3. ~~是否用作者当前值作 example~~（已结案）：**作者当前值 = 内置默认参数**（写入 `lib/user_config.py::_DEFAULTS`，`D:/study/book` 等），不再有 example 文件；配置文件名统一 `user_config.json`（gitignore，首次使用由 Agent 探测 + 询问写入），README 注明按需修改。
4. ~~发布形态~~（已结案）：**公开 GitHub 仓库，纯 skill 目录即仓库**（`.github/workflows` 已就绪）。skill 本质是「SKILL.md + 脚本」目录，opencode / Claude Code 等按目录加载，不绑定工具；README 安装章节写清：clone → 把目录放入目标工具的 skills 路径（如 `~/.agents/skills/`）→ 配置 `user_config.json` → 跑 prep 验证。

---

## 6. 实施顺序

1. `lib/user_config.py` + `user_config.example.json` + `.gitignore`
2. 代码文件改造（2.1）→ 跑 `verify-smoke`（`python -m pytest verify/tests`）回归
3. 临时工具清理（2.2）
4. 文档改造（2.3）+ README 重写
5. 本机实测：`flow_runner.py run <book> prep/extract` 跑通一章确认无回归