import base64
import binascii
import html
import urllib.parse
SCHEMES = ("base64", "base64url", "url", "hex", "html", "unicode", "utf8hex")
def _need(scheme):
    s = str(scheme or "base64").strip().lower().replace("-", "").replace("_", "")
    alias = {"b64": "base64", "base64url": "base64url", "urlencode": "url",
             "percent": "url", "urlcode": "url", "entity": "html", "entities": "html",
             "u": "unicode", "utf8": "utf8hex"}
    s = alias.get(s, s)
    if s not in SCHEMES:
        return None
    return s
def encode_text(text, scheme="base64"):
    s = _need(scheme)
    if s is None:
        return "只支持 %s" % "、".join(SCHEMES)
    raw = str(text or "").encode("utf-8")
    if s == "base64":
        return base64.b64encode(raw).decode("ascii")
    if s == "base64url":
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    if s == "url":
        return urllib.parse.quote(str(text or ""), safe="")
    if s == "hex":
        return binascii.hexlify(raw).decode("ascii")
    if s == "utf8hex":
        return "".join("\\x%02x" % b for b in raw)
    if s == "html":
        return html.escape(str(text or ""), quote=True)
    if s == "unicode":
        return "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in str(text or ""))
    return "不支持"
def decode_text(text, scheme="base64"):
    s = _need(scheme)
    if s is None:
        return "只支持 %s" % "、".join(SCHEMES)
    t = str(text or "").strip()
    try:
        if s == "base64":
            pad = "=" * (-len(t) % 4)
            return base64.b64decode(t + pad, validate=False).decode("utf-8", "replace")
        if s == "base64url":
            pad = "=" * (-len(t) % 4)
            return base64.urlsafe_b64decode(t + pad).decode("utf-8", "replace")
        if s == "url":
            return urllib.parse.unquote(t)
        if s == "hex":
            return binascii.unhexlify("".join(t.split())).decode("utf-8", "replace")
        if s == "utf8hex":
            body = t.replace("\\x", " ").replace("0x", " ").split()
            return bytes(int(b, 16) for b in body).decode("utf-8", "replace")
        if s == "html":
            return html.unescape(t)
        if s == "unicode":
            return t.encode("utf-8").decode("unicode_escape")
    except Exception as e:
        return "解码失败：%s: %s" % (type(e).__name__, str(e)[:120])
    return "不支持"
def text_inspect(text):
    t = str(text or "")
    raw = t.encode("utf-8")
    cjk = sum(1 for c in t if "\u4e00" <= c <= "\u9fff")
    lines = ["字符 %d 个，UTF-8 占 %d 字节" % (len(t), len(raw))]
    if cjk:
        lines.append("其中汉字 %d 个" % cjk)
    odd = []
    for c in t:
        if c in ("\u200b", "\u200c", "\u200d", "\ufeff", "\u00a0", "\u3000"):
            odd.append("U+%04X" % ord(c))
    if odd:
        lines.append("发现不可见字符：%s（%d 处，容易导致比对失败）"
                     % ("、".join(sorted(set(odd))), len(odd)))
    if t != t.strip():
        lines.append("首尾有空白，共 %d 个字符" % (len(t) - len(t.strip())))
    if any(ord(c) > 127 for c in t):
        lines.append("UTF-8 十六进制：%s" % binascii.hexlify(raw[:64]).decode("ascii"))
    return "\n".join(lines)
TOOLS = {
    "encode_text": (encode_text, {"text": "str", "scheme": "str"},
                    "把文字编码成 base64/url/hex 等"),
    "decode_text": (decode_text, {"text": "str", "scheme": "str"}, "把编码解回文字"),
    "text_inspect": (text_inspect, {"text": "str"}, "看一段文字的真实构成和隐藏字符"),
}
