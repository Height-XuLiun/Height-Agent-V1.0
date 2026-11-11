import hashlib
import json
import math
import re
import threading
import time
import unicodedata
from collections import Counter, defaultdict
VERSION = "s2v1"
_HARD = frozenset("""
a an the of to in on at for with and or but is are was were be been being am
this that these those it its as by from into about what which who whom how why
when where can could would should shall may might will do does did done i you he
she we they my your our their me him her them us mine yours ours theirs
please help show tell find search query look up just also very really ok okay
yes no not nor so than then there here now only same other another any all some
的 了 是 在 和 与 及 或 也 就 都 而 且 但 把 被 给 从 到 对 为 以 于 之 其 这 那
此 该 各 每 有 无 不 没 很 更 最 请 帮 我 你 他 她 它 我们 你们 他们 什么 怎么
为什么 哪些 如何 可以 能否 一下 查 查询 搜索 找 看看 告诉 关于 请问 谢谢 以及
还有 等等 这个 那个 这些 那些 吗 呢 啊 吧 呀 哦 嗯 着 过 得 地 并 则 若 如 使
让 由 将 已 未 再 又 还 只 才 均 亦 即 者 等 中 内 外 上 下 前 后 时 个 些 条
种 类 项 次 一个 一下 是不是 有没有 多少 几 哪 谁 何处 何时 咋 啥 呗 嘛 咯
""".split())
_SOFT = frozenset("""
latest news info information about guide tutorial best top review overview
introduction detail details details introduction general current today now
最新 消息 资料 信息 介绍 相关 情况 内容 说明 简单 详细 全面 一下 现在 目前 今天
近日 网上 网络 网络上的 报道 文章 帖子 内容 东西 问题 答案 结果 方法 方式
""".split())
_PRIVATE = re.compile(
    r"余额|配额|订单|账单|账号|账户|密码|私钥|我的(?:资料|信息|记录|文件)|"
    r"balance|quota|my account|order history|password|api.?key", re.I)
_INTENTS = (
    ("private", re.compile(r"余额|配额|订单|账单|账号|密码|balance|quota|invoice", re.I)),
    ("version", re.compile(r"版本|更新日志| changelog|release notes|latest version|"
                           r"\bv?\d+(?:\.\d+){1,3}\b|升级|新版", re.I)),
    ("price", re.compile(r"价格|多少钱|定价|收费|报价|pricing|\bprice\b|\bcost\b", re.I)),
    ("doc", re.compile(r"文档|接口|参数|用法|怎么调用|sdk|\bapi\b|reference|"
                       r"official docs|documentation", re.I)),
    ("news", re.compile(r"新闻|发布|官宣|最近|刚刚|公告|announce|released|news", re.I)),
    ("compare", re.compile(r"对比|区别|哪个好|差异|versus|\bvs\b|compare|difference", re.I)),
    ("howto", re.compile(r"怎么|如何|步骤|教程|how to|how do i|steps", re.I)),
    ("nav", re.compile(r"官网|入口|网址|链接|下载地址|official site|homepage", re.I)),
    ("code", re.compile(r"报错|异常|代码|bug|error|exception|stack trace", re.I)),
    ("fact", re.compile(r"是什么|是谁|定义|原理|谁发明|what is|who is|define", re.I)),
)
_ENT_PATTERNS = (
    ("url", re.compile(r"https?://[^\s<>\"']+", re.I), 2.4),
    ("domain", re.compile(r"\b(?:[a-z0-9-]+\.)+(?:com|cn|net|org|io|ai|dev|app|edu|gov|"
                          r"xyz|top|tech|cloud|site|online|co)\b(?:/[^\s]*)?", re.I), 2.2),
    ("version", re.compile(r"\b[a-z]{0,4}[- ]?v?\d+(?:\.\d+){1,4}(?:[-.][a-z0-9]+)*\b", re.I), 2.4),
    ("date", re.compile(r"\b(?:19|20)\d{2}(?:[-/年.]\d{1,2})?(?:[-/月.]\d{1,2})?日?\b"), 1.9),
    ("acronym", re.compile(r"\b[A-Z][A-Z0-9]{1,9}(?:-[A-Z0-9]+)*\b"), 2.0),
    ("product", re.compile(r"\b[A-Z][a-zA-Z0-9]*(?:[- ][A-Z][a-zA-Z0-9]*)+"
                           r"(?:[- ]\d+(?:\.\d+)?)?\b"), 2.2),
    ("quoted", re.compile("《[^》]{1,40}》|「[^」]{1,40}」|\"[^\"]{2,40}\"|'[^']{2,40}'"), 1.8),
    ("org", re.compile(r"[\u4e00-\u9fff]{2,10}(?:公司|大学|学院|研究院|实验室|"
                       r"集团|组织|委员会|平台|系统|模型|协议|算法|框架)"), 1.7),
    ("camel", re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b"), 1.6),
    ("brand", re.compile(r"\b[A-Z][a-zA-Z0-9]{2,}\b"), 1.8),
)
_INJECT = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above) instructions|"
    r"disregard (?:the |all )?(?:system|previous)|"
    r"you are now (?:a|an|the)|system\s*[:=]|assistant\s*[:=]|"
    r"忽略(?:以上|前面|之前|所有)(?:的)?(?:指令|提示|要求)|"
    r"你现在是|请把(?:系统|提示词)|越狱|开发者模式|dan mode|"
    r"prompt\s*injection|<\|im_start\|>|\[INST\]|###\s*system", re.I)
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\ufeff]")
_WORD = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*|[\u4e00-\u9fff]+")
_HAN = re.compile(r"[\u4e00-\u9fff]")
_HAN_RUN = re.compile(r"[\u4e00-\u9fff]+")
_HAN_FUNC = frozenset(w for w in _HARD if len(w) == 1 and _HAN.match(w))
_BRAND_STOP = frozenset(("the and for with from this that what which when where how why "
                         "are was were will can could would should please help show tell "
                         "best top latest news guide about into your our their more most "
                         "some any all new old use used using get lets let now here there "
                         "official documentation release version price review compare")
                        .split())
def normalize(text):
    s = unicodedata.normalize("NFKC", str(text or ""))
    s = _CTRL.sub(" ", s)
    s = s.lower()
    s = s.replace("＃", "#").replace("％", "%")
    s = re.sub(r"[“”‘’]", '"', s)
    s = re.sub(r"[，、；：！？（）【】]", " ", s)
    s = re.sub(r"[^\w\u4e00-\u9fff./:+-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()
def stop_level(term):
    t = str(term or "").lower().strip()
    if not t:
        return "hard"
    if t in _HARD:
        return "hard"
    if t in _SOFT:
        return "soft"
    if len(t) == 1 and not t.isdigit() and not _HAN.match(t):
        return "hard"
    return ""
def stopped_units(raw):
    s = normalize(raw)
    n = 0
    for m in re.finditer(r"[a-z0-9]+(?:[._-][a-z0-9]+)*|[\u4e00-\u9fff]+", s):
        w = m.group(0)
        if _HAN.match(w):
            i = 0
            while i < len(w):
                hit = 0
                for L in (4, 3, 2, 1):
                    if i + L <= len(w) and stop_level(w[i:i + L]) in ("hard", "soft"):
                        hit = L
                        break
                if hit:
                    n += hit
                    i += hit
                else:
                    i += 1
        elif stop_level(w) in ("hard", "soft"):
            n += len(w)
    return n
def tokenize(text):
    s = normalize(text)
    out = []
    for m in _WORD.finditer(s):
        w = m.group(0).strip(".-_")
        if not w:
            continue
        if _HAN.match(w):
            if len(w) > 1 and stopped_units(w) >= len(w) * 0.6:
                continue
            base = m.start()
            for n in (2, 3):
                for i in range(len(w) - n + 1):
                    bg = w[i:i + n]
                    if stop_level(bg) != "":
                        continue
                    if bg[0] in _HAN_FUNC and bg[-1] in _HAN_FUNC:
                        continue
                    if n == 3 and any(stop_level(bg[j:j + 2]) != ""
                                      for j in range(2)):
                        continue
                    out.append((bg, base + i))
            continue
        out.append((w.lower(), m.start()))
        if re.fullmatch(r"[a-z0-9]+[._-][a-z0-9]+", w) and len(w) > 3:
            for part in re.split(r"[._-]", w):
                if len(part) > 1:
                    out.append((part.lower(), m.start()))
    seen = set()
    uniq = []
    for w, p in out:
        if w not in seen:
            seen.add(w)
            uniq.append((w, p))
    return uniq
class Entity:
    __slots__ = ("kind", "text", "weight", "span")
    def __init__(self, kind, text, weight, span):
        self.kind, self.text, self.weight, self.span = kind, text, weight, span
    def as_dict(self):
        return {"kind": self.kind, "text": self.text, "weight": self.weight,
                "span": list(self.span)}
def extract_entities(text):
    s = str(text or "")
    found, taken = [], []
    for kind, pat, base in _ENT_PATTERNS:
        for m in pat.finditer(s):
            a, b = m.span()
            val = m.group(0).strip()
            if not val or len(val) > 120:
                continue
            if any(a < eb and b > ea for ea, eb in taken):
                continue
            low = val.lower()
            if stop_level(low) == "hard" or low in _SOFT:
                continue
            if kind == "brand" and (low in _BRAND_STOP or val.isupper()):
                continue
            taken.append((a, b))
            w = base
            if kind in ("version", "date", "domain", "url"):
                w += 0.3
            found.append(Entity(kind, val, round(min(w, 3.0), 2), (a, b)))
    found.sort(key=lambda e: (-e.weight, e.span[0]))
    out, seen = [], set()
    for e in found:
        k = e.text.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out[:12]
def classify_intent(text, goal=""):
    s = str(text or "") + " " + str(goal or "")
    for name, pat in _INTENTS:
        if pat.search(s):
            return name
    return "general"
def admit(query, goal=""):
    q = str(query or "").strip()
    if not q:
        return False, "empty", ""
    if len(q) > 200:
        return False, "too-long", ""
    if _INJECT.search(q):
        return False, "injection", ""
    if _CTRL.search(q):
        q = _CTRL.sub(" ", q).strip()
    if not re.search(r"[\w\u4e00-\u9fff]", q):
        return False, "no-alnum", ""
    if re.fullmatch(r"(.)\1{3,}", q):
        return False, "repeated-char", ""
    terms = [w for w, _ in tokenize(q)]
    hard = [w for w in terms if stop_level(w) != "hard"]
    if not hard:
        norm = normalize(q)
        if len(norm) >= 2 and any(w in norm for w in _SOFT if len(w) >= 2):
            return True, "low-information", q
        return False, "all-stopwords", ""
    if len(q) < 2:
        return False, "too-short", ""
    if classify_intent(q, goal) == "private" and not extract_entities(q):
        return False, "private-data", ""
    return True, "ok", q
class QueryPlan:
    __slots__ = ("raw", "intent", "entities", "terms", "exact", "lexical",
                 "semantic", "weights", "variants", "phrase", "dilution", "notes")
    def __init__(self):
        self.raw = ""
        self.intent = "general"
        self.entities = []
        self.terms = []
        self.exact = []
        self.lexical = []
        self.semantic = ""
        self.weights = {}
        self.variants = []
        self.phrase = ""
        self.dilution = 0.0
        self.notes = []
    def as_dict(self):
        return {"raw": self.raw, "intent": self.intent,
                "entities": [e.as_dict() for e in self.entities],
                "exact": self.exact, "lexical": self.lexical,
                "semantic": self.semantic, "variants": self.variants,
                "phrase": self.phrase, "dilution": round(self.dilution, 3),
                "notes": self.notes}
_INTENT_BOOST = {
    "version": ("changelog", "release"), "doc": ("documentation", "reference"),
    "price": ("pricing",), "news": ("announcement",), "compare": ("versus",),
    "howto": ("guide",), "nav": ("official site",), "code": ("fix",),
}
def rewrite(query, goal="", history=None, allow_variants=False):
    p = QueryPlan()
    p.raw = str(query or "").strip()
    p.intent = classify_intent(p.raw, goal)
    p.entities = extract_entities(p.raw)
    toks = tokenize(p.raw)
    kept, dropped = [], 0
    for w, pos in toks:
        lv = stop_level(w)
        if lv == "hard":
            dropped += 1
            continue
        if lv == "soft":
            if len(kept) >= 1 or any(e.weight >= 2.0 for e in p.entities):
                dropped += 1
                continue
        kept.append((w, pos))
    raw_chars = len(re.findall(r"[\w\u4e00-\u9fff]", normalize(p.raw)))
    p.dilution = round(min(1.0, (stopped_units(p.raw) + dropped)
                           / max(1, raw_chars + len(toks))), 3)
    ent_texts = {e.text.lower() for e in p.entities}
    ent_words = set()
    for e in p.entities:
        for w, _ in tokenize(e.text):
            ent_words.add(w)
    for w, pos in kept:
        is_ent = w in ent_words or w in ent_texts
        base = 1.0
        if is_ent:
            e = next((x for x in p.entities
                      if w in x.text.lower() or w in tokenize_texts(x.text)), None)
            base = (e.weight if e else 1.8)
        if _HAN.match(w) and len(w) <= 3 and base == 1.0:
            base *= 0.72
        channel = "exact" if (is_ent and base >= 1.9) else "lexical"
        p.terms.append((w, round(base, 2), channel, pos))
        p.weights[w] = round(base, 2)
        if channel == "exact":
            p.exact.append(w)
        else:
            p.lexical.append(w)
    if not p.exact and p.entities:
        for e in p.entities[:2]:
            for w, _ in tokenize(e.text)[:2]:
                if w not in p.exact and stop_level(w) == "":
                    p.exact.append(w)
                    p.weights[w] = max(p.weights.get(w, 0), e.weight)
    p.exact = compact_terms(p.exact, 8)
    p.lexical = compact_terms([w for w in p.lexical if w not in p.exact], 10)
    if not p.exact and not p.lexical:
        flat = re.sub(r"\s+", "", normalize(p.raw))
        p.lexical = compact_terms([flat[i:i + 2]
                                   for i in range(max(0, len(flat) - 1))], 4)
        for w in p.lexical:
            p.weights[w] = 0.5
        if p.lexical:
            p.notes.append("low-information-fallback")
    p.semantic = " ".join(p.lexical)
    ordered = sorted(p.terms, key=lambda x: x[3])
    p.phrase = " ".join(ordered_compact(
        [w for w, _, _, _ in ordered], 6))
    p.variants = [p.raw]
    if allow_variants and (p.dilution >= 0.4 or len(p.exact) >= 2):
        core = " ".join(([e.text for e in p.entities[:2]] or p.exact[:3]))
        extra = " ".join(_INTENT_BOOST.get(p.intent, ())[:1])
        v = " ".join(x for x in (core, extra) if x).strip()
        if v and v.lower() != p.raw.lower() and len(v) <= 120:
            p.variants.append(v[:120])
    p.notes.append("intent=" + p.intent)
    p.notes.append("dilution=%.2f" % p.dilution)
    if p.exact:
        p.notes.append("exact-channel=" + ",".join(p.exact[:4]))
    return p
def tokenize_texts(text):
    return [w for w, _ in tokenize(text)]
def compact_terms(words, limit=10):
    ws = list(dict.fromkeys(w for w in words if w))
    out = []
    for w in sorted(ws, key=lambda x: (-len(x), x)):
        if any(w in o for o in out):
            continue
        out.append(w)
        if len(out) >= limit:
            break
    return out
def ordered_compact(words, limit=6):
    ws = list(dict.fromkeys(w for w in words if w))
    out = []
    for w in ws:
        if any(w != o and w in o for o in ws):
            continue
        out.append(w)
        if len(out) >= limit:
            break
    return out
def signature_text(text, entities=None, intent=""):
    norm = normalize(text)
    terms = sorted({w for w, _ in tokenize(norm) if stop_level(w) == ""})
    core = " ".join(terms)
    ent = " ".join(sorted({normalize(e.text if hasattr(e, "text") else str(e))
                           for e in (entities or [])}))
    return VERSION + " " + intent + " " + core + " " + ent
def canonical_signature(text, entities=None, intent=""):
    return hashlib.sha1(signature_text(text, entities, intent)
                        .encode("utf-8")).hexdigest()
def ngrams(text, n=3):
    s = normalize(text)
    s = re.sub(r"\s+", "", s)
    if len(s) < n:
        return [s] if s else []
    return [s[i:i + n] for i in range(len(s) - n + 1)]
def vectorize(text, n=3, weights=None):
    c = Counter()
    for g in ngrams(text, n):
        c[g] += 1.0
    for w, _ in tokenize(text):
        if stop_level(w) == "":
            c["#" + w] += (weights or {}).get(w, 1.0) * 1.5
    norm = math.sqrt(sum(v * v for v in c.values())) or 1.0
    return {k: v / norm for k, v in c.items()}
def cosine(a, b):
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())
def simhash(text, bits=64):
    c = Counter()
    for g in ngrams(text, 3):
        c[g] += 1
    for w, _ in tokenize(text):
        c["w:" + w] += 1
    out = [0] * bits
    for g, w in c.items():
        h = int(hashlib.blake2b(g.encode("utf-8"), digest_size=8).hexdigest(), 16)
        for i in range(bits):
            out[i] += w if (h >> i) & 1 else -w
    v = 0
    for i in range(bits):
        if out[i] > 0:
            v |= 1 << i
    return v
def hamming(a, b):
    return bin(a ^ b).count("1")
class Doc:
    __slots__ = ("rid", "title", "url", "snippet", "domain", "score",
                 "reasons", "trust", "raw")
    def __init__(self, rid, title, url, snippet, raw=""):
        self.rid = str(rid)
        self.title = str(title or "")
        self.url = str(url or "")
        self.snippet = str(snippet or "")
        self.domain = _domain(self.url)
        self.score = 0.0
        self.reasons = []
        self.trust = 0.5
        self.raw = raw
    def text(self):
        return self.title + " " + self.snippet
    def as_dict(self):
        return {"rid": self.rid, "title": self.title, "url": self.url,
                "snippet": self.snippet, "domain": self.domain,
                "score": round(self.score, 4), "trust": round(self.trust, 3),
                "reasons": self.reasons}
def _domain(url):
    m = re.match(r"https?://([^/:?#]+)", str(url or ""), re.I)
    if not m:
        return ""
    d = m.group(1).lower()
    parts = d.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else d
def parse_results(text, limit=24):
    s = str(text or "")
    docs, cur = [], None
    for line in s.splitlines():
        m = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if m:
            if cur:
                docs.append(cur)
            cur = Doc(m.group(1), m.group(2).strip(), "", "")
            continue
        if cur is None:
            continue
        t = line.strip()
        if not t:
            continue
        if t.startswith(("http://", "https://")) and not cur.url:
            cur.url = t.split()[0]
        elif not cur.snippet:
            cur.snippet = t
        if len(docs) >= limit:
            break
    if cur:
        docs.append(cur)
    for d in docs:
        d.domain = _domain(d.url)
    return [d for d in docs if d.title][:limit]
class CorpusStats:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.k1, self.b = k1, b
        self.N = max(1, len(docs))
        self.df = Counter()
        self.avgdl = {"title": 1.0, "snippet": 1.0, "url": 1.0}
        self._toks = []
        for d in docs:
            f = {"title": tokenize(d.title), "snippet": tokenize(d.snippet),
                 "url": tokenize(d.url)}
            self._toks.append(f)
            for key, toks in f.items():
                self.avgdl[key] += len(toks) or 1
                for w in {w for w, _ in toks if stop_level(w) == ""}:
                    self.df[(key, w)] += 1
        for key in self.avgdl:
            self.avgdl[key] = max(1.0, self.avgdl[key] / self.N)
    def idf(self, term, field="snippet"):
        df = self.df.get((field, term), 0)
        v = math.log(1.0 + (self.N - df + 0.5) / (df + 0.5))
        return max(0.12, min(v, 4.0))
_FIELD_W = {"title": 3.0, "snippet": 1.0, "url": 1.3}
def bm25f(plan, doc, ftoks, stats):
    score = 0.0
    qterms = list(dict.fromkeys(plan.exact + plan.lexical))
    if not qterms:
        return 0.0
    qnorm = 1.0 / math.sqrt(len(qterms))
    for term in qterms:
        if stop_level(term) == "hard":
            continue
        w = plan.weights.get(term, 1.0)
        term_score = 0.0
        for field, fw in _FIELD_W.items():
            toks = ftoks.get(field, [])
            tf = sum(1 for t, _ in toks if t == term)
            if not tf:
                continue
            dl = len(toks) or 1
            avg = stats.avgdl.get(field, 1.0)
            denom = tf + stats.k1 * (1 - stats.b + stats.b * dl / avg)
            term_score += fw * (tf * (stats.k1 + 1) / denom) * stats.idf(term, field)
        score += w * qnorm * term_score
    return score
def phrase_boost(plan, doc):
    t = normalize(doc.text())
    boost = 0.0
    if plan.phrase and len(plan.phrase) >= 4 and plan.phrase.lower() in t:
        boost += 1.6
    for e in plan.entities:
        if e.weight >= 2.0 and normalize(e.text) in t:
            boost += 0.55 * e.weight
    return boost
def proximity_boost(plan, doc):
    toks = [w for w, _ in tokenize(doc.text()) if stop_level(w) == ""]
    idx = defaultdict(list)
    for i, w in enumerate(toks):
        idx[w].append(i)
    want = list(dict.fromkeys(plan.exact + plan.lexical))[:6]
    if len(want) < 2:
        return 0.0
    positions = [idx[w][0] for w in want if idx.get(w)]
    if len(positions) < 2:
        return 0.0
    span = max(positions) - min(positions)
    return 0.9 / (1.0 + span / 4.0)
def rrf(rankings, k=60.0):
    out = defaultdict(float)
    for ranking, weight in rankings:
        for rank, rid in enumerate(ranking, 1):
            out[rid] += weight / (k + rank)
    return out
def rank_docs(docs, plan, corpus=None):
    if not docs:
        return [], {}
    stats = corpus or CorpusStats(docs)
    ftoks = []
    for d in docs:
        ftoks.append({"title": tokenize(d.title), "snippet": tokenize(d.snippet),
                      "url": tokenize(d.url)})
    qvec = vectorize(plan.semantic or plan.raw, weights=plan.weights)
    lexical, semantic, exact, reput = [], [], [], []
    detail = {}
    for i, d in enumerate(docs):
        bm = bm25f(plan, d, ftoks[i], stats)
        ph = phrase_boost(plan, d)
        px = proximity_boost(plan, d)
        trust = d.trust if d.trust else 0.5
        base = bm + ph + px
        sem = cosine(qvec, vectorize(d.text(), weights=plan.weights)) * 2.2
        ex = sum(1 for e in plan.entities
                 if e.weight >= 2.0 and normalize(e.text) in normalize(d.text()))
        exact_score = ex * 1.4 + (1.2 if plan.exact and all(
            w in normalize(d.text()) for w in plan.exact[:2]) else 0.0)
        d.score = round(base + 0.45 * sem + exact_score + (trust - 0.5), 4)
        detail[d.rid] = {"bm25f": round(bm, 3), "phrase": round(ph, 3),
                         "proximity": round(px, 3), "semantic": round(sem, 3),
                         "exact": round(exact_score, 3), "trust": trust}
        lexical.append((base, d.rid))
        semantic.append((sem, d.rid))
        exact.append((exact_score, d.rid))
        reput.append((trust, d.rid))
    def order(pairs):
        return [rid for _, rid in sorted(pairs, key=lambda x: -x[0])]
    fused = rrf([(order(lexical), 1.0), (order(semantic), 0.45),
                 (order(exact), 0.75), (order(reput), 0.25)])
    for d in docs:
        d.score = round(d.score * 0.7 + fused.get(d.rid, 0.0) * 12.0, 4)
        detail[d.rid]["rrf"] = round(fused.get(d.rid, 0.0), 5)
    ranked = sorted(docs, key=lambda d: -d.score)
    selected, hashes = [], []
    for d in ranked:
        h = simhash(d.text())
        if any(hamming(h, x) <= 3 for x in hashes):
            d.reasons.append("near-duplicate")
            continue
        lam = 0.72
        vec = vectorize(d.text(), weights=plan.weights)
        red = max((cosine(vec, vectorize(s.text(), weights=plan.weights))
                   for s in selected), default=0.0)
        mmr = lam * (d.score / max(1.0, ranked[0].score)) - (1 - lam) * red
        if selected and red > 0.94:
            d.reasons.append("redundant")
            continue
        d.score = round(mmr, 5)
        hashes.append(h)
        selected.append(d)
    return selected, detail
class ResultCache:
    def __init__(self, ttl=300, capacity=256, near_threshold=24, jac_threshold=0.60):
        self.ttl, self.capacity, self.near = ttl, capacity, near_threshold
        self.jac = jac_threshold
        self.data = {}
        self.buckets = defaultdict(list)
        self.lock = threading.RLock()
        self.hits = Counter()
    def _key(self, plan, query):
        return canonical_signature(query, plan.entities if plan else None,
                                   plan.intent if plan else "")
    def _sig(self, query, plan):
        core = frozenset(w for w, _ in tokenize(normalize(query))
                         if stop_level(w) == "")
        ents = "|".join(sorted({normalize(e.text if hasattr(e, "text") else str(e))
                                for e in (plan.entities if plan else [])}))
        text = signature_text(query, plan.entities if plan else None,
                              plan.intent if plan else "")
        return core, ents, text
    @staticmethod
    def _jac(a, b):
        if not a or not b:
            return 0.0
        return len(a & b) / max(1, len(a | b))
    def _purge(self):
        now = time.time()
        for k in [k for k, v in self.data.items() if now - v[0] > self.ttl]:
            self.data.pop(k, None)
        for b in list(self.buckets):
            self.buckets[b] = [k for k in self.buckets[b] if k in self.data]
            if not self.buckets[b]:
                self.buckets.pop(b, None)
        if len(self.data) > self.capacity:
            for k in sorted(self.data, key=lambda k: self.data[k][0])[
                    :len(self.data) - self.capacity]:
                self.data.pop(k, None)
    def get(self, query, plan=None, payload_key=""):
        with self.lock:
            self._purge()
            k = self._key(plan, query)
            if k in self.data and self.data[k][3] == payload_key:
                self.hits["exact"] += 1
                return "exact", self.data[k][1]
            core, ents, sig = self._sig(query, plan)
            h = simhash(sig)
            cands = []
            for i in range(4):
                cands.extend(self.buckets.get((i, (h >> (i * 16)) & 0xFFFF), []))
            for cand in list(dict.fromkeys(cands)) or list(self.data):
                ent = self.data.get(cand)
                if not ent or ent[3] != payload_key or ent[5] != ents:
                    continue
                if hamming(h, ent[2]) > 18:
                    continue
                if self._jac(core, ent[4]) >= self.jac:
                    self.hits["near"] += 1
                    return "near", ent[1]
            for ent in self.data.values():
                if ent[3] != payload_key or ent[5] != ents:
                    continue
                if self._jac(core, ent[4]) >= self.jac:
                    self.hits["near"] += 1
                    return "near", ent[1]
            self.hits["miss"] += 1
            return "", None
    def put(self, query, payload, plan=None, payload_key=""):
        with self.lock:
            self._purge()
            k = self._key(plan, query)
            core, ents, sig = self._sig(query, plan)
            h = simhash(sig)
            self.data[k] = (time.time(), payload, h, payload_key, core, ents)
            for i in range(4):
                self.buckets[(i, (h >> (i * 16)) & 0xFFFF)].append(k)
            if len(self.data) > self.capacity:
                for old in sorted(self.data, key=lambda x: self.data[x][0])[
                        :len(self.data) - self.capacity]:
                    self.data.pop(old, None)
    def stats(self):
        with self.lock:
            return dict(self.hits, size=len(self.data))
    def clear(self):
        with self.lock:
            self.data.clear()
            self.buckets.clear()
            self.hits.clear()
CACHE = ResultCache()
def stable_prefix_key(system_text, vendor="", model=""):
    blob = VERSION + "|" + str(vendor or "") + "|" + str(model or "") + "|" + system_text
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:24]
def cache_hints(vendor, model, stable_tokens, enabled=True):
    v = str(vendor or "").lower()
    hints = {"prefix_stable": enabled, "min_tokens": 1024,
             "stable_tokens": stable_tokens, "vendor": v}
    if not enabled:
        return hints
    hints["eligible"] = stable_tokens >= 1024
    if "anthropic" in v or "claude" in str(model or "").lower():
        hints["strategy"] = "explicit-breakpoint"
        hints["breakpoint"] = {"type": "ephemeral"}
        hints["place"] = "end-of-stable-system-block"
        hints["lookback_blocks"] = 20
        hints["min_tokens"] = 1024
    elif "deepseek" in v or "deepseek" in str(model or "").lower():
        hints["strategy"] = "auto-common-prefix"
        hints["place"] = "stable-system-prefix"
        hints["usage_fields"] = ["prompt_cache_hit_tokens", "prompt_cache_miss_tokens"]
    elif "openai" in v or str(model or "").lower().startswith("gpt-"):
        hints["strategy"] = "implicit-prefix"
        hints["place"] = "stable-developer-prefix"
        hints["prompt_cache_key"] = True
        hints["min_tokens"] = 1024
    else:
        hints["strategy"] = "stable-prefix-only"
    return hints
def est_tokens_compat(text):
    s = str(text or "")
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    return int(cjk + (len(s) - cjk) / 3.6)
def diagnose_dilution(query, plan=None):
    p = plan or rewrite(query)
    toks = tokenize(query)
    raw_chars = len(re.findall(r"[\w\u4e00-\u9fff]", normalize(query)))
    stopped = stopped_units(query)
    return {"terms": len(toks), "raw_chars": raw_chars, "stopped": stopped,
            "kept": len(p.lexical) + len(p.exact), "dilution": p.dilution,
            "exact_channel": p.exact, "intent": p.intent,
            "verdict": "ok" if p.dilution < 0.35 else "diluted-compensated"}
