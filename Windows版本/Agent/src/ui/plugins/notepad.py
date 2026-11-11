import json
import os
import re
import time
HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(HERE)
FILE = os.path.join(UI, "notes.json")
MAX = 400
def _load():
    try:
        with open(FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except Exception:
        return []
def _save(data):
    try:
        with open(FILE, "w", encoding="utf-8") as f:
            json.dump(data[-MAX:], f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False
def note_add(text, tags=""):
    body = str(text or "").strip()
    if not body:
        return "没有内容"
    if len(body) > 4000:
        return "太长了，超过 4000 字。拆成几条写。"
    tag = [t.strip() for t in re.split(r"[,，\s]+", str(tags or "")) if t.strip()]
    data = _load()
    data.append({"ts": int(time.time()),
                 "day": time.strftime("%Y-%m-%d %H:%M"),
                 "tags": tag[:6],
                 "text": body})
    if not _save(data):
        return "写不进去，检查 %s 的权限" % FILE
    return "记下了（第 %d 条）%s" % (len(data), ("，标签：" + "、".join(tag)) if tag else "")
def note_search(q="", tag="", limit=10):
    data = _load()
    if not data:
        return "还没有笔记。用 note_add 写一条。"
    kw = str(q or "").strip().lower()
    tg = str(tag or "").strip().lower()
    hits = []
    for x in reversed(data):
        text = str(x.get("text", ""))
        if kw and kw not in text.lower():
            continue
        if tg and tg not in [t.lower() for t in x.get("tags", [])]:
            continue
        hits.append(x)
        if len(hits) >= max(1, int(limit or 10)):
            break
    if not hits:
        return "没找到匹配的笔记（共 %d 条）" % len(data)
    lines = ["找到 %d 条（共 %d 条）" % (len(hits), len(data))]
    for x in hits:
        head = x.get("day", "")
        if x.get("tags"):
            head += "  [" + " ".join(x["tags"]) + "]"
        body = str(x.get("text", ""))
        if len(body) > 240:
            body = body[:240] + "……"
        lines.append("")
        lines.append(head)
        lines.append(body)
    return "\n".join(lines)
def note_list(tag="", limit=20):
    data = _load()
    if not data:
        return "还没有笔记。"
    tg = str(tag or "").strip().lower()
    rows = [x for x in data if not tg or tg in [t.lower() for t in x.get("tags", [])]]
    rows = rows[-max(1, int(limit or 20)):]
    lines = ["最近 %d 条（共 %d 条）" % (len(rows), len(data))]
    for x in reversed(rows):
        first = str(x.get("text", "")).splitlines()[0][:60]
        tagtxt = (" [" + " ".join(x["tags"]) + "]") if x.get("tags") else ""
        lines.append("  %s%s  %s" % (x.get("day", ""), tagtxt, first))
    return "\n".join(lines)
def note_drop(index):
    data = _load()
    if not data:
        return "还没有笔记"
    i = int(index or 0)
    if i < 1 or i > len(data):
        return "序号超出范围，共 %d 条" % len(data)
    gone = data.pop(i - 1)
    _save(data)
    return "删掉了第 %d 条：%s" % (i, str(gone.get("text", ""))[:40])
TOOLS = {
    "note_add": (note_add, {"text": "str", "tags": "str"}, "记一条笔记，可以带标签"),
    "note_search": (note_search, {"q": "str", "tag": "str", "limit": "int"},
                    "按关键词或标签搜笔记"),
    "note_list": (note_list, {"tag": "str", "limit": "int"}, "列出最近的笔记"),
    "note_drop": (note_drop, {"index": "int"}, "删掉第几条笔记"),
}
