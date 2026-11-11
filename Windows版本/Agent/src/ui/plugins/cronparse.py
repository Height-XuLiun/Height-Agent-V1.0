import datetime as dt
FIELDS = (("分", 0, 59), ("时", 0, 23), ("日", 1, 31), ("月", 1, 12), ("周", 0, 7))
NAMES = {"SUN": 0, "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6}
MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
          "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
def _num(tok, table):
    t = tok.strip().upper()
    if t in table:
        return table[t]
    return int(t)
def _field(expr, lo, hi, table=None):
    table = table or {}
    out = set()
    for part in expr.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            step = int(s)
        if part in ("*", "?"):
            a, b = lo, hi
        elif "-" in part:
            x, y = part.split("-", 1)
            a, b = _num(x, table), _num(y, table)
        else:
            a = _num(part, table)
            b = hi if step > 1 else a
        if a < lo or b > hi or a > b:
            raise ValueError("超出范围 %s-%s：%s" % (lo, hi, part))
        out.update(range(a, b + 1, step))
    return out
def _parse(expr):
    parts = str(expr or "").split()
    if len(parts) == 6:
        parts = parts[1:]
    if len(parts) == 5:
        pass
    elif len(parts) == 4:
        parts = ["0"] + parts
    else:
        raise ValueError("要 5 段：分 时 日 月 周")
    mins = _field(parts[0], 0, 59)
    hours = _field(parts[1], 0, 23)
    dom = _field(parts[2], 1, 31)
    mon = _field(parts[3], 1, 12, MONTHS)
    dow = _field(parts[4].replace("7", "0") if parts[4].strip() == "7" else parts[4],
                 0, 6, NAMES)
    return parts, mins, hours, dom, mon, dow
WEEK = {"0": "周日", "1": "周一", "2": "周二", "3": "周三",
        "4": "周四", "5": "周五", "6": "周六", "7": "周日"}
def _explain_field(expr, lo, hi, label):
    e = expr.strip()
    if label == "周":
        return "周：%s" % _week_words(e)
    if e in ("*", "?"):
        return "%s：每个" % label
    if e.startswith("*/"):
        return "%s：每 %s %s" % (label, e[2:], {"分": "分钟", "时": "小时"}.get(label, "个"))
    if "/" in e:
        a, s = e.split("/", 1)
        if "-" in a:
            x, y = a.split("-", 1)
            return "%s：%s 到 %s 之间每 %s" % (label, x, y, s)
        return "%s：从 %s 开始每 %s" % (label, a, s)
    if "," in e:
        return "%s：%s" % (label, "、".join(x.strip() for x in e.split(",")))
    if "-" in e:
        x, y = e.split("-", 1)
        return "%s：%s 到 %s" % (label, x, y)
    return "%s：%s" % (label, e)
def _week_words(e):
    e = e.strip()
    if e in ("*", "?"):
        return "每天"
    if e.startswith("*/"):
        return "每 %s 天" % e[2:]
    if "," in e:
        return "、".join(WEEK.get(x.strip(), x.strip()) for x in e.split(","))
    if "-" in e:
        x, y = e.split("-", 1)
        return "%s到%s" % (WEEK.get(x.strip(), x), WEEK.get(y.strip(), y))
    return WEEK.get(e, e)
def cron_explain(expr, count=5):
    try:
        parts, mins, hours, dom, mon, dow = _parse(expr)
    except Exception as e:
        return "这句 cron 看不懂：%s" % e
    lines = ["表达式：%s" % " ".join(parts)]
    for i, (label, lo, hi) in enumerate(FIELDS):
        lines.append("  " + _explain_field(parts[i], lo, hi, label))
    per_day = len(mins) * len(hours)
    if len(dom) < 31 or len(mon) < 12 or len(dow) < 7:
        lines.append("触发条件里带了日期限制，不是每天固定次数")
    else:
        lines.append("每天约 %d 次（约每 %.0f 分钟一次）"
                     % (per_day, 1440.0 / per_day) if per_day else "每天约 0 次")
    nxt = _next(expr, max(1, min(20, int(count or 5))))
    if nxt:
        lines.append("接下来 %d 次：" % len(nxt))
        lines.extend("  " + t for t in nxt)
    else:
        lines.append("未来两年内不会触发（日期组合可能永远不成立）")
    return "\n".join(lines)
def _next(expr, n):
    try:
        parts, mins, hours, dom, mon, dow = _parse(expr)
    except Exception:
        return []
    dom_any = parts[2].strip() in ("*", "?")
    dow_any = parts[4].strip() in ("*", "?")
    t = dt.datetime.now().replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
    out = []
    limit = t + dt.timedelta(days=730)
    while t < limit and len(out) < n:
        if t.month not in mon:
            t = (t.replace(day=1) + dt.timedelta(days=32)).replace(
                day=1, hour=0, minute=0)
            continue
        if (t.day not in dom and not dom_any) or \
                (not dow_any and (t.weekday() + 1) % 7 not in dow):
            t = (t + dt.timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if t.hour not in hours:
            t = (t + dt.timedelta(hours=1)).replace(minute=0)
            continue
        if t.minute not in mins:
            t += dt.timedelta(minutes=1)
            continue
        out.append(t.strftime("%Y-%m-%d %H:%M 周") + "一二三四五六日"[t.weekday()])
        t += dt.timedelta(minutes=1)
    return out
TOOLS = {
    "cron_explain": (cron_explain, {"expr": "str", "count": "int"},
                     "解释 cron 表达式，并算出接下来几次触发时间"),
}
