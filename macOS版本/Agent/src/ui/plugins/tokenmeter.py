import os
import re
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")
PUNCT = re.compile(r"[^\w\s]")
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def count_tokens(text):
    t = str(text or "")
    if not t:
        return 0
    cjk = len(CJK.findall(t))
    words = len(ASCII_WORD.findall(t))
    rest = len(t) - cjk - sum(len(w) for w in ASCII_WORD.findall(t))
    punct = len(PUNCT.findall(t))
    return int(cjk * 0.75 + words * 1.3 + max(0, rest - punct) / 4.0 + punct * 0.6) + 1
def _fmt(n):
    if n < 1000:
        return str(n)
    if n < 1000000:
        return "%.1fK" % (n / 1000.0)
    return "%.2fM" % (n / 1000000.0)
def token_estimate(text="", path="", context=128000):
    if path:
        parts = [x.strip() for x in str(path).split(",") if x.strip()]
        lines = []
        total = 0
        for rel in parts:
            p = _safe(rel)
            if not p or not os.path.isfile(p):
                lines.append("  %s  读不到" % rel)
                continue
            try:
                body = open(p, encoding="utf-8", errors="replace").read()
            except Exception as e:
                lines.append("  %s  读取失败：%s" % (rel, e))
                continue
            n = count_tokens(body)
            total += n
            lines.append("  %-32s %8s token  %8d 字节" % (rel, _fmt(n), len(body.encode("utf-8"))))
        head = "合计 %s token" % _fmt(total)
    else:
        body = str(text or "")
        total = count_tokens(body)
        lines = ["  %d 字符 → %s token" % (len(body), _fmt(total))]
        head = "这段文字约 %s token" % _fmt(total)
    ctx = int(context or 128000)
    pct = total * 100.0 / ctx if ctx else 0
    out = [head, ""] + lines
    out.append("")
    out.append("占 %s 上下文的 %.1f%%" % (_fmt(ctx), pct))
    if pct > 80:
        out.append("太满了。先摘要、或者只挑需要的段落再发。")
    elif pct > 40:
        out.append("超过四成。留意后面还要放回复的空间。")
    else:
        out.append("还有余量。")
    return "\n".join(out)
def token_trim(text="", path="", budget=2000):
    if path:
        p = _safe(path)
        if not p or not os.path.isfile(p):
            return "文件读不到：%s" % path
        body = open(p, encoding="utf-8", errors="replace").read()
    else:
        body = str(text or "")
    budget = max(50, int(budget or 2000))
    if count_tokens(body) <= budget:
        return "本来就够短（%d token），不用裁" % count_tokens(body)
    paras = [x.strip() for x in re.split(r"\n\s*\n", body) if x.strip()]
    if not paras:
        paras = [x for x in body.splitlines() if x.strip()]
    scored = []
    for i, p in enumerate(paras):
        score = count_tokens(p) * 0.0 + 1
        if i == 0:
            score += 3
        if re.search(r"[。！？]$", p):
            score += 1
        if re.search(r"\d", p):
            score += 1
        if re.search(r"(结论|因此|所以|总之|关键|注意|必须)", p):
            score += 2
        if len(p) > 1200:
            score -= 2
        scored.append((score, i, p))
    scored.sort(key=lambda x: (-x[0], x[1]))
    keep = []
    used = 0
    for _, i, p in scored:
        n = count_tokens(p)
        if used + n > budget:
            continue
        keep.append((i, p))
        used += n
    keep.sort()
    out = "\n\n".join(p for _, p in keep)
    return "裁到 %s token（原 %s，保留 %d/%d 段）\n\n%s" % (
        _fmt(used), _fmt(count_tokens(body)), len(keep), len(paras), out[:6000])
TOOLS = {
    "token_estimate": (token_estimate, {"text": "str", "path": "str", "context": "int"},
                       "估一段文字或几个文件占多少 token"),
    "token_trim": (token_trim, {"text": "str", "path": "str", "budget": "int"},
                   "把长文裁到 token 预算内，留下最值的段落"),
}
