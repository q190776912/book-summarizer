# derive-translate / script — 派生 + 校验翻译版（Stage 5）

本流程**不新增脚本**，复用前面流程的代码：
- 派生翻译：`write-source/format/script` 的 `flows/extract/script/extract/extract_items` 系列 + `format/*` 后处理
- 嵌图：`write-source/figures/script` 的 `../../script/figure/embed_figures.py`
- 校验：`verify/script/verify_chapter.py --all <extract_dir> <book_dir>`（针对翻译版）
