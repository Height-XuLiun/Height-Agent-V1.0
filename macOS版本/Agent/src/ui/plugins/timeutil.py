import datetime as dt
import time
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
FIXED = {
    "asia/shanghai": 8, "asia/chongqing": 8, "asia/hong_kong": 8, "asia/macau": 8,
    "asia/taipei": 8, "asia/singapore": 8, "asia/tokyo": 9, "asia/seoul": 9,
    "asia/bangkok": 7, "asia/kolkata": 5.5, "asia/dubai": 4,
    "europe/london": 0, "europe/paris": 1, "europe/berlin": 1, "europe/moscow": 3,
    "america/new_york": -5, "america/chicago": -6, "america/denver": -7,
    "america/los_angeles": -8, "america/sao_paulo": -3,
    "australia/sydney": 10, "pacific/auckland": 12,
}
def _zone(name):
    n = str(name or "").strip()
    if not n:
        return None
    if n.upper() in ("UTC", "GMT", "Z"):
        return dt.timezone.utc
    try:
        off = float(n)
        return dt.timezone(dt.timedelta(hours=off))
    except Exception:
        pass
    if ZoneInfo is not None:
        try:
            return ZoneInfo(n)
        except Exception:
            pass
    off = FIXED.get(n.lower().replace(" ", "_"))
    if off is not None:
        return dt.timezone(dt.timedelta(hours=off), n)
    return None
def time_now(tz="Asia/Shanghai"):
    name = str(tz or "Asia/Shanghai")
    z = _zone(name) or dt.timezone.utc
    now = dt.datetime.now(z)
    utc = dt.datetime.now(dt.timezone.utc)
    week = "一二三四五六日"[now.weekday()]
    return ("%s（%s）\n星期%s\nUTC：%s\n时间戳：%d\n今年第 %d 天，第 %d 周"
            % (now.strftime("%Y-%m-%d %H:%M:%S"), name,
               week, utc.strftime("%Y-%m-%d %H:%M:%S"),
               int(now.timestamp()), int(now.strftime("%j")),
               int(now.strftime("%W")) + 1))
def time_convert(value, tz="Asia/Shanghai"):
    s = str(value if value is not None else "").strip()
    if not s:
        return time_now(tz)
    src = None
    try:
        src = dt.datetime.fromtimestamp(float(s), dt.timezone.utc)
    except Exception:
        src = None
    if src is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%Y%m%d"):
            try:
                src = dt.datetime.strptime(s, fmt).replace(tzinfo=dt.timezone.utc)
                break
            except Exception:
                continue
    if src is None:
        try:
            src = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            if src.tzinfo is None:
                src = src.replace(tzinfo=dt.timezone.utc)
        except Exception:
            return "看不懂这个时间：%s（给时间戳或 2024-01-01 08:00 这种写法）" % s
    lines = ["原值：" + s, "UTC：" + src.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
             "时间戳：%d" % int(src.timestamp())]
    for name in (tz, "UTC", "Asia/Shanghai", "America/New_York", "Europe/London"):
        z = _zone(name)
        if z is None:
            continue
        t = src.astimezone(z)
        line = "%-18s %s" % (str(name), t.strftime("%Y-%m-%d %H:%M:%S"))
        if line not in lines:
            lines.append(line)
    return "\n".join(dict.fromkeys(lines))
def time_diff(start, end=""):
    a = _parse(start)
    b = _parse(end) if str(end or "").strip() else dt.datetime.now(dt.timezone.utc)
    if a is None or b is None:
        return "看不懂这两个时间，给时间戳或 2024-01-01 08:00"
    d = abs((b - a).total_seconds())
    sign = "之前" if b >= a else "之后"
    parts = []
    for unit, sec in (("天", 86400), ("小时", 3600), ("分", 60)):
        if d >= sec:
            n = int(d // sec)
            parts.append("%d %s" % (n, unit))
            d -= n * sec
    parts.append("%d 秒" % int(d))
    return "%s %s %s（共 %d 秒）" % (start, sign, " ".join(parts), int(abs((b - a).total_seconds())))
def _parse(s):
    txt = str(s or "").strip()
    if not txt:
        return None
    try:
        return dt.datetime.fromtimestamp(float(txt), dt.timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(txt, fmt).replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue
    try:
        t = dt.datetime.fromisoformat(txt.replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None
TOOLS = {
    "time_now": (time_now, {"tz": "str"}, "现在几点，几个主要时区一起给"),
    "time_convert": (time_convert, {"value": "str", "tz": "str"},
                     "把时间戳或日期换成各时区时间"),
    "time_diff": (time_diff, {"start": "str", "end": "str"},
                  "算两个时间差多久，不填 end 就按现在算"),
}
