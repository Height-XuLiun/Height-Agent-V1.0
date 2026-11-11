import re
CJK = re.compile(r"[\u4e00-\u9fff]")
WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
SENT = re.compile(r"[.!?。！？；;]+")
STOP = set("""的 了 和 是 在 我 有 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着
没有 看 好 自己 这 那 他 她 它 我们 你们 他们 这个 那个 什么 怎么 因为 所以 但是 如果
the a an and or of to in is are was were be been it this that for on with as at by from""".split())
def _read(path):
    import os
    HERE = os.path.dirname(os.path.abspath(__file__))
    ROOT = os.path.join(os.path.dirname(HERE), "workspace")
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    if not p.startswith(os.path.abspath(ROOT)) or not os.path.isfile(p):
        return None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return open(p, encoding=enc).read()
        except Exception:
            continue
    return None
def text_stats(text="", path=""):
    if path:
        body = _read(path)
        if body is None:
            return "文件读不到：%s" % path
    else:
        body = str(text or "")
    if not body.strip():
        return "没有内容"
    chars = len(body)
    no_space = len(re.sub(r"\s", "", body))
    cjk = len(CJK.findall(body))
    words_en = len(WORD.findall(body))
    lines = body.count("\n") + 1
    sents = max(1, len(SENT.findall(body)))
    minutes = cjk / 400.0 + words_en / 220.0
    paragraphs = len([x for x in re.split(r"\n\s*\n", body) if x.strip()])
    out = [
        "字符 %d（不含空白 %d）" % (chars, no_space),
        "汉字 %d 个，英文单词 %d 个" % (cjk, words_en),
        "行 %d，段 %d，句 %d" % (lines, paragraphs, sents),
        "平均每句 %.1f 字" % (no_space / sents),
        "阅读约 %d 分 %d 秒" % (int(minutes), int((minutes % 1) * 60)),
    ]
    if cjk and words_en:
        out.append("中英混排，汉字占 %.0f%%" % (cjk * 100.0 / max(1, cjk + words_en)))
    return "\n".join(out)
def word_freq(text="", path="", top=15):
    if path:
        body = _read(path)
        if body is None:
            return "文件读不到：%s" % path
    else:
        body = str(text or "")
    if not body.strip():
        return "没有内容"
    n = max(3, min(50, int(top or 15)))
    cjk_bigram = {}
    run = ""
    for ch in body:
        if CJK.match(ch):
            run += ch
        else:
            for i in range(len(run) - 1):
                w = run[i:i + 2]
                if w not in STOP:
                    cjk_bigram[w] = cjk_bigram.get(w, 0) + 1
            run = ""
    if len(run) > 1:
        for i in range(len(run) - 1):
            w = run[i:i + 2]
            if w not in STOP:
                cjk_bigram[w] = cjk_bigram.get(w, 0) + 1
    words = {}
    for w in WORD.findall(body.lower()):
        if len(w) < 3 or w in STOP:
            continue
        words[w] = words.get(w, 0) + 1
    lines = []
    if cjk_bigram:
        lines.append("中文高频双字：")
        for w, c in sorted(cjk_bigram.items(), key=lambda x: -x[1])[:n]:
            lines.append("  %s  %d" % (w, c))
    if words:
        lines.append("英文高频词：")
        for w, c in sorted(words.items(), key=lambda x: -x[1])[:n]:
            lines.append("  %s  %d" % (w, c))
    return "\n".join(lines) or "没有统计出高频词"
TOOLS = {
    "text_stats": (text_stats, {"text": "str", "path": "str"},
                   "统计字数、句数、阅读时长（给 text 或 path）"),
    "word_freq": (word_freq, {"text": "str", "path": "str", "top": "int"},
                  "找高频词，看这段文字在讲什么"),
}
