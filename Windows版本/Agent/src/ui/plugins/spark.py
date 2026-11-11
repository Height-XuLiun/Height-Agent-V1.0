import csv
import io
import os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
BARS = "▁▂▃▄▅▆▇█"
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _read_text(p):
    for enc in ("utf-8-sig", "gb18030"):
        try:
            with open(p, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()
def _num(s):
    t = str(s).strip().replace(",", "").replace("¥", "").replace("$", "").replace("%", "")
    if not t or t in ("-", "--", "NA", "N/A", "null"):
        return None
    try:
        return float(t)
    except ValueError:
        return None
def spark_plot(path: str, column: str = "", rows: int = 40, mode: str = "spark") -> str:
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return "文件不存在：%s" % path
    text = _read_text(p)
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except Exception:
        dialect = csv.excel
    table = list(csv.reader(io.StringIO(text), dialect))
    if len(table) < 2:
        return "至少需要表头 + 一行数据"
    head = table[0]
    idx = None
    if column:
        c = str(column).strip()
        for i, h in enumerate(head):
            if h.strip() == c:
                idx = i
                break
        if idx is None and c.lstrip("-").isdigit():
            idx = int(c)
            if idx < 0:
                idx += len(head)
    if idx is None:
        numeric = []
        for i in range(len(head)):
            vals = [_num(r[i]) for r in table[1:] if i < len(r)]
            vals = [v for v in vals if v is not None]
            if len(vals) >= max(2, len(table) // 2):
                numeric.append("%d:%s" % (i, head[i]))
        return ("请指定列。看起来是数字的列有：%s\n用法：spark_plot(path, \"列名\")"
                % (", ".join(numeric) or "（没找到数字列）"))
    series, labels = [], []
    for r in table[1:]:
        if idx >= len(r):
            continue
        v = _num(r[idx])
        if v is None:
            continue
        series.append(v)
        labels.append(r[0] if r else "")
    if len(series) < 2:
        return "列「%s」里有效数字少于 2 个" % head[idx]
    if len(series) > int(rows):
        step = len(series) / float(int(rows))
        series = [series[int(i * step)] for i in range(int(rows))]
        labels = [labels[int(i * step)] for i in range(len(labels) and int(rows))]
    lo, hi = min(series), max(series)
    span = (hi - lo) or 1.0
    name = head[idx] if idx < len(head) else str(idx)
    if str(mode).lower() == "bar":
        top = max(abs(v) for v in series) or 1.0
        out = []
        for lab, v in list(zip(labels, series))[:int(rows)]:
            n = int(round(abs(v) / top * 30))
            out.append("%-12s %s %s" % (str(lab)[:12], "█" * max(1, n) if v >= 0 else "░" * max(1, n), _fmt(v)))
        return "%s（%d 点，柱状）\n%s" % (name, len(series), "\n".join(out))
    line = "".join(BARS[min(7, int((v - lo) / span * 7.999))] for v in series)
    trend = "上升" if series[-1] > series[0] else ("下降" if series[-1] < series[0] else "持平")
    delta = series[-1] - series[0]
    pct = (delta / abs(series[0]) * 100) if series[0] else 0
    return ("%s（%d 点）\n%s\n最低 %s · 最高 %s · 均值 %s · 首尾 %s（%+.1f%%）"
            % (name, len(series), line, _fmt(lo), _fmt(hi),
               _fmt(sum(series) / len(series)), trend, pct))
def _fmt(v):
    if abs(v) >= 1000:
        return "%.0f" % v
    if abs(v) >= 10:
        return "%.1f" % v
    return "%.3g" % v
TOOLS = {
    "spark_plot": (spark_plot, {"path": "str", "column": "str", "rows": "int", "mode": "str"},
                   "把 CSV 某一列画成字符趋势图（spark 折线 / bar 柱状），带首尾变化"),
}
