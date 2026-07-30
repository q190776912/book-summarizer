#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mathify_plaintext.py — 把总结 md 中"裸写"的数学记号包进 $...$ 数学模式。

背景：早期生成的章节总结把行内数学直接写成纯文本，例如
    [x,y]、Rᵉ、K^+(A)、M⊗Rⁿ、g_{ab}、γ^n=0、H¹(R,Rᵉ)=0
这些 KaTeX 校验查不出来（它们根本不在数学模式里），但渲染出来就是原始字符。

本工具做三件事（只处理数学模式之外的文本）：
  1. Unicode 上/下标 → ^{...} / _{...}（Rᵒᵖ→R^{op}, vⱼ₋₁→v_{j-1}），
     该转换同时也应用于既有 $...$ / $$ 块内部（纯粹改善，语义不变）。
  2. 含"数学触发符"（[ ] = ^ _ ⊗ → ⊆ ∈ × ≅ 希腊字母 等）的 token
     整体包进 $...$，并把 Unicode 符号翻译成 KaTeX 宏（⊗→\otimes 等）。
  3. 字面花括号转义（{e_i}→\{e_i\}；g_{ij} 的下标花括号保留）。

安全护栏：
  - 跳过 display math（$$…$$，含 > $$ 块引用形式）内部（仅做上/下标转换）。
  - 跳过 HTML 行（<div/<img/</div>）、图片行（![）、代码围栏内部。
  - 行内 $ 计数为奇数的行整行跳过（结构可疑，不碰）。
  - token 紧邻既有 $ 时不包（避免造出 $$ 相邻）。
  - 含 ** 的 token 不碰（markdown 加粗标记）。
  - 默认 dry-run 只报告；--apply 才写回。

用法：
  python mathify_plaintext.py <book_dir|file.md> [--apply]
处理目录时自动发现 第*.md / Chapter*.md / 附录*.md / Appendix*.md。
之后务必跑 check_katex.py <file> --fix 复验真实 KaTeX 渲染。
"""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

import sys, re, glob, io, os

SUP = {'⁰':'0','¹':'1','²':'2','³':'3','⁴':'4','⁵':'5','⁶':'6','⁷':'7','⁸':'8','⁹':'9',
       '⁺':'+','⁻':'-','ⁿ':'n','ⁱ':'i','ᵉ':'e','ᵒ':'o','ᵖ':'p','ᵃ':'a','ᵇ':'b','ᶜ':'c',
       'ᵈ':'d','ˢ':'s','ᵗ':'t','ʳ':'r','ᵏ':'k','ˡ':'l','ᵐ':'m','ᵘ':'u','ᵛ':'v','ˣ':'x',
       'ʸ':'y','ᶻ':'z','ᵍ':'g','ʰ':'h','ʷ':'w','ᶠ':'f','ʲ':'j'}
SUB = {'₀':'0','₁':'1','₂':'2','₃':'3','₄':'4','₅':'5','₆':'6','₇':'7','₈':'8','₉':'9',
       '₊':'+','₋':'-','ₐ':'a','ₑ':'e','ₕ':'h','ᵢ':'i','ⱼ':'j','ₖ':'k','ₗ':'l','ₘ':'m',
       'ₙ':'n','ₒ':'o','ₚ':'p','ᵣ':'r','ₛ':'s','ₜ':'t','ᵤ':'u','ᵥ':'v','ₓ':'x'}
GREEK = {'α':'\\alpha','β':'\\beta','γ':'\\gamma','δ':'\\delta','ε':'\\varepsilon','ζ':'\\zeta',
         'η':'\\eta','θ':'\\theta','ι':'\\iota','κ':'\\kappa','λ':'\\lambda','μ':'\\mu','ν':'\\nu',
         'ξ':'\\xi','π':'\\pi','ρ':'\\rho','σ':'\\sigma','τ':'\\tau','υ':'\\upsilon','φ':'\\varphi',
         'χ':'\\chi','ψ':'\\psi','ω':'\\omega','Γ':'\\Gamma','Δ':'\\Delta','Θ':'\\Theta',
         'Λ':'\\Lambda','Ξ':'\\Xi','Π':'\\Pi','Σ':'\\Sigma','Φ':'\\Phi','Ψ':'\\Psi','Ω':'\\Omega',
         'ϕ':'\\phi','ϵ':'\\epsilon'}
SYM = {'⊗':'\\otimes','→':'\\to','←':'\\leftarrow','↦':'\\mapsto','⊆':'\\subseteq','⊇':'\\supseteq',
       '⊂':'\\subset','⊃':'\\supset','∈':'\\in','∉':'\\notin','×':'\\times','≅':'\\cong','≃':'\\simeq',
       '≠':'\\neq','≥':'\\ge','≤':'\\le','∀':'\\forall','∃':'\\exists','⇒':'\\Rightarrow',
       '⇐':'\\Leftarrow','⇔':'\\Leftrightarrow','∩':'\\cap','∪':'\\cup','⋊':'\\rtimes','⋉':'\\ltimes',
       '∑':'\\sum','∏':'\\prod','⊕':'\\oplus','⊖':'\\ominus','∘':'\\circ','·':'\\cdot','⋅':'\\cdot',
       '∧':'\\wedge','∨':'\\vee','∂':'\\partial','∇':'\\nabla','⊣':'\\dashv','⊥':'\\perp',
       '⟨':'\\langle','⟩':'\\rangle','∅':'\\varnothing','∞':'\\infty','±':'\\pm','∓':'\\mp',
       '≈':'\\approx','≡':'\\equiv','…':'\\dots','⋯':'\\cdots','−':'-','√':'\\sqrt',
       'ℂ':'\\mathbb{C}','ℤ':'\\mathbb{Z}','ℝ':'\\mathbb{R}','ℚ':'\\mathbb{Q}','ℕ':'\\mathbb{N}'}

ASCII_TOKEN = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                  "()[]{}=^_+-*/\\|.,:;'!?~&<>")
UNI_TOKEN = set(SUP) | set(SUB) | set(GREEK) | set(SYM) | set('–—′″')
TOKEN_CHARS = ASCII_TOKEN | UNI_TOKEN
# 触发包裹的字符（出现其一才认为 token 是数学）
TRIGGERS = set('[]=^_\\{}') | set(SUP) | set(SUB) | set(GREEK) | \
           (set(SYM) - set('–—')) 
NON_TRIG = set('…–—′″−')  # 这些即使在 SYM/token 中也不单独触发
TRIGGERS -= NON_TRIG
STRIP_TRAIL = '.,;:!?'


def conv_subsup(s):
    """把连续 Unicode 上/下标转为 ^{...}/_{...}。可用于任何文本（含数学内部）。"""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in SUP:
            j = i
            while j < n and s[j] in SUP:
                j += 1
            grp = ''.join(SUP[x] for x in s[i:j])
            out.append('^{%s}' % grp if len(grp) > 1 else '^' + grp)
            i = j
        elif c in SUB:
            j = i
            while j < n and s[j] in SUB:
                j += 1
            grp = ''.join(SUB[x] for x in s[i:j])
            out.append('_{%s}' % grp if len(grp) > 1 else '_' + grp)
            i = j
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def latexify(tok):
    """token → 合法 KaTeX：上下标转换、符号宏替换、字面花括号转义。"""
    t = conv_subsup(tok)
    out, i, n = [], 0, len(t)
    stack = []  # True=latex 花括号(保留)，False=字面(转义)
    while i < n:
        c = t[i]
        if c == '\\':                       # 反斜杠转义序列
            if i + 1 < n and t[i+1] in '*_':
                out.append(t[i+1])          # markdown 转义 \* \_ → 数学模式内还原
                i += 2
                continue
            out.append(c)
            if i + 1 < n:
                out.append(t[i+1])
                if t[i+1] == '{':
                    stack.append(True)
                i += 2
            else:
                i += 1
            continue
        if c == '{':
            if i > 0 and t[i-1] in '^_':
                stack.append(True); out.append('{')
            else:
                stack.append(False); out.append('\\{')
        elif c == '}':
            keep = stack.pop() if stack else False
            out.append('}' if keep else '\\}')
        elif c in GREEK:
            out.append(GREEK[c] + ' ')
        elif c in SYM:
            out.append(SYM[c] + ' ')
        else:
            out.append(c)
        i += 1
    r = ''.join(out)
    r = re.sub(r'\s+', ' ', r).strip()
    return r


def process_segment(seg, lbound='', rbound=''):
    """处理一段数学模式之外的纯文本，返回 (新文本, 包裹数)。
    lbound/rbound：该段左右紧邻的字符（'$' 表示贴着既有行内数学）。"""
    out, i, n, cnt = [], 0, len(seg), 0
    while i < n:
        c = seg[i]
        if c in TOKEN_CHARS:
            j = i
            while j < n and seg[j] in TOKEN_CHARS:
                j += 1
            tok = seg[i:j]
            trail = ''
            while tok and (tok[-1] in STRIP_TRAIL
                           or (tok[-1] == '-' and not (len(tok) >= 2 and tok[-2] in '^_'))):
                trail = tok[-1] + trail
                tok = tok[:-1]
            lead = ''
            has_trig = any(ch in TRIGGERS for ch in tok)
            prev_ch = seg[i-1] if i > 0 else lbound
            next_ch = seg[j] if j < n else rbound
            if (tok and has_trig and '**' not in tok and '%' not in tok
                    and prev_ch != '$' and next_ch != '$'
                    and not tok.startswith('---')):
                out.append(lead + '$' + latexify(tok) + '$' + trail)
                cnt += 1
            else:
                out.append(seg[i:j])
            i = j
        else:
            out.append(c)
            i += 1
    return ''.join(out), cnt


def process_line(line):
    """按行内 $...$ 分段处理。返回 (新行, 包裹数)。"""
    # $ 计数（未转义）为奇数 → 跳过整行
    dollars = [m.start() for m in re.finditer(r'(?<!\\)\$', line)]
    if len(dollars) % 2 == 1:
        return line, 0
    parts, cnt = [], 0
    pos, inmath = 0, False
    for d in dollars + [len(line)]:
        seg = line[pos:d]
        if inmath:
            parts.append(conv_subsup(seg))       # 数学内部只做上下标规范化
        else:
            lb = '$' if pos > 0 else ''
            rb = '$' if d < len(line) else ''
            new, k = process_segment(seg, lb, rb)
            parts.append(new); cnt += k
        if d < len(line):
            parts.append('$')
        pos = d + 1
        inmath = not inmath
    return ''.join(parts), cnt


def process_file(path, apply=False):
    text = io.open(path, encoding='utf-8').read()
    lines = text.split('\n')
    out, total = [], 0
    in_display = False
    in_fence = False
    for ln in lines:
        s = ln.strip()
        core = s.lstrip('> ').strip()
        if core.startswith('```'):
            in_fence = not in_fence
            out.append(ln); continue
        if in_fence:
            out.append(ln); continue
        if core == '$$':
            in_display = not in_display
            out.append(ln); continue
        if in_display:
            out.append(conv_subsup(ln)); continue
        if ('<div' in ln or '</div' in ln or '<img' in ln or '![' in ln
                or '](' in ln):
            out.append(ln); continue
        new, k = process_line(ln)
        out.append(new); total += k
    if total and apply:
        io.open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(out))
    return total


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply = '--apply' in sys.argv
    if not args:
        print(__doc__); sys.exit(1)
    target = args[0]
    if os.path.isdir(target):
        files = sorted(sum((glob.glob(os.path.join(target, p))
                            for p in ('第*.md', 'Chapter*.md', '附录*.md', 'Appendix*.md')), []))
    else:
        files = [target]
    grand = 0
    for f in files:
        n = process_file(f, apply=apply)
        grand += n
        if n:
            print('%-60s %4d token(s) %s' % (os.path.basename(f), n,
                  'WRAPPED' if apply else 'would wrap'))
    print('TOTAL: %d token(s) %s' % (grand, '(applied)' if apply else '(dry-run; use --apply)'))


if __name__ == '__main__':
    main()
