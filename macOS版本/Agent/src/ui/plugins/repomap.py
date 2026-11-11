import os
import re
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java")
SKIP = {".git", "node_modules", "__pycache__", ".snapshots", "dist", "build"}
PY_CLASS = re.compile(r"^class\s+(\w+)\s*(?:\(([^)]*)\))?")
PY_DEF = re.compile(r"^(\s*)def\s+(\w+)\s*\(([^)]*)\)")
PY_CONST = re.compile(r"^([A-Z][A-Z0-9_]{2,})\s*=")
JS_CLASS = re.compile(r"^\s*(?:export\s+)?class\s+(\w+)")
JS_FUNC = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)")
JS_ARROW = re.compile(r"^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>")
GO_FUNC = re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(([^)]*)\)")
def _sig(args, limit=90):
    a = re.sub(r"\s+", " ", args or "").strip()
    return a[:limit]
def _scan(path):
    try:
        if os.path.getsize(path) > 800_000:
            return []
        lines = open(path, encoding="utf-8", errors="ignore").read().split("\n")
    except Exception:
        return []
    out, ext = [], os.path.splitext(path)[1]
    for ln in lines[:4000]:
        if ext == ".py":
            m = PY_CLASS.match(ln)
            if m:
                out.append("class %s" % m.group(1))
                continue
            m = PY_DEF.match(ln)
            if m:
                depth = len(m.group(1)) // 4
                out.append("%sdef %s(%s)" % ("  " * depth, m.group(2), _sig(m.group(3))))
                continue
            m = PY_CONST.match(ln)
            if m:
                out.append("%s = ..." % m.group(1))
                continue
        elif ext in (".js", ".ts", ".tsx", ".jsx"):
            m = JS_CLASS.match(ln)
            if m:
                out.append("class %s" % m.group(1))
                continue
            m = JS_FUNC.match(ln) or JS_ARROW.match(ln)
            if m:
                out.append("function %s(%s)" % (m.group(1), _sig(m.group(2))))
                continue
        elif ext == ".go":
            m = GO_FUNC.match(ln)
            if m:
                out.append("func %s(%s)" % (m.group(1), _sig(m.group(2))))
                continue
    return out
def repo_map(path: str = "", depth: int = 3, budget: int = 3000) -> str:
    base = os.path.join(ROOT, str(path).strip().lstrip("/\\")) if str(path).strip() else ROOT
    if not os.path.isdir(base):
        return "目录不存在：%s" % path
    chunks, used = [], 0
    for dirpath, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        rel = os.path.relpath(dirpath, ROOT)
        if rel.count(os.sep) >= int(depth):
            dirs[:] = []
        for fn in sorted(files):
            if not fn.endswith(EXTS):
                continue
            fp = os.path.join(dirpath, fn)
            items = _scan(fp)
            if not items:
                continue
            head = os.path.relpath(fp, ROOT)
            lines_out = []
            for i in items:
                cand = "%s\n%s" % (head, "\n".join("  " + x for x in lines_out + [i]))
                if used + len(cand) > int(budget):
                    if lines_out:
                        chunks.append("%s\n%s\n  …（本文件还有 %d 项未列）"
                                      % (head, "\n".join("  " + x for x in lines_out),
                                         len(items) - len(lines_out)))
                        used = int(budget)
                    chunks.append("…（已达预算上限，剩余文件未列出）")
                    return "\n\n".join(chunks)
                lines_out.append(i)
            block = "%s\n%s" % (head, "\n".join("  " + x for x in lines_out))
            chunks.append(block)
            used += len(block)
    return "\n\n".join(chunks) if chunks else "没有可分析的源码文件。"
TOOLS = {
    "repo_map": (repo_map, {"path": "str", "depth": "int", "budget": "int"},
                 "仓库结构地图：类与函数签名，不含实现"),
}
