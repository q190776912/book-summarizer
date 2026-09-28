# -*- coding: utf-8 -*-
"""snapshot_guard.py — 书树防误删护栏（mark 时快照 + 已完成步证据复演）

动机（2026-09-28 Apostol IANT 事故）：一个子代理把手敲错异体的探针文件写到
`book/数論/`，随后用 `rm -rf` "清理"时删掉了**真**书目录 `book/数论/<书>/` 整棵树——
源 PDF、分章契约、703 个已验收源单元、全部 manifest、OCR 结果 `page_*.json`、
图像资产、流程台账一次全灭；回收站无记录、卷影副本不可用。事后只能从会话转录
部分回放正文，OCR 只能重跑数小时。

本模块提供两件机械护栏，由 `tools/flow_runner.py` 在 sanctioned 入口上强制调用：

1. ``snapshot``：每次 `mark` 落账后把**可重建成本最高**的产物压成
   ``<extract_dir>/_snapshots/<时间戳>_<flow>.<step>.tar.gz``。
   轻量快照 = `book_structure/`（契约 + units + units-translate + manifest）
   + `_extract` 顶层 JSON/MD + 台账 + 书目录根级章 md；
   全量快照（tag 以 `.full` 结尾）另含 `page_*.json` 与 `figure*` 图像目录——
   只在 OCR 定稿（`extract.mm_repair`）那一刻打一次，因为此后它只会变不会回来。
   清理只发生在本模块自己创建的 `_snapshots/` 内，且只删同名家族的旧归档。

2. ``audit``：**复用 `flows/_flow_contract.EVIDENCE` 里已有的谓词**（不另造判据，
   避免检测趟与落账趟口径漂移），对台账里每个已完成步重新跑一遍证据复核；
   一旦某步的产物已经消失（被删/被移动/被截断），立即报告——这正是本事故里
   缺失的那 55 分钟告警。
"""
import glob
import os
import re
import tarfile
import time

SNAP_SUBDIR = "_snapshots"
KEEP_LITE = 6      # 轻量快照保留份数
KEEP_FULL = 2      # 全量快照保留份数

_LITE_GLOBS = [
    ("book_structure", "**"),          # 契约 + units + units-translate + manifest
    ("*.json", ""),                    # chapter_map / verify_config / _extraction_done / figure_index ...
    ("*.md", ""),                      # 工作单与仲裁笔记（brief / notes）
    (".flow_gate.json", ""),           # 台账本身
    ("_mm_repair/*.json", ""),         # 视觉决策与修复清单
]
_FULL_EXTRA = [
    ("page_*.json", ""),               # OCR 产物：重跑代价最大
    ("figure*", ""),                   # 图资产目录
]


def _snap_dir(extract_dir):
    return os.path.join(extract_dir, SNAP_SUBDIR)


def _is_ocr_page(name):
    """`page_NNN.json`（含多册子目录命名变体）= OCR 产物，只进全量快照。"""
    return re.match(r"^page_\d+\.json$", name) is not None


def _collect(extract_dir, book_dir, include_pages):
    """返回 (绝对路径, 归档内名) 清单；目录整体入档，通配只取顶层。"""
    out = []

    def add(path, arc):
        if os.path.isfile(path):
            out.append((path, arc))

    def keep(ap, rel):
        # 轻量快照只收文本级产物：OCR 页与图像体积大且只在 extract.mm_repair 定稿一次
        if not include_pages and (_is_ocr_page(os.path.basename(ap)) or rel.startswith("figure")):
            return False
        return True

    bs = os.path.join(extract_dir, "book_structure")
    if os.path.isdir(bs):
        for root, _dirs, files in os.walk(bs):
            for fn in files:
                ap = os.path.join(root, fn)
                rel = os.path.relpath(ap, extract_dir).replace(os.sep, "/")
                if keep(ap, rel):
                    out.append((ap, rel))
    patterns = list(_LITE_GLOBS)
    if include_pages:
        patterns += _FULL_EXTRA
    for pat, sub in patterns:
        base = os.path.join(extract_dir, sub) if sub else extract_dir
        if pat == "book_structure":
            continue
        for p in glob.glob(os.path.join(base, pat)):
            rel = os.path.relpath(p, extract_dir).replace(os.sep, "/")
            if os.path.isfile(p):
                if keep(p, rel):
                    add(p, rel)
            elif os.path.isdir(p):
                for root, _d, files in os.walk(p):
                    for fn in files:
                        ap = os.path.join(root, fn)
                        rel2 = os.path.relpath(ap, extract_dir).replace(os.sep, "/")
                        if keep(ap, rel2):
                            out.append((ap, rel2))
    for p in sorted(glob.glob(os.path.join(book_dir, "*.md"))):
        out.append((p, "_book_root/" + os.path.basename(p)))
    return out


def _prune(sd, family, keep):
    """只删本模块在 _snapshots/ 里写出的旧归档，别的文件一概不碰。"""
    group = sorted(glob.glob(os.path.join(sd, "*_%s.tar.gz" % family)))
    for old in group[:-keep] if keep > 0 else group:
        try:
            os.remove(old)
        except OSError:
            pass


def snapshot(book_dir, extract_dir, tag):
    """打一次快照；返回归档路径，无可归档内容时返回 None。"""
    if not extract_dir or not os.path.isdir(extract_dir):
        return None
    include_pages = tag.endswith(".full")
    files = _collect(extract_dir, book_dir, include_pages)
    if not files:
        return None
    sd = _snap_dir(extract_dir)
    os.makedirs(sd, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = "%s_%s.tar.gz" % (stamp, tag.replace("/", "_"))
    dest = os.path.join(sd, name)
    tmp = dest + ".part"
    with tarfile.open(tmp, "w:gz") as tf:
        for ap, arc in files:
            try:
                tf.add(ap, arcname=arc)
            except OSError:
                pass
    os.replace(tmp, dest)
    _prune(sd, tag.replace("/", "_"), KEEP_FULL if include_pages else KEEP_LITE)
    return dest


def restore_hint(extract_dir):
    sd = _snap_dir(extract_dir)
    group = sorted(glob.glob(os.path.join(sd, "*.tar.gz")))
    if not group:
        return "（无快照可回滚）"
    return "可用最近快照回滚: %s   命令: tar xzf <archive> -C <extract_dir>" % group[-1]


def audit(book_dir, extract_dir, status_fn, evidence_map, check_fn):
    """对台账里 DONE 的步复演证据谓词。

    参数由调用方（flow_runner）注入，判据与落账完全同源：
      status_fn(book_dir, extract_dir) -> {flow: {step: bool}}
      evidence_map  ``{"flow.step": callable|None}``（None = agent 自证，跳过）
      check_fn(flow, step, book_dir, extract_dir) -> (ok, detail)
    返回 [(flow.step, detail)]，空列表 = 全部证据仍在位。
    """
    bad = []
    st = status_fn(book_dir, extract_dir)
    for flow, steps in st.items():
        for step, done in steps.items():
            if not done:
                continue
            if not evidence_map.get("%s.%s" % (flow, step)):
                continue
            ok, detail = check_fn(flow, step, book_dir, extract_dir)
            if not ok:
                bad.append(("%s.%s" % (flow, step), detail))
    return bad
