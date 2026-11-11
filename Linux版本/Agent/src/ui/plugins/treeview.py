import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
SKIP = {".git", "__pycache__", "node_modules", ".snapshots", ".store", ".venv", "venv",
        "dist", "build", ".idea", ".vscode", ".next", "target"}
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path or ".").lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _size(n):
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return ("%d%s" % (n, unit)) if unit == "B" else ("%.1f%s" % (n, unit))
        n /= 1024.0
def tree_view(path: str = ".", depth: int = 3, limit: int = 200) -> str:
    base = _safe(path)
    if not base or not os.path.isdir(base):
        return "目录不存在：%s" % path
    depth = max(1, min(8, int(depth)))
    limit = max(10, min(2000, int(limit)))
    lines, count, total = [], [0], [0]
    lines.append(os.path.basename(base) or base)
    def walk(d, prefix, level):
        if level > depth or count[0] >= limit:
            return
        try:
            items = sorted(os.scandir(d), key=lambda e: (not e.is_dir(), e.name.lower()))
        except Exception:
            return
        items = [e for e in items if e.name not in SKIP]
        for i, e in enumerate(items):
            if count[0] >= limit:
                lines.append(prefix + "└── …（已达上限 %d 项）" % limit)
                return
            last = i == len(items) - 1
            branch = "└── " if last else "├── "
            if e.is_dir():
                lines.append(prefix + branch + e.name + "/")
                walk(e.path, prefix + ("    " if last else "│   "), level + 1)
            else:
                try:
                    sz = e.stat().st_size
                except Exception:
                    sz = 0
                total[0] += sz
                lines.append(prefix + branch + "%s  %s" % (e.name, _size(sz)))
            count[0] += 1
    walk(base, "", 1)
    lines.append("— %d 项，合计 %s" % (count[0], _size(total[0])))
    return "\n".join(lines)
TOOLS = {
    "tree_view": (tree_view, {"path": "str", "depth": "int", "limit": "int"},
                  "目录树：带文件大小，跳过 .git/node_modules 等噪音目录"),
}
