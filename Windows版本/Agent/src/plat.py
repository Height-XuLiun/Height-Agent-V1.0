import locale
import os
import re
import shutil
import socket
import subprocess
import sys
CREATE_NO_WINDOW = 0x08000000
_IS_WIN32 = sys.platform.startswith("win")
def _detect():
    p = sys.platform
    if p.startswith("win"):
        return "windows"
    if p == "darwin":
        return "macos"
    if p == "ios":
        return "ios"
    if p.startswith("linux") or p.startswith("android"):
        if p.startswith("android") or os.environ.get("ANDROID_ROOT") or os.environ.get("ANDROID_DATA"):
            return "android"
        if os.environ.get("HARMONYOS") or os.environ.get("OHOS"):
            return "harmony"
        try:
            with open("/etc/os-release", encoding="utf-8", errors="replace") as f:
                blob = f.read().lower()
            if "harmony" in blob or "ohos" in blob:
                return "harmony"
        except Exception:
            pass
        return "linux"
    return p or "unknown"
OS = _detect()
IS_WIN = OS == "windows"
IS_MAC = OS == "macos"
IS_LINUX = OS in ("linux", "android", "harmony")
IS_MOBILE = OS in ("android", "ios", "harmony")
IS_IOS = OS == "ios"
def shell():
    forced = (os.environ.get("SA_SHELL") or "").strip()
    if forced:
        return forced
    if IS_WIN:
        return os.environ.get("COMSPEC") or "cmd.exe"
    for p in ("/bin/sh", "/system/bin/sh", "/usr/bin/sh"):
        if os.path.isfile(p):
            return p
    return "/bin/sh"
def decode(raw):
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw
    cands = ["utf-8", locale.getpreferredencoding(False), "gb18030", "latin-1"]
    seen = set()
    for enc in cands:
        if not enc or enc.lower() in seen:
            continue
        seen.add(enc.lower())
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")
def kill(proc):
    if proc is None or proc.poll() is not None:
        return
    if IS_WIN:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=CREATE_NO_WINDOW)
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        return
    try:
        os.killpg(os.getpgid(proc.pid), 9)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
def run(cmd, cwd=None, timeout=60, input=None, env=None):
    kw = dict(shell=True, cwd=cwd, executable=shell(),
              stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if env:
        kw["env"] = env
    if IS_WIN:
        kw["creationflags"] = CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    try:
        p = subprocess.Popen(cmd, **kw)
    except Exception as e:
        return 127, "%s: %s" % (type(e).__name__, e)
    payload = input.encode("utf-8") if isinstance(input, str) else input
    try:
        out, err = p.communicate(payload, timeout=timeout)
        code = p.returncode
    except subprocess.TimeoutExpired:
        kill(p)
        try:
            out, err = p.communicate(timeout=5)
        except Exception:
            out, err = b"", b""
        code = 124
    return code, (decode(out) + decode(err))
def run_argv(argv, cwd=None, timeout=30, input=None, env=None):
    kw = dict(cwd=cwd, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if env:
        kw["env"] = env
    if IS_WIN:
        kw["creationflags"] = CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    try:
        p = subprocess.Popen(list(argv), **kw)
    except Exception as e:
        return 127, "%s: %s" % (type(e).__name__, e)
    payload = input.encode("utf-8") if isinstance(input, str) else input
    try:
        out, err = p.communicate(payload, timeout=timeout)
        code = p.returncode
    except subprocess.TimeoutExpired:
        kill(p)
        try:
            out, err = p.communicate(timeout=5)
        except Exception:
            out, err = b"", b""
        code = 124
    return code, (decode(out) + decode(err))
def which(name):
    try:
        return shutil.which(name)
    except Exception:
        return None
def python_argv():
    forced = (os.environ.get("SA_PYTHON") or "").strip()
    if forced:
        return [forced]
    exe = sys.executable
    if exe and os.path.isfile(exe):
        return [exe]
    if IS_WIN:
        for c in (["py", "-3"], ["python"], ["python3"]):
            if which(c[0]):
                return c
        return ["python"]
    for c in (["python3"], ["python"]):
        if which(c[0]):
            return c
    return ["python3"]
def _shq(s):
    s = str(s)
    if IS_WIN:
        return '"%s"' % s
    return "'" + s.replace("'", "'\\''") + "'"
def check_file(path):
    if IS_WIN:
        return 'if exist %s (exit 0) else (exit 1)' % _shq(path)
    return "test -f %s" % _shq(path)
def check_text(path, needle):
    code = ("import sys;"
            "p,n=sys.argv[1],sys.argv[2];"
            "hit=[l for l in open(p,encoding='utf-8',errors='replace').read().splitlines()"
            " if n in l];"
            "print(hit[0] if hit else '');"
            "sys.exit(0 if hit else 1)")
    return _join(python_argv() + ["-c", _shq(code), _shq(path), _shq(needle)])
def _join(argv):
    return " ".join(argv)
_TEXT_SEARCH = re.compile(
    r'^(?:findstr(?:\s+/\w+)*\s+/C:\s*(?P<a1>"[^"]*"|\S+)\s+(?P<b1>.+?)'
    r'|grep\s+(?:-\w+\s+)*["\']?(?P<a2>[^"\']+)["\']?\s+(?P<b2>\S+?))\s*$',
    re.I)
def soft_text_check(cmd, cwd=None):
    s = str(cmd or "").strip()
    m = _TEXT_SEARCH.match(s)
    if not m:
        return None
    needle = m.group("a1") or m.group("a2") or ""
    path = m.group("b1") or m.group("b2") or ""
    needle = needle.strip().strip('"').strip("'")
    path = path.strip().strip('"').strip("'")
    if not needle or not path or any(c in path for c in "*?") or " " in path:
        return None
    full = path if os.path.isabs(path) else os.path.join(cwd or os.getcwd(), path)
    if not os.path.isfile(full):
        return None
    try:
        with open(full, "rb") as f:
            raw = f.read()
    except Exception:
        return None
    for enc in ("utf-8", "gb18030", "utf-16", locale.getpreferredencoding(False)):
        try:
            if needle in raw.decode(enc):
                return True
        except Exception:
            continue
    return False
def list_cmd(path="."):
    if IS_WIN:
        return "dir /b %s" % _shq(path)
    return "ls -1 %s" % _shq(path)
def open_url(url):
    try:
        if IS_WIN and hasattr(os, "startfile"):
            os.startfile(url)
            return True
        if IS_MAC:
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if OS == "android" and which("termux-open-url"):
            subprocess.Popen(["termux-open-url", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if which("xdg-open"):
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        return False
    except Exception:
        return False
def lan_ips():
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.25)
        try:
            s.connect(("8.8.8.8", 80))
        except Exception:
            pass
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            out.append(ip)
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and ip not in out and not ip.startswith("127."):
                out.append(ip)
    except Exception:
        pass
    return out
def describe():
    arch = (os.uname().machine if hasattr(os, "uname")
            else os.environ.get("PROCESSOR_ARCHITECTURE", ""))
    return {"os": OS, "platform": sys.platform, "arch": arch, "machine": arch,
            "python": sys.version.split()[0], "shell": shell(),
            "mobile": IS_MOBILE, "lan": lan_ips()}
