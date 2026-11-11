import html
import os
import re
import urllib.parse
import urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
_TODO = []
_ASKED = []
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def edit_file(path: str, old: str, new: str, count: int = 1) -> str:
    p = _safe(path)
    if not p:
        return "路径越界，拒绝执行"
    if not os.path.isfile(p):
        return "文件不存在：%s" % path
    try:
        src = open(p, encoding="utf-8").read()
    except Exception as e:
        return "读取失败：%s" % e
    if old not in src:
        return "没找到要替换的内容。原文前 200 字：\n" + src[:200]
    n = src.count(old)
    if n > count:
        return ("目标片段出现 %d 次，超过允许的 %d 次。请提供更长的上下文使其唯一。"
                % (n, count))
    out = src.replace(old, new, count)
    try:
        open(p + ".bak", "w", encoding="utf-8").write(src)
        open(p, "w", encoding="utf-8").write(out)
    except Exception as e:
        return "写入失败：%s" % e
    line_no = src[:src.index(old)].count("\n") + 1
    return "已替换 %d 处，第 %d 行。文件现有 %d 行。" % (n, line_no, out.count("\n") + 1)
def fetch_url(url: str, limit: int = 4000) -> str:
    u = str(url).strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    host = urllib.parse.urlparse(u).hostname or ""
    opener = (urllib.request.build_opener(urllib.request.ProxyHandler({}))
              if host in ("127.0.0.1", "localhost", "::1")
              else urllib.request.build_opener())
    try:
        req = urllib.request.Request(u, headers={"User-Agent": UA})
        with opener.open(req, timeout=25) as r:
            raw = r.read()
            charset = r.headers.get_content_charset() or "utf-8"
        text = raw.decode(charset, "replace")
    except Exception as e:
        return "抓取失败（%s）。不要编造页面内容。" % type(e).__name__
    text = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[: int(limit)] if text else "页面没有可读正文。"
def todo(items: str = "") -> str:
    s = str(items).strip()
    if not s:
        if not _TODO:
            return "清单为空。"
        return "\n".join("%d. [%s] %s" % (i + 1, m, t) for i, (m, t) in enumerate(_TODO))
    if s.lower().startswith("add:"):
        _TODO.append((" ", s[4:].strip()))
        return "已添加第 %d 项：%s" % (len(_TODO), s[4:].strip())
    if s.lower().startswith("done:"):
        try:
            i = int(s[5:].strip()) - 1
            m, t = _TODO[i]
            _TODO[i] = ("x", t)
            return "已完成：%s" % t
        except Exception:
            return "序号无效，当前共 %d 项。" % len(_TODO)
    _TODO.append((" ", s))
    return "已添加第 %d 项：%s" % (len(_TODO), s)
def ask_user(question: str) -> str:
    q = str(question).strip()
    if not q:
        return "问题为空。"
    _ASKED.append(q)
    p = os.path.join(ROOT, "_question.md")
    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n## 待确认\n%s\n" % q)
    except Exception:
        pass
    return ("问题已记录到 _question.md：%s\n"
            "无法阻塞等待回复。请先按最合理的假设继续，并在最终答案里说明这个假设。" % q)
def glob_files(pattern: str, limit: int = 60) -> str:
    import glob as g
    pat = os.path.join(ROOT, str(pattern).lstrip("/\\"))
    hits = sorted(g.glob(pat, recursive=True))[: int(limit)]
    if not hits:
        return "没有匹配的文件。"
    return "\n".join(os.path.relpath(h, ROOT) for h in hits)
def grep_files(pattern: str, ext: str = "", limit: int = 40) -> str:
    try:
        rx = re.compile(str(pattern))
    except Exception as e:
        return "正则无效：%s" % e
    out = []
    for dirpath, _, files in os.walk(ROOT):
        for fn in files:
            if ext and not fn.endswith(ext):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(fp) > 2_000_000:
                    continue
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    for ln, line in enumerate(f, 1):
                        if rx.search(line):
                            out.append("%s:%d: %s" % (os.path.relpath(fp, ROOT), ln, line.strip()[:160]))
                            if len(out) >= int(limit):
                                return "\n".join(out)
            except Exception:
                continue
    return "\n".join(out) if out else "没有匹配。"
TOOLS = {
    "edit_file": (edit_file, {"path": "str", "old": "str", "new": "str", "count": "int"},
                  "精确替换文件片段"),
    "fetch_url": (fetch_url, {"url": "str", "limit": "int"},
                  "抓网页转纯文本"),
    "todo": (todo, {"items": "str"},
             "任务清单，add:/done:/留空查看"),
    "ask_user": (ask_user, {"question": "str"},
                 "记录待确认的问题"),
    "glob_files": (glob_files, {"pattern": "str", "limit": "int"},
                   "按通配符找文件"),
    "grep_files": (grep_files, {"pattern": "str", "ext": "str", "limit": "int"},
                   "按内容搜索"),
}
