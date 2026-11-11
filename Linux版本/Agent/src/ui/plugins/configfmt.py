import configparser
import io
import json
import os
import re
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
try:
    import tomllib
except Exception:
    tomllib = None
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _read(path):
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return None, "文件不存在：%s" % path
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return open(p, encoding=enc).read(), ""
        except Exception:
            continue
    return None, "编码认不出"
def _scalar(v):
    s = str(v).strip()
    if s.lower() in ("true", "yes", "on"):
        return True
    if s.lower() in ("false", "no", "off"):
        return False
    if re.match(r"^-?\d+$", s):
        return int(s)
    if re.match(r"^-?\d+\.\d+$", s):
        return float(s)
    if s[:1] in "\"'" and s[-1:] == s[:1]:
        return s[1:-1]
    return s
def config_to_json(path, fmt="", indent=1):
    text, err = _read(path)
    if text is None:
        return err
    kind = str(fmt or "").strip().lower()
    ext = os.path.splitext(path)[1].lower()
    if not kind:
        kind = {".ini": "ini", ".cfg": "ini", ".conf": "ini", ".toml": "toml",
                ".env": "env", ".properties": "env", ".json": "json"}.get(ext, "ini")
    try:
        if kind == "toml":
            if tomllib is None:
                return "这个 Python 没有 tomllib（要 3.11+）"
            data = tomllib.loads(text)
        elif kind == "json":
            data = json.loads(text)
        elif kind == "env":
            data = {}
            for line in text.splitlines():
                s = line.strip()
                if not s or s.startswith(("#", "!", ";")):
                    continue
                if s.lower().startswith("export "):
                    s = s[7:]
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                data[k.strip()] = _scalar(v)
        else:
            cp = configparser.ConfigParser(interpolation=None)
            cp.optionxform = str
            cp.read_string(text)
            data = {}
            for sec in cp.sections():
                data[sec] = {k: _scalar(v) for k, v in cp.items(sec)}
            for k, v in cp.defaults().items():
                data.setdefault("DEFAULT", {})[k] = _scalar(v)
    except Exception as e:
        return "解析失败（按 %s 读）：%s: %s" % (kind, type(e).__name__, str(e)[:150])
    body = json.dumps(data, ensure_ascii=False, indent=int(indent or 1))
    keys = sum(len(v) for v in data.values()) if all(
        isinstance(v, dict) for v in data.values()) else len(data)
    return "%s（按 %s 解析，%d 个键）\n%s" % (
        os.path.basename(path), kind, keys, body[:6000])
def config_lint(path):
    text, err = _read(path)
    if text is None:
        return err
    seen = {}
    dups = []
    empty = []
    secrets = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith(("#", ";", "[", "!")):
            continue
        if "=" not in s and ":" not in s:
            continue
        k = re.split(r"[=:]", s, 1)[0].strip()
        if k in seen:
            dups.append("第 %d 行 %s（第 %d 行也有）" % (i, k, seen[k]))
        else:
            seen[k] = i
        if re.split(r"[=:]", s, 1)[1].strip() in ("", '""', "''"):
            empty.append("第 %d 行 %s 是空的" % (i, k))
        if re.search(r"(key|token|secret|password|passwd)", k, re.I) and \
                len(re.split(r"[=:]", s, 1)[1].strip()) > 8:
            secrets.append("第 %d 行 %s 像是明文密钥" % (i, k))
    out = ["共 %d 个键" % len(seen)]
    for label, items in (("重复键", dups), ("空值", empty), ("明文密钥", secrets)):
        if items:
            out.append("%s %d 处：" % (label, len(items)))
            out.extend("  - " + x for x in items[:10])
    if len(out) == 1:
        out.append("没发现问题")
    return "\n".join(out)
TOOLS = {
    "config_to_json": (config_to_json, {"path": "str", "fmt": "str", "indent": "int"},
                       "把 ini/toml/env 配置读成 JSON"),
    "config_lint": (config_lint, {"path": "str"}, "检查配置文件里的重复键和明文密钥"),
}
