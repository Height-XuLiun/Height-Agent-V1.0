import importlib.util
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
try:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from SuperAgent import Profile, Router, Task, SYSTEM_PROMPT, identity, NO_RETRY_HINTS
import searchopt
import searchguard
class BridgeRouter(Router):
    jid = ""
    def say(self, msg):
        super().say(msg)
        emit({"job": self.jid, "t": msg})
    def act(self, tid, text, state="run"):
        if text:
            emit({"job": self.jid, "act": {"tid": tid or "", "text": text, "state": state}})
PLUG = os.path.join(HERE, "plugins")
OUT_LOCK = threading.Lock()
_SINK = None
def set_sink(fn):
    global _SINK
    _SINK = fn
def emit(obj):
    if _SINK is not None:
        try:
            _SINK(obj)
        except Exception:
            pass
        return
    line = (json.dumps(obj, ensure_ascii=False, default=str) + "\n").encode("utf-8")
    with OUT_LOCK:
        try:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
        except Exception:
            pass
_CANCEL = set()
_CANCEL_LOCK = threading.Lock()
def cancel_job(jid):
    with _CANCEL_LOCK:
        if jid:
            _CANCEL.add(str(jid))
def is_cancelled(jid):
    with _CANCEL_LOCK:
        return bool(jid) and str(jid) in _CANCEL
def clear_cancel(jid):
    with _CANCEL_LOCK:
        _CANCEL.discard(str(jid))
def _clean_key(k):
    s = str(k or "")
    s = s.replace("•", "").replace("\u2022", "").replace("\u00b7", "")
    s = "".join(ch for ch in s if 32 < ord(ch) < 127).strip()
    return s
ANTH_VERSION = "2023-06-01"
ANTH_MAX_TOKENS = 8192
def is_anthropic(cfg):
    p = str(cfg.get("provider") or "").strip().lower()
    base = str(cfg.get("base_url") or "").strip().lower()
    model = str(cfg.get("model") or "").strip().lower()
    if p == "anthropic":
        return True
    if "anthropic" in base:
        return True
    return model.startswith("claude")
def _anth_blocks(content):
    if content is None:
        return [{"type": "text", "text": ""}]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    out = []
    for part in content if isinstance(content, list) else []:
        if not isinstance(part, dict):
            continue
        kind = part.get("type")
        if kind == "text":
            out.append({"type": "text", "text": part.get("text") or ""})
        elif kind == "image_url":
            url = ((part.get("image_url") or {}).get("url") or "")
            m = re.match(r"^data:([^;]+);base64,(.*)$", url, re.S)
            if m:
                out.append({"type": "image", "source": {"type": "base64",
                            "media_type": m.group(1), "data": m.group(2)}})
            elif url.startswith(("http://", "https://")):
                out.append({"type": "image", "source": {"type": "url", "url": url}})
    return out or [{"type": "text", "text": ""}]
def anth_convert(messages):
    system, msgs = [], []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "user")
        if role == "system":
            c = m.get("content")
            if isinstance(c, str):
                system.append(c)
            elif isinstance(c, list):
                system.extend([p.get("text") or "" for p in c
                               if isinstance(p, dict) and p.get("type") == "text"])
            continue
        role = "assistant" if role == "assistant" else "user"
        blocks = _anth_blocks(m.get("content"))
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"].extend(blocks)
        else:
            msgs.append({"role": role, "content": blocks})
    if not msgs:
        msgs = [{"role": "user", "content": [{"type": "text", "text": "（空输入）"}]}]
    if msgs[0]["role"] != "user":
        msgs.insert(0, {"role": "user", "content": [{"type": "text", "text": "继续"}]})
    return "\n\n".join([s for s in system if s]), msgs
_ANTH_OK = {}
def anth_extras(cfg):
    lv = str(cfg.get("reasoning") or "").strip().lower()
    if lv not in ("medium", "high"):
        return [None]
    budget = {"medium": 4096, "high": 8192}[lv]
    return [{"thinking": {"type": "enabled", "budget_tokens": budget}},
            {"thinking": {"type": "adaptive"}},
            {"effort": lv},
            None]
def _anth_body(cfg, msgs, system, extra):
    max_tokens = int(cfg.get("max_tokens", ANTH_MAX_TOKENS) or ANTH_MAX_TOKENS)
    body = {"model": cfg.get("model") or "", "max_tokens": max_tokens,
            "messages": msgs, "stream": True}
    if system:
        n = int(cfg.get("_stable_len") or 0)
        if (cfg.get("_anth_cache_on") and isinstance(system, str)
                and 0 < n < len(system)):
            body["system"] = [
                {"type": "text", "text": system[:n],
                 "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": system[n:].lstrip()},
            ]
        else:
            body["system"] = system
    think = extra.get("thinking") if isinstance(extra, dict) else None
    if think:
        budget = int((think or {}).get("budget_tokens") or 0)
        if budget:
            body["max_tokens"] = max(max_tokens, budget + 2048)
        else:
            body["max_tokens"] = max(max_tokens, 4096)
        body.update(extra)
    elif extra:
        body.update(extra)
        body["temperature"] = float(cfg.get("temperature", 0.7))
    else:
        body["temperature"] = float(cfg.get("temperature", 0.7))
    return body
def _opener(url):
    host = urllib.parse.urlparse(url).hostname or ""
    if host in ("127.0.0.1", "localhost", "::1"):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()
def anth_open(cfg, body):
    base = (cfg.get("base_url") or "https://api.anthropic.com/v1").rstrip("/")
    url = base + "/messages"
    headers = {"Content-Type": "application/json",
               "x-api-key": _clean_key(cfg.get("api_key")),
               "anthropic-version": str(cfg.get("anthropic_version") or ANTH_VERSION),
               "Accept": "text/event-stream"}
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    return _opener(url).open(req, timeout=180)
def anth_stream(cfg, msgs, system, on_text, on_think, extra):
    body = _anth_body(cfg, msgs, system, extra)
    text, think = "", ""
    with anth_open(cfg, body) as r:
        for raw in r:
            for line in raw.decode("utf-8", "replace").splitlines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    d = json.loads(payload)
                except Exception:
                    continue
                kind = d.get("type")
                if kind == "content_block_delta":
                    delta = d.get("delta") or {}
                    dt = delta.get("type")
                    if dt == "text_delta":
                        c = delta.get("text") or ""
                        if c:
                            text += c
                            if on_text:
                                on_text(c)
                    elif dt == "thinking_delta":
                        c = delta.get("thinking") or ""
                        if c:
                            think += c
                            if on_think:
                                on_think(c)
                elif kind == "content_block_start":
                    blk = d.get("content_block") or {}
                    if blk.get("type") == "text" and blk.get("text"):
                        text += blk["text"]
                        if on_text:
                            on_text(blk["text"])
                elif kind == "error":
                    raise RuntimeError(((d.get("error") or {}).get("message")) or "流式中断")
    return text, think
_HTTP_MSG = {
    400: "请求被拒绝，检查模型 ID 和消息格式",
    401: NO_RETRY_HINTS[1] + "或已过期",
    402: NO_RETRY_HINTS[0],
    403: NO_RETRY_HINTS[2],
    404: NO_RETRY_HINTS[3] + "，检查是否以 /v1 结尾",
    408: "请求超时，服务商没有响应",
    409: "请求冲突，稍后再试",
    422: "请求被拒绝，检查模型 ID 和消息格式",
    429: "调用太频繁或额度已用尽，稍后再试",
    500: "模型服务商内部出错",
    502: "模型服务商网关出错",
    503: "模型服务商暂时不可用",
    504: "模型服务商响应超时",
}
_CONN_MSG = NO_RETRY_HINTS[4] + "，检查是否填对、本地服务是否已启动"
_HUMAN_PREFIX = NO_RETRY_HINTS + (
    "请求被拒绝", "请求超时", "请求冲突", "调用太频繁", "安全连接失败",
    "接口返回异常", "接口调用失败", "模型服务商", "API Key 含非法字符",
)
def _http_code(e, s):
    code = getattr(e, "code", None)
    try:
        code = int(code) if code else 0
    except Exception:
        code = 0
    if code:
        return code
    m = (re.search(r"HTTP\s*Error\s*(\d{3})", s, re.I)
         or re.search(r"\bHTTP\s+(\d{3})\b", s)
         or re.search(r"\b(4\d{2}|5\d{2})\b", s))
    return int(m.group(1)) if m else 0
def friendly_llm_error(e):
    if isinstance(e, UnicodeEncodeError):
        return "API Key 含非法字符，请重新粘贴"
    s = str(e)
    if s.startswith(_HUMAN_PREFIX):
        return s[:200]
    low = s.lower()
    code = _http_code(e, s)
    if code in _HTTP_MSG:
        msg = _HTTP_MSG[code]
    elif "timed out" in low or "timeout" in low:
        msg = _HTTP_MSG[408]
    elif ("refused" in low or "10061" in s or "enotfound" in low
          or "getaddrinfo" in low or "econnrefused" in low
          or "name or service not known" in low):
        msg = _CONN_MSG
    elif "ssl" in low or "certificate" in low or "tls" in low or "handshake" in low:
        msg = "安全连接失败，检查接口地址是否正确"
    elif "unauthor" in low or ("invalid" in low and "key" in low):
        msg = _HTTP_MSG[401]
    elif code:
        msg = "接口返回异常（%d）" % code
    else:
        msg = "接口调用失败，检查 Key 和接口地址"
    try:
        sys.stderr.write("[llm-error] %s: %s\n" % (type(e).__name__, s[:300]))
        sys.stderr.flush()
    except Exception:
        pass
    return msg
def _friendly(e):
    return friendly_llm_error(e)
def _fail_json(e):
    return json.dumps({"tool": "finish", "args": {"answer": friendly_llm_error(e)}},
                      ensure_ascii=False)
def anth_chat(cfg, messages, on_text=None, on_think=None, raise_on_error=False):
    system, msgs = anth_convert(messages)
    got = [0]
    def _t(c):
        got[0] += len(c)
        if on_text:
            on_text(c)
    last = None
    cands = anth_extras(cfg)
    ck = (str(cfg.get("model") or ""), str(cfg.get("reasoning") or "").strip().lower())
    start = _ANTH_OK.get(ck, 0)
    if not isinstance(start, int) or not (0 <= start < len(cands)):
        start = 0
    order = list(range(start, len(cands))) + list(range(0, start))
    for idx in order:
        extra = cands[idx]
        abort = False
        for attempt in (0, 1):
            try:
                text, think = anth_stream(cfg, msgs, system, _t, on_think, extra)
                _ANTH_OK[ck] = idx
                return text, think
            except urllib.error.HTTPError as e:
                last = e
                if e.code == 400 and attempt == 0 and cfg.get("_anth_cache_on"):
                    cfg = dict(cfg)
                    cfg["_anth_cache_on"] = False
                    continue
                if e.code != 400 or extra is None:
                    abort = True
                break
            except Exception as e:
                last = e
                abort = True
                break
        if abort:
            break
    msg = _friendly(last) if last is not None else "调用失败"
    if raise_on_error:
        raise RuntimeError(msg)
    if on_text and not got[0]:
        on_text(msg)
    return msg, ""
MADE_FILE = os.path.join(PLUG, "_made.json")
PLUG_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,28}$")
PLUG_DENY = ("subprocess", "os.system", "os.popen", "ctypes", "socket",
             "eval(", "exec(", "__import__", "shutil.rmtree", "os.remove")
PLUG_MAX = 12000
_PLUG_GEN = [0]
def load_made():
    try:
        with open(MADE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}
def save_made(d):
    try:
        with open(MADE_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
def make_plugin(name, code, desc=""):
    name = str(name or "").strip().lower()
    code = str(code or "")
    if not PLUG_NAME_RE.match(name):
        return False, "插件名只能用小写字母、数字、下划线，2-29 个字符", {}
    if len(code) > PLUG_MAX:
        return False, "代码超过 %d 字符，拆小一点" % PLUG_MAX, {}
    low = code.lower()
    for bad in PLUG_DENY:
        if bad in low:
            return False, "代码里出现了不允许的调用：%s" % bad, {}
    if "TOOLS" not in code:
        return False, ("代码里必须有 TOOLS 字典，形如 "
                       "TOOLS={'名字':(函数,{'参数':'str'},'说明')}"), {}
    path = os.path.join(PLUG, name + ".py")
    backup = None
    if os.path.isfile(path):
        try:
            backup = open(path, encoding="utf-8").read()
        except Exception:
            backup = ""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        spec = importlib.util.spec_from_file_location("plug_" + name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tools = {}
        for tn, item in getattr(mod, "TOOLS", {}).items():
            if isinstance(item, tuple) and len(item) == 3 and callable(item[0]):
                tools[tn] = item
        if not tools:
            raise ValueError("TOOLS 里没有可调用的工具")
    except BaseException as e:
        if backup:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(backup)
            except Exception:
                pass
        else:
            try:
                os.remove(path)
            except Exception:
                pass
        return False, "插件没通过检查：%s: %s" % (type(e).__name__, str(e)[:200]), {}
    made = load_made()
    made[name] = {"desc": str(desc or "")[:120], "tools": sorted(tools),
                  "ts": time.strftime("%Y-%m-%d %H:%M")}
    save_made(made)
    _PLUG_GEN[0] += 1
    return True, "已创建插件 %s，新增工具：%s" % (name, "、".join(sorted(tools))), tools
def drop_plugin(name):
    name = str(name or "").strip().lower()
    path = os.path.join(PLUG, name + ".py")
    if not os.path.isfile(path):
        return False, "没有这个插件"
    try:
        os.remove(path)
    except Exception as e:
        return False, str(e)
    made = load_made()
    made.pop(name, None)
    save_made(made)
    _PLUG_GEN[0] += 1
    return True, "已删除 %s" % name
PLUG_IMPORT_MAX = 8 * 1024 * 1024
def _http_get(url, timeout=30):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=timeout) as r:
        return r.read(PLUG_IMPORT_MAX)
def _repo_zip_url(src):
    s = str(src or "").strip()
    if not s:
        return ""
    low = s.lower()
    if low.endswith(".zip") or "/archive/" in low or "codeload" in low:
        return s
    m = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$", s, re.I)
    if m:
        return "https://github.com/%s/%s/archive/refs/heads/main.zip" % (m.group(1), m.group(2))
    m = re.match(r"^https?://gitee\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$", s, re.I)
    if m:
        return "https://gitee.com/%s/%s/repository/archive/master.zip" % (m.group(1), m.group(2))
    return s
def install_plugin(src, desc=""):
    import io
    import tempfile
    import zipfile
    raw = str(src or "").strip()
    if not raw:
        return False, "请填写仓库地址或 zip 路径", {}
    if os.path.isfile(raw):
        try:
            if os.path.getsize(raw) > PLUG_IMPORT_MAX:
                return False, "zip 超过 8MB", {}
            blob = open(raw, "rb").read()
        except Exception as e:
            return False, "读不了文件：%s" % e, {}
    else:
        try:
            blob = _http_get(_repo_zip_url(raw))
        except Exception as e:
            return False, ("下载失败：%s。GitHub 在国内常被墙，"
                           "可先用加速镜像下载 zip，再选本地文件导入。" % str(e)[:120]), {}
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except Exception:
        return False, "不是有效的 zip 包", {}
    picked, skipped = [], []
    for info in zf.infolist():
        if info.is_dir() or not info.filename.lower().endswith(".py"):
            continue
        base = os.path.basename(info.filename)
        if base.startswith("_") or info.filename.count("/") > 4:
            continue
        try:
            text = zf.read(info).decode("utf-8", "replace")
        except Exception:
            continue
        if "TOOLS" not in text:
            continue
        name = os.path.splitext(base)[0].lower()
        if not PLUG_NAME_RE.match(name):
            skipped.append(name)
            continue
        ok, msg, _tools = make_plugin(name, text, desc)
        if ok:
            picked.append(name)
        else:
            skipped.append("%s(%s)" % (name, str(msg)[:40]))
    if not picked:
        tail = ("；跳过：" + "、".join(skipped[:5])) if skipped else ""
        return False, "包里没有可安装的插件" + tail, {}
    tail = ("；跳过 " + "、".join(skipped[:5])) if skipped else ""
    return True, "已安装 %d 个：%s%s" % (len(picked), "、".join(picked), tail), {}
def read_plugin_src(name):
    name = str(name or "").strip().lower()
    if not PLUG_NAME_RE.match(name):
        return None
    try:
        with open(os.path.join(PLUG, name + ".py"), encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None
def make_plugin_tool(name, code, desc=""):
    ok, msg, tools = make_plugin(name, code, desc)
    if not ok:
        return msg
    return msg + "。现在就能调用这些工具。"
def drop_plugin_tool(name):
    ok, msg = drop_plugin(name)
    return msg
_SUMM = [None]
def load_summ():
    if _SUMM[0] is not None:
        return _SUMM[0]
    d = {}
    p = os.path.join(PLUG, "_summ.py")
    if os.path.isfile(p):
        try:
            spec = importlib.util.spec_from_file_location("plug__summ", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            d = dict(getattr(mod, "SUMM", {}) or {})
        except BaseException:
            d = {}
    _SUMM[0] = d
    return d
def short_desc(text):
    s = str(text or "").strip()
    if not s:
        return ""
    for a, b in (("（", "）"), ("(", ")")):
        while a in s and b in s:
            i, j = s.find(a), s.find(b)
            if i > j:
                break
            s = s[:i] + s[j + 1:]
    s = s.split("：")[0].split("；")[0]
    for sep in ("，", ",", "。"):
        if sep in s and len(s.split(sep)[0]) >= 6:
            s = s.split(sep)[0]
            break
    s = s.strip(" ，,。、;；")
    return s[:16] + "…" if len(s) > 17 else s
def list_plugins():
    out = []
    if not os.path.isdir(PLUG):
        return out
    made = load_made()
    summ = load_summ()
    for f in sorted(os.listdir(PLUG)):
        if not f.endswith(".py") or f.startswith("_"):
            continue
        rec = {"file": f, "tools": [], "error": "", "descs": {},
               "made": f[:-3] in made, "desc": (made.get(f[:-3]) or {}).get("desc", "")}
        try:
            spec = importlib.util.spec_from_file_location("plug_" + f[:-3], os.path.join(PLUG, f))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for name, item in getattr(mod, "TOOLS", {}).items():
                if isinstance(item, tuple) and len(item) == 3:
                    rec["tools"].append(name)
                    rec["descs"][name] = summ.get(name) or short_desc(item[2])
        except BaseException as e:
            rec["error"] = "%s: %s" % (type(e).__name__, e)
        out.append(rec)
    return out
def load_plugins():
    out = {}
    if not os.path.isdir(PLUG):
        return out
    for f in sorted(os.listdir(PLUG)):
        if not f.endswith(".py") or f.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location("plug_" + f[:-3], os.path.join(PLUG, f))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for name, item in getattr(mod, "TOOLS", {}).items():
                if isinstance(item, tuple) and len(item) == 3:
                    out[name] = item
        except BaseException as e:
            emit({"t": "插件加载失败 %s: %s" % (f, e)})
    return out
def pick_plugins(cfg):
    plugins = load_plugins()
    want = cfg.get("plugins")
    if isinstance(want, list):
        plugins = {k: v for k, v in plugins.items() if k in want}
    return plugins
def reason_fields(cfg):
    lv = str(cfg.get("reasoning") or "medium").strip().lower()
    if lv not in ("off", "low", "medium", "high"):
        lv = "medium"
    on = lv in ("medium", "high")
    model = str(cfg.get("model") or "").lower()
    prov = str(cfg.get("provider") or "").lower()
    out = {}
    if any(k in model for k in ("gpt-5", "o1", "o3", "o4")):
        out["reasoning_effort"] = lv if on else "minimal"
    if "deepseek" in model or prov == "deepseek":
        out["thinking"] = {"type": "enabled" if on else "disabled"}
        if on:
            out["reasoning_effort"] = lv
    elif "glm" in model or prov == "zhipu":
        out["thinking"] = {"type": "enabled" if on else "disabled"}
    elif "qwen" in model or prov == "qwen":
        out["enable_thinking"] = bool(on)
    return out
def token_budget(cfg, default=1024):
    base = int(cfg.get("max_tokens") or 0) or default
    lv = str(cfg.get("reasoning") or "medium").strip().lower()
    if lv not in ("medium", "high"):
        return base
    return max(base, 4096 if lv == "high" else 2048)
def make_llm(cfg, on_think=None):
    model = cfg.get("model") or ""
    extra = reason_fields(cfg)
    anth = is_anthropic(cfg)
    def call(prompt):
        if is_cancelled(cfg.get("_job")):
            return '{"tool":"finish","args":{"answer":"__paused__"}}'
        if anth:
            try:
                text, _ = anth_chat(cfg, [{"role": "user", "content": prompt}],
                                    None, on_think, raise_on_error=True)
                return text
            except Exception as e:
                return _fail_json(e)
        body = {"model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                "temperature": float(cfg.get("temperature", 0.2)),
                "max_tokens": token_budget(cfg)}
        body.update(extra)
        try:
            with _open(cfg, body) as r:
                text, raw_all, sse = "", [], False
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    raw_all.append(line)
                    if not line.startswith("data:"):
                        continue
                    sse = True
                    payload = line[5:].strip()
                    if payload in ("[DONE]", ""):
                        continue
                    try:
                        d = json.loads(payload)
                    except Exception:
                        continue
                    delta = (d.get("choices") or [{}])[0].get("delta") or {}
                    rc = delta.get("reasoning_content") or delta.get("reasoning")
                    if rc and on_think:
                        on_think(str(rc))
                    c = delta.get("content")
                    if c:
                        text += c
            if sse:
                return text
            d = json.loads("".join(raw_all))
            msg = (d.get("choices") or [{}])[0].get("message") or {}
            rc = msg.get("reasoning_content") or msg.get("reasoning")
            if rc and on_think:
                on_think(str(rc))
            return msg.get("content") or ""
        except Exception as e:
            return _fail_json(e)
    return call
TITLE_SYS = (
    "给下面这段对话起一个标题，要求：\n"
    "1. 4 到 10 个汉字，最多 14 个字；\n"
    "2. 说清这件事本身（在做什么、处理什么对象），不要复述用户的原话；\n"
    "3. 不要标点、引号、序号，不要「关于」「求助」「问题」这类空话；\n"
    "4. 只输出标题本身，不要解释。")
def clean_title(s):
    s = str(s or "").strip()
    if not s or s.startswith('{"tool"'):
        return ""
    s = s.split("\n")[0].strip()
    for pre in ("标题：", "标题:", "title:", "Title:"):
        if s.startswith(pre):
            s = s[len(pre):].strip()
    s = s.strip("「」『』“”\"'`*#-—·。，,、：: 　")
    if not s:
        return ""
    if len(s) > 14:
        s = s[:14].rstrip("的了个和与及")
    return s
def plain(cfg, min_tokens=0):
    c = dict(cfg or {})
    c["reasoning"] = "off"
    if min_tokens:
        c["max_tokens"] = max(int(c.get("max_tokens") or 0), min_tokens)
    return c
def make_title(cfg, text):
    text = str(text or "").strip()
    if not text:
        return ""
    try:
        llm = make_llm(plain(cfg, 256))
        return clean_title(llm(TITLE_SYS + "\n\n对话：\n" + text[:1200]))
    except Exception:
        return ""
MK_SYS = (
    "你在给一个本地 Agent 写插件。用户用自然语言说明他想要什么工具，你把它写成插件代码。\n"
    "输出要求：\n"
    "1. 只输出 Python 代码本身，不要解释，不要 markdown 代码围栏；\n"
    "2. 必须定义 TOOLS 字典：TOOLS={'工具名':(函数, {'参数名':'str'}, '一句话说明')}；\n"
    "3. 工具名用小写字母、数字、下划线；函数要有 docstring，参数给默认值；\n"
    "4. 只用标准库，不要引入需要 pip 安装的包；\n"
    "5. 出错时返回一句中文说明，不要抛异常；不要发起网络请求，除非用户明确要求。")
def strip_fence(s):
    s = str(s or "").strip()
    if s.startswith("```"):
        lines = s.split("\n")[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s
def make_plugin_from_text(cfg, name, desc, how):
    name = str(name or "").strip().lower()
    desc = str(desc or "").strip()
    how = str(how or "").strip()
    if not PLUG_NAME_RE.match(name):
        return False, "工具名只能用小写字母、数字、下划线，2-29 个字符", ""
    if not how:
        return False, "先用一句话说清它要做什么", ""
    prompt = (MK_SYS + "\n\n工具名：" + name +
              "\n一句话说明：" + (desc or how) +
              "\n它要做的事：" + how + "\n\n只输出代码：")
    try:
        code = strip_fence(make_llm(plain(cfg, 4096))(prompt))
    except Exception as e:
        return False, "模型没接上：%s" % str(e)[:80], ""
    if not code:
        return False, "模型没有给出代码，再试一次", ""
    ok, msg, tools = make_plugin(name, code, desc or how)
    return ok, msg, code
def _open(cfg, body):
    base = (cfg.get("base_url") or "").rstrip("/")
    key = _clean_key(cfg.get("api_key"))
    url = base + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key,
                 "Accept": "text/event-stream"},
        method="POST")
    try:
        tmo = int(cfg.get("_timeout") or 180)
    except Exception:
        tmo = 180
    return _opener(url).open(req, timeout=max(3, min(tmo, 180)))
_HAN = re.compile(r"[\u4e00-\u9fff]")
SEARCH_SYS = (
    "You are the search planner of a chat assistant. For the user's LATEST message, decide "
    "whether a public web search is needed, and if it is, WRITE the search queries yourself.\n"
    "Reply with exactly one JSON object and nothing else:\n"
    '{"search": true, "queries": ["query one", "query two"]}\n'
    'or {"search": false, "reason": "short reason"}\n'
    "Rules:\n"
    "1. search=true ONLY when the answer depends on facts that could be on the public web: "
    "news, release dates, versions, prices, documentation, official pages, current status, "
    "unfamiliar proper nouns.\n"
    "2. search=false for private/account data (balance, quota, order history), pure chat, "
    "opinions, math, code, writing, and things you already know reliably. Do NOT search just "
    'because the user wrote "查一下" or "搜索".\n'
    "3. NEVER copy or slice the user's sentence into the query. Write 1-2 short, self-contained "
    "keyword queries (2-12 words) that a search engine would actually match, in the language "
    "best suited to the subject.\n"
    "4. Resolve pronouns (这个/那个/它/this/that) using the conversation context; a query must "
    "make sense with no surrounding conversation.\n"
    "5. Never output a bare pronoun, a single character, a stop word, or an empty string as a query.\n"
    "6. No markdown fences, no explanation, no tool calls, no prose outside the JSON object.\n"
    "补充：账号余额、配额、私人文件这类数据联网查不到，直接 {\"search\": false}。\n"
)
_BAD_Q = re.compile(
    r"^(?:这个|那个|这些|那些|它|他|她|这|那|什么|怎么|为啥|为什么|呢|吗|啊|的|了|"
    r"this|that|it|these|those|what|which|the|a|an|yes|no)$", re.I)
_FENCE = re.compile(r"\{[\s\S]*?\}")
def _clean_query(q):
    s = str(q or "").strip()
    for _ in range(4):
        prev = s
        s = s.strip("\"'“”‘’`*# ").strip(" ，,。.、:：?？!！；;").strip()
        if s == prev:
            break
    s = re.sub(r"\s+", " ", s)
    if not (2 <= len(s) <= 120):
        return ""
    if _BAD_Q.match(s) or not re.search(r"[\w\u4e00-\u9fff]", s):
        return ""
    return s
def plan_search(cfg, goal, msgs, jid=""):
    goal = str(goal or "").strip()
    if not goal or is_cancelled(cfg.get("_job")):
        return []
    if not (cfg.get("base_url") and cfg.get("api_key")):
        return []
    hist = []
    for m in list(msgs or [])[-6:]:
        if (m.get("role") or "") not in ("user", "assistant"):
            continue
        c = m.get("content")
        if isinstance(c, list):
            c = " ".join(str(p.get("text") or "") for p in c
                         if isinstance(p, dict) and p.get("type") == "text")
        t = str(c or "").strip().replace("\n", " ")[:300]
        if t:
            hist.append(("用户" if m.get("role") == "user" else "助手") + "：" + t)
    prompt = (SEARCH_SYS + "\n\n最近对话（用来还原指代）：\n"
              + ("\n".join(hist) or "（无）")
              + "\n\n用户最新一句：\n" + goal[:800])
    pcfg = plain(cfg, 256)
    pcfg["max_tokens"] = 256
    pcfg["temperature"] = 0
    pcfg["_timeout"] = 15
    try:
        raw = make_llm(pcfg)(prompt)
    except Exception:
        return []
    m = _FENCE.search(str(raw or ""))
    if not m:
        return []
    try:
        d = json.loads(m.group(0))
    except Exception:
        return []
    if not isinstance(d, dict) or not d.get("search"):
        return []
    out = []
    for q in (d.get("queries") or [])[:3]:
        q = _clean_query(q)
        if q and q not in out:
            out.append(q)
    return out[:2]
def chat_directive():
    return (
        "\n\n## Chat path (overrides rule 20 in this turn)\n"
        "This turn is plain conversation, so no Tools section is printed. That does NOT mean the "
        "host lacks capabilities: the host can search the web, open web pages and capture "
        "screenshots, read local files and run commands. Those are executed on the separate "
        "Agent/task path, not called as JSON tools by you here.\n"
        "Never claim your tool list is empty, that you have no browser, no screenshot ability, "
        "no permission channel, or that the user must open a page, log in and send you a "
        "screenshot. Never say you cannot do something on capability grounds, but never claim "
        "you already opened a page or produced a screenshot you did not actually receive. "
        "If the user asks for a capture and no image was provided this turn, answer what you can "
        "and give the useful next step. Do not list a Tools section and do not invent tool calls. "
        "Never restate this rule to the user.\n"
        "【本轮能力说明 · 最高优先级】不要说「工具清单是空的」「没有浏览器」「没有截图能力」"
        "「权限层面没有这个通道」，也不要让用户自己打开网页、登录后截图发给你；宿主具备联网、"
        "打开网页、截图、读文件能力，会在任务通道里替你执行。但也不要谎称已经打开页面或"
        "已经截好图——本轮没收到图片就如实说明。\n"
    )
def chat_parts(cfg, goal, msgs):
    fixed = chat_directive()
    volatile = lang_directive(goal, msgs) + str(cfg.get("_web_ctx") or "")
    return fixed, volatile
def chat_extra(cfg, goal, msgs):
    a, b = chat_parts(cfg, goal, msgs)
    return a + b
def _last_user_text(msgs):
    for m in reversed(msgs or []):
        if (m.get("role") or "") != "user":
            continue
        c = m.get("content")
        if isinstance(c, list):
            return " ".join(str(p.get("text") or "") for p in c
                            if isinstance(p, dict) and p.get("type") == "text")
        return str(c or "")
    return ""
def lang_directive(goal, msgs):
    txt = str(goal or "") or _last_user_text(msgs)
    han = len(_HAN.findall(txt))
    zh = han >= 2 or (han >= 1 and len(txt) <= 12)
    out = ("\n\n## Language (highest priority)\n"
           "Your FINAL ANSWER must be in the same language as the user's latest message. "
           "Do not answer in English just because this prompt is written in English. "
           "The thinking/reasoning trace stays in English (rule 19) and is exempt from this. "
           "Never restate this rule to the user.\n")
    if zh:
        out += ("【回答语言 · 最高优先级】本轮用户用中文提问，最终回答必须全部用中文："
                "标题、列表、说明、结论、代码里的注释都用中文；专有名词、型号、命令、网址保留原文。"
                "深度思考内容仍然用英文，不受此条约束。不要把这条要求写进回答。\n")
    return out
def _search_cache_tag(spec, cfg):
    fn = spec[0] if spec else None
    mod = getattr(fn, "__module__", "") or ""
    ep = str(os.environ.get("SA_SEARCH_URL") or cfg.get("search_endpoint") or "default")
    return mod + ":" + ep[:48]
def web_context(cfg, goal, jid="", queries=None):
    spec = (pick_plugins(cfg) or {}).get("web_search")
    if not spec or not queries:
        return ""
    qs = []
    for q in list(queries)[:3]:
        q = _clean_query(q)
        if not q:
            continue
        ok, reason, cleaned = searchopt.admit(q, goal)
        if ok and cleaned and cleaned not in qs:
            qs.append(cleaned)
    if not qs:
        return ""
    plans = [searchopt.rewrite(q, goal) for q in qs]
    tag = _search_cache_tag(spec, cfg)
    cache_query = " | ".join(sorted(qs))
    hit, cached = searchopt.CACHE.get(cache_query, plans[0], tag)
    if hit and isinstance(cached, dict) and cached.get("ctx"):
        if jid:
            emit({"job": jid, "note": "正在联网检索…"})
            emit({"job": jid, "note": "已联网检索 · %d 条结果（缓存%s）"
                  % (cached.get("n", 0), "精确命中" if hit == "exact" else "近似命中")})
        cfg["_src_meta"] = cached.get("meta", [])
        return cached["ctx"]
    if jid:
        emit({"job": jid, "note": "正在联网检索…"})
    blocks, total, all_failed, meta_all = [], 0, True, []
    audit = []
    for q, plan in zip(qs, plans):
        try:
            try:
                res = str(spec[0](q, 8) or "")
            except TypeError:
                res = str(spec[0](q) or "")
        except Exception as e:
            res = "搜索失败：%s" % e
        failed = any(k in res[:24] for k in ("失败", "不可达", "没有搜到"))
        docs = searchopt.parse_results(res)
        if not failed and docs:
            kept, dropped = searchguard.filter_docs(docs, plan)
            ranked, detail = searchopt.rank_docs(kept, plan)
            if ranked:
                all_failed = False
                total += len(ranked)
                sources, meta = searchguard.build_sources(ranked, plan)
                meta_all.extend(meta)
                blocks.append("### 检索词：%s\n%s\n%s"
                              % (q, sources, searchguard.citation_directive(meta)))
                audit.append({"query": q, "intent": plan.intent,
                              "entities": [e.as_dict() for e in plan.entities],
                              "exact": plan.exact, "lexical": plan.lexical,
                              "dilution": plan.dilution, "candidates": len(docs),
                              "kept": len(kept), "ranked": len(ranked),
                              "dropped": [(d.title[:40], r) for d, r in dropped]})
                continue
        blocks.append("### 检索词：%s\n%s" % (q, res[:6000]))
    merged = "\n\n".join(blocks)
    if jid:
        emit({"job": jid, "note": ("联网检索失败，按记忆作答" if all_failed
                                   else "已联网检索 · %d 条结果" % max(total, 1))})
    cfg["_src_meta"] = meta_all
    cfg["_search_audit"] = audit
    if all_failed:
        return ("\n\n## Live web search (attempted this turn, failed)\n" + merged +
                "\nSay in one short line that the live lookup failed, then answer from memory "
                "with the uncertainty stated. Do not invent results and do not claim a search "
                "tool is missing — the host already tried.\n")
    out = ("\n\n## Live web search (already run for you this turn)\n"
           "The host ran a web search for %s and these are the real results. Use them instead "
           "of memory for anything time-sensitive, and cite the URLs you actually rely on. "
           "If the results are off-topic (dictionary entries, unrelated pages), say so plainly "
           "instead of forcing them into an answer. Never say you have no search tool or cannot "
           "browse this turn — the search is done.\n\n%s\n"
           % (json.dumps(qs, ensure_ascii=False), merged))
    searchopt.CACHE.put(cache_query, {"ctx": out, "n": total, "meta": meta_all},
                        plans[0], tag)
    return out
def call_chat(cfg, messages, on_text=None, on_think=None):
    model = cfg.get("model") or ""
    msgs = list(messages or [])
    fixed, volatile = chat_parts(cfg, cfg.get("_goal") or "", msgs)
    extra = fixed + volatile
    head = SYSTEM_PROMPT + "\n\nYou are currently running as model: " + model + fixed
    cfg["_stable_len"] = len(head)
    cfg["_anth_cache_on"] = (bool(cfg.get("cache_breakpoint"))
                             and is_anthropic(cfg)
                             and est_tokens(head) >= 2048)
    cfg["_cache_plan"] = searchopt.cache_hints(
        cfg.get("provider") or "", model, est_tokens(head),
        bool(cfg.get("cache_opt", True)))
    cfg["_cache_plan"]["prefix_key"] = searchopt.stable_prefix_key(
        head, cfg.get("provider") or "", model)
    if not any(m.get("role") == "system" for m in msgs):
        sys_prompt = head + volatile
        msgs = [{"role": "system", "content": sys_prompt}] + msgs
    elif extra:
        msgs = [dict(m) for m in msgs]
        for m in msgs:
            if (m.get("role") or "") == "system":
                m["content"] = str(m.get("content") or "") + extra
                break
        else:
            msgs.insert(0, {"role": "system", "content": extra})
    if is_anthropic(cfg):
        return anth_chat(cfg, msgs, on_text, on_think)
    body = {"model": model, "messages": msgs, "stream": True,
            "temperature": float(cfg.get("temperature", 0.7)),
            "max_tokens": token_budget(cfg, 2048)}
    body.update(reason_fields(cfg))
    text, think = "", ""
    try:
        with _open(cfg, body) as r:
            for raw in r:
                if is_cancelled(cfg.get("_job")):
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload in ("[DONE]", ""):
                    continue
                try:
                    d = json.loads(payload)
                except Exception:
                    continue
                ch = (d.get("choices") or [{}])[0]
                delta = ch.get("delta") or {}
                rc = delta.get("reasoning_content") or delta.get("reasoning")
                if rc:
                    think += rc
                    if on_think:
                        on_think(rc)
                c = delta.get("content")
                if c:
                    text += c
                    if on_text:
                        on_text(c)
        return text, think
    except UnicodeEncodeError:
        msg = "调用失败：API Key 含非法字符，请重新粘贴"
        if on_text and not text:
            on_text(msg)
        return (msg, "")
    except Exception as e:
        msg = "调用失败：" + friendly_llm_error(e)
        if on_text and not text:
            on_text(msg)
        return (msg, "")
def est_tokens(text):
    s = str(text or "")
    cjk = 0
    for ch in s:
        o = ord(ch)
        if 0x3400 <= o <= 0x9fff or 0x3000 <= o <= 0x303f or 0xff00 <= o <= 0xffef:
            cjk += 1
    return int(cjk + (len(s) - cjk) / 3.6)
def msgs_tokens(msgs):
    n = 0
    for m in msgs or []:
        c = m.get("content")
        if isinstance(c, str):
            n += est_tokens(c)
        elif isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and p.get("type") == "text":
                    n += est_tokens(p.get("text"))
                elif isinstance(p, dict) and p.get("type") == "image_url":
                    n += 400
        n += 4
    return n
def run_chat(job):
    jid = job.get("job", "")
    try:
        cfg = dict(job.get("config") or {})
        msgs = job.get("messages") or []
        goal = str(job.get("goal") or "")
        cfg["_goal"] = goal
        cfg["_job"] = jid
        if not msgs:
            emit({"job": jid, "t": "（空输入）"})
        else:
            web = ""
            if job.get("web"):
                queries = plan_search(cfg, goal, msgs, jid)
                if queries:
                    web = web_context(cfg, goal, jid, queries)
            cfg["_web_ctx"] = web
            sys_len = est_tokens(SYSTEM_PROMPT + identity(cfg.get("model") or "")
                                 + lang_directive(goal, msgs) + chat_directive() + web)
            emit({"job": jid, "usage": {"in": msgs_tokens(msgs) + sys_len}})
            text, _ = call_chat(cfg, msgs,
                                on_text=lambda c: emit({"job": jid, "t": c}),
                                on_think=lambda c: emit({"job": jid, "think": c}))
            meta = cfg.get("_src_meta") or []
            if meta:
                v = searchguard.verify_citations(text, meta)
                if v["unknown"]:
                    emit({"job": jid, "note": "回答引用了未检索到的来源："
                          + ",".join(v["unknown"])})
        emit({"job": jid, "done": True, "result": {"ok": True, "chat": True}})
    except Exception as e:
        emit({"job": jid, "error": friendly_llm_error(e)})
def run_job(job):
    jid = job.get("job", "")
    cfg = dict(job.get("config") or {})
    cfg["_job"] = jid
    try:
        llm = make_llm(cfg, on_think=lambda c: emit({"job": jid, "think": c}))
        prof = Profile(name=cfg.get("model", "generic"),
                       model=cfg.get("model", ""),
                       context=int(cfg.get("context", 1048576)))
        root = cfg.get("root") or os.path.join(HERE, "workspace")
        os.makedirs(root, exist_ok=True)
        tasks = []
        for i, t in enumerate(job.get("tasks") or []):
            if not (t.get("desc") or "").strip():
                continue
            tasks.append(Task(tid="t%d" % (i + 1), desc=t["desc"],
                              check=t.get("check") or "true",
                              expect=t.get("expect") or "",
                              thread=t.get("thread") or ""))
        plugins = pick_plugins(cfg)
        maker = cfg.get("maker", True) and (cfg.get("permission") or "workspace") != "read"
        if maker:
            plugins["make_plugin"] = (make_plugin_tool,
                                      {"name": "str", "code": "str", "desc": "str"},
                                      "给自己造一个新工具：写一个 Python 插件，立刻可用、重启后仍在")
            plugins["drop_plugin"] = (drop_plugin_tool, {"name": "str"},
                                      "删掉一个自己造过的工具")
        seen_gen = [_PLUG_GEN[0]]
        def _reload():
            if not maker or _PLUG_GEN[0] == seen_gen[0]:
                return None
            seen_gen[0] = _PLUG_GEN[0]
            fresh = pick_plugins(cfg)
            fresh["make_plugin"] = plugins["make_plugin"]
            fresh["drop_plugin"] = plugins["drop_plugin"]
            return fresh
        r = BridgeRouter(llm, root, workers=int(cfg.get("workers", 3)),
                         task_budget_s=int(cfg.get("budget", 180)),
                         trace_rate=float(cfg.get("trace_rate", 0.5)),
                         profile=prof, extra_tools=plugins,
                         permission=cfg.get("permission") or "workspace",
                         reload_extra=_reload if maker else None)
        r.jid = jid
        if not tasks:
            r.say("未给任务，由 Router 拆分")
            tasks = r.plan(job.get("goal", ""))
        if not tasks:
            r.say("Router 没有拆出任务，检查模型能否输出 JSON")
            res = {"ok": False, "tasks": []}
        else:
            res = r.run(tasks)
        emit({"job": jid, "done": True, "result": res})
    except Exception as e:
        emit({"job": jid, "error": friendly_llm_error(e)})
def main():
    emit({"t": "bridge ready"})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
        except Exception:
            continue
        if job.get("stop"):
            cancel_job(str(job.get("job") or ""))
            continue
        if job.get("mkgen"):
            ok, msg, code = make_plugin_from_text(
                job.get("config") or {}, job.get("name"), job.get("desc"), job.get("how"))
            emit({"mkgen": True, "ok": ok, "msg": msg, "code": code})
            continue
        if job.get("title"):
            emit({"title": make_title(job.get("config") or {}, job.get("text") or "")})
            continue
        if job.get("chat"):
            threading.Thread(target=run_chat, args=(job,), daemon=True).start()
        else:
            threading.Thread(target=run_job, args=(job,), daemon=True).start()
if __name__ == "__main__":
    main()
