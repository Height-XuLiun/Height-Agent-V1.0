import os
import platform
import shutil
import sys
import time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
def _gb(n):
    return "%.1f GB" % (n / (1024.0 ** 3))
def sys_info(disk_path=""):
    out = []
    out.append("系统：%s %s（%s）" % (platform.system(), platform.release(), platform.machine()))
    out.append("主机：%s" % (platform.node() or "未知"))
    out.append("Python：%s（%s 位）" % (platform.python_version(),
                                       "64" if sys.maxsize > 2 ** 32 else "32"))
    out.append("CPU：%d 核" % (os.cpu_count() or 0))
    try:
        if hasattr(os, "getloadavg"):
            a, b, c = os.getloadavg()
            out.append("负载：%.2f / %.2f / %.2f" % (a, b, c))
    except Exception:
        pass
    total, used, free = 0, 0, 0
    target = os.path.abspath(disk_path) if disk_path else ROOT
    try:
        total, used, free = shutil.disk_usage(target)
        out.append("磁盘（%s）：共 %s，已用 %s，剩 %s（%.0f%%）"
                   % (os.path.splitdrive(target)[0] or "/", _gb(total), _gb(used),
                      _gb(free), used * 100.0 / total if total else 0))
    except Exception:
        pass
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        size = os.sysconf("SC_PAGE_SIZE")
        out.append("内存：%s" % _gb(pages * size))
    except Exception:
        if os.name == "nt":
            try:
                import ctypes
                class M(ctypes.Structure):
                    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                                ("ullTotalPhys", ctypes.c_ulonglong),
                                ("ullAvailPhys", ctypes.c_ulonglong),
                                ("ullTotalPageFile", ctypes.c_ulonglong),
                                ("ullAvailPageFile", ctypes.c_ulonglong),
                                ("ullTotalVirtual", ctypes.c_ulonglong),
                                ("ullAvailVirtual", ctypes.c_ulonglong),
                                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
                m = M()
                m.dwLength = ctypes.sizeof(M)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
                out.append("内存：%s（已用 %d%%，剩 %s）"
                           % (_gb(m.ullTotalPhys), m.dwMemoryLoad,
                              _gb(m.ullAvailPhys)))
            except Exception:
                pass
    out.append("工作目录：%s" % ROOT)
    out.append("可写：%s" % ("是" if os.access(ROOT, os.W_OK) else "否"))
    out.append("时区：%s" % time.strftime("%Z %z"))
    return "\n".join(out)
def sys_path(limit=40):
    path = os.environ.get("PATH", "")
    parts = [p for p in path.split(os.pathsep) if p.strip()]
    lines = ["PATH 共 %d 项" % len(parts)]
    for p in parts[:int(limit or 40)]:
        lines.append(("  有  " if os.path.isdir(p) else "  无  ") + p)
    keys = ("LANG", "LC_ALL", "PYTHONIOENCODING", "PYTHONPATH", "TZ",
            "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY")
    hit = ["%s=%s" % (k, os.environ[k]) for k in keys if k in os.environ]
    if hit:
        lines.append("相关变量：")
        lines.extend("  " + x for x in hit)
    return "\n".join(lines)
def sys_which(name):
    n = str(name or "").strip()
    if not n:
        return "给一个命令名"
    p = shutil.which(n)
    if p:
        return "%s -> %s" % (n, p)
    if os.path.isabs(n) and os.path.isfile(n):
        return "%s -> %s（绝对路径，存在）" % (n, n)
    return "%s 找不到。检查 PATH，或者装一下。" % n
TOOLS = {
    "sys_info": (sys_info, {"disk_path": "str"}, "看系统、内存、磁盘、Python 版本"),
    "sys_path": (sys_path, {"limit": "int"}, "看 PATH 和环境变量，排查命令找不到"),
    "sys_which": (sys_which, {"name": "str"}, "查一个命令装在哪"),
}
