import html
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
_ENV = os.environ.get("SA_SEARCH_URL", "").strip()
ENDPOINT = _ENV if _ENV else "https://www.bing.com/search?q=%s"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
_RES = re.compile(
    r'<h2[^>]*>\s*<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>(.*?)(?=<h2|</ol>|$)',
    re.S | re.I)
_SNIP = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
_JUNK = ("iciba.com", "cambridge.org", "youdao.com", "dict.cn", "hujiang.com",
         "baike.baidu.com", "zhidao.baidu.com", "wikipedia.org/wiki/词典")
def _clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return html.unescape(re.sub(r"\s+", " ", s)).strip()
def web_search(query: str, n: int = 5) -> str:
    qs = urllib.parse.quote(str(query)[:200])
    url = ENDPOINT % qs if "%s" in ENDPOINT else ENDPOINT + qs
    body = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception:
        body = None
    if body is None:
        curl = shutil.which("curl")
        if curl:
            try:
                r = subprocess.run([curl, "-sSL", "-m", "25", "-A", UA, url],
                                   capture_output=True, text=True, timeout=30)
                if r.returncode == 0 and r.stdout:
                    body = r.stdout
            except Exception:
                body = None
    if body is None:
        return "搜索失败（网络不可达）。不要编造结果，如实说明无法联网。"
    out = []
    hrefs = []
    for href, title, rest in _RES.findall(body):
        t = _clean(title)
        if not t or len(t) < 4 or href in hrefs:
            continue
        hrefs.append(href)
        m = _SNIP.search(rest)
        snip = _clean(m.group(1))[:220] if m else ""
        out.append("%d. %s\n   %s\n   %s" % (len(out) + 1, t, href, snip))
        if len(out) >= int(n):
            break
    if not out:
        return "没有搜到结果。不要编造，如实说明。"
    if sum(1 for h in hrefs if any(j in h for j in _JUNK)) * 2 > len(hrefs):
        out.append("（以上多是词典/百科页，可能答不了问题。查事实请改用 fetch_url "
                   "打开官网、文档或发布页。）")
    return "\n".join(out)
TOOLS = {
    "web_search": (web_search, {"query": "str", "n": "int"},
                   "联网搜索，返回标题/链接/摘要"),
}
