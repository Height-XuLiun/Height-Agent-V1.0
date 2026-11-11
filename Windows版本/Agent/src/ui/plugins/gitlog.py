import datetime
import os
import re
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
import plat
STAT_RE = re.compile(r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?")
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path or ".").lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _w(s):
    n = 0
    for ch in s:
        n += 2 if ord(ch) > 0x2E7F else 1
    return n
def _pad(s, width):
    s = s if _w(s) <= width else s[:max(1, width - 1)] + "…"
    return s + " " * max(0, width - _w(s))
def _git(d, args, timeout=20):
    return plat.run_argv(["git", "-C", d] + args, timeout=timeout)
def git_log(path: str = ".", n: int = 20, file: str = "", author: str = "",
            stat: bool = False) -> str:
    d = _safe(path)
    if not d:
        return "路径越界，拒绝执行"
    if not os.path.isdir(d):
        return "目录不存在：%s" % path
    code, out = _git(d, ["rev-parse", "--is-inside-work-tree"])
    if code == 127:
        return "没找到 git 命令，这台机器上可能没装。"
    if code != 0 or "true" not in (out or ""):
        why = (out or "").strip().splitlines()
        return "不是 git 仓库：%s\n（git 说：%s）" % (path, why[0] if why else "无输出")
    n = max(1, min(200, int(n or 20)))
    br_code, branch = _git(d, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = (branch or "").strip() or "?"
    if br_code != 0:
        branch = "（还没有提交）"
    fmt = "--pretty=format:%h\t%ad\t%an\t%s"
    args = ["log", "-n", str(n), "--date=short", fmt]
    if author:
        args.append("--author=" + author)
    if file:
        args += ["--", file]
    code, out = _git(d, args, timeout=30)
    if code != 0:
        return "git log 失败：\n%s" % (out or "").strip()[:800]
    rows = []
    for line in (out or "").splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            rows.append(parts[:4])
    if not rows:
        return "仓库 %s（分支 %s）里没有符合条件的提交。" % (path, branch)
    dates = sorted(r[1] for r in rows if r[1])
    span = ""
    if dates:
        try:
            a = datetime.date.fromisoformat(dates[0])
            b = datetime.date.fromisoformat(dates[-1])
            span = "，%s → %s（跨 %d 天）" % (dates[0], dates[-1], (b - a).days + 1)
        except ValueError:
            span = "，%s → %s" % (dates[0], dates[-1])
    lines = [_pad("提交", 9) + " " + _pad("日期", 10) + " " + _pad("作者", 12) + "说明"]
    for h, dt, au, sub in rows:
        lines.append(_pad(h, 9) + " " + _pad(dt, 10) + " " + _pad(au, 12) + sub[:70])
    au_count = {}
    for r in rows:
        au_count[r[2]] = au_count.get(r[2], 0) + 1
    tops = sorted(au_count.items(), key=lambda x: -x[1])[:6]
    today = datetime.date.today()
    d7 = d30 = 0
    for r in rows:
        try:
            age = (today - datetime.date.fromisoformat(r[1])).days
        except ValueError:
            continue
        if age <= 7:
            d7 += 1
        if age <= 30:
            d30 += 1
    tail = ["作者分布：" + " · ".join("%s %d" % (k, v) for k, v in tops),
            "活跃度：近 7 天 %d 次，近 30 天 %d 次（按本次取样的 %d 条算）" % (d7, d30, len(rows))]
    if stat:
        sargs = ["log", "-n", str(n), "--pretty=format:@@", "--shortstat"]
        if author:
            sargs.append("--author=" + author)
        if file:
            sargs += ["--", file]
        scode, sout = _git(d, sargs, timeout=30)
        if scode == 0:
            files = ins = dels = 0
            for line in (sout or "").splitlines():
                m = STAT_RE.search(line)
                if m:
                    files += int(m.group(1))
                    ins += int(m.group(2) or 0)
                    dels += int(m.group(3) or 0)
            tail.append("改动合计：%d 文件次，+%d −%d 行" % (files, ins, dels))
    head = "仓库：%s（分支 %s）\n取样：最近 %d 次提交%s" % (d, branch, len(rows), span)
    return head + "\n\n" + "\n".join(lines) + "\n\n" + "\n".join(tail)
TOOLS = {
    "git_log": (git_log, {"path": "str", "n": "int", "file": "str", "author": "str", "stat": "bool"},
                "看 git 提交历史：最近 N 次提交、作者分布、活跃度，stat=True 加增删行数"),
}
