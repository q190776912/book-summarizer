"""
_template_layer.py — 新增校验层时的复制起点（非层文件，自动发现跳过）。

使用方法：
  1. 复制本文件为 `X_layer.py`（`X` 为大写字母，且不能与现有 16 个 code 重复：
     EXTRACT / D / A / B / C / E / F / G / H / I / J / K / L / M / N / O）。
  2. 修改类名为 `XLayer`，设置 `code='X'`、`order`（现有占用 0..15，新层用 16+）、
     `auto_fixable` 及（若可自动修复）`fix_order`。
  3. 实现 `run(self, ctx) -> LayerResult`（返回本层贡献的结果字典键）。
     若层可自动修复，再实现 `fix(self, ctx) -> LayerFixResult`，并把变更数放进
     `fix_dict`（键名即 fix 契约键，须与 registry.py 的合并逻辑、report.py 的
     展示顺序约定保持一致）。
  4. 本文件以 '_' 开头，register_all.py 的自动发现会跳过它，因此它不会被当作一层。

⚠️ 若你的层要贡献**新的**结果字典键（即 DEFAULT_RESULT 里还没有的键），
   必须同步更新：
     - `verify/registry.py` 的 `DEFAULT_RESULT`（增加该键及正确类型的占位值），
     - `verify/report.py` 的 `print_result`（增加该键的展示逻辑），
   否则会破坏字节契约（report 可能遇到缺失键 / 错误类型）。本次重构只做加层用，
   作为提醒，不必现在就改。

`ctx` 可用字段（由 VerifyContext 提供）：ch, start, end, md_file, ext_dir,
manual_path, ignore_keys, ignore_fig, scheme，以及部分层写入的 e_layer / fig_skipped。
"""
from verify.registry import VerifyLayer, LayerResult, LayerFixResult


class TemplateLayer(VerifyLayer):
    """示例层：复制到 X_layer.py 后改名并填实现。"""

    code = 'X'            # 稳定标识符，单大写字母，禁止与现有 16 个重复
    order = 16            # 运行顺序；现有 0..15 已占用，新层用 16+
    fix_order = 12        # 仅当 auto_fixable=True 时需要；当前占用 1/5/6/7/8/9/10/11
    auto_fixable = False  # 若支持 --fix 自动修复，改为 True 并实现 fix()

    def run(self, ctx):
        # 示例：照搬 G 层形态，返回 LayerResult(code=self.code, metadata={...})
        count = 0
        return LayerResult(code=self.code, legacy=None, metadata={
            'xxxx': count,   # 'xxxx' 换成你的结果字典键（须已在 DEFAULT_RESULT 注册）
        })

    def fix(self, ctx):
        # 仅当 auto_fixable=True 时实现；返回 LayerFixResult(fix_dict={'xxxx': 变更数})
        changes = 0
        return LayerFixResult(fix_dict={'xxxx': changes})
