import os
import re
import zipfile
import xml.etree.ElementTree as ET
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _tag(e):
    return e.tag.rsplit("}", 1)[-1]
def _col(ref):
    m = re.match(r"([A-Z]+)", ref or "")
    if not m:
        return 0
    n = 0
    for ch in m.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1
def _shared(z):
    out = []
    name = "xl/sharedStrings.xml"
    if name not in z.namelist():
        return out
    root = ET.fromstring(z.read(name))
    for si in root:
        if _tag(si) != "si":
            continue
        out.append("".join(t.text or "" for t in si.iter() if _tag(t) == "t"))
    return out
def _sheets(z):
    names = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
    return sorted(names, key=lambda s: int(re.sub(r"\D", "", s) or 0))
def xlsx_read(path, sheet=1, limit=200, as_csv=True):
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return "文件不存在：%s" % path
    if not zipfile.is_zipfile(p):
        return "不是 xlsx（旧版 .xls 要先另存为 xlsx）"
    try:
        with zipfile.ZipFile(p) as z:
            sheets = _sheets(z)
            if not sheets:
                return "这个文件里没有工作表"
            idx = int(sheet or 1) - 1
            if idx < 0 or idx >= len(sheets):
                return "只有 %d 个工作表，序号从 1 开始" % len(sheets)
            shared = _shared(z)
            root = ET.fromstring(z.read(sheets[idx]))
            rows = []
            for row in root.iter():
                if _tag(row) != "row":
                    continue
                cells = {}
                for c in row:
                    if _tag(c) != "c":
                        continue
                    ci = _col(c.get("r"))
                    t = c.get("t")
                    v = ""
                    for ch in c:
                        if _tag(ch) == "v":
                            v = ch.text or ""
                        elif _tag(ch) == "is":
                            v = "".join(x.text or "" for x in ch.iter() if _tag(x) == "t")
                    if t == "s":
                        try:
                            v = shared[int(v)]
                        except Exception:
                            v = ""
                    cells[ci] = v
                if not cells:
                    continue
                width = max(cells) + 1
                rows.append([cells.get(i, "") for i in range(width)])
                if len(rows) >= int(limit or 200):
                    break
    except Exception as e:
        return "读取失败：%s: %s" % (type(e).__name__, str(e)[:150])
    if not rows:
        return "第 %d 个工作表是空的" % (idx + 1)
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    head = "%s · 工作表 %d/%d · 前 %d 行 · %d 列" % (
        os.path.basename(p), idx + 1, len(sheets), len(rows), width)
    if not as_csv:
        return head + "\n" + "\n".join(" | ".join(r) for r in rows)
    out = []
    for r in rows:
        out.append(",".join('"%s"' % c.replace('"', '""') if ("," in c or '"' in c or "\n" in c) else c
                            for c in r))
    return head + "\n" + "\n".join(out)
TOOLS = {
    "xlsx_read": (xlsx_read, {"path": "str", "sheet": "int", "limit": "int", "as_csv": "bool"},
                  "读 xlsx 的内容，按行输出"),
}
