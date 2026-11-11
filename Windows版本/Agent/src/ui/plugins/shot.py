import base64
import os
import shutil
import subprocess
import time
import urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
SHOTS = os.path.join(ROOT, "shots")
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
_FORBID = [os.environ.get("SystemRoot") or r"C:\Windows",
           os.environ.get("ProgramFiles") or r"C:\Program Files",
           os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"]
def _out(path, prefix="shot"):
    if path:
        p = str(path).strip().strip('"')
        p = p if os.path.isabs(p) else os.path.join(ROOT, p)
    else:
        os.makedirs(SHOTS, exist_ok=True)
        p = os.path.join(SHOTS, "%s-%s.png" % (prefix, time.strftime("%Y%m%d-%H%M%S")))
    p = os.path.abspath(p)
    if not p.lower().endswith(".png"):
        p += ".png"
    low = os.path.normcase(p)
    for bad in _FORBID:
        if bad and low.startswith(os.path.normcase(os.path.abspath(bad))):
            return None
    d = os.path.dirname(p)
    try:
        if d:
            os.makedirs(d, exist_ok=True)
    except Exception:
        return None
    return p
def _nice(p):
    return p.replace("\\", "/")
def _ps(script, timeout=45):
    b64 = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                            "-ExecutionPolicy", "Bypass", "-EncodedCommand", b64],
                           capture_output=True, timeout=timeout)
    except FileNotFoundError:
        return "", "这台机器上没有 powershell"
    except subprocess.TimeoutExpired:
        return "", "powershell 超时"
    out = (r.stdout or b"").decode("utf-8", "replace").strip()
    err = (r.stderr or b"").decode("utf-8", "replace").strip()
    return out, err
_PS_HEAD = (
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8\n"
    "Add-Type -AssemblyName System.Drawing\n"
    "Add-Type -AssemblyName System.Windows.Forms\n"
    "Add-Type -TypeDefinition @'\n"
    "using System;using System.Runtime.InteropServices;\n"
    "public class SaDpi{[DllImport(\"user32.dll\")]public static extern bool SetProcessDPIAware();}\n"
    "'@\n"
    "[SaDpi]::SetProcessDPIAware() | Out-Null\n"
)
def _report(path):
    size = os.path.getsize(path)
    return ("截图已保存：%s（%d KB）\n要在回答里把图显示出来，就单独写一行：![]( %s )"
            % (_nice(path), max(1, size // 1024), _nice(path)))
def screenshot(path: str = "", region: str = "") -> str:
    p = _out(path)
    if not p:
        return "这个位置不让写，换一个路径（默认存到工作目录的 shots/ 下）"
    if region:
        parts = [x.strip() for x in str(region).replace("，", ",").split(",")]
        if len(parts) != 4 or not all(x.lstrip("-").isdigit() for x in parts):
            return "region 要写成 x,y,w,h 四个数字，比如 100,100,800,600"
        x, y, w, h = [int(v) for v in parts]
        if w <= 0 or h <= 0:
            return "region 的宽高要大于 0"
        src = ("$bmp=New-Object System.Drawing.Bitmap(%d,%d)\n" % (w, h)
               + "$g=[System.Drawing.Graphics]::FromImage($bmp)\n"
               + "$g.CopyFromScreen(%d,%d,0,0,$bmp.Size)\n" % (x, y))
        note = "%d x %d 区域" % (w, h)
    else:
        src = ("$vs=[System.Windows.Forms.SystemInformation]::VirtualScreen\n"
               "$bmp=New-Object System.Drawing.Bitmap($vs.Width,$vs.Height)\n"
               "$g=[System.Drawing.Graphics]::FromImage($bmp)\n"
               "$g.CopyFromScreen($vs.X,$vs.Y,0,0,$bmp.Size)\n")
        note = "整个屏幕"
    script = (_PS_HEAD + src +
              "$bmp.Save('%s',[System.Drawing.Imaging.ImageFormat]::Png)\n" % p.replace("'", "''") +
              "$g.Dispose();$bmp.Dispose()\n"
              "Write-Output 'ok'\n")
    out, err = _ps(script)
    if not os.path.isfile(p) or os.path.getsize(p) < 100:
        return "截屏失败：%s" % (err or out or "没有生成文件")
    return "截了%s。%s" % (note, _report(p))
def window_list() -> str:
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8\n"
              "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | "
              "ForEach-Object { \"$($_.ProcessName) | $($_.MainWindowTitle)\" }\n")
    out, err = _ps(script, timeout=30)
    if not out:
        return "没读到窗口：%s" % (err or "一个都没有")
    lines = [x.strip() for x in out.splitlines() if x.strip()]
    return "当前打开的窗口：\n" + "\n".join(lines[:40])
def shot_window(title: str = "", path: str = "") -> str:
    title = str(title or "").strip()
    if not title:
        return "要给一个窗口标题（可以先调 window_list 看看有哪些）"
    p = _out(path, prefix="win")
    if not p:
        return "这个位置不让写，换一个路径"
    t = title.replace("'", "''").replace("*", "")
    script = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8\n"
        "Add-Type -AssemblyName System.Drawing\n"
        "Add-Type -TypeDefinition @'\n"
        "using System;using System.Runtime.InteropServices;\n"
        "public class SaWin{\n"
        " [DllImport(\"user32.dll\")]public static extern bool SetForegroundWindow(IntPtr h);\n"
        " [DllImport(\"user32.dll\")]public static extern bool ShowWindow(IntPtr h,int c);\n"
        " [DllImport(\"user32.dll\")]public static extern bool GetWindowRect(IntPtr h,out RECT r);\n"
        " [StructLayout(LayoutKind.Sequential)]public struct RECT{public int L,T,R,B;}\n"
        "}\n"
        "'@\n"
        "$p=Get-Process | Where-Object {$_.MainWindowTitle -like '*" + t + "*'} | Select-Object -First 1\n"
        "if(-not $p){Write-Output 'NO-WINDOW';exit}\n"
        "$h=$p.MainWindowHandle\n"
        "[SaWin]::ShowWindow($h,9) | Out-Null\n"
        "[SaWin]::SetForegroundWindow($h) | Out-Null\n"
        "Start-Sleep -Milliseconds 400\n"
        "$r=New-Object SaWin+RECT\n"
        "[SaWin]::GetWindowRect($h,[ref]$r) | Out-Null\n"
        "$w=$r.R-$r.L; $ht=$r.B-$r.T\n"
        "if($w -le 0 -or $ht -le 0){Write-Output 'NO-SIZE';exit}\n"
        "$bmp=New-Object System.Drawing.Bitmap($w,$ht)\n"
        "$g=[System.Drawing.Graphics]::FromImage($bmp)\n"
        "$g.CopyFromScreen($r.L,$r.T,0,0,$bmp.Size)\n"
        "$bmp.Save('" + p.replace("'", "''") + "',[System.Drawing.Imaging.ImageFormat]::Png)\n"
        "$g.Dispose();$bmp.Dispose()\n"
        "Write-Output \"ok $w x $ht\"\n"
    )
    out, err = _ps(script, timeout=40)
    if "NO-WINDOW" in out:
        return "没有标题包含「%s」的窗口。可以先调 window_list 看看有哪些。" % title
    if not os.path.isfile(p) or os.path.getsize(p) < 100:
        return "截这个窗口失败：%s" % (err or out or "没有生成文件")
    return "截了窗口「%s」（%s）。%s" % (title, out.replace("ok ", ""), _report(p))
def _browser():
    for c in EDGE_CANDIDATES:
        if os.path.isfile(c):
            return c
    for name in ("msedge", "chrome", "chromium"):
        w = shutil.which(name)
        if w:
            return w
    return None
def shot_page(url: str = "", path: str = "", width: int = 1440, height: int = 900) -> str:
    url = str(url or "").strip()
    if not url:
        return "要给一个网址，本地文件用 file:/// 开头"
    if not url.lower().startswith(("http://", "https://", "file://", "data:")):
        if os.path.isfile(url) or os.path.isfile(os.path.join(ROOT, url)):
            f = url if os.path.isfile(url) else os.path.join(ROOT, url)
            url = "file:///" + _nice(os.path.abspath(f))
        else:
            url = "https://" + url
    exe = _browser()
    if not exe:
        return "没找到 Edge 或 Chrome，截不了网页"
    p = _out(path, prefix="page")
    if not p:
        return "这个位置不让写，换一个路径"
    try:
        w = max(320, min(3840, int(width or 1440)))
        h = max(240, min(3840, int(height or 900)))
    except Exception:
        w, h = 1440, 900
    args = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--no-first-run", "--no-default-browser-check",
            "--virtual-time-budget=4000",
            "--window-size=%d,%d" % (w, h),
            "--screenshot=" + p, url]
    try:
        subprocess.run(args, capture_output=True, timeout=90)
    except subprocess.TimeoutExpired:
        return "浏览器截图超时（页面可能一直在加载）"
    except Exception as e:
        return "浏览器截图失败：%s" % str(e)[:120]
    if not os.path.isfile(p) or os.path.getsize(p) < 100:
        return "没截出图来，检查一下地址能不能打开：%s" % url
    return "截了 %s。%s" % (url, _report(p))
def clipboard(action: str = "get", text: str = "") -> str:
    act = str(action or "get").strip().lower()
    if act in ("set", "write", "copy"):
        if not text:
            return "要写的内容是空的"
        script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8\n"
                  "[Console]::InputEncoding=[Text.Encoding]::UTF8\n"
                  "$t=[Console]::In.ReadToEnd()\n"
                  "Set-Clipboard -Value $t\nWrite-Output 'ok'\n")
        b64 = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                            "-ExecutionPolicy", "Bypass", "-EncodedCommand", b64],
                           input=str(text).encode("utf-8"), capture_output=True, timeout=30)
        except Exception as e:
            return "写剪贴板失败：%s" % str(e)[:120]
        return "已复制 %d 个字到剪贴板" % len(str(text))
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8\n"
              "$c=Get-Clipboard -Raw\n"
              "if($null -eq $c){Write-Output ''}else{Write-Output $c}\n")
    out, err = _ps(script, timeout=30)
    if err and not out:
        return "读剪贴板失败：%s" % err[:120]
    return out if out else "（剪贴板是空的，或者里面不是文字）"
TOOLS = {
    "screenshot": (screenshot, {"path": "str", "region": "str"},
                   "截屏幕。region 留空截全屏，也可以给 x,y,w,h 只截一块；不给 path 就存到工作目录 shots/ 下"),
    "window_list": (window_list, {},
                    "列出当前打开的窗口标题，决定截哪个窗口时先看这个"),
    "shot_window": (shot_window, {"title": "str", "path": "str"},
                    "按窗口标题截某个窗口，会先把它切到前台"),
    "shot_page": (shot_page, {"url": "str", "path": "str", "width": "int", "height": "int"},
                  "截一个网页（http(s) 或本地 file:///），用来检查自己做出来的页面长什么样"),
    "clipboard": (clipboard, {"action": "str", "text": "str"},
                  "读或写剪贴板：action=get 读回来，action=set 把 text 放进去"),
}
