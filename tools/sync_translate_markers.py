"""tools/sync_translate_markers.py — 用**本侧 manifest 记录**复位单元首行标记（源侧/译侧各自对账）。

`check_translate_parity` 判据 12 要求：每个单元文件首行
`<!-- book-summarizer DONE unit: id=… type=… key=… name=… -->` 的四个字段，必须与**该单元
在自己那侧 `manifest.json` 里的记录**逐字相同。历史上代理会改写首行 `name=`（补全被拆分截断
的标题、顺手多敲字符），也有源文件首行存着 UTF-8 二次解码成的乱码而 manifest 正确——首行是
「代理有没有动过这一行」的唯一证据，脱账即失效。

姿势：只重写首行、且以 **manifest 为真值**（manifest 若错，先改 manifest——那才是审计面）。
正文一字节不动；首行不进最终 md（`merge_units._read_body` 从 marker 之后取正文），故复位
标记**不需要**重跑 merge / verify。

用法：
    python tools/sync_translate_markers.py <extract_dir> [--ch 1 2 A ...] [--side units|units-translate] [--apply]
默认 dry-run（列出将要复位的单元与差异），`--apply` 才写盘。退出码：dry-run 下有差异 = 1。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lib.boot as boot  # noqa: E402
boot.setup()

from data.book_structure.book_structure import (  # noqa: E402
    list_chapter_keys, prime_chapter_kinds, resolve_chapter_json_path, unit_dir_name)

MARK_RE = re.compile(
    r"^<!--\s*book-summarizer\s+(DONE|DRAFT)\s+unit:\s*"
    r"id=(\S*)\s+type=(?P<type>\S*)\s+key=(.*?)\s+name=(.*?)\s*-->$")
TPL = "<!-- book-summarizer %s unit: id=%s type=%s key=%s name=%s -->"


def contract_names(ext, ch):
    """该章契约里所有节点的 `name` 集合（真值锚点）。

    🔴 契约路径必须走 `resolve_chapter_json_path`（按磁盘物理证据解析章型）：旧的
    手写候选只有 `ch{N}` / `appendix{X}`，**补篇 `supplement{S}.json` 永远读不到**
    → `names` 为空 → 该章每个单元都被判成「manifest 与契约脱账」而跳过复位
    （Katok supplementS 实测 41 个单元全部误跳）。
    """
    p = resolve_chapter_json_path(ext, ch)
    names = set()
    if not os.path.exists(p):
        return names

    def walk(n):
        if isinstance(n, dict):
            v = str(n.get("name") or "")
            if v:
                names.add(v)
            for x in n.values():
                walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)
    walk(json.load(open(p, encoding="utf-8")))
    return names


def manifest_matches_contract(name, key, names):
    """manifest 的 `name` 是否站在契约那一侧（拆分时的两种成形方式：原样 / `key + 空格 + 名`）。

    空 `name` 无需仲裁（desc/条目常无契约名，`contract_names` 本就不收空串）——放行让 `type` 那关裁定。
    """
    if not name:
        return True
    return any(name == n or name == "%s %s" % (key, n) for n in names)


# 契约节点 type → 单元/manifest 侧的单元 type（与 split_draft_units.emit 的取值一致：
# 描述节点叫 desc、条目按体例叫 item、节/章/习题块同名）。
_CTYPE2UTYPE = {"description": "desc", "exercise": "exercise",
                "section": "section", "chapter": "chapter"}


def contract_unit_types(ext, ch):
    """→ `{契约 key: {该键允许的单元 type…}}`。

    同一键可对应多个契约节点（`10.2` 既是节也是该节习题块；`例1` 逐节重启），故取集合。
    用途 = 仲裁 `type` 脱账究竟是谁错：real-analysis `ch22/0014` 的契约节点是
    `type=description`，同书 568 个同类单元的 manifest 都已归一成 `desc`，唯独这条
    manifest 仍写 `description` → **错的一侧是 manifest**，按 manifest 复位首行会把对的改成错的。
    """
    p = resolve_chapter_json_path(ext, ch)
    out = {}
    if not os.path.exists(p):
        return out

    def walk(n):
        if isinstance(n, dict):
            k = str(n.get("key") or "")
            t = str(n.get("type") or "")
            if k and t:
                out.setdefault(k, set()).add(_CTYPE2UTYPE.get(t, "item"))
            for x in n.values():
                walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)
    walk(json.load(open(p, encoding="utf-8")))
    return out


def type_side_that_matches_contract(unit_type, manifest_type, key, types_by_key):
    """`type` 脱账时裁定哪一侧站在契约上 → ("manifest"|"unit"|"both"|"neither", 契约允许的集合)。

    "manifest" = manifest 合契约（应把首行复位成它）；"unit" = 首行合契约、**manifest 才是错的**，
    此时复位首行会把对的一侧改成错的，必须跳过并提示先修 manifest。
    """
    allowed = types_by_key.get(str(key or ""), set())
    u_ok, m_ok = unit_type in allowed, manifest_type in allowed
    if m_ok and not u_ok:
        return "manifest", allowed
    if u_ok and not m_ok:
        return "unit", allowed
    return ("both" if (u_ok and m_ok) else "neither"), allowed


def _diff(path, rec):
    """→ (raw, nl, 现首行, 应有首行)；已一致时返回 None。

    🔴 CRLF 判定只能看「首段是否以 CR 结尾」：`raw.split(b"\\n",1)[0]` 已经把换行符当分隔
    吃掉，段内永远不含 CRLF，用 `in` 判会恒定得出 LF，于是首行留着一个 CR 参与比较——
    实测把整本书的单元都误报成「脱账」。
    """
    with open(path, "rb") as f:
        raw = f.read()
    head, sep, _rest = raw.partition(b"\n")
    if head.endswith(b"\r"):
        nl, line_bytes = b"\r\n", head[:-1]
    elif sep:
        nl, line_bytes = b"\n", head
    else:
        nl, line_bytes = b"", head
    line = line_bytes.decode("utf-8", "strict")
    m = MARK_RE.match(line)
    mark = m.group(1) if m else "DONE"
    want = TPL % (mark, rec.get("id"), rec.get("type"),
                  str(rec.get("key") or ""), str(rec.get("name") or ""))
    return (raw, nl, line, want) if line != want else None


def sync_side(ext, sub, ch, apply_changes=False):
    """→ (checked, changed, diffs)。

    🔴 只修「manifest 站在契约那一侧」的单元：两侧首行历史上互相被回填过，manifest 本身
    也可能是错的一侧（Robinson 动力学 `ch3/0051_section_3_6` 的 manifest name 是
    `3.6 Substitutions2`（多一个 2），而契约与文件首行都是正确的 `3.6 Substitutions`）——
    无脑按 manifest 复位会把**对的一侧改成错的**。逐字段裁定：
      * `name` → `manifest_matches_contract`（契约节点 name 集合）；
      * `type` → `contract_unit_types` + `type_side_that_matches_contract`（契约把
        `description` 归一成 `desc`、条目归一成 `item`；real-analysis `ch22/0014` 的
        manifest 漏归一仍写 `description`，错的一侧是 manifest，首行不得改）。
    任一字段裁定为「manifest 错」→ 整条跳过并打印「须先修 manifest」，本工具不动文件。
    """
    d = os.path.join(ext, "book_structure", sub, unit_dir_name(ch))
    mp = os.path.join(d, "manifest.json")
    if not os.path.isdir(d) or not os.path.exists(mp):
        return 0, 0, []
    names = contract_names(ext, ch)
    types_by_key = contract_unit_types(ext, ch)
    units = json.load(open(mp, encoding="utf-8")).get("units") or []
    checked = changed = skipped = 0
    diffs = []
    for u in units:
        p = os.path.join(d, str(u.get("file") or ""))
        if not os.path.exists(p):
            continue
        checked += 1
        r = _diff(p, u)
        if not r:
            continue
        raw, nl, line, want = r
        mname = str(u.get("name") or "")
        if not manifest_matches_contract(mname, str(u.get("key") or ""), names):
            skipped += 1
            diffs.append("%s/%s\n    跳过（manifest 与契约脱账，须先修 manifest）：\n"
                         "      manifest name=%s\n      契约 name 候选=%s"
                         % (unit_dir_name(ch), u.get("file"), mname[:120],
                            " / ".join(sorted(n for n in names
                                              if n[:20] == mname[:20])[:3])[:160] or "?"))
            continue
        # 🔴 type 单独裁定：契约把 description 归一成 desc、条目归一成 item。
        # 若 manifest 的 type 不合契约而首行的 type 合契约，则错的一侧是 manifest，不能改首行。
        lm = MARK_RE.match(line)
        unit_type = lm.group("type") if lm else ""
        mtype = str(u.get("type") or "")
        if unit_type != mtype:
            winner, allowed = type_side_that_matches_contract(
                unit_type, mtype, u.get("key"), types_by_key)
            if winner != "manifest":
                skipped += 1
                who = ("首行才是契约那一侧" if winner == "unit"
                       else "两侧都合契约（无法裁定）" if winner == "both"
                       else "两侧均不在契约账上")
                diffs.append("%s/%s\n    跳过（type 脱账，%s，须先修 manifest）：\n"
                             "      首行 type=%s / manifest type=%s / 契约该键允许=%s"
                             % (unit_dir_name(ch), u.get("file"), who, unit_type, mtype,
                                sorted(allowed) or "?"))
                continue
        changed += 1
        diffs.append("%s/%s\n    现首行: %s\n    manifest: %s"
                     % (unit_dir_name(ch), u.get("file"), line[:150], want[:150]))
        if apply_changes:
            head, sep, rest = raw.partition(nl)
            new = want.encode("utf-8") + (nl if sep else b"") + rest
            with open(p, "wb") as f:
                f.write(new)
            chk = MARK_RE.match(new.split(nl, 1)[0].decode("utf-8"))
            if not chk or chk.group(1) != "DONE":
                raise SystemExit("BUG: %s 复位后首行仍非 DONE 标记，已中止" % p)
            if len(new) - len(want.encode("utf-8")) != len(raw) - len(head):
                raise SystemExit("BUG: %s 复位改动了首行以外的字节，已中止" % p)
    if skipped:
        print("  [%s/%s] %d 个单元跳过（manifest 侧待人工修）" % (sub, unit_dir_name(ch), skipped))
    return checked, changed, diffs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("extract_dir")
    ap.add_argument("--ch", nargs="*", default=None, help="章键（1 / A / appendix），默认全部")
    ap.add_argument("--side", nargs="*", default=["units", "units-translate"])
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ext = a.extract_dir
    prime_chapter_kinds(ext)
    troot = os.path.join(ext, "book_structure", "units-translate")
    chs = a.ch or [k for k in list_chapter_keys(ext)
                   if any(os.path.isdir(os.path.join(ext, "book_structure", s,
                                                     unit_dir_name(k))) for s in a.side)]
    tot_c = tot_m = 0
    all_d = []
    for ch in chs:
        for sub in a.side:
            c, m, d = sync_side(ext, sub, ch, a.apply)
            tot_c += c
            tot_m += m
            all_d += d
    print("[%s] 单元文件 %d，首行与本侧 manifest 脱账 %d"
          % ("已复位" if a.apply else "待复位(dry-run)", tot_c, tot_m))
    for x in all_d:
        print("  " + x)
    if a.apply and tot_m and os.path.isdir(troot):
        print("提示：译侧首行变更后请复跑 check_translate_parity 确认判据 12 归零。")
    return 1 if (tot_m and not a.apply) else 0


if __name__ == "__main__":
    sys.exit(main())
