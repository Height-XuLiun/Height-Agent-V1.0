import json
import os
import re
import sys
import zipfile
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t]+")
def unescape(s):
    return (s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
             .replace("&apos;", "'").replace("&amp;", "&"))
def tidy(text):
    text = unescape(text)
    text = WS.sub(" ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()
def _zip_text(path, inner, sep="\n"):
    with zipfile.ZipFile(path) as z:
        try:
            raw = z.read(inner).decode("utf-8", "replace")
        except KeyError:
            return ""
    raw = raw.replace("</w:p>", "\n").replace("</a:p>", "\n")
    return raw
def docx(path):
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n == "word/document.xml"]
        if not names:
            return ""
        raw = z.read(names[0]).decode("utf-8", "replace")
    raw = raw.replace("</w:p>", "\n").replace("<w:br/>", "\n")
    return tidy(TAG.sub("", raw))
def pptx(path):
    out = []
    with zipfile.ZipFile(path) as z:
        slides = sorted([n for n in z.namelist()
                         if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                        key=lambda s: int(re.findall(r"\d+", s)[-1]))
        for i, n in enumerate(slides, 1):
            raw = z.read(n).decode("utf-8", "replace").replace("</a:p>", "\n")
            body = tidy(TAG.sub("", raw))
            if body:
                out.append("[第 %d 页]\n%s" % (i, body))
    return "\n\n".join(out)
def xlsx(path):
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            raw = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
            shared = [tidy(TAG.sub("", m)) for m in re.findall(r"<si>(.*?)</si>", raw, re.S)]
        sheets = sorted([n for n in z.namelist()
                         if re.match(r"xl/worksheets/sheet\d+\.xml$", n)])
        out = []
        for si, name in enumerate(sheets, 1):
            raw = z.read(name).decode("utf-8", "replace")
            rows = []
            for row in re.findall(r"<row[^>]*>(.*?)</row>", raw, re.S):
                cells = []
                for c in re.findall(r"<c([^>]*)>(.*?)</c>", row, re.S):
                    attrs, body = c
                    v = re.search(r"<v>(.*?)</v>", body, re.S)
                    if not v:
                        istr = re.search(r"<is>(.*?)</is>", body, re.S)
                        cells.append(tidy(TAG.sub("", istr.group(1))) if istr else "")
                        continue
                    val = v.group(1)
                    if 't="s"' in attrs:
                        try:
                            val = shared[int(val)]
                        except Exception:
                            pass
                    cells.append(unescape(val))
                if any(x.strip() for x in cells):
                    rows.append("\t".join(cells))
            if rows:
                out.append("[工作表 %d]\n%s" % (si, "\n".join(rows)))
        return "\n\n".join(out)
def pdf(path):
    try:
        import pypdf
        r = pypdf.PdfReader(path)
        return "\n".join((p.extract_text() or "") for p in r.pages).strip()
    except Exception:
        pass
    data = open(path, "rb").read()
    chunks = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        seg = m.group(1)
        txt = b"".join(re.findall(rb"\((.*?)(?<!\\)\)", seg))
        if txt:
            chunks.append(txt.decode("latin-1", "replace"))
    text = tidy(" ".join(chunks))
    if len(text) < 40:
        return ""
    return text
def plain(path):
    for enc in ("utf-8", "gbk", "utf-16"):
        try:
            return open(path, encoding=enc).read()
        except Exception:
            continue
    return open(path, "rb").read().decode("utf-8", "replace")
def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "缺文件路径"}))
        return
    path = sys.argv[1]
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".docx":
            text = docx(path)
        elif ext == ".pptx":
            text = pptx(path)
        elif ext == ".xlsx":
            text = xlsx(path)
        elif ext == ".pdf":
            text = pdf(path)
        elif ext in (".doc", ".ppt", ".xls"):
            print(json.dumps({"error": "旧版二进制格式读不了，另存为 %sx 再拖进来" % ext},
                             ensure_ascii=False))
            return
        else:
            text = plain(path)
    except zipfile.BadZipFile:
        print(json.dumps({"error": "文件损坏，或不是标准的 Office 文档"}, ensure_ascii=False))
        return
    except Exception as e:
        print(json.dumps({"error": "%s: %s" % (type(e).__name__, e)}, ensure_ascii=False))
        return
    text = (text or "").strip()
    if not text:
        print(json.dumps({"error": "这个文件里没抽出文字（可能是扫描件或纯图）"},
                         ensure_ascii=False))
        return
    print(json.dumps({"text": text[:120000]}, ensure_ascii=False))
if __name__ == "__main__":
    main()
