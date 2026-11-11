import json
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bridge
try:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
except Exception:
    pass
def out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
def main():
    a = sys.argv[1:]
    cmd = (a[0] if a else "list").lower()
    try:
        if cmd == "list":
            return out({"ok": True, "plugins": bridge.list_plugins()})
        if cmd == "src":
            name = a[1] if len(a) > 1 else ""
            src = bridge.read_plugin_src(name)
            return out({"ok": src is not None, "code": src or "",
                        "msg": "" if src is not None else "没有这个插件"})
        if cmd == "make":
            name = a[1] if len(a) > 1 else ""
            desc = a[2] if len(a) > 2 else ""
            try:
                code = sys.stdin.read()
            except Exception:
                code = ""
            ok, msg, tools = bridge.make_plugin(name, code, desc)
            return out({"ok": ok, "msg": msg, "tools": sorted(tools),
                        "plugins": bridge.list_plugins()})
        if cmd == "install":
            src = a[1] if len(a) > 1 else ""
            desc = a[2] if len(a) > 2 else ""
            ok, msg, _tools = bridge.install_plugin(src, desc)
            return out({"ok": ok, "msg": msg, "plugins": bridge.list_plugins()})
        if cmd == "drop":
            ok, msg = bridge.drop_plugin(a[1] if len(a) > 1 else "")
            return out({"ok": ok, "msg": msg, "plugins": bridge.list_plugins()})
        return out({"ok": False, "msg": "未知命令：%s" % cmd})
    except Exception as e:
        return out({"ok": False, "msg": "%s: %s" % (type(e).__name__, e)})
if __name__ == "__main__":
    main()
