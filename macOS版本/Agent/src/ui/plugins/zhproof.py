import os
import re
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
TYPOS = {
    "既使": "即使", "按耐": "按捺", "按纳": "按捺", "做为": "作为",
    "必竟": "毕竟", "必竞": "毕竟", "分岐": "分歧", "服贴": "服帖",
    "高梁": "高粱", "各别": "个别", "关怀倍至": "关怀备至", "好高鹜远": "好高骛远",
    "宏扬": "弘扬", "侯车": "候车", "记帐": "记账", "既往不究": "既往不咎",
    "坚苦": "艰苦", "交待": "交代", "金钢": "金刚", "痉孪": "痉挛",
    "就序": "就绪", "困绕": "困扰", "拉笼": "拉拢", "兰色": "蓝色",
    "老俩口": "老两口", "立杆见影": "立竿见影", "罗嗦": "啰嗦", "漫延": "蔓延",
    "冒然": "贸然", "蒙胧": "朦胧", "磨擦": "摩擦", "内咎": "内疚",
    "年令": "年龄", "披漏": "披露", "凭添": "平添", "牵就": "迁就",
    "清淅": "清晰", "溶入": "融入", "散慢": "散漫", "神彩": "神采",
    "松驰": "松弛", "随然": "虽然", "坦护": "袒护", "通谍": "通牒",
    "图径": "途径", "无耐": "无奈", "陷井": "陷阱", "消毁": "销毁",
    "欣尉": "欣慰", "严竣": "严峻", "一慨": "一概", "依付": "依附",
    "义愤填鹰": "义愤填膺", "应骋": "应聘", "由奇": "尤其", "原故": "缘故",
    "再所不惜": "在所不惜", "遭塌": "糟蹋", "扎记": "札记", "沾污": "玷污",
    "震憾": "震撼", "中恳": "中肯", "贮立": "伫立", "装璜": "装潢",
    "追朔": "追溯", "坐阵": "坐镇", "做品": "作品", "既使如此": "即便如此",
}
CJK = r"\u4e00-\u9fff"
RE_FULLWIDTH_ASCII = re.compile(r"[\uff01-\uff5e]")
RE_HALF_PUNCT_CN = re.compile(r"(?<=[%s])[,;:?!]" % CJK)
RE_DUP_PUNCT = re.compile(r"([。，、；：！？])\1+")
RE_CJK_LATIN = re.compile(r"(?<=[%s])([A-Za-z0-9])|([A-Za-z0-9])(?=[%s])" % (CJK, CJK))
RE_SPACE_IN_CJK = re.compile(r"(?<=[%s])\s+(?=[%s])" % (CJK, CJK))
RE_ELLIPSIS = re.compile(r"(?<!\.)\.\.\.(?!\.)")
def _read(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    if not p.startswith(os.path.abspath(ROOT)) or not os.path.isfile(p):
        return None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return open(p, encoding=enc).read()
        except Exception:
            continue
    return None
def zh_proof(text="", path="", limit=30):
    if path:
        body = _read(path)
        if body is None:
            return "文件读不到：%s" % path
    else:
        body = str(text or "")
    if not body.strip():
        return "没有内容"
    n = max(3, min(100, int(limit or 30)))
    issues = []
    for wrong, right in TYPOS.items():
        if wrong == right:
            continue
        for m in re.finditer(re.escape(wrong), body):
            line = body.count("\n", 0, m.start()) + 1
            issues.append("第 %d 行：%s → 应该是「%s」" % (line, wrong, right))
            break
    for m in RE_DUP_PUNCT.finditer(body):
        line = body.count("\n", 0, m.start()) + 1
        issues.append("第 %d 行：标点重复「%s」" % (line, m.group(0)))
    for m in RE_HALF_PUNCT_CN.finditer(body):
        line = body.count("\n", 0, m.start()) + 1
        issues.append("第 %d 行：中文后面用了半角标点「%s」，改成全角" % (line, m.group(0)))
        break
    for m in RE_ELLIPSIS.finditer(body):
        line = body.count("\n", 0, m.start()) + 1
        issues.append("第 %d 行：三个点写成「……」（中文省略号是六点）" % line)
        break
    gaps = RE_CJK_LATIN.findall(body)
    if gaps:
        issues.append("中英文紧贴 %d 处，建议中间加空格（例如「用 Python 写」）" % len(gaps))
    spaces = RE_SPACE_IN_CJK.findall(body)
    if spaces:
        issues.append("汉字之间有 %d 处多余空格" % len(spaces))
    lines = body.splitlines()
    longl = [i + 1 for i, l in enumerate(lines) if len(l) > 120]
    if longl:
        issues.append("%d 行超过 120 字（第 %s 行起），读起来累"
                      % (len(longl), "、".join(str(x) for x in longl[:5])))
    head = "%d 字，%d 行" % (len(body), len(lines))
    if not issues:
        return head + "\n没发现明显问题"
    return "%s\n发现 %d 处：\n" % (head, len(issues)) + "\n".join(
        "  - " + x for x in issues[:n])
def zh_width(text=""):
    t = str(text or "")
    if not t.strip():
        return "没有内容"
    full = RE_FULLWIDTH_ASCII.findall(t)
    paren = (t.count("（"), t.count("("))
    quote = (t.count("“"), t.count('"'))
    return "\n".join([
        "全角字符 %d 个（１２３ＡＢＣ（）这种）" % len(full),
        "括号：全角 %d 个，半角 %d 个%s" % (
            paren[0], paren[1], "，混用了" if paren[0] and paren[1] else ""),
        "引号：中文引号 %d 个，直引号 %d 个%s" % (
            quote[0], quote[1], "，混用了" if quote[0] and quote[1] else ""),
        "建议：正文用全角括号和中文引号，代码和英文里用半角。",
    ])
TOOLS = {
    "zh_proof": (zh_proof, {"text": "str", "path": "str", "limit": "int"},
                 "中文校对：错别字、标点、中英混排"),
    "zh_width": (zh_width, {"text": "str"}, "检查全角半角混用"),
}
