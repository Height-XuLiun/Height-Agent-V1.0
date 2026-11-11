import json, os, sys, time
d = json.loads(sys.stdin.read() or "{}")
log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit.log")
with open(log, "a", encoding="utf-8") as f:
    f.write("%s\t%s\t%s\t%s\n" % (
        time.strftime("%H:%M:%S"), d.get("tool"),
        "ok" if d.get("ok") else "FAIL",
        str(d.get("args"))[:160]))
sys.exit(0)
