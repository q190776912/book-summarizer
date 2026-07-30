"""verify.layers — 每层一个自包含文件。

约定：
- 每个校验层 = 一个 X_layer.py 文件，文件内定义唯一的 VerifyLayer 子类，
  设置 code / order / fix_order / auto_fixable 并实现 run() / fix()。
- register_all.py 自动发现本包下所有非 '_' 前缀模块并注册，故新增层无需改其他文件。
- 以 '_' 开头的文件不是层：_fig_common.py 存放 E/F 共用 helper，_template_layer.py
  是新增层的复制模板，均被自动发现跳过。
"""
