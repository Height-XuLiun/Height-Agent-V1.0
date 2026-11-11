import secrets
import string
import uuid
WORDS = ("amber", "basil", "cobalt", "dune", "ember", "fjord", "glade", "hazel",
         "ivory", "jade", "kelp", "lumen", "maple", "nimbus", "onyx", "pearl",
         "quartz", "reef", "slate", "tundra", "umber", "verdant", "willow", "zephyr")
SAFE = string.ascii_lowercase + string.digits
def uuid_gen(count=1, style="uuid4"):
    n = max(1, min(50, int(count or 1)))
    s = str(style or "uuid4").strip().lower()
    out = []
    for _ in range(n):
        if s in ("uuid1", "v1"):
            out.append(str(uuid.uuid1()))
        elif s in ("hex", "32"):
            out.append(uuid.uuid4().hex)
        elif s in ("short", "id"):
            out.append("".join(secrets.choice(SAFE) for _ in range(12)))
        elif s in ("slug", "word"):
            out.append("%s-%s-%d" % (secrets.choice(WORDS), secrets.choice(WORDS),
                                     secrets.randbelow(900) + 100))
        else:
            out.append(str(uuid.uuid4()))
    return "\n".join(out)
def password_gen(length=20, symbols=True, count=1):
    n = max(4, min(128, int(length or 20)))
    k = max(1, min(20, int(count or 1)))
    pool = string.ascii_letters + string.digits
    if symbols:
        pool += "!@#$%^&*-_=+"
    out = []
    for _ in range(k):
        while True:
            p = "".join(secrets.choice(pool) for _ in range(n))
            if (any(c.islower() for c in p) and any(c.isupper() for c in p)
                    and any(c.isdigit() for c in p)):
                break
        out.append(p)
    strength = "强" if n >= 16 else ("中" if n >= 12 else "弱")
    return "\n".join(out) + "\n（%d 位，强度：%s）" % (n, strength)
def secret_check(text):
    t = str(text or "")
    if not t:
        return "给一段要检查的口令"
    kinds = sum([any(c.islower() for c in t), any(c.isupper() for c in t),
                 any(c.isdigit() for c in t), any(not c.isalnum() for c in t)])
    pool = 0
    if any(c.islower() for c in t):
        pool += 26
    if any(c.isupper() for c in t):
        pool += 26
    if any(c.isdigit() for c in t):
        pool += 10
    if any(not c.isalnum() for c in t):
        pool += 32
    bits = len(t) * (pool.bit_length() - 1) if pool else 0
    weak = ("password", "123456", "qwerty", "admin", "letmein", "abc123")
    notes = ["长度 %d，字符种类 %d 类" % (len(t), kinds)]
    if any(w in t.lower() for w in weak):
        notes.append("含常见弱口令片段，直接换掉")
    if len(set(t)) < max(4, len(t) // 3):
        notes.append("重复字符太多")
    level = "强" if bits >= 100 and len(t) >= 14 else ("中" if bits >= 60 else "弱")
    notes.append("粗略强度：%s" % level)
    return "\n".join(notes)
TOOLS = {
    "uuid_gen": (uuid_gen, {"count": "int", "style": "str"},
                 "生成 UUID 或短 ID（style: uuid4/hex/short/slug）"),
    "password_gen": (password_gen, {"length": "int", "symbols": "bool", "count": "int"},
                     "生成随机密码"),
    "secret_check": (secret_check, {"text": "str"}, "评估一段口令的强度"),
}
