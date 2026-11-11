import os
import zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path).lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.1f %s" % (n, unit)) if unit != "B" else ("%d B" % n)
        n /= 1024.0
def zip_list(path, limit=200):
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return "压缩包不存在：%s" % path
    if not zipfile.is_zipfile(p):
        return "不是 zip 格式（rar / 7z 需要额外工具）"
    try:
        with zipfile.ZipFile(p) as z:
            items = z.infolist()
            total = sum(i.file_size for i in items)
            lines = ["%s · %d 个条目 · 解开后 %s" % (os.path.basename(p), len(items), _size(total))]
            for i in items[:int(limit or 200)]:
                tag = "/" if i.is_dir() else ""
                lines.append("%10s  %s%s" % (_size(i.file_size), i.filename, tag))
            if len(items) > int(limit or 200):
                lines.append("……还有 %d 个没列" % (len(items) - int(limit or 200)))
            return "\n".join(lines)
    except Exception as e:
        return "读取失败：%s" % e
def zip_extract(path, dest="", limit=500):
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return "压缩包不存在：%s" % path
    d = _safe(dest or (os.path.splitext(os.path.basename(p))[0] + "_x"))
    if not d:
        return "目标路径越界"
    try:
        with zipfile.ZipFile(p) as z:
            names = [n for n in z.namelist() if not n.endswith("/")]
            if len(names) > int(limit or 500):
                return "里面有 %d 个文件，超过上限 %s，先看清单再决定" % (len(names), limit)
            bad = [n for n in names if ".." in n.split("/") or n.startswith("/")]
            if bad:
                return "包里有越界路径，拒绝解压：%s" % bad[0]
            os.makedirs(d, exist_ok=True)
            z.extractall(d)
            return "解到 %s，共 %d 个文件" % (os.path.relpath(d, ROOT).replace("\\", "/"), len(names))
    except Exception as e:
        return "解压失败：%s" % e
def zip_create(path, source, limit=2000):
    p = _safe(path)
    if not p:
        return "目标路径越界"
    if not p.lower().endswith(".zip"):
        p += ".zip"
    parts = [x.strip() for x in str(source or "").split(",") if x.strip()]
    if not parts:
        return "给一个要打包的目录或文件"
    n = 0
    try:
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in parts:
                src = _safe(rel)
                if not src or not os.path.exists(src):
                    return "找不到：%s" % rel
                if os.path.isfile(src):
                    z.write(src, os.path.basename(src))
                    n += 1
                    continue
                base = os.path.dirname(src)
                for dirpath, _, files in os.walk(src):
                    for f in files:
                        fp = os.path.join(dirpath, f)
                        z.write(fp, os.path.relpath(fp, base))
                        n += 1
                        if n >= int(limit or 2000):
                            return "文件太多，打到 %d 个就停了：%s" % (n, os.path.basename(p))
        return "已打包 %d 个文件 -> %s（%s）" % (
            n, os.path.relpath(p, ROOT).replace("\\", "/"), _size(os.path.getsize(p)))
    except Exception as e:
        return "打包失败：%s" % e
TOOLS = {
    "zip_list": (zip_list, {"path": "str", "limit": "int"}, "看 zip 里有什么"),
    "zip_extract": (zip_extract, {"path": "str", "dest": "str", "limit": "int"}, "解开 zip"),
    "zip_create": (zip_create, {"path": "str", "source": "str", "limit": "int"},
                   "把文件或目录打成 zip"),
}
