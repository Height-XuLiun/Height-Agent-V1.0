import base64
import json
import mimetypes
import os
import queue
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import bridge
import extract as extractor
import localmodel
SESS_FILE = os.path.join(HERE, "sessions.json")
SESS_BAK = os.path.join(HERE, "sessions.bak.json")
SESS_FLAG = os.path.join(HERE, "sessions.cleared")
def read_sessions(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []
SESS_LOCK = threading.Lock()
CFG_LOCK = threading.Lock()
def write_sessions(data):
    with SESS_LOCK:
        old = read_sessions(SESS_FILE)
        if old:
            try:
                with open(SESS_BAK, "w", encoding="utf-8") as f:
                    json.dump(old, f, ensure_ascii=False, indent=1)
            except Exception:
                pass
        tmp = SESS_FILE + "." + uuid.uuid4().hex[:8] + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data[:60], f, ensure_ascii=False, indent=1)
            os.replace(tmp, SESS_FILE)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
PORT = int(os.environ.get("SA_PORT") or 5000)
BAD_PORTS = {1, 7, 9, 11, 13, 15, 17, 19, 21, 22, 23, 25, 37, 42, 43, 53, 69, 77, 79,
             87, 95, 101, 102, 103, 104, 109, 110, 111, 113, 115, 117, 119, 123, 135,
             137, 139, 143, 161, 179, 389, 427, 465, 512, 513, 514, 515, 526, 530, 531,
             532, 540, 548, 554, 556, 563, 587, 601, 636, 989, 990, 993, 995, 1719,
             1720, 1723, 2049, 3659, 4045, 5060, 5061, 6000, 6566, 6665, 6666, 6667,
             6668, 6669, 6697, 10080}
HOST = os.environ.get("SA_HOST") or ("0.0.0.0" if "--lan" in sys.argv else "127.0.0.1")
LOCAL_ONLY = HOST in ("127.0.0.1", "localhost", "::1")
TOKEN = os.environ.get("SA_TOKEN") or uuid.uuid4().hex[:12]
JOBS = {}
LOCK = threading.Lock()
CTYPES = {
    ".html": "text/html", ".js": "application/javascript", ".css": "text/css",
    ".svg": "image/svg+xml", ".json": "application/json",
    ".webmanifest": "application/manifest+json", ".png": "image/png",
    ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
    ".ico": "image/x-icon",
}
def new_job():
    jid = uuid.uuid4().hex[:8]
    with LOCK:
        JOBS[jid] = {"subs": set(), "buf": [], "done": False,
                     "result": None, "error": None, "ts": time.time()}
    return jid
def push(jid, evt):
    with LOCK:
        job = JOBS.get(jid)
        if not job:
            return
        job["buf"].append(evt)
        subs = list(job["subs"])
    for q in subs:
        try:
            q.put_nowait(evt)
        except Exception:
            pass
def finish(jid, result=None):
    with LOCK:
        job = JOBS.get(jid)
        if not job or job["done"]:
            return
        job["done"] = True
        job["result"] = result
        subs = list(job["subs"])
    for q in subs:
        try:
            q.put_nowait({"done": True, "result": result})
        except Exception:
            pass
def sink(obj):
    jid = obj.get("job")
    if jid and bridge.is_cancelled(jid):
        return
    if not jid:
        if obj.get("t"):
            print("[bridge]", obj["t"])
        return
    if obj.get("error"):
        push(jid, {"t": "错误：" + bridge.friendly_llm_error(obj["error"])})
        finish(jid)
        return
    if obj.get("done"):
        finish(jid, obj.get("result"))
        return
    evt = {}
    for k in ("usage", "think", "t", "act", "note"):
        if obj.get(k) is not None:
            evt[k] = obj[k]
    if evt:
        push(jid, evt)
bridge.set_sink(sink)
def run_async(payload):
    jid = payload.get("job")
    try:
        if payload.get("chat"):
            bridge.run_chat(payload)
        else:
            bridge.run_job(payload)
    except Exception as e:
        if not bridge.is_cancelled(jid):
            push(jid, {"t": "错误：" + bridge.friendly_llm_error(e)})
        finish(jid)
    finally:
        with LOCK:
            job = JOBS.get(jid)
            alive = job and not job["done"]
        if alive:
            finish(jid)
        bridge.clear_cancel(jid)
def reaper():
    while True:
        time.sleep(60)
        now = time.time()
        with LOCK:
            for jid in [k for k, v in JOBS.items() if v["done"] and now - v["ts"] > 600]:
                JOBS.pop(jid, None)
def proxy_models(base, key, provider=""):
    base = (base or "").rstrip("/")
    host = (urllib.parse.urlparse(base).hostname or "").lower()
    anth = (str(provider or "").lower() == "anthropic"
            or "anthropic" in host or "anthropic" in base.lower())
    url = base + "/models" + ("?limit=100" if anth else "")
    if anth:
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                   "Accept": "application/json"}
    else:
        headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    if host in ("127.0.0.1", "localhost", "::1"):
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    else:
        op = urllib.request.build_opener()
    try:
        with op.open(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"error": str(e)[:120]}
    arr = d if isinstance(d, list) else (d.get("data") or d.get("models") or [])
    ids = []
    for x in arr:
        v = x if isinstance(x, str) else (x.get("id") or x.get("name") or "")
        if v:
            ids.append(v)
    return {"models": sorted(ids)}
def do_extract(data):
    name = str(data.get("name") or "file")
    ext = os.path.splitext(name)[1].lower()
    raw = base64.b64decode(str(data.get("data") or ""))
    if len(raw) > 24 * 1024 * 1024:
        return {"error": "文件超过 24MB"}
    tmp = os.path.join(tempfile.gettempdir(),
                       "sa_up_%d_%s%s" % (int(time.time() * 1000), uuid.uuid4().hex[:4], ext))
    try:
        with open(tmp, "wb") as f:
            f.write(raw)
    except Exception:
        return {"error": "写临时文件失败"}
    try:
        if ext == ".docx":
            text = extractor.docx(tmp)
        elif ext == ".pptx":
            text = extractor.pptx(tmp)
        elif ext == ".xlsx":
            text = extractor.xlsx(tmp)
        elif ext == ".pdf":
            text = extractor.pdf(tmp)
        elif ext in (".doc", ".ppt", ".xls"):
            return {"error": "旧版二进制格式读不了，另存为 %sx 再拖进来" % ext}
        else:
            text = extractor.plain(tmp)
        text = (text or "").strip()
        if not text:
            return {"error": "这个文件里没抽出文字（可能是扫描件或纯图）"}
        return {"text": text[:120000]}
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a):
        pass
    def send_body(self, code, body, ctype="application/json", headers=None):
        b = body if isinstance(body, bytes) else str(body).encode("utf-8")
        if ctype.startswith("text/") or ctype in (
                "application/json", "application/javascript",
                "application/manifest+json", "image/svg+xml"):
            ctype += "; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        if getattr(self, "extra_cookie", ""):
            self.send_header("Set-Cookie", self.extra_cookie
                             + "; Path=/; SameSite=Lax; Max-Age=31536000")
            self.extra_cookie = ""
        self.end_headers()
        self.wfile.write(b)
    def send_json(self, obj, code=200):
        self.send_body(code, json.dumps(obj, ensure_ascii=False), "application/json")
    def remote_ok(self, q):
        ip = (self.client_address[0] or "").replace("::ffff:", "")
        if LOCAL_ONLY or ip in ("127.0.0.1", "::1", ""):
            return True
        k = (q.get("k") or [""])[0]
        if k and k == TOKEN:
            self.extra_cookie = "sa_k=" + TOKEN
            return True
        cookie = self.headers.get("Cookie") or ""
        return ("sa_k=" + TOKEN) in [c.strip() for c in cookie.split(";")]
    MAX_BODY = 8 * 1024 * 1024
    def read_json(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            return None
        if n <= 0:
            return {}
        if n > self.MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(n).decode("utf-8", "replace") or "{}")
        except Exception:
            return None
    def user_file(self, path):
        raw = urllib.parse.unquote(str(path or "")).strip().strip('"')
        if not raw:
            return self.send_body(400, "no path", "text/plain")
        real = os.path.realpath(raw if os.path.isabs(raw) else os.path.join(HERE, raw))
        roots = [os.path.realpath(os.path.join(HERE, "workspace"))]
        for d in ("Desktop", "Pictures", "Downloads"):
            roots.append(os.path.realpath(os.path.join(os.path.expanduser("~"), d)))
        ok = False
        for r in roots:
            if os.path.normcase(real) == os.path.normcase(r) or \
                    os.path.normcase(real).startswith(os.path.normcase(r) + os.sep):
                ok = True
                break
        if not ok:
            return self.send_body(403, "forbidden", "text/plain")
        ext = os.path.splitext(real)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
            return self.send_body(403, "not an image", "text/plain")
        if not os.path.isfile(real):
            return self.send_body(404, "not found", "text/plain")
        try:
            if os.path.getsize(real) > 32 * 1024 * 1024:
                return self.send_body(413, "too large", "text/plain")
            with open(real, "rb") as f:
                data = f.read()
        except Exception:
            return self.send_body(500, "read failed", "text/plain")
        ctype = CTYPES.get(ext) or mimetypes.guess_type(real)[0] or "image/png"
        self.send_body(200, data, ctype)
    def static_file(self, rel):
        path = os.path.join(HERE, rel.replace("/", os.sep))
        real = os.path.realpath(path)
        root = os.path.realpath(HERE)
        if os.path.normcase(real) != os.path.normcase(root) and \
                not os.path.normcase(real).startswith(os.path.normcase(root) + os.sep):
            return self.send_body(403, "forbidden", "text/plain")
        if not os.path.isfile(real):
            return self.send_body(404, "not found", "text/plain")
        ext = os.path.splitext(real)[1].lower()
        ctype = CTYPES.get(ext) or mimetypes.guess_type(real)[0] or "application/octet-stream"
        try:
            with open(real, "rb") as f:
                data = f.read()
        except Exception:
            return self.send_body(500, "read failed", "text/plain")
        self.send_body(200, data, ctype)
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p = u.path
        q = urllib.parse.parse_qs(u.query)
        self.extra_cookie = ""
        if not self.remote_ok(q):
            return self.send_body(401,
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<body style="font:15px/1.8 system-ui;padding:32px">需要访问令牌。'
                '请用启动日志里带 <code>?k=</code> 的地址打开一次。</body>', "text/html")
        if p == "/api/info":
            import plat
            info = plat.describe()
            info.update({"node": "", "host": HOST, "port": PORT,
                         "secure": not LOCAL_ONLY})
            return self.send_json(info)
        if p in ("/", "/index.html"):
            return self.static_file("index.html")
        if p in ("/backdrop.js", "/sw.js", "/manifest.webmanifest"):
            return self.static_file(p.lstrip("/"))
        if p.startswith("/fonts/") or p.startswith("/logos/") or p.startswith("/icons/") \
                or p.startswith("/vendor/"):
            return self.static_file(p.lstrip("/"))
        if p == "/file":
            return self.user_file((q.get("path") or [""])[0])
        if p == "/plugins":
            return self.send_json(bridge.list_plugins())
        if p == "/plugin-src":
            name = (q.get("name") or [""])[0]
            src = bridge.read_plugin_src(name)
            if src is None:
                return self.send_json({"error": "没有这个插件"}, 404)
            return self.send_json({"name": name, "code": src})
        if p == "/sessions":
            cleared = os.path.exists(SESS_FLAG)
            data = read_sessions(SESS_FILE)
            if not data and not cleared:
                data = read_sessions(SESS_BAK)
                if data:
                    try:
                        write_sessions(data)
                    except Exception:
                        pass
            return self.send_body(200, json.dumps(data, ensure_ascii=False),
                                  "application/json",
                                  {"X-SA-Cleared": "1"} if cleared else None)
        if p == "/config":
            f = os.path.join(HERE, "config.json")
            try:
                txt = open(f, encoding="utf-8").read()
                json.loads(txt)
            except Exception:
                txt = "{}"
            return self.send_body(200, txt, "application/json")
        if p == "/stream":
            return self.stream((q.get("id") or [""])[0])
        self.send_body(404, '{"error":"not found"}')
    def stream(self, jid):
        with LOCK:
            job = JOBS.get(jid)
            q = queue.Queue()
            done = False
            if job:
                for e in job["buf"]:
                    q.put_nowait(e)
                done = job["done"]
                if not done:
                    job["subs"].add(q)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True
        def write(evt):
            self.wfile.write(("data: " + json.dumps(evt, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        try:
            if not job:
                write({"t": "任务不存在"})
                return
            if done:
                write({"done": True, "result": job["result"]})
                return
            while True:
                try:
                    evt = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                write(evt)
                if evt.get("done"):
                    break
        except Exception:
            pass
        finally:
            with LOCK:
                if job:
                    job["subs"].discard(q)
    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        p = u.path
        q = urllib.parse.parse_qs(u.query)
        self.extra_cookie = ""
        if not self.remote_ok(q):
            return self.send_body(401, '{"error":"token"}')
        data = self.read_json()
        if data is None:
            return self.send_json({"error": "bad json"}, 400)
        if p == "/stop":
            jid = str(data.get("id") or "")
            with LOCK:
                known = bool(jid) and jid in JOBS
            if known:
                bridge.cancel_job(jid)
            return self.send_json({"ok": True, "stopped": known})
        if p in ("/chat", "/run"):
            jid = new_job()
            payload = {"job": jid}
            if p == "/chat":
                payload.update({"chat": True, "config": data.get("config") or {},
                                "messages": data.get("messages") or [],
                                "goal": str(data.get("goal") or "")[:300],
                                "web": bool(data.get("web"))})
            else:
                payload.update({"config": data.get("config") or {},
                                "tasks": data.get("tasks") or [],
                                "goal": data.get("goal") or ""})
            threading.Thread(target=run_async, args=(payload,), daemon=True).start()
            return self.send_json({"id": jid})
        if p == "/title":
            try:
                t = bridge.make_title(data.get("config") or {}, data.get("text") or "")
            except Exception as e:
                t = ""
            return self.send_json({"title": t})
        if p == "/models":
            base = str(data.get("base_url") or "").rstrip("/")
            if not base:
                return self.send_json({"error": "缺接口地址"})
            return self.send_json(proxy_models(base, str(data.get("api_key") or ""),
                                               str(data.get("provider") or "")))
        if p.startswith("/localmodel/"):
            act = p.rsplit("/", 1)[-1]
            if act == "inspect":
                return self.send_json(localmodel.inspect_manifest(
                    data.get("entries"), str(data.get("name") or "")[:120]))
            if act == "register":
                return self.send_json(localmodel.register_model(
                    data.get("info") or {}, data.get("override")))
            if act == "list":
                return self.send_json({"ok": True, "models": localmodel.list_models()})
            if act == "unregister":
                return self.send_json(localmodel.unregister_model(data.get("id")))
            return self.send_json({"error": "unknown action"}, 400)
        if p == "/extract":
            if not data.get("data"):
                return self.send_json({"error": "没有文件内容"})
            return self.send_json(do_extract(data))
        if p == "/sessions":
            if not isinstance(data, list):
                return self.send_json({"error": "expect array"}, 400)
            if len(data) > 60:
                return self.send_json({"error": "too many sessions"}, 413)
            for item in data:
                if not isinstance(item, dict):
                    return self.send_json({"error": "bad session item"}, 400)
                try:
                    if len(json.dumps(item, ensure_ascii=False)) > 512 * 1024:
                        return self.send_json({"error": "session too large"}, 413)
                except Exception:
                    return self.send_json({"error": "bad session item"}, 400)
            force = (q.get("force") or [""])[0] in ("1", "true", "yes")
            replace = (q.get("replace") or [""])[0] in ("1", "true", "yes")
            if not data and not force:
                kept = read_sessions(SESS_FILE)
                if kept:
                    return self.send_json({"ok": False, "reason": "refuse-empty",
                                           "kept": len(kept)}, 409)
            if data and not replace:
                old = read_sessions(SESS_FILE)
                if old:
                    idx = {}
                    for s in old:
                        if isinstance(s, dict):
                            idx[s.get("id") or ("t:" + str(s.get("title")))] = s
                    for s in data:
                        if isinstance(s, dict):
                            idx[s.get("id") or ("t:" + str(s.get("title")))] = s
                    data = sorted(idx.values(),
                                  key=lambda x: -(x.get("ts") or 0) if isinstance(x, dict) else 0)[:60]
            try:
                write_sessions(data)
                if not data and force:
                    with open(SESS_FLAG, "w", encoding="utf-8") as f:
                        f.write("cleared by user\n")
                elif os.path.exists(SESS_FLAG):
                    os.remove(SESS_FLAG)
            except Exception as e:
                return self.send_json({"error": str(e)}, 500)
            return self.send_json({"ok": True})
        if p == "/mkgen":
            ok, msg, code = bridge.make_plugin_from_text(
                data.get("config") or {}, data.get("name"), data.get("desc"),
                data.get("how"))
            return self.send_json({"ok": ok, "msg": msg, "code": code,
                                   "plugins": bridge.list_plugins()})
        if p == "/mkplugin":
            ok, msg, tools = bridge.make_plugin(data.get("name"), data.get("code"),
                                                data.get("desc") or "")
            return self.send_json({"ok": ok, "msg": msg, "tools": sorted(tools),
                                   "plugins": bridge.list_plugins()})
        if p == "/rmplugin":
            ok, msg = bridge.drop_plugin(data.get("name"))
            return self.send_json({"ok": ok, "msg": msg,
                                   "plugins": bridge.list_plugins()})
        if p == "/plugin-install":
            ok, msg, _tools = bridge.install_plugin(
                data.get("src") or data.get("url") or "",
                str(data.get("desc") or ""))
            return self.send_json({"ok": ok, "msg": msg,
                                   "plugins": bridge.list_plugins()})
        if p == "/config":
            f = os.path.join(HERE, "config.json")
            try:
                try:
                    with open(f, encoding="utf-8") as fp:
                        old = json.load(fp)
                    if not isinstance(old, dict):
                        old = {}
                except Exception:
                    old = {}
                for k, v in (data or {}).items():
                    old[k] = v
                if len(json.dumps(old, ensure_ascii=False)) > 256 * 1024:
                    return self.send_json({"error": "config too large"}, 413)
                with CFG_LOCK:
                    tmp = f + "." + uuid.uuid4().hex[:8] + ".tmp"
                    try:
                        with open(tmp, "w", encoding="utf-8") as fp:
                            json.dump(old, fp, ensure_ascii=False, indent=2)
                        os.replace(tmp, f)
                    finally:
                        if os.path.exists(tmp):
                            try:
                                os.remove(tmp)
                            except Exception:
                                pass
            except Exception as e:
                return self.send_json({"error": str(e)}, 500)
            return self.send_json({"ok": True})
        self.send_json({"error": "not found"}, 404)
def main():
    threading.Thread(target=reaper, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), H)
    srv.daemon_threads = True
    print("平台 %s | Python %s | 纯 Python 服务端（无需 Node）"
          % (sys.platform, sys.version.split()[0]))
    print("http://127.0.0.1:%d/" % PORT)
    if PORT in BAD_PORTS:
        print("警告：%d 在浏览器黑名单里，Chrome / Edge / Firefox 会拒绝连接"
              "（ERR_UNSAFE_PORT）。curl 正常，网页打不开。" % PORT)
        print("      换端口：SA_PORT=6688 python start.py")
    if not LOCAL_ONLY:
        import plat
        for ip in plat.lan_ips():
            print("局域网/手机  http://%s:%d/?k=%s" % (ip, PORT, TOKEN))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
if __name__ == "__main__":
    main()
