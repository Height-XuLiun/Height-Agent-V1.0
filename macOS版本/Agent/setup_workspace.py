#!/usr/bin/env python3
import argparse
import json
import os
import sys
import tempfile
import uuid
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "src", "ui", "config.json")
DEFAULT_NAME = "Agent工作区"
_DOWNLOADS_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"
def _exists(p):
    try:
        return bool(p) and os.path.isdir(os.path.realpath(p))
    except Exception:
        return False
def _expand(p):
    return os.path.normpath(os.path.expanduser(os.path.expandvars(str(p or ""))))
def _usable_dir(p):
    p = _expand(p)
    if not p or not os.path.isabs(p):
        return False
    tail = os.path.splitdrive(p)[1]
    if tail in (os.sep, "/", "\\"):
        return False
    if os.path.normcase(p) == os.path.normcase(os.path.expanduser("~")):
        return False
    return _exists(p)
def _win_registry_downloads():
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as k:
            val, _ = winreg.QueryValueEx(k, _DOWNLOADS_GUID)
            return _expand(val)
    except Exception:
        return ""
def _xdg_downloads():
    cfg = os.path.join(os.path.expanduser("~"), ".config", "user-dirs.dirs")
    try:
        with open(cfg, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("XDG_DOWNLOAD_DIR"):
                    continue
                val = line.split("=", 1)[1].strip().strip('"')
                return _expand(val.replace("$HOME", os.path.expanduser("~")))
    except Exception:
        pass
    return ""
def _browser_pref_paths():
    home = os.path.expanduser("~")
    out = []
    if sys.platform == "win32":
        la = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        out += [
            os.path.join(la, "Microsoft", "Edge", "User Data", "Default", "Preferences"),
            os.path.join(la, "Google", "Chrome", "User Data", "Default", "Preferences"),
        ]
    elif sys.platform == "darwin":
        sup = os.path.join(home, "Library", "Application Support")
        out += [
            os.path.join(sup, "Microsoft Edge", "Default", "Preferences"),
            os.path.join(sup, "Google", "Chrome", "Default", "Preferences"),
        ]
    else:
        cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
        out += [
            os.path.join(cfg, "microsoft-edge", "Default", "Preferences"),
            os.path.join(cfg, "google-chrome", "Default", "Preferences"),
            os.path.join(home, ".config", "chromium", "Default", "Preferences"),
        ]
    return out
def _browser_downloads():
    found = []
    for p in _browser_pref_paths():
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            val = ((d.get("download") or {}).get("default_directory") or "").strip()
            val = _expand(val)
            if _usable_dir(val) and val not in found:
                found.append(val)
        except Exception:
            continue
    return found
def _default_candidates():
    home = os.path.expanduser("~")
    c = [os.path.join(home, "Downloads"), os.path.join(home, "下载")]
    if sys.platform == "win32":
        for base in (os.environ.get("USERPROFILE") or home,
                     os.path.join(home, "OneDrive")):
            c.append(os.path.join(base, "Downloads"))
    return c
def detect_downloads(explicit=""):
    if explicit:
        p = os.path.abspath(_expand(explicit))
        if _exists(p):
            return p, "explicit", _browser_downloads()
    browser = [p for p in _browser_downloads() if _usable_dir(p)]
    if browser:
        return browser[0], "browser-preferences", browser
    for getter, tag in ((_win_registry_downloads, "windows-registry"),
                        (_xdg_downloads, "xdg-user-dirs")):
        p = getter()
        if _usable_dir(p):
            return _expand(p), tag, browser
    for p in _default_candidates():
        if _usable_dir(p):
            return _expand(p), "default-path", browser
    return "", "not-found", browser
def choose_workspace(downloads, use_download=False, root="", name=DEFAULT_NAME):
    if root:
        return _expand(root), "explicit-root"
    if not downloads:
        return "", "no-download-dir"
    if use_download:
        return downloads, "downloads-itself"
    sub = str(name or DEFAULT_NAME).strip().strip("/\\")
    if not sub or sub in (".", ".."):
        sub = DEFAULT_NAME
    return os.path.join(downloads, sub), "downloads-subdir"
def write_config(root, config_path=None):
    config_path = config_path or CONFIG
    old = {}
    try:
        with open(config_path, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            old = d
    except Exception:
        pass
    old["root"] = root
    d = os.path.dirname(config_path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, ".config.%s.tmp" % uuid.uuid4().hex[:8])
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False, indent=2)
        os.replace(tmp, config_path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
    return old
def main(argv=None):
    ap = argparse.ArgumentParser(description="自动识别下载位置并设置 Agent 工作目录")
    ap.add_argument("--downloads", default="", help="显式指定下载目录")
    ap.add_argument("--root", default="", help="显式指定工作目录，跳过探测")
    ap.add_argument("--use-download", action="store_true", help="直接用下载目录作为工作目录")
    ap.add_argument("--name", default=DEFAULT_NAME, help="下载目录下的子目录名")
    ap.add_argument("--dry-run", action="store_true", help="只探测，不创建目录、不写配置")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    a = ap.parse_args(argv)
    downloads, source, browser = detect_downloads(a.downloads)
    workspace, how = choose_workspace(downloads, a.use_download, a.root, a.name)
    result = {
        "download_dir": downloads,
        "download_source": source,
        "browser_overrides": browser,
        "workspace": workspace,
        "workspace_source": how,
        "config_path": CONFIG,
        "written": False,
        "created": False,
    }
    if not workspace:
        result["error"] = "没有找到下载目录，请用 --root 指定工作目录"
    elif not a.dry_run:
        try:
            os.makedirs(workspace, exist_ok=True)
            result["created"] = True
            write_config(workspace)
            result["written"] = True
        except Exception as e:
            result["error"] = str(e)
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("下载目录：%s（来源：%s）" % (downloads or "未找到", source))
        if browser:
            print("浏览器自定义下载目录：%s" % "、".join(browser))
        print("工作目录：%s（%s）" % (workspace or "未设置", how))
        if a.dry_run:
            print("dry-run：未创建目录、未写配置")
        elif result.get("written"):
            print("已写入：%s" % CONFIG)
        if result.get("error"):
            print("错误：%s" % result["error"], file=sys.stderr)
    return 0 if result.get("written") or a.dry_run and workspace else 1
if __name__ == "__main__":
    sys.exit(main())
