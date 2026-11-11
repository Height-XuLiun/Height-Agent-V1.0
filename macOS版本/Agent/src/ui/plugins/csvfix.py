import csv
import io
import os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
ENCS = ("utf-8-sig", "utf-8", "gb18030", "big5", "utf-16", "latin-1")
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _decode(raw):
    for enc in ENCS:
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("utf-8", "replace"), "utf-8(有损)"
def csv_sniff(path):
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return "文件不存在：%s" % path
    try:
        raw = open(p, "rb").read(1 << 20)
    except Exception as e:
        return "读取失败：%s" % e
    text, enc = _decode(raw)
    lines = text.splitlines()
    if not lines:
        return "空文件"
    sample = "\n".join(lines[:30])
    delim = ","
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except Exception:
        for d in (",", ";", "\t", "|"):
            if sample.count(d) > sample.count(delim):
                delim = d
    name = {",": "逗号", ";": "分号", "\t": "制表符", "|": "竖线"}.get(delim, delim)
    rows = list(csv.reader(io.StringIO(sample), delimiter=delim))
    widths = {}
    for r in rows:
        widths[len(r)] = widths.get(len(r), 0) + 1
    main = max(widths, key=widths.get) if widths else 0
    odd = sum(1 for k, v in widths.items() if k != main for _ in range(v))
    has_bom = raw[:3] == b"\xef\xbb\xbf"
    head = "%s · %d 行（抽样 30 行）" % (os.path.basename(p), text.count("\n") + 1)
    return "\n".join([
        head,
        "编码：%s%s" % (enc, "（带 BOM）" if has_bom else ""),
        "分隔符：%s" % name,
        "列数：多数行 %d 列，%d 行列数不齐" % (main, odd),
        "表头：%s" % " | ".join(rows[0][:12]) if rows else "表头：无",
        "建议：%s" % ("直接读就行" if enc.startswith("utf-8") and not odd
                      else "先转成 UTF-8 再处理，列数不齐的行要单独看"),
    ])
def csv_fix(path, dest="", delim=""):
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return "文件不存在：%s" % path
    out = _safe(dest or (os.path.splitext(os.path.basename(p))[0] + ".utf8.csv"))
    if not out:
        return "目标路径越界"
    try:
        raw = open(p, "rb").read()
    except Exception as e:
        return "读取失败：%s" % e
    text, enc = _decode(raw)
    d = delim or ","
    if not delim:
        try:
            d = csv.Sniffer().sniff("\n".join(text.splitlines()[:30]),
                                    delimiters=",;\t|").delimiter
        except Exception:
            d = ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=d)]
    if not rows:
        return "没有内容"
    width = max(len(r) for r in rows)
    fixed = [r + [""] * (width - len(r)) for r in rows]
    try:
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(fixed)
    except Exception as e:
        return "写入失败：%s" % e
    pad = sum(1 for r in rows if len(r) != width)
    return "已转好 -> %s\n原编码 %s，%d 行 %d 列，补了 %d 行空值" % (
        os.path.relpath(out, ROOT).replace("\\", "/"), enc, len(rows), width, pad)
TOOLS = {
    "csv_sniff": (csv_sniff, {"path": "str"}, "看 CSV 的编码、分隔符、列数是否整齐"),
    "csv_fix": (csv_fix, {"path": "str", "dest": "str", "delim": "str"},
                "把 CSV 统一成 UTF-8 逗号分隔"),
}
