import hashlib
import os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
ALGS = ("md5", "sha1", "sha256", "sha512")
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def hash_file(path, alg="sha256"):
    p = _safe(path)
    if not p:
        return "路径越界，拒绝执行"
    if not os.path.isfile(p):
        return "文件不存在：%s" % path
    a = str(alg or "sha256").lower()
    if a not in ALGS:
        return "只支持 %s" % "、".join(ALGS)
    h = hashlib.new(a)
    size = 0
    try:
        with open(p, "rb") as f:
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                size += len(b)
                h.update(b)
    except Exception as e:
        return "读取失败：%s" % e
    return "%s\n%s\n%s 字节" % (a.upper(), h.hexdigest(), size)
def hash_text(text, alg="sha256"):
    a = str(alg or "sha256").lower()
    if a not in ALGS:
        return "只支持 %s" % "、".join(ALGS)
    h = hashlib.new(a)
    h.update(str(text or "").encode("utf-8"))
    return "%s\n%s" % (a.upper(), h.hexdigest())
def hash_compare(path, expect):
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return "文件不存在：%s" % path
    want = str(expect or "").strip().lower()
    if not want:
        return "给一个要核对的校验值"
    for a in ALGS:
        if len(want) == hashlib.new(a).digest_size * 2:
            got = hashlib.new(a)
            with open(p, "rb") as f:
                for b in iter(lambda: f.read(1 << 20), b""):
                    got.update(b)
            same = got.hexdigest() == want
            if same:
                return "%s 一致" % a.upper()
            return "%s 对不上\n实际：%s\n期望：%s" % (a.upper(), got.hexdigest(), want)
    return "校验值长度不像 md5/sha1/sha256/sha512"
TOOLS = {
    "hash_file": (hash_file, {"path": "str", "alg": "str"}, "算文件的校验值"),
    "hash_text": (hash_text, {"text": "str", "alg": "str"}, "算一段文字的校验值"),
    "hash_compare": (hash_compare, {"path": "str", "expect": "str"},
                     "拿校验值核对文件有没有下错"),
}
