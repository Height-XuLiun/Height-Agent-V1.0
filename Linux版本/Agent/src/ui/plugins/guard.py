import hashlib
import json
import os
import shutil
import time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
SNAPDIR = os.path.join(os.path.dirname(HERE), ".snapshots")
SKIP = {".snapshots", "__pycache__", ".git"}
_T0 = time.time()
_BUDGET = {"steps": 40, "seconds": 600, "steps_used": 0}
def _walk():
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for fn in files:
            fp = os.path.join(dirpath, fn)
            yield fp, os.path.relpath(fp, ROOT)
def snapshot(label: str = "") -> str:
    os.makedirs(SNAPDIR, exist_ok=True)
    tag = "%s_%s" % (time.strftime("%H%M%S"), (str(label) or "auto").replace(" ", "_")[:20])
    dest = os.path.join(SNAPDIR, tag)
    os.makedirs(dest, exist_ok=True)
    index = {}
    for fp, rel in _walk():
        try:
            data = open(fp, "rb").read()
            out = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(data)
            index[rel] = hashlib.sha1(data).hexdigest()[:12]
        except Exception:
            continue
    open(os.path.join(dest, "_index.json"), "w", encoding="utf-8").write(
        json.dumps(index, ensure_ascii=False, indent=1))
    return "快照 %s 已建立，%d 个文件。回滚用 rollback('%s')。" % (tag, len(index), tag)
def rollback(tag: str) -> str:
    dest = os.path.join(SNAPDIR, str(tag).strip())
    if not os.path.isdir(dest):
        snaps = sorted(os.listdir(SNAPDIR)) if os.path.isdir(SNAPDIR) else []
        return "快照不存在。可用：%s" % ("、".join(snaps[-5:]) or "无")
    idx = json.loads(open(os.path.join(dest, "_index.json"), encoding="utf-8").read())
    removed = 0
    for fp, rel in list(_walk()):
        if rel not in idx:
            try:
                os.remove(fp); removed += 1
            except Exception:
                pass
    restored = 0
    for rel in idx:
        src = os.path.join(dest, rel)
        if os.path.isfile(src):
            out = os.path.join(ROOT, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy2(src, out)
            restored += 1
    return "已回滚到 %s：恢复 %d 个，删除 %d 个。" % (tag, restored, removed)
def budget(note: str = "") -> str:
    _BUDGET["steps_used"] += 1
    used_s = time.time() - _T0
    left_s = max(0, _BUDGET["seconds"] - used_s)
    left_n = max(0, _BUDGET["steps"] - _BUDGET["steps_used"])
    lines = [
        "步数  %d / %d（剩 %d）" % (_BUDGET["steps_used"], _BUDGET["steps"], left_n),
        "时间  %d 秒 / %d 秒（剩 %d）" % (int(used_s), _BUDGET["seconds"], int(left_s)),
    ]
    if left_n <= 3:
        lines.append("步数即将用尽，请立即收尾：直接给出当前最佳结果，不要再开新步骤。")
    elif left_s <= 60:
        lines.append("时间即将用尽，请立即收尾。")
    elif note:
        lines.append("备注：%s" % note)
    return "\n".join(lines)
TOOLS = {
    "snapshot": (snapshot, {"label": "str"}, "动手前拍快照，可回滚"),
    "rollback": (rollback, {"tag": "str"}, "恢复到指定快照"),
    "budget": (budget, {"note": "str"}, "查剩余步数与时间"),
}
