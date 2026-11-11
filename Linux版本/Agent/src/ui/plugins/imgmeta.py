import os
import struct
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
ORIENT = {1: "正常", 2: "水平镜像", 3: "旋转 180°", 4: "垂直镜像",
          5: "镜像后转 90°", 6: "顺时针转 90°", 7: "镜像后转 270°", 8: "逆时针转 90°"}
IFD0 = {0x010F: "厂商", 0x0110: "机型", 0x0112: "方向", 0x0132: "修改时间", 0x010E: "描述"}
EXIF = {0x9003: "拍摄时间", 0x829A: "曝光时间", 0x829D: "光圈", 0x8827: "ISO",
        0xA002: "像素宽", 0xA003: "像素高"}
def _safe(path):
    p = os.path.abspath(os.path.join(ROOT, str(path or ".").lstrip("/\\")))
    return p if p.startswith(os.path.abspath(ROOT)) else None
def _jpeg(f):
    w = h = 0
    exif = {}
    f.seek(2)
    while True:
        b = f.read(1)
        while b and b != b"\xff":
            b = f.read(1)
        if not b:
            break
        mk = f.read(1)
        while mk == b"\xff":
            mk = f.read(1)
        if not mk:
            break
        m = mk[0]
        if m in (0x01,) or 0xD0 <= m <= 0xD9:
            continue
        ln_raw = f.read(2)
        if len(ln_raw) < 2:
            break
        ln = struct.unpack(">H", ln_raw)[0]
        if ln < 2:
            break
        if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            data = f.read(5)
            if len(data) == 5:
                h, w = struct.unpack(">HH", data[1:5])
        elif m == 0xE1:
            data = f.read(ln - 2)
            if data[:6] == b"Exif\x00\x00" and not exif:
                exif = _exif(data[6:])
            continue
        f.seek(ln - 2, 1)
    return w, h, exif
def _val(e, typ, num, raw, t):
    size = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}.get(typ, 1) * num
    if size > 4:
        off = struct.unpack(e + "I", raw)[0]
        buf = t[off:off + size]
    else:
        buf = raw[:size]
    if len(buf) < size or not size:
        return None
    if typ == 2:
        return buf.split(b"\x00")[0].decode("utf-8", "replace").strip()
    if typ == 3:
        return struct.unpack(e + "%dH" % num, buf)[0]
    if typ == 4:
        return struct.unpack(e + "%dI" % num, buf)[0]
    if typ in (1, 7):
        return buf[0]
    if typ == 5 and size >= 8:
        a, b = struct.unpack(e + "II", buf[:8])
        return "%d/%d" % (a, b) if b else str(a)
    return None
def _exif(t):
    if len(t) < 8:
        return {}
    if t[:2] == b"II":
        e = "<"
    elif t[:2] == b"MM":
        e = ">"
    else:
        return {}
    out = {}
    def rd(off, want, depth=0):
        if depth > 2 or off + 2 > len(t):
            return
        cnt = struct.unpack(e + "H", t[off:off + 2])[0]
        p = off + 2
        for _ in range(min(cnt, 300)):
            if p + 12 > len(t):
                return
            tag, typ, num = struct.unpack(e + "HHI", t[p:p + 8])
            raw = t[p + 8:p + 12]
            p += 12
            if tag in want:
                v = _val(e, typ, num, raw, t)
                if v not in (None, ""):
                    out[want[tag]] = v
            if tag == 0x8769 and depth == 0:
                try:
                    rd(struct.unpack(e + "I", raw)[0], EXIF, depth + 1)
                except struct.error:
                    pass
    rd(struct.unpack(e + "I", t[4:8])[0], IFD0)
    return out
def _dims(p):
    with open(p, "rb") as f:
        head = f.read(30)
        if len(head) < 12:
            return None, 0, 0, {}
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            if head[12:16] != b"IHDR":
                return None, 0, 0, {}
            w, h = struct.unpack(">II", head[16:24])
            return "PNG", w, h, {}
        if head[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", head[6:10])
            return "GIF", w, h, {}
        if head[:2] == b"BM":
            w, h = struct.unpack("<ii", head[18:26])
            return "BMP", abs(w), abs(h), {}
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            f.seek(12)
            cc = f.read(4)
            if cc == b"VP8 ":
                f.seek(26)
                b = f.read(4)
                if len(b) == 4:
                    w = struct.unpack("<H", b[:2])[0] & 0x3FFF
                    h = struct.unpack("<H", b[2:])[0] & 0x3FFF
                    return "WebP", w, h, {}
            elif cc == b"VP8L":
                f.seek(21)
                b = f.read(4)
                if len(b) == 4:
                    v = struct.unpack("<I", b)[0]
                    return "WebP", (v & 0x3FFF) + 1, ((v >> 14) & 0x3FFF) + 1, {}
            elif cc == b"VP8X":
                f.seek(24)
                b = f.read(6)
                if len(b) == 6:
                    w = b[0] | (b[1] << 8) | (b[2] << 16)
                    h = b[3] | (b[4] << 8) | (b[5] << 16)
                    return "WebP", w + 1, h + 1, {}
            return "WebP", 0, 0, {}
        if head[:2] == b"\xff\xd8":
            w, h, ex = _jpeg(f)
            return "JPEG", w, h, ex
    return None, 0, 0, {}
def _kb(n):
    return "%.0f B" % n if n < 1024 else ("%.1f KB" % (n / 1024.0) if n < 1048576
                                          else "%.2f MB" % (n / 1048576.0))
def _w(s):
    return sum(2 if ord(c) > 0x2E7F else 1 for c in s)
def _pad(s, width):
    return s + " " * max(0, width - _w(s))
def _lpad(s, width):
    return " " * max(0, width - _w(s)) + s
def _one(p):
    name = os.path.basename(p)
    size = os.path.getsize(p)
    try:
        fmt, w, h, ex = _dims(p)
    except Exception as e:
        return "%s：读失败（%s）" % (name, type(e).__name__)
    if not fmt:
        return "%s：认不出格式（%s）" % (name, _kb(size))
    ratio = "%.2f:1" % (w / float(h)) if h else "-"
    lines = ["文件：%s" % name, "格式：%s" % fmt, "尺寸：%d × %d 像素（%s）" % (w, h, ratio),
             "体积：%s" % _kb(size)]
    if ex:
        if "方向" in ex:
            o = ex.pop("方向")
            ex["方向"] = "%s（%s）" % (o, ORIENT.get(o, "未知"))
        lines.append("EXIF：")
        for k in ("厂商", "机型", "拍摄时间", "修改时间", "曝光时间", "光圈", "ISO", "方向", "描述"):
            if k in ex:
                lines.append("  %s：%s" % (k, ex[k]))
        for k, v in ex.items():
            if k not in ("厂商", "机型", "拍摄时间", "修改时间", "曝光时间", "光圈", "ISO", "方向", "描述"):
                lines.append("  %s：%s" % (k, v))
    else:
        lines.append("EXIF：无")
    return "\n".join(lines)
def image_meta(path: str = ".", limit: int = 20) -> str:
    p = _safe(path)
    if not p:
        return "路径越界，拒绝执行"
    if not os.path.exists(p):
        return "路径不存在：%s" % path
    limit = max(1, min(100, int(limit or 20)))
    if os.path.isfile(p):
        return _one(p)
    found = []
    for base, dirs, files in os.walk(p):
        dirs[:] = [x for x in dirs if x not in (".git", "node_modules", "__pycache__", ".snapshots")]
        if base[len(p):].count(os.sep) >= 2:
            dirs[:] = []
        for fn in files:
            if fn.lower().endswith(EXT):
                fp = os.path.join(base, fn)
                try:
                    found.append((os.path.getsize(fp), fp))
                except OSError:
                    pass
    if not found:
        return "目录里没有图片（看的是 %s，认 %s）。" % (path, " ".join(EXT))
    found.sort(reverse=True)
    total = sum(s for s, _ in found)
    rows = []
    for s, fp in found[:limit]:
        try:
            fmt, w, h, _ = _dims(fp)
        except Exception:
            fmt, w, h = None, 0, 0
        rel = os.path.relpath(fp, p)
        dims = "%d×%d" % (w, h) if fmt else "-"
        rows.append(_pad(rel, 36) + " " + _pad(fmt or "?", 5) + " "
                    + _lpad(dims, 10) + "  " + _kb(s))
    more = "" if len(found) <= limit else "\n…（共 %d 张，只列最大的 %d 张）" % (len(found), limit)
    head = _pad("文件", 36) + " " + _pad("格式", 5) + " " + _lpad("尺寸", 10) + "  体积"
    return "目录：%s\n共 %d 张图片，合计 %s\n\n%s\n%s%s" % (
        p, len(found), _kb(total), head, "\n".join(rows), more)
TOOLS = {
    "image_meta": (image_meta, {"path": "str", "limit": "int"},
                   "读图片尺寸/格式/EXIF，不依赖 Pillow；给目录就按体积列出所有图片"),
}
