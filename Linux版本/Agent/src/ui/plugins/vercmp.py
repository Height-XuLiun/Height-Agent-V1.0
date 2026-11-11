import re
VER = re.compile(r"^[vV]?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-+]?([0-9A-Za-z.\-]+))?$")
PRE_RANK = {"dev": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2, "rc": 3,
            "pre": 3, "preview": 3, "snapshot": 0}
def _parse(v):
    s = str(v or "").strip()
    m = VER.match(s)
    if not m:
        return None
    major, minor, patch, tail = m.groups()
    pre = 9
    tail = (tail or "").strip()
    if tail:
        low = tail.lower()
        for k, r in PRE_RANK.items():
            if low.startswith(k):
                pre = r
                break
        else:
            pre = 8
    return (int(major), int(minor or 0), int(patch or 0), pre, tail)
def ver_compare(a, b=""):
    pa = _parse(a)
    if pa is None:
        return "看不懂这个版本号：%s" % a
    if not str(b or "").strip():
        return "版本：%s.%s.%s%s" % (pa[0], pa[1], pa[2],
                                     ("-" + pa[4]) if pa[4] else "")
    pb = _parse(b)
    if pb is None:
        return "看不懂这个版本号：%s" % b
    ka, kb = pa[:4], pb[:4]
    if ka == kb:
        rel = "相同"
    elif ka > kb:
        rel = "%s 更新（高 %d 个主版本，%d 个次版本）" % (
            a, pa[0] - pb[0], pa[1] - pb[1])
    else:
        rel = "%s 更新（高 %d 个主版本，%d 个次版本）" % (
            b, pb[0] - pa[0], pb[1] - pa[1])
    risk = ""
    if pa[0] != pb[0]:
        risk = "主版本不同，八成有不兼容改动"
    elif pa[1] != pb[1]:
        risk = "次版本不同，新增功能，一般向后兼容"
    elif pa[2] != pb[2]:
        risk = "补丁版本不同，只有修复"
    return "a=%s  b=%s\n%s\n%s" % (a, b, rel, risk or "同一版本线")
def ver_sort(list_text):
    items = [x.strip() for x in re.split(r"[,\s]+", str(list_text or "")) if x.strip()]
    if not items:
        return "给几个版本号，用逗号或空格隔开"
    good, bad = [], []
    for x in items:
        p = _parse(x)
        (good if p else bad).append((p, x) if p else x)
    good.sort(key=lambda t: t[0])
    out = ["从小到大："]
    out.extend("  " + x for _, x in good)
    if bad:
        out.append("看不懂的：%s" % "、".join(bad))
    return "\n".join(out)
def ver_bump(v, part="patch"):
    p = _parse(v)
    if p is None:
        return "看不懂这个版本号：%s" % v
    major, minor, patch = p[0], p[1], p[2]
    k = str(part or "patch").lower()
    if k in ("major", "主"):
        return "%d.0.0" % (major + 1)
    if k in ("minor", "次"):
        return "%d.%d.0" % (major, minor + 1)
    if k in ("patch", "修", "修订"):
        return "%d.%d.%d" % (major, minor, patch + 1)
    return "part 只能是 major / minor / patch"
TOOLS = {
    "ver_compare": (ver_compare, {"a": "str", "b": "str"}, "比较两个版本号，提示兼容风险"),
    "ver_sort": (ver_sort, {"list_text": "str"}, "把一堆版本号排序"),
    "ver_bump": (ver_bump, {"v": "str", "part": "str"}, "按 major/minor/patch 递增版本"),
}
