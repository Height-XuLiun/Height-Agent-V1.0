import json
import os
import re
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
STEP = re.compile(r"""
    \.\s*([A-Za-z_$][\w$\-]*)
  | \[\s*(-?\d+)\s*\]
  | \[\s*\]
  | \[\s*([A-Za-z_$][\w$\-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\]\s]+))\s*\]
  | \[\s*\*\s*\]
""", re.X)
FUNCS = {
    "keys": "取所有键",
    "values": "取所有值",
    "len": "取长度",
    "count": "同 len",
    "type": "取类型",
    "first": "取第一个",
    "last": "取最后一个",
    "sort": "排序",
    "uniq": "去重",
    "flatten": "拍平一层",
    "sum": "求和",
    "min": "最小值",
    "max": "最大值",
    "join": "拼成一行",
}
AGG = {"uniq", "sort", "sum", "min", "max", "join", "count", "len", "flatten"}
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _load(path, text):
    if text and text.strip():
        try:
            return True, json.loads(text), "（内联文本）"
        except json.JSONDecodeError as e:
            return False, "不是合法 JSON：%s（第 %d 行第 %d 列）" % (e.msg, e.lineno, e.colno), ""
    p = _safe(path)
    if not p:
        return False, "路径越界，拒绝执行", ""
    if not os.path.isfile(p):
        return False, "文件不存在：%s" % path, ""
    raw = ""
    for enc in ("utf-8-sig", "gb18030"):
        try:
            with open(p, encoding=enc) as f:
                raw = f.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        with open(p, encoding="utf-8", errors="replace") as f:
            raw = f.read()
    if not raw.strip():
        return False, "空文件", ""
    try:
        return True, json.loads(raw), path
    except json.JSONDecodeError as e:
        return False, "不是合法 JSON：%s（第 %d 行第 %d 列）" % (e.msg, e.lineno, e.colno), ""
def _parse(path):
    if not path or path.strip() in (".", "$"):
        return []
    path = path.strip()
    if path.startswith("$"):
        path = path[1:]
    if path and path[0] not in ".[":
        path = "." + path
    steps, pos = [], 0
    for m in STEP.finditer(path):
        if m.start() != pos:
            raise ValueError("看不懂这段：%s" % path[pos:m.start()])
        pos = m.end()
        if m.group(1) is not None:
            steps.append(("key", m.group(1)))
        elif m.group(2) is not None:
            steps.append(("idx", int(m.group(2))))
        elif m.group(3) is not None:
            steps.append(("filter", (m.group(3),
                                     m.group(4) if m.group(4) is not None
                                     else m.group(5) if m.group(5) is not None
                                     else m.group(6))))
        else:
            steps.append(("iter", None))
    if pos != len(path):
        raise ValueError("看不懂这段：%s" % path[pos:])
    return steps
def _apply(vals, kind, arg):
    out = []
    for v in vals:
        if kind == "key":
            if isinstance(v, dict) and arg in v:
                out.append(v[arg])
        elif kind == "idx":
            if isinstance(v, list):
                try:
                    out.append(v[arg])
                except IndexError:
                    pass
        elif kind == "iter":
            if isinstance(v, list):
                out.extend(v)
            elif isinstance(v, dict):
                out.extend(v.values())
        elif kind == "filter":
            k, want = arg
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, dict) and str(x.get(k)) == want:
                        out.append(x)
    return out
def _fn(name, vals):
    v = vals[0] if len(vals) == 1 else vals
    if name == "keys":
        return list(v.keys()) if isinstance(v, dict) else []
    if name == "values":
        return list(v.values()) if isinstance(v, dict) else []
    if name in ("len", "count"):
        return len(v) if hasattr(v, "__len__") else 0
    if name == "type":
        return ("object" if isinstance(v, dict) else "array" if isinstance(v, list)
                else "string" if isinstance(v, str) else "number"
                if isinstance(v, (int, float)) and not isinstance(v, bool)
                else "boolean" if isinstance(v, bool) else "null" if v is None else "unknown")
    if name == "first":
        return v[0] if isinstance(v, list) and v else None
    if name == "last":
        return v[-1] if isinstance(v, list) and v else None
    if name == "sort":
        if not isinstance(v, list):
            return v
        try:
            return sorted(v)
        except TypeError:
            return sorted(v, key=lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True))
    if name == "uniq":
        if not isinstance(v, list):
            return v
        seen, out = set(), []
        for x in v:
            k = json.dumps(x, ensure_ascii=False, sort_keys=True)
            if k not in seen:
                seen.add(k)
                out.append(x)
        return out
    if name == "flatten":
        if not isinstance(v, list):
            return v
        out = []
        for x in v:
            out.extend(x if isinstance(x, list) else [x])
        return out
    if name == "sum":
        return sum(x for x in (v if isinstance(v, list) else [v])
                   if isinstance(x, (int, float)) and not isinstance(x, bool))
    if name == "min":
        return min(v) if isinstance(v, list) and v else None
    if name == "max":
        return max(v) if isinstance(v, list) and v else None
    if name == "join":
        return ", ".join(_one(x) for x in (v if isinstance(v, list) else [v]))
    return v
def _one(v):
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    return json.dumps(v, ensure_ascii=False)
def _show(v, limit):
    if isinstance(v, list):
        n = len(v)
        head = v[:limit]
        body = "\n".join("%3d. %s" % (i + 1, _one(x)) for i, x in enumerate(head))
        if n > limit:
            body += "\n…（共 %d 项，只显示前 %d 项）" % (n, limit)
        return "%d 项\n%s" % (n, body)
    return _one(v)
def _shape(v, depth=0):
    if isinstance(v, dict):
        ks = list(v.keys())
        s = "对象 { %s }" % ", ".join(str(k) for k in ks[:8])
        if len(ks) > 8:
            s += " …"
        if depth < 2 and ks:
            first = v[ks[0]]
            if isinstance(first, (dict, list)):
                s += "\n  %s 的形状：%s" % (ks[0], _shape(first, depth + 1))
        return s
    if isinstance(v, list):
        return "数组 [%d 项]" % len(v) + (
            "，首项：%s" % _shape(v[0], depth + 1) if v and isinstance(v[0], (dict, list)) else "")
    return "标量（%s）" % _one(v)[:60]
def json_query(path: str = "", expr: str = "", text: str = "", limit: int = 30) -> str:
    limit = max(1, min(200, int(limit or 30)))
    ok, data, src = _load(path, text)
    if not ok:
        return data
    if not (expr or "").strip():
        return ("数据源：%s\n形状：%s\n\n用法：json_query(path, \".items[0].name\")\n"
                "支持 .a.b、[0]、[]（展开）、[key=值]（过滤）、[].name（取值），"
                "管道：| keys | len | type | first | last | sort | uniq | sum | min | max | join"
                % (src, _shape(data)))
    stages = [s.strip() for s in expr.split("|")]
    vals = [data]
    try:
        for k, st in enumerate(stages):
            if not st:
                continue
            if st in FUNCS:
                if st in AGG:
                    v = vals[0] if len(vals) == 1 else vals
                    vals = [_fn(st, [v])]
                else:
                    vals = [_fn(st, [v]) for v in vals]
                continue
            for kind, arg in _parse(st):
                prev = vals
                vals = _apply(vals, kind, arg)
                if not vals:
                    hint = ""
                    if kind == "key" and prev and isinstance(prev[0], dict):
                        keys = [str(x) for x in list(prev[0])[:15]]
                        hint = "\n这一层只有这些键：%s" % ", ".join(keys)
                    elif k == 0:
                        hint = "\n根节点形状是 %s" % _shape(data)
                    return "0 项，没有匹配。%s\n表达式：%s" % (hint, expr)
            if not vals:
                hint = "\n根节点形状是 %s" % _shape(data) if k == 0 else ""
                return "0 项，没有匹配。%s\n表达式：%s" % (hint, expr)
    except ValueError as e:
        return "%s\n表达式：%s" % (e, expr)
    if len(vals) == 1:
        return _show(vals[0], limit)
    return _show(vals, limit)
TOOLS = {
    "json_query": (json_query, {"path": "str", "expr": "str", "text": "str", "limit": "int"},
                   "用 jq 式表达式查 JSON：.a.b、[0]、[] 展开、[k=v] 过滤、| keys/len/sort/sum"),
}
