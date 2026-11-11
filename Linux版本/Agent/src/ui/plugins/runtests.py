import os
import re
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
import plat
FAIL_RE = re.compile(r"(FAILED|FAIL:|ERROR|✗|×|AssertionError|Traceback|not ok)", re.I)
def _detect():
    def has(*names):
        return any(os.path.exists(os.path.join(ROOT, n)) for n in names)
    if has("go.mod"):
        return "go test ./...", "Go"
    if has("Cargo.toml"):
        return "cargo test --quiet", "Rust"
    if has("package.json"):
        return "npm test --silent", "Node"
    if has("pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg", "tests", "test"):
        return " ".join(plat.python_argv()) + " -m pytest -q", "Python"
    if has("Makefile"):
        return "make test", "Make"
    return "", ""
def run_tests(cmd: str = "", timeout: int = 180) -> str:
    if not os.path.isdir(ROOT):
        return "工作区不存在：%s" % ROOT
    if not cmd:
        cmd, kind = _detect()
        if not cmd:
            return ("没认出项目类型。可手动指定，例如 "
                    "run_tests(\"python -m pytest -q\") 或 run_tests(\"npm test\")。")
    else:
        kind = "自定义"
    code, out = plat.run(cmd, cwd=ROOT, timeout=max(10, int(timeout)))
    lines = [l.rstrip() for l in (out or "").splitlines() if l.strip()]
    tail = lines[-40:]
    bad = [l for l in lines if FAIL_RE.search(l)][:12] if code != 0 else []
    head = "命令：%s（%s）\n退出码：%s" % (cmd, kind, code)
    if code == 0:
        verdict = "结果：通过"
    elif code == 124:
        verdict = "结果：超时（%ds）" % int(timeout)
    else:
        verdict = "结果：失败"
    parts = [head, verdict]
    if bad:
        parts.append("失败线索：\n" + "\n".join("- " + b[:200] for b in bad))
    parts.append("输出末尾：\n" + ("\n".join(tail) if tail else "(无输出)"))
    return "\n\n".join(parts)
TOOLS = {
    "run_tests": (run_tests, {"cmd": "str", "timeout": "int"},
                  "自动识别项目类型跑测试，返回退出码、失败线索和输出末尾"),
}
