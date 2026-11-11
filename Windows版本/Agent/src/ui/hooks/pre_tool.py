import json, sys, re
d = json.loads(sys.stdin.read() or "{}")
tool, args = d.get("tool", ""), d.get("args", {})
target = str(args.get("path", "") or args.get("cmd", ""))
bad = re.search(r"([A-Za-z]:\\Windows|/etc/|/usr/|C:/Windows|\.\./\.\.)", target, re.I)
if bad:
    print("拒绝：目标路径越出工作区（%s）" % bad.group(1))
    sys.exit(1)
if tool == "run_shell":
    cmd = str(args.get("cmd", ""))
    if re.search(r"\b(rm\s+-rf|del\s+/[sq]|format\s+[a-z]:|shutdown)", cmd, re.I):
        print("拒绝：命令含破坏性操作")
        sys.exit(1)
sys.exit(0)
