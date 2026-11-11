import os
import re
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
TEXT_EXT = (".txt", ".md", ".py", ".js", ".ts", ".json", ".yml", ".yaml", ".toml",
            ".ini", ".cfg", ".csv", ".tsv", ".html", ".css", ".sh", ".bat", ".go",
            ".rs", ".java", ".c", ".h", ".cpp", ".sql", ".log")
SKIP_DIR = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _collect(target, depth, out):
    p = _safe(target)
    if not p or not os.path.exists(p):
        return
    if os.path.isfile(p):
        out.append(p)
        return
    base_depth = p.rstrip("\\/").count(os.sep)
    for dirpath, dirnames, files in os.walk(p):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR and not d.startswith(".")]
        if dirpath.count(os.sep) - base_depth >= depth:
            dirnames[:] = []
        for f in files:
            if f.lower().endswith(TEXT_EXT) and not f.endswith((".min.js", ".map")):
                out.append(os.path.join(dirpath, f))
def context_pack(paths, budget=8000, depth=2, with_line_no=True, dedupe=True):
    items = [x.strip() for x in str(paths or "").split(",") if x.strip()]
    if not items:
        return "给几个文件或目录，用逗号隔开"
    files = []
    for x in items:
        _collect(x, int(depth or 2), files)
    files = sorted(dict.fromkeys(files))
    if not files:
        return "这些路径下没有可读的文本文件"
    budget = max(200, int(budget or 8000))
    seen_hash = {}
    chunks = []
    used = 0
    skipped = []
    for fp in files:
        rel = os.path.relpath(fp, ROOT).replace("\\", "/")
        try:
            body = open(fp, encoding="utf-8", errors="replace").read()
        except Exception as e:
            skipped.append("%s（%s）" % (rel, e))
            continue
        if dedupe:
            import hashlib
            h = hashlib.md5(re.sub(r"\s+", "", body).encode("utf-8")).hexdigest()
            if h in seen_hash:
                skipped.append("%s（和 %s 一样）" % (rel, seen_hash[h]))
                continue
            seen_hash[h] = rel
        share = max(300, budget // max(1, len(files)))
        lines = body.splitlines()
        keep = lines[: max(1, share // 40)]
        text = "\n".join(
            ("%4d| %s" % (i + 1, l)) if with_line_no else l
            for i, l in enumerate(keep))
        if len(keep) < len(lines):
            text += "\n     | ……（共 %d 行，这里只放前 %d 行）" % (len(lines), len(keep))
        n = len(text)
        if used + n > budget and chunks:
            skipped.append("%s（超出预算）" % rel)
            continue
        chunks.append("### %s\n```\n%s\n```" % (rel, text))
        used += n
    head = "打包 %d 个文件，约 %d 字符" % (len(chunks), used)
    if skipped:
        head += "\n跳过 %d 个：%s" % (len(skipped), "；".join(skipped[:6]))
    return head + "\n\n" + "\n\n".join(chunks)
def context_scan(paths=".", depth=2, top=20):
    items = [x.strip() for x in str(paths or ".").split(",") if x.strip()]
    files = []
    for x in items:
        _collect(x, int(depth or 2), files)
    files = sorted(dict.fromkeys(files))
    if not files:
        return "没有可读的文本文件"
    rows = []
    for fp in files:
        try:
            rows.append((os.path.getsize(fp), os.path.relpath(fp, ROOT).replace("\\", "/")))
        except Exception:
            continue
    rows.sort(reverse=True)
    total = sum(r[0] for r in rows)
    lines = ["%d 个文本文件，合计 %.1f KB" % (len(rows), total / 1024.0)]
    for size, rel in rows[: max(1, int(top or 20))]:
        lines.append("  %8.1f KB  %s" % (size / 1024.0, rel))
    if len(rows) > int(top or 20):
        lines.append("  ……还有 %d 个" % (len(rows) - int(top or 20)))
    lines.append("建议：先读最大的那几个，或者用 context_pack 带预算打包。")
    return "\n".join(lines)
TOOLS = {
    "context_pack": (context_pack, {"paths": "str", "budget": "int", "depth": "int",
                                    "with_line_no": "bool", "dedupe": "bool"},
                     "把多个文件/目录压成一份带行号的材料"),
    "context_scan": (context_scan, {"paths": "str", "depth": "int", "top": "int"},
                     "先看目录里哪些文件最大，决定读什么"),
}
