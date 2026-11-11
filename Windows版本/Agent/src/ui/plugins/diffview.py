import difflib
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _read(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except Exception as e:
        return ["<读取失败 %s>" % e]
def diff_view(path: str, other: str = "", context: int = 3) -> str:
    a = _safe(path)
    if not a:
        return "路径越界，拒绝执行"
    if not os.path.isfile(a):
        return "文件不存在：%s" % path
    if other:
        b = _safe(other)
        if not b or not os.path.isfile(b):
            return "对比目标不存在：%s" % other
        old_p, new_p, label = b, a, "%s → %s" % (other, path)
    else:
        bak = a + ".bak"
        if not os.path.isfile(bak):
            return ("没有 %s.bak 可比。edit_file 改过的文件会自动留 .bak，"
                    "也可以用 other 指定另一个文件。" % path)
        old_p, new_p, label = bak, a, "%s 的 .bak → 现在" % path
    old, new = _read(old_p), _read(new_p)
    diff = list(difflib.unified_diff(old, new, fromfile=label, tofile=path,
                                     lineterm="", n=max(0, int(context))))
    if not diff:
        return "没有差异：%s 与对比版本一致（%d 行）" % (path, len(new))
    add = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    rem = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    head = "差异 %s：+%d −%d 行（%d 行 → %d 行）" % (label, add, rem, len(old), len(new))
    body = "\n".join(diff[:200])
    if len(diff) > 200:
        body += "\n…（还有 %d 行差异未显示）" % (len(diff) - 200)
    return head + "\n" + body
TOOLS = {
    "diff_view": (diff_view, {"path": "str", "other": "str", "context": "int"},
                  "看文件改了什么：与 .bak 或另一个文件对比，输出统一 diff"),
}
