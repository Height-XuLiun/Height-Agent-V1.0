import json
import os
import socket
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(HERE)
ROOT = os.path.join(UI, "workspace")
CFG = os.path.join(UI, "config.json")
def _ok(flag):
    return "正常" if flag else "有问题"
def self_check():
    lines = []
    cfg = {}
    if os.path.isfile(CFG):
        try:
            with open(CFG, encoding="utf-8") as f:
                cfg = json.load(f)
            lines.append("[配置] config.json 读到了")
        except Exception as e:
            lines.append("[配置] config.json 存在但读不动：%s" % e)
    else:
        lines.append("[配置] 没有 config.json，还没接入模型")
    key = str(cfg.get("api_key") or cfg.get("key") or "")
    base = str(cfg.get("base_url") or "")
    model = str(cfg.get("model") or "")
    lines.append("  模型：%s" % (model or "未设置"))
    lines.append("  接口：%s" % (base or "未设置"))
    lines.append("  Key：%s" % ("已填（%d 位）" % len(key) if key else "没填"))
    if key and key.startswith("sk-") is False and len(key) < 12:
        lines.append("  Key 看着太短，可能贴漏了")
    perm = str(cfg.get("permission") or "workspace")
    lines.append("  权限：%s" % perm)
    try:
        os.makedirs(ROOT, exist_ok=True)
        probe = os.path.join(ROOT, ".selfcheck.tmp")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        n = len(os.listdir(ROOT))
        lines.append("[目录] 可读写，里面 %d 个文件" % n)
    except Exception as e:
        lines.append("[目录] 不可写：%s" % e)
    bad = []
    total = 0
    try:
        for f in sorted(os.listdir(HERE)):
            if not f.endswith(".py") or f.startswith("_"):
                continue
            total += 1
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("chk_" + f[:-3],
                                                              os.path.join(HERE, f))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if not getattr(mod, "TOOLS", None):
                    bad.append("%s：没有 TOOLS" % f)
            except Exception as e:
                bad.append("%s：%s" % (f, type(e).__name__))
    except Exception as e:
        lines.append("[插件] 目录读不到：%s" % e)
    lines.append("[插件] %d 个文件，%d 个有问题" % (total, len(bad)))
    for b in bad[:6]:
        lines.append("  - " + b)
    port = int(os.environ.get("SA_PORT") or 5000)
    s = socket.socket()
    s.settimeout(0.4)
    try:
        busy = s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()
    lines.append("[服务] 端口 %d %s" % (port, "有人在听" if busy else "没人在听"))
    lines.append("[环境] Python %s · %s" % (sys.version.split()[0], sys.platform))
    lines.append("[环境] 工作目录 %s" % ROOT)
    problems = sum(1 for x in lines if "有问题" in x or "没填" in x or "没人在听" in x)
    lines.append("")
    lines.append("结论：%s" % ("一切正常" if problems == 0 else "有 %d 处要处理" % problems))
    return "\n".join(lines)
def self_demo():
    return "自检插件在跑：%s\nPython %s\n当前目录 %s" % (
        os.path.basename(__file__), sys.version.split()[0], os.getcwd())
TOOLS = {
    "self_check": (self_check, {}, "体检：配置、目录、插件、端口一次看完"),
    "self_demo": (self_demo, {}, "确认插件机制本身是通的"),
}
