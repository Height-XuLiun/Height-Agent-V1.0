import os
import zipfile
import xml.etree.ElementTree as ET
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _tag(e):
    return e.tag.rsplit("}", 1)[-1]
def _text(node):
    return "".join(t.text or "" for t in node.iter() if _tag(t) == "t")
def docx_read(path, limit=6000, with_table=True):
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return "文件不存在：%s" % path
    if not zipfile.is_zipfile(p):
        return "不是 docx（旧版 .doc 要先另存为 docx）"
    try:
        with zipfile.ZipFile(p) as z:
            if "word/document.xml" not in z.namelist():
                return "这个文件里没有正文"
            root = ET.fromstring(z.read("word/document.xml"))
    except Exception as e:
        return "读取失败：%s: %s" % (type(e).__name__, str(e)[:150])
    body = None
    for e in root.iter():
        if _tag(e) == "body":
            body = e
            break
    if body is None:
        return "找不到正文"
    out = []
    paras = 0
    tables = 0
    for child in body:
        tg = _tag(child)
        if tg == "p":
            txt = _text(child).strip()
            if not txt:
                continue
            style = ""
            for e in child.iter():
                if _tag(e) == "pStyle":
                    style = e.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val") or ""
                    break
            if style.lower().startswith("heading"):
                num = "".join(c for c in style if c.isdigit()) or "1"
                txt = "#" * min(6, int(num)) + " " + txt
            out.append(txt)
            paras += 1
        elif tg == "tbl" and with_table:
            rows = []
            for tr in child:
                if _tag(tr) != "tr":
                    continue
                cells = [_text(tc).strip().replace("\n", " ")
                         for tc in tr if _tag(tc) == "tc"]
                if cells:
                    rows.append("| " + " | ".join(cells) + " |")
                    if len(rows) == 1:
                        rows.append("|" + "---|" * len(cells))
            if rows:
                out.append("\n".join(rows))
                tables += 1
        if sum(len(x) for x in out) > int(limit or 6000):
            out.append("……后面还有内容，已截断")
            break
    if not out:
        return "文档是空的"
    return ("%s · %d 段 · %d 张表\n\n" % (os.path.basename(p), paras, tables)) + "\n\n".join(out)
TOOLS = {
    "docx_read": (docx_read, {"path": "str", "limit": "int", "with_table": "bool"},
                  "读 docx 的正文和表格"),
}
