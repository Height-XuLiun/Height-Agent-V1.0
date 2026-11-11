import os
import re
import subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
KINDS = (("feat", "新功能"), ("fix", "修复"), ("perf", "性能"),
         ("refactor", "重构"), ("docs", "文档"), ("test", "测试"),
         ("style", "格式"), ("chore", "杂项"), ("build", "构建"), ("ci", "流水线"))
CONV = re.compile(r"^(%s)(\([^)]*\))?!?:\s*(.+)$" % "|".join(k for k, _ in KINDS), re.I)
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _git(repo, args):
    try:
        r = subprocess.run(["git", "-C", repo] + args, capture_output=True, timeout=30)
        return r.returncode, r.stdout.decode("utf-8", "replace").strip()
    except Exception as e:
        return -1, str(e)
def changelog_make(repo=".", limit=60, since="", version=""):
    p = _safe(repo or ".")
    if not p or not os.path.isdir(p):
        return "目录不存在：%s" % repo
    code, _ = _git(p, ["rev-parse", "--is-inside-work-tree"])
    if code != 0:
        return "不是 git 仓库：%s" % repo
    args = ["log", "--no-merges", "--pretty=%h%x1f%an%x1f%ad%x1f%s", "--date=short"]
    n = max(1, min(500, int(limit or 60)))
    args.append("-n%d" % n)
    if str(since or "").strip():
        args.append("--since=%s" % since)
    code, out = _git(p, args)
    if code != 0 or not out:
        return "取不到提交记录"
    groups = {}
    others = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) < 4:
            continue
        sha, who, day, subject = parts[0], parts[1], parts[2], parts[3]
        m = CONV.match(subject)
        if m:
            kind = m.group(1).lower()
            scope = (m.group(2) or "").strip("()")
            text = m.group(3).strip()
            label = dict(KINDS).get(kind, kind)
            if scope:
                text = "**%s**：%s" % (scope, text)
        else:
            label = "其他"
            text = subject
        item = "- %s（%s %s）" % (text, sha, who)
        groups.setdefault(label, []).append(item)
    if not groups:
        return "没有可整理的提交"
    order = [x[1] for x in KINDS] + ["其他"]
    lines = []
    if str(version or "").strip():
        lines.append("## %s" % version)
        lines.append("")
    total = sum(len(v) for v in groups.values())
    lines.append("整理 %d 条提交" % total)
    lines.append("")
    for label in order:
        if label not in groups:
            continue
        lines.append("### %s" % label)
        lines.extend(groups[label])
        lines.append("")
    return "\n".join(lines).rstrip()
def commit_check(repo=".", limit=15):
    p = _safe(repo or ".")
    if not p or not os.path.isdir(p):
        return "目录不存在：%s" % repo
    code, _ = _git(p, ["rev-parse", "--is-inside-work-tree"])
    if code != 0:
        return "不是 git 仓库：%s" % repo
    code, out = _git(p, ["log", "--pretty=%h%x1f%s", "-n%d" % max(1, int(limit or 15))])
    if code != 0 or not out:
        return "取不到提交记录"
    bad = []
    ok = 0
    for line in out.splitlines():
        if "\x1f" not in line:
            continue
        sha, subject = line.split("\x1f", 1)
        if CONV.match(subject):
            ok += 1
        else:
            bad.append("%s  %s" % (sha, subject[:50]))
    lines = ["%d 条里 %d 条符合 type: 描述 的写法" % (ok + len(bad), ok)]
    if bad:
        lines.append("不规范：")
        lines.extend("  - " + x for x in bad[:10])
        lines.append("建议写成 feat: xxx / fix: xxx，CHANGELOG 才能自动分组。")
    else:
        lines.append("写法都规范。")
    return "\n".join(lines)
TOOLS = {
    "changelog_make": (changelog_make, {"repo": "str", "limit": "int",
                                        "since": "str", "version": "str"},
                       "从 git 提交生成 CHANGELOG"),
    "commit_check": (commit_check, {"repo": "str", "limit": "int"},
                     "检查提交信息写得规不规范"),
}
