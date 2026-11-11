import os
import shutil
import subprocess
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
UI = os.path.join(SRC, "ui")
def main():
    args = [a for a in sys.argv[1:]]
    node = shutil.which("node") or shutil.which("nodejs")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    if node:
        cmd = [node, os.path.join(UI, "server.js")] + args
        print("runtime: node %s" % node)
    else:
        cmd = [sys.executable, os.path.join(UI, "serve.py")] + args
        print("runtime: python（未找到 node，使用纯 Python 服务端）")
    try:
        return subprocess.call(cmd, cwd=SRC, env=env)
    except KeyboardInterrupt:
        return 0
if __name__ == "__main__":
    sys.exit(main())
