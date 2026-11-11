import csv
import io
import os
import sqlite3
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
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
def _table(rows, limit):
    if not rows:
        return "(0 行)"
    w = []
    for r in rows[:limit + 1]:
        for i, c in enumerate(r):
            while len(w) <= i:
                w.append(0)
            w[i] = max(w[i], min(28, len(str(c))))
    out = []
    for n, r in enumerate(rows[:limit]):
        cells = []
        for i, c in enumerate(r):
            s = str(c)
            if len(s) > 28:
                s = s[:27] + "…"
            cells.append(s.ljust(w[i]) if i < len(w) else s)
        out.append(" | ".join(cells).rstrip())
        if n == 0:
            out.append("-+-".join("-" * x for x in w))
    if len(rows) > limit:
        out.append("…（共 %d 行，只显示前 %d 行）" % (len(rows), limit))
    return "\n".join(out)
def csv_sql(path: str, sql: str = "", limit: int = 50) -> str:
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return "文件不存在：%s" % path
    text = _read_text(p)
    if not text.strip():
        return "空文件"
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except Exception:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        return "空文件"
    head, body = rows[0], rows[1:]
    cols, used = [], {}
    for i, h in enumerate(head):
        name = (h or "").strip() or "c%d" % i
        name = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in name)
        if name[0].isdigit():
            name = "c_" + name
        if name.lower() in used:
            used[name.lower()] += 1
            name = "%s_%d" % (name, used[name.lower()])
        else:
            used[name.lower()] = 0
        cols.append(name)
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE t (%s)" % ", ".join('"%s" TEXT' % c for c in cols))
    width = len(cols)
    db.executemany("INSERT INTO t VALUES (%s)" % ",".join("?" * width),
                   [(r + [""] * width)[:width] for r in body])
    db.commit()
    if not sql.strip():
        preview = _table([cols] + body[:min(10, limit)], limit)
        return ("表 t：%d 行 × %d 列\n列名：%s\n\n前几行：\n%s\n\n"
                "用法：csv_sql(path, \"SELECT 列, COUNT(*) FROM t GROUP BY 1\")"
                % (len(body), width, ", ".join(cols), preview))
    q = sql.strip().rstrip(";").strip()
    low = q.lower()
    if not (low.startswith("select") or low.startswith("with")):
        return "只允许 SELECT / WITH 查询，不做写入。"
    if ";" in q:
        return "一次只能跑一条语句。"
    try:
        cur = db.execute(q)
        data = cur.fetchall()
    except Exception as e:
        return "SQL 出错：%s\n可用列：%s" % (e, ", ".join(cols))
    if not data:
        return "查询没有结果（0 行）"
    head2 = [d[0] for d in cur.description] if cur.description else []
    return "%d 行\n%s" % (len(data), _table([head2] + [list(r) for r in data], max(1, int(limit))))
TOOLS = {
    "csv_sql": (csv_sql, {"path": "str", "sql": "str", "limit": "int"},
                "把 CSV 当表用 SQL 查（只读 SELECT/WITH），不用写脚本"),
}
