#!/usr/bin/env node
// katex_validate.js — REAL KaTeX rendering check for book-summarizer markdown.
// Unlike check_katex.py (regex heuristic only), this actually renders every
// display ($$...$$) and inline ($...$) math block with KaTeX and reports any
// parse error at its source line. Catches genuine LaTeX syntax errors
// (unbalanced braces, unsupported commands, bad \\ usage, etc.) that the
// heuristic cannot see.
//
// Usage:  node katex_validate.js <markdown_file>
// Exit 1 if any math block fails to render, else 0.
const katex = require('katex');
const fs = require('fs');

const file = process.argv[2];
if (!file) { console.error('Usage: node katex_validate.js <markdown_file>'); process.exit(2); }

const text = fs.readFileSync(file, 'utf8');
const lines = text.split('\n');
const errors = [];

function render(formula, display, line) {
  if (!formula.trim()) return;
  try {
    katex.renderToString(formula, { throwOnError: true, displayMode: display, strict: false });
  } catch (e) {
    const head = formula.length > 60 ? formula.slice(0, 57) + '…' : formula;
    errors.push(`line ${line}: ${display ? '$$ ' : 'inline $ '}[${head}] :: ${e.message.split('\n')[0]}`);
  }
}

function checkInline(str, lineNo) {
  let j = 0;
  while (j < str.length) {
    if (str[j] === '\\' && str[j + 1] === '$') { j += 2; continue; }
    if (str[j] === '$') {
      if (str[j + 1] === '$') { j += 2; continue; } // block delimiter, skip
      let k = str.indexOf('$', j + 1);
      while (k !== -1 && str[k - 1] === '\\') { k = str.indexOf('$', k + 1); }
      if (k === -1) {
        const head = str.slice(j + 1).length > 60 ? str.slice(j + 1, j + 61) + '…' : str.slice(j + 1);
        errors.push(`line ${lineNo + 1}: inline $ : UNPAIRED $ (no closing delimiter) :: [${head}]`);
        break;
      }
      render(str.slice(j + 1, k), false, lineNo + 1);
      j = k + 1;
    } else j++;
  }
}

let mode = 'text';
let buf = [];
let startLine = -1;

for (let idx = 0; idx < lines.length; idx++) {
  const raw = lines[idx];
  const s = raw.replace(/^(?:>\s*)+/, '');     // strip all blockquote levels for boundary detection
  const hasBq = raw.trimStart().startsWith('>');
  if (mode === 'text') {
    if (s.trim() === '$$') {
      mode = 'block'; buf = []; startLine = idx + 1;
    } else if (s.trim().startsWith('$$') && s.trim().endsWith('$$') && s.trim().length > 4) {
      render(s.trim().slice(2, -2).trim(), true, idx + 1);
    } else {
      checkInline(raw, idx);
    }
  } else { // block mode
    if (s.trim() === '$$') {
      render(buf.join('\n').trim(), true, startLine);
      mode = 'text'; buf = [];
    } else {
      buf.push(raw.replace(/^(?:>\s*)+/, '')); // strip all blockquote levels from content
    }
  }
}

if (errors.length) {
  console.log('KATEX RENDER ERRORS:');
  errors.forEach(e => console.log('  ' + e));
  process.exit(1);
} else {
  console.log('KATEX RENDER OK');
  process.exit(0);
}
