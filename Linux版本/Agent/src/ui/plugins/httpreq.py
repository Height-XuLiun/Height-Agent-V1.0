import json
import time
import urllib.error
import urllib.request
UA = "Mozilla/5.0 (compatible; HeightAgent/1.0)"
def _headers(raw):
    out = {}
    s = str(raw or "").strip()
    if not s:
        return out
    if s.startswith("{"):
        try:
            for k, v in json.loads(s).items():
                out[str(k)] = str(v)
            return out
        except Exception:
            pass
    for line in s.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out
def http_request(url, method="GET", headers="", body="", timeout=20, limit=4000):
    u = str(url or "").strip()
    if not u:
        return "没给 URL"
    if not u.lower().startswith(("http://", "https://")):
        return "只支持 http:// 和 https://"
    m = str(method or "GET").upper()
    hd = {"User-Agent": UA}
    hd.update(_headers(headers))
    data = None
    if body:
        data = str(body).encode("utf-8")
        if "content-type" not in {k.lower() for k in hd}:
            hd["Content-Type"] = "application/json"
    req = urllib.request.Request(u, data=data, headers=hd, method=m)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=float(timeout or 20)) as r:
            raw = r.read()
            code = r.status
            ctype = r.headers.get("Content-Type", "")
            total = r.headers.get("Content-Length") or len(raw)
    except urllib.error.HTTPError as e:
        raw = e.read() if hasattr(e, "read") else b""
        code = e.code
        ctype = (e.headers or {}).get("Content-Type", "") if e.headers else ""
        total = len(raw)
    except Exception as e:
        return "请求失败：%s: %s" % (type(e).__name__, str(e)[:150])
    cost = (time.time() - t0) * 1000
    text = raw.decode("utf-8", "replace")
    if "json" in ctype.lower():
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=1)
        except Exception:
            pass
    text = text[:int(limit or 4000)]
    head = "%s %s · %s 字节 · %.0f ms · %s" % (m, code, total, cost, ctype or "未知类型")
    return head + "\n" + text
TOOLS = {
    "http_request": (http_request,
                     {"url": "str", "method": "str", "headers": "str",
                      "body": "str", "timeout": "int", "limit": "int"},
                     "发一个 HTTP 请求，返回状态码和正文"),
}
