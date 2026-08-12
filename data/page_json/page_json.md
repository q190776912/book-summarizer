# page_*.json（OCR 原始页数据）

## 来源与性质
- **外部 OCR 工具**（PDF-Extract-Kit / UniMERNet / PaddleOCR）在抽取阶段生成，落盘于
  `<book>/_extract/page_NNN.json`（NNN 为三位零填充页码）。
- 本 skill **消费**此文件、但**不构造**它 —— 因此 `..` 下**没有**对应构造脚本。
  它是整条流水线的数据源头（"前置输入"），不是本 skill 的中间产物。

## 数据结构（核心字段；工具版本不同字段略异）
- `text`：`list[dict]`，每页文本行 / 块。每项常见字段：
  - `text`：字符串，该行/块文本；
  - `poly`：四点包围盒坐标数组 `[[x0,y0],[x1,y1],[x2,y2],[x3,y3]]`（版面坐标）；
  - `conf` / `score`：识别置信度。
- `formulas`：`list[dict]`（若存在公式），含 LaTeX 与位置信息。
- `page`：页序号；部分版本另含页面尺寸 `width` / `height`。

示例（最小形态，真实文件字段更丰富）：
```json
{
  "text": [
    { "text": "Chapter 3.1 introduces the basics of vector spaces." },
    { "text": "Definition 3.1. ...", "poly": [[0, 0], [100, 0], [100, 12], [0, 12]], "conf": 0.91 }
  ],
  "formulas": []
}
```

## 消费方
- verify **EXTRACT 层**（权威说明见 `../../verify/layers/data_provider/data_provider.md`）：扫描 `_extract` 的
  `page_*.json`，填 `ctx.items` / `ctx.entry_keys` / `ctx.all_keys`。
- `flows/extract/structure/script/extract_items*.py`：读取条目与键集，产出章节 `.md`。
- MM Repair 链路回写修正也落在 `page_*.json`（见 `../../flows/extract/mm_repair/mm_repair.md`）。

## 注意事项
- 书页码为**原书印刷页码**，不是 PDF 文件页码；OCR 噪声可能写入错误编号，需经 mm_repair 修复。
- `page_*.json` 缺失 / 无内容 → EXTRACT 层 FAIL（数据缺失）。
- 字段契约以实际 OCR 工具版本为准；本文件仅描述本 skill **读取**的字段。
