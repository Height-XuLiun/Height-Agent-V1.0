import os
import re
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
ESC = {
    "d": "数字 0-9", "D": "非数字", "w": "字母/数字/下划线", "W": "非字母数字下划线",
    "s": "空白（空格、制表、换行）", "S": "非空白", "b": "单词边界", "B": "非单词边界",
    "n": "换行符", "t": "制表符", "r": "回车", "f": "换页", "v": "垂直制表",
    "A": "字符串开头", "Z": "字符串结尾", "0": "空字符",
}
FLAGS = {"i": re.I, "m": re.M, "s": re.S, "x": re.X, "u": re.U, "a": re.A}
FLAG_DESC = {"i": "忽略大小写", "m": "多行（^ $ 匹配每行首尾）", "s": ". 也匹配换行",
             "x": "忽略空白与 # 注释", "u": "Unicode", "a": "仅 ASCII"}
STOP = set("\\[(|^$.?*+{})")
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _read(path):
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return None
    for enc in ("utf-8-sig", "gb18030"):
        try:
            with open(p, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()
def _esc(pat, i):
    c = pat[i + 1] if i + 1 < len(pat) else ""
    if c in ESC:
        return "\\" + c, ESC[c], i + 2
    if c.isdigit():
        return "\\" + c, "反向引用第 %s 组" % c, i + 2
    if c == "x" and re.match(r"[0-9a-fA-F]{2}", pat[i + 2:i + 4] or ""):
        return pat[i:i + 4], "字符 U+%s" % pat[i + 2:i + 4].upper(), i + 4
    return "\\" + c, "字面量 “%s”" % c, i + 2
def _cls(pat, i):
    j, n = i + 1, len(pat)
    if j < n and pat[j] == "^":
        j += 1
    if j < n and pat[j] == "]":
        j += 1
    while j < n:
        if pat[j] == "\\":
            j += 2
            continue
        if pat[j] == "]":
            j += 1
            break
        j += 1
    frag = pat[i:j]
    inner = frag[1:-1] if frag.endswith("]") else frag[1:]
    neg = inner.startswith("^")
    if neg:
        inner = inner[1:]
    what = inner.replace("\\d", "0-9").replace("\\w", "字母数字下划线").replace("\\s", "空白")
    desc = ("不能是其中任一字符：%s" if neg else "是其中任一字符：%s") % (what or "空")
    return frag, desc, j
def _group(pat, i, counter, depth=0):
    head = ""
    kind = "捕获组"
    if pat.startswith("(?:", i):
        head, kind = "(?:", "非捕获组"
    elif pat.startswith("(?P<", i):
        m = re.match(r"\(\?P<([^>]+)>", pat[i:])
        if m:
            head, kind = m.group(0), "命名捕获组 <%s>" % m.group(1)
    elif pat.startswith("(?=", i):
        head, kind = "(?=", "正向先行断言：后面必须跟着"
    elif pat.startswith("(?!", i):
        head, kind = "(?!", "负向先行断言：后面不能是"
    elif pat.startswith("(?<=", i):
        head, kind = "(?<=", "正向后行断言：前面必须是"
    elif pat.startswith("(?<!", i):
        head, kind = "(?<!", "负向后行断言：前面不能是"
    elif pat.startswith("(?", i):
        m = re.match(r"\(\?[a-zA-Z\-]+\)", pat[i:])
        if m:
            return m.group(0), "内联标志（改后续匹配行为）", i + len(m.group(0))
        head, kind = "(?", "特殊分组"
    else:
        head, kind = "(", "捕获组"
        counter[0] += 1
        kind = "捕获组 %d" % counter[0]
    j = i + len(head)
    lv = 1
    while j < len(pat) and lv:
        c = pat[j]
        if c == "\\":
            j += 2
            continue
        if c == "[":
            _, _, j = _cls(pat, j)
            continue
        if c == "(":
            lv += 1
        elif c == ")":
            lv -= 1
        j += 1
    inner = pat[i + len(head):j - 1] if j > i + len(head) else ""
    if inner and depth < 3:
        subs = explain(inner, depth + 1)
        summary = "；".join(d for _, d in subs)
        if len(summary) > 70:
            summary = summary[:69] + "…"
        kind += "（内含 %s）" % summary
    return pat[i:j], kind, j
def _quant(pat, i):
    n = len(pat)
    if i >= n:
        return "", "", i
    c = pat[i]
    if c in "*+?":
        desc = {"*": "重复 0 次或多次", "+": "重复 1 次或多次", "?": "出现 0 或 1 次"}[c]
        j = i + 1
    elif c == "{":
        m = re.match(r"\{(\d+)(,(\d*))?\}", pat[i:])
        if not m:
            return "", "", i
        lo, comma, hi = m.group(1), m.group(2), m.group(3)
        if not comma:
            desc = "正好重复 %s 次" % lo
        elif hi == "":
            desc = "至少重复 %s 次" % lo
        else:
            desc = "重复 %s 到 %s 次" % (lo, hi)
        j = i + len(m.group(0))
    else:
        return "", "", i
    lazy = ""
    if j < n and pat[j] in "?+":
        lazy = "（非贪婪，尽量少匹配）" if pat[j] == "?" else "（占有，不回溯）"
        j += 1
    return pat[i:j], desc + lazy, j
def explain(pat, depth=0):
    parts, i, counter = [], 0, [0]
    while i < len(pat):
        c = pat[i]
        if c == "\\":
            frag, desc, i = _esc(pat, i)
        elif c == "[":
            frag, desc, i = _cls(pat, i)
        elif c == "(":
            frag, desc, i = _group(pat, i, counter, depth)
        elif c == "|":
            frag, desc, i = "|", "或：左边或右边匹配其一", i + 1
        elif c == "^":
            frag, desc, i = "^", "开头（多行模式下每行开头）", i + 1
        elif c == "$":
            frag, desc, i = "$", "结尾（多行模式下每行结尾）", i + 1
        elif c == ".":
            frag, desc, i = ".", "任意一个字符（默认不含换行）", i + 1
        elif c in "*+?":
            frag, desc, i = c, "孤立的量词，前面没有可重复的内容", i + 1
        elif c in "{}":
            frag, desc, i = c, "字面量 “%s”" % c, i + 1
        else:
            j = i
            while j < len(pat) and pat[j] not in STOP:
                j += 1
            frag, desc, i = pat[i:j], "字面量 “%s”" % pat[i:j], j
        q, qd, i = _quant(pat, i)
        if q:
            frag += q
            desc += "，" + qd
        parts.append((frag, desc))
    return parts
def _mark(text, spans):
    out, last = [], 0
    for s, e in spans:
        out.append(text[last:s])
        out.append("【" + text[s:e] + "】")
        last = e
    out.append(text[last:])
    return "".join(out)
def regex_lab(pattern: str = "", text: str = "", path: str = "", flags: str = "",
              mode: str = "test", repl: str = "") -> str:
    if not pattern:
        return ("用法：regex_lab(pattern, text=\"待测文本\")，"
                "mode=\"explain\" 只看解释，repl 做替换。")
    fl = 0
    used = []
    for ch in (flags or ""):
        if ch in FLAGS:
            fl |= FLAGS[ch]
            used.append(FLAG_DESC.get(ch, ch))
    parts = explain(pattern)
    table = "\n".join("  %-18s %s" % (f.replace("\n", "\\n"), d) for f, d in parts)
    flagline = ("标志：" + "、".join(used)) if used else "标志：无"
    if (mode or "").lower().startswith("exp"):
        try:
            re.compile(pattern, fl)
            okline = "语法检查：通过"
        except re.error as e:
            okline = "语法检查：失败 —— %s（位置 %s）" % (e.msg, e.pos)
        return "模式：%s\n%s\n%s\n\n逐段解释：\n%s" % (pattern, okline, flagline, table)
    if not text and path:
        text = _read(path) or ""
        if not text:
            return "读不到文本：%s" % path
    if not text:
        return "没有待测文本。给 text 参数，或用 path 指定文件。\n\n逐段解释：\n%s" % table
    try:
        rx = re.compile(pattern, fl)
    except re.error as e:
        return "正则写错了：%s（位置 %s）\n出错位置附近：%s" % (
            e.msg, e.pos, pattern[max(0, e.pos - 8):e.pos + 8])
    if repl:
        new, n = rx.subn(repl, text)
        body = new if len(new) <= 2000 else new[:2000] + "\n…（结果 %d 字符，只显示前 2000）" % len(new)
        return "替换 %d 处\n模式：%s\n替换为：%s\n\n结果：\n%s" % (n, pattern, repl, body)
    hits = list(rx.finditer(text))
    if not hits:
        return "没有匹配。\n模式：%s\n文本：%d 字符\n\n逐段解释：\n%s" % (pattern, len(text), table)
    lines = []
    for k, m in enumerate(hits[:20]):
        g = m.groups()
        tail = ""
        if g:
            tail = "  分组：" + "，".join("#%d=%r" % (i + 1, x) for i, x in enumerate(g))
        lines.append("%2d. [%d,%d) %r%s" % (k + 1, m.start(), m.end(), m.group(0)[:80], tail))
    if len(hits) > 20:
        lines.append("…（共 %d 处，只列前 20）" % len(hits))
    preview = _mark(text[:600], [(m.start(), m.end()) for m in hits if m.start() < 600][:5])
    return "匹配 %d 处（文本 %d 字符）\n模式：%s\n%s\n\n前几处位置：\n%s\n\n标出匹配：\n%s" % (
        len(hits), len(text), pattern, flagline, "\n".join(lines), preview)
TOOLS = {
    "regex_lab": (regex_lab, {"pattern": "str", "text": "str", "path": "str",
                              "flags": "str", "mode": "str", "repl": "str"},
                  "正则测试与逐段中文解释：找匹配位置、分组、做替换，mode=explain 只看解释"),
}
