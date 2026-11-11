import os
import re
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
HEAD = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
def _read(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    if not p.startswith(os.path.abspath(ROOT)) or not os.path.isfile(p):
        return None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return open(p, encoding=enc).read()
        except Exception:
            continue
    return None
def _slug(title):
    s = re.sub(r"`([^`]*)`", r"\1", title)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[^\w\u4e00-\u9fff \-]", "", s).strip().lower()
    return re.sub(r"\s+", "-", s)
def md_toc(path="", text="", depth=3, numbered=True, with_anchor=False):
    if path:
        body = _read(path)
        if body is None:
            return "文件读不到：%s" % path
    else:
        body = str(text or "")
    if not body.strip():
        return "没有内容"
    maxd = max(1, min(6, int(depth or 3)))
    items = []
    infence = False
    for line in body.splitlines():
        if FENCE.match(line):
            infence = not infence
            continue
        if infence:
            continue
        m = HEAD.match(line)
        if not m:
            continue
        lv = len(m.group(1))
        if lv > maxd:
            continue
        items.append((lv, m.group(2).strip()))
    if not items:
        return "没找到标题（# 开头的行）"
    base = min(x[0] for x in items)
    lines = []
    counters = [0] * 7
    for lv, title in items:
        counters[lv] += 1
        for deeper in range(lv + 1, 7):
            counters[deeper] = 0
        indent = "  " * (lv - base)
        num = ""
        if numbered:
            num = ".".join(str(counters[i]) for i in range(base, lv + 1) if counters[i]) + ". "
        tail = " (#%s)" % _slug(title) if with_anchor else ""
        lines.append("%s- %s[%s](#%s)%s" % (indent, num, title, _slug(title), tail))
    return "%d 个标题\n\n" % len(items) + "\n".join(lines)
def md_check(path="", text=""):
    if path:
        body = _read(path)
        if body is None:
            return "文件读不到：%s" % path
    else:
        body = str(text or "")
    if not body.strip():
        return "没有内容"
    problems = []
    prev = 0
    infence = False
    longlines = 0
    bullets = set()
    for i, line in enumerate(body.splitlines(), 1):
        if FENCE.match(line):
            infence = not infence
            continue
        if infence:
            continue
        m = HEAD.match(line)
        if m:
            lv = len(m.group(1))
            if prev and lv > prev + 1:
                problems.append("第 %d 行：标题从 H%d 跳到 H%d" % (i, prev, lv))
            prev = lv
        if len(line) > 160 and not line.lstrip().startswith(("|", "http")):
            longlines += 1
        s = line.lstrip()
        if s[:2] in ("- ", "* ", "+ "):
            bullets.add(s[0])
    if longlines:
        problems.append("%d 行超过 160 字，读起来累" % longlines)
    if len(bullets) > 1:
        problems.append("列表符号混用：%s" % " ".join(sorted(bullets)))
    if "  \n" in body or "\t\n" in body:
        problems.append("有行尾多余空白")
    if body.count("```") % 2:
        problems.append("代码块没闭合（``` 是单数）")
    if not problems:
        return "没发现明显问题"
    return "发现 %d 处：\n" % len(problems) + "\n".join("  - " + p for p in problems)
TOOLS = {
    "md_toc": (md_toc, {"path": "str", "text": "str", "depth": "int",
                        "numbered": "bool", "with_anchor": "bool"},
               "给 Markdown 生成目录"),
    "md_check": (md_check, {"path": "str", "text": "str"},
                 "交稿前粗检 Markdown 的格式问题"),
}
