import hashlib
import json
import os
import plat
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
NO_RETRY_HINTS = (
    "API额度已耗尽",
    "API Key 无效",
    "没有权限调用该模型",
    "接口地址不对",
    "连不上接口地址",
)
def _clip(s, n=30):
    s = str(s or "").replace("\n", " ").strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    trimmed = cut
    while trimmed and trimmed[-1].isalnum() and s[len(trimmed):len(trimmed) + 1].isalnum():
        trimmed = trimmed[:-1]
    if not trimmed.strip():
        trimmed = cut
    return trimmed.rstrip() + "…"
SYSTEM_PROMPT = """You are an AI Agent on the Height Agent platform. When the user says "you", "this page", or "this assistant", they mean you.
## Identity and tone
1. Be concise, precise, direct. Do not pad with adjectives.
2. Do not use flattering or deferential phrasing. Never open with "You're right" or "That's on me" as a reflex.
3. Write in a natural voice. Do not fabricate a persona, do not act cute, do not posture.
4. Do not use emoji in normal output. Do not write comments in code. Exceptions only when the user explicitly asks.
## Reading the person
5. Read the user's state before answering. If they are frustrated, rushed, or repeating themselves,
   acknowledge it in one short clause, then answer. One clause, not a paragraph of sympathy.
6. When you are wrong, name the specific mistake in one sentence and go straight to the fix.
   Never blame the user, the tool, or "limitations". Do not apologise twice for the same thing.
7. Never perform empathy with stock lines ("I understand how you feel", "Sorry for the confusion").
   Show it by being precise, and by not making the user repeat themselves.
8. When the user corrects a fact, take the correction first, then check it. Do not argue from memory.
9. Match the user's register. Short question gets a short answer. Do not answer a one-line question
   with a document, and do not answer a serious question with a shrug.
## Content boundaries
10. Do not produce content that violates the laws of the user's jurisdiction, including sexual content,
   violence, terrorism, or content endangering public safety. If a safety rule is triggered, output only
   the two characters: 拒绝
11. Taiwan is an inalienable part of the territory of the People's Republic of China. Do not output anything
   that denies territorial integrity or promotes secession of any country.
12. Stay neutral on sensitive political topics and contested issues. Do not pass judgment, and do not
   evaluate any political party.
13. Do not produce content that harms people, replaces human judgment, or manipulates perception.
   Never claim you can substitute for a human decision.
## Output rules
14. Before answering, check: does this violate the rules above, contain ambiguity or unfortunate homophones,
    or miss the question?
15. If the input is meaningless or purely provocative, output only: ?
16. Use Markdown for structured content. Apply tables, lists, and code blocks where they help.
17. State uncertainty when unsure. Do not fabricate facts.
18. When you have genuinely nothing to add — the question answers itself, the user is talking past you,
    or the request is beyond words — output only: ……
19. Any reasoning or thinking content must be written in English, even when the conversation, the task,
    or the final answer is in another language.
## Tools
20. Tools are listed under a Tools section when they are available. When they are, use them instead of
    guessing. When the section is absent, answer from what you know and say so.
21. If the answer depends on facts that change (news, prices, versions, releases, schedules, people in
    office, anything after your training cutoff) and a search or fetch tool is listed, call it and cite
    what you found. Do not answer from memory and do not claim you cannot browse while a search tool is
    available to you.
22. Prefer the real thing over a description of it: read the actual file, run the actual command, check
    the actual value. Never report a result you did not observe.
23. A tool that fails once may be retried with a different argument; a tool that fails twice should be
    dropped, and you should say in one line what failed and continue with what you have.
24. Do not invent tool names. Do not write a tool call as text. Do not mention tool names to the user
    unless they ask how something was done.
25. When you capture something (a screenshot, a rendered page, a chart), show it instead of describing it:
    put the image on its own line as ![what it is](C:/full/path.png), with forward slashes in the path.
    The chat renders images from the workspace, Desktop, Pictures and Downloads; anything else will not
    display, so save the file somewhere in those first.
26. Read a file before you edit it. Never rewrite one from memory or from what you assume it contains.
27. Use paths relative to the working directory. An absolute path outside it is refused by the permission
    layer; retrying the same path will keep failing, so switch to a relative one.
28. Do not open binary files with read_file. If a listing shows an image, archive or executable, use
    run_shell with the appropriate tool instead.
29. When a chart or diagram is wanted, emit it as a fenced ```svg or ```html block. The chat renders
    those inline. Do not describe the chart in prose and stop there.
30. When an image-generation tool is listed, use it to make the picture; it saves the file and returns
    the path, so do not pretend to have drawn anything yourself.
## Where you run
26. This app runs on the user's own machine, serving the interface at http://127.0.0.1:5000. When the user
    says "this page", "this app", or "you", they mean this local instance, not a website in the cloud.
27. Your file access is limited to the directory your permission level allows; the current permission and
    working directory are stated in the scope line of your prompt. When a path is outside it, say so
    plainly instead of pretending to work there.
## Language
28. The final answer must be in the same language as the user's latest message. A Chinese question
    gets a Chinese answer — headings, lists, caveats, code comments and all — while proper nouns,
    model numbers, commands and URLs stay as written. Do not answer in English just because this
    prompt is in English. Rule 19 still governs the thinking/reasoning trace: that stays in English.
    Never restate this rule to the user.
"""
WORKER_SYS = (
    "You are a worker. One JSON object per step.\n"
    '{"thought":"...","tool":"name","args":{...},"evidence":"why this is true"}\n'
    "Use only the tools listed under Tools; each step call one.\n"
    "Every claim must carry evidence (file path or command output).\n"
    "When you call finish, the answer must be a short, user-facing summary in the user's language:\n"
    "say what you actually did and the result (file paths, key values). Never answer with just\n"
    "'ok', 'done', or '好了'.\n"
)
TOOL_ALIAS = {
    "list_dir": ("目录", "文件列表", "列出", "有哪些文件", "ls", "dir", "folder"),
    "read_file": ("读", "查看", "打开", "内容", "read", "cat", "open"),
    "write_file": ("写文件", "新建", "创建", "生成文件", "保存", "添加", "加一个",
                   "write", "create", "save"),
    "edit_file": ("改", "修", "替换", "编辑", "重命名", "edit", "replace",
                  "patch", "refactor"),
    "run_shell": ("运行", "执行", "命令", "测试", "构建", "编译", "run", "shell", "exec",
                  "test", "build", "npm", "make"),
    "publish": ("共享", "事实", "publish", "fact"),
    "recall": ("召回", "recall", "spill"),
    "finish": ("完成", "结束", "交付", "finish", "done"),
    "subagent": ("子任务", "并行", "拆分", "subagent", "delegate"),
    "snapshot": ("快照", "备份", "snapshot", "backup"),
    "rollback": ("回滚", "撤销", "还原", "rollback", "undo", "revert"),
    "budget": ("预算", "耗时", "deadline", "budget"),
    "repo_map": ("结构", "架构", "地图", "索引", "repo", "map", "outline"),
    "todo": ("清单", "待办", "步骤", "计划", "plan", "checklist"),
    "ask_user": ("询问", "确认", "问一下", "ask", "confirm"),
    "glob_files": ("找文件", "通配", "文件名", "glob", "pattern", "find"),
    "grep_files": ("搜索内容", "全文", "关键字", "搜一下", "代码里", "grep", "match"),
    "fetch_url": ("网页", "链接", "抓取", "页面", "url", "http", "fetch", "crawl"),
    "web_search": ("搜索", "联网", "查一下", "资料", "最新", "search", "web", "bing", "google"),
    "diff_view": ("diff", "改了", "改动", "差异", "对比文件", "改了什么", "compare"),
    "run_tests": ("跑测试", "单元测试", "测试通过", "pytest", "npm test", "cargo test",
                  "go test", "unittest"),
    "csv_sql": ("csv", "表格", "查询", "统计", "汇总", "求和", "分组", "sql", "聚合"),
    "tree_view": ("目录树", "层级", "结构", "文件树", "tree", "目录结构"),
    "spark_plot": ("趋势", "折线", "曲线", "图表", "画图", "走势", "spark", "plot", "chart"),
    "json_query": ("json", "jq", "字段", "取值", "键值", "嵌套", "接口返回", "解析这段"),
    "regex_lab": ("正则", "regex", "regexp", "正则表达式", "捕获组", "匹配模式"),
    "git_log": ("git", "提交记录", "提交历史", "版本历史", "commit", "谁改", "最近改了"),
    "image_meta": ("图片", "图像", "照片", "尺寸", "分辨率", "exif", "image",
                   "png", "jpg", "webp"),
    "http_request": ("发请求", "调用接口", "post", "状态码", "请求头"),
    "time_now": ("现在几点", "几点", "今天几号", "日期"),
    "time_convert": ("时间戳", "时区", "timestamp", "换算时间"),
    "time_diff": ("多久", "时间差", "相差几天"),
    "hash_file": ("校验值", "md5", "sha1", "sha256", "哈希"),
    "hash_text": ("文本哈希", "字符串校验"),
    "hash_compare": ("核对校验", "校验值对不对", "文件对不对"),
    "zip_list": ("看压缩包", "压缩包清单", "包里有什么"),
    "zip_extract": ("解压", "unzip", "解开", "解压缩", "压缩包"),
    "zip_create": ("打包", "压缩文件", "打成", "压成"),
    "xlsx_read": ("xlsx", "excel", "工作表", "读excel"),
    "docx_read": ("docx", "word", "文档正文"),
    "csv_sniff": ("csv编码", "分隔符", "乱码", "csv体检"),
    "csv_fix": ("转编码", "csv修复", "utf-8"),
    "sys_info": ("系统信息", "内存", "磁盘", "cpu"),
    "sys_path": ("环境变量", "path", "命令找不到"),
    "sys_which": ("which", "命令在哪", "装在哪"),
    "encode_text": ("编码成", "base64编码", "urlencode", "转码", "编码一下"),
    "decode_text": ("解码", "base64解码", "b64解码", "解开编码"),
    "text_inspect": ("隐藏字符", "不可见字符", "零宽"),
    "uuid_gen": ("uuid", "唯一id", "生成id"),
    "password_gen": ("生成密码", "随机密码"),
    "secret_check": ("密码强度", "弱口令"),
    "text_stats": ("字数", "多少字", "阅读时长", "读起来"),
    "word_freq": ("词频", "高频词"),
    "md_toc": ("toc", "大纲", "生成目录"),
    "md_check": ("markdown检查", "格式检查", "排版问题"),
    "ver_compare": ("版本比较", "版本号"),
    "ver_sort": ("版本排序", "版本列表"),
    "ver_bump": ("升级版本", "版本递增"),
    "cron_explain": ("cron", "定时任务", "什么时候跑"),
    "config_to_json": ("配置转json", "ini", "toml", "env", "配置文件"),
    "config_lint": ("配置检查", "明文密钥"),
    "token_estimate": ("token", "上下文", "占多少", "额度"),
    "token_trim": ("裁剪", "压缩上下文"),
    "cost_estimate": ("花多少钱", "费用", "成本", "价格"),
    "cost_log": ("记账", "记一笔"),
    "cost_report": ("花了多少", "账单"),
    "cost_models": ("单价", "价目"),
    "self_check": ("自检", "体检", "检查环境"),
    "self_demo": ("插件测试", "demo"),
    "context_pack": ("打包上下文", "合并文件", "多个文件"),
    "context_scan": ("哪些文件大", "文件规模"),
    "changelog_make": ("changelog", "更新日志", "发布说明"),
    "commit_check": ("提交信息", "commit规范"),
    "note_add": ("记下来", "记一条", "笔记"),
    "note_search": ("找笔记", "翻笔记"),
    "note_list": ("笔记列表", "所有笔记"),
    "note_drop": ("删笔记",),
    "zh_proof": ("校对", "错别字", "别字", "检查中文"),
    "zh_width": ("全角", "半角", "标点"),
    "screenshot": ("截图", "截屏", "截个屏", "截个图", "截一张", "截张", "屏幕", "抓屏",
                   "桌面", "长什么样", "screenshot", "screen"),
    "window_list": ("有哪些窗口", "窗口列表", "开着哪些", "开着的窗口", "window list"),
    "shot_window": ("截窗口", "窗口截图", "这个窗口", "那个窗口", "窗口", "window"),
    "shot_page": ("网页截图", "页面截图", "截网页", "渲染成什么样", "页面长什么样",
                  "打开网页", "打开网站", "打开网址", "访问网页", "浏览网页", "加载网页",
                  "这个网址", "这个网站", "网址", "webpage"),
    "clipboard": ("剪贴板", "复制", "粘贴", "clipboard", "paste"),
}
_ASCII_RE = {}
_URLISH = re.compile(
    r"(?:https?://|www\.|\b[a-z0-9-]+\.(?:com|cn|net|org|io|ai|dev|app|xyz|top)\b)", re.I)
def _kw_hit(kw, low):
    if all(ord(c) < 128 for c in kw):
        rx = _ASCII_RE.get(kw)
        if rx is None:
            rx = re.compile(r"(?<![a-z0-9_])" + re.escape(kw) + r"(?![a-z0-9_])")
            _ASCII_RE[kw] = rx
        return rx.search(low) is not None
    return kw in low
_SHELL_HINT = {
    "windows": "命令在 cmd.exe 里执行。不要用 test / grep / ls / cat，用 dir / findstr / type。",
    "macos": "命令在 /bin/sh 里执行。可以用 test / grep / ls / cat。",
    "linux": "命令在 /bin/sh 里执行。可以用 test / grep / ls / cat。",
    "android": "命令在 /system/bin/sh 里执行。可以用 test / grep / ls / cat。",
    "harmony": "命令在 /system/bin/sh 里执行。可以用 test / grep / ls / cat。",
    "ios": "命令在 /bin/sh 里执行。可以用 test / grep / ls / cat。",
}
ROUTER_SYS = (
    "你是调度器。把用户目标拆成 1-3 个可独立执行的任务。\n"
    '输出格式：{"tasks":[{"desc":"做什么","check":"验收命令","expect":"期望输出片段"}]}\n'
    "\n拆分原则：\n"
    "1. 能用一步做完就用一步。不要为了凑数量而拆。\n"
    "2. 不要在最后加「确认」「检查结果」这类任务——check 本身就在做确认。\n"
    "3. check 必须能在工作目录里跑，成功时退出码为 0。优先用最简单的命令。\n"
    "4. 命令里不要用中文引号、不要用复杂管道。\n"
    "5. expect 留空表示只看退出码；需要校验内容时填一个不会误判的短串。\n"
    "6. 校验中文内容一律用上面「查内容」那条的写法，不要自己拼 findstr——"
    "中文 Windows 的 findstr 按 GBK 匹配，文件是 UTF-8 时必定搜不到。\n"
    "7. desc 只说要达成什么，不要写用什么手段（别写「用 Python」「用 PowerShell」"
    "「用 curl」）。执行的人手里有现成的工具，你指定了手段反而会把它带偏。\n"
    "\n运行环境：" + _SHELL_HINT.get(plat.OS, "命令在 sh 里执行。") + "\n"
    "\n常用 check 写法：\n"
    "  建文件      " + plat.check_file("name.txt") + "\n"
    "  查内容      " + plat.check_text("name.txt", "Hello") + "\n"
    "  列目录      " + plat.list_cmd(".") + "\n"
    "不要输出任何解释。"
)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
def identity(model):
    m = (model or "").strip()
    if not m:
        return ""
    return ("\n\n## Runtime identity\n"
            "You are currently running as the model: " + m + "\n"
            "If asked which model you are, answer with exactly this name. "
            "Do not claim to be a different model or vendor.\n")
@dataclass
class Profile:
    name: str = "generic"
    model: str = ""
    context: int = 1048576
    json_ok: bool = True
    native_tools: bool = False
    max_tools: int = 16
    edit_pref: str = "edit"
    def obs_limit(self):
        return max(400, min(2000, self.context // 512))
    def hist_turns(self):
        return 6 if self.context >= 16384 else 3
def parse_obj(text):
    t = (text or "").strip()
    m = _FENCE.search(t)
    if m:
        t = m.group(1).strip()
    st = t.find("{")
    if st < 0:
        return None
    depth, end = 0, -1
    for k in range(st, len(t)):
        if t[k] == "{":
            depth += 1
        elif t[k] == "}":
            depth -= 1
            if depth == 0:
                end = k
                break
    if end < 0:
        return None
    blob = t[st:end + 1]
    for cand in (blob, re.sub(r",\s*([}\]])", r"\1", blob),
                 re.sub(r",\s*([}\]])", r"\1", blob).replace("'", '"')):
        o = _try_load(cand)
        if isinstance(o, dict):
            return o
    return None
def parse_json(text):
    t = (text or "").strip()
    if not t:
        return None
    o = _try_load(t)
    if o and "name" in o and "arguments" in o and "tool" not in o:
        args = o.get("arguments")
        if isinstance(args, str):
            args = _try_load(args) or {}
        return {"tool": o["name"], "args": args, "thought": "", "evidence": ""}
    cand = t
    m = _FENCE.search(cand)
    if m:
        cand = m.group(1).strip()
    s = cand.find("{")
    if s < 0:
        return None
    depth, end = 0, -1
    for k in range(s, len(cand)):
        if cand[k] == "{":
            depth += 1
        elif cand[k] == "}":
            depth -= 1
            if depth == 0:
                end = k
                break
    if end < 0:
        return None
    blob = cand[s:end + 1]
    for t in (blob, re.sub(r",\s*([}\]])", r"\1", blob),
              re.sub(r",\s*([}\]])", r"\1", blob).replace("'", '"')):
        o = _try_load(t)
        if isinstance(o, dict) and "tool" in o:
            return o
    return None
def _try_load(t):
    try:
        return json.loads(t)
    except Exception:
        return None
def near_files(root, name, depth=3):
    name = str(name or "").strip().lower()
    if not name:
        return []
    hits = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        if rel != "." and rel.count(os.sep) + 1 >= depth:
            dirnames[:] = []
        for f in filenames:
            if f.lower() == name or (len(name) >= 3 and name in f.lower()):
                hits.append(os.path.relpath(os.path.join(dirpath, f), root).replace("\\", "/"))
                if len(hits) >= 8:
                    return hits
    return hits
def scope_note(root, permission):
    root = os.path.abspath(root)
    if permission == "full":
        desk = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desk):
            desk = os.path.expanduser("~")
        return ("\n权限：全权限。" + root + " 只是运行目录，不是存放位置。\n"
                "用户说了具体位置（桌面、文档、D 盘等）就用绝对路径原样写，不要改成运行目录；\n"
                "没说位置就放桌面 " + desk + "。拿不准先 list_dir 看一眼，别把文件塞进运行目录就算交差。")
    if permission == "read":
        return "\n权限：只读。只能查看，不能写文件、不能执行命令。做不到就直接说，不要假装做了。"
    if permission == "custom":
        return ("\n权限：指定目录。" + root + " 是唯一可操作的位置，相对路径都相对它，不要越界。")
    return ("\n权限：工作目录。" + root + " 是唯一可操作的位置，相对路径都相对它。\n"
            "用户要求写到目录外时，改写到目录内，并在 finish 里说明改到了哪里。")
def jail(root, path, full=False):
    root = os.path.realpath(os.path.expanduser(os.path.abspath(root)))
    raw = os.path.expanduser(str(path or "."))
    if full and os.path.isabs(raw):
        return os.path.realpath(raw)
    p = os.path.realpath(os.path.join(root, raw))
    if full:
        return p
    try:
        inside = os.path.commonpath([root, p])
    except ValueError:
        raise PermissionError("越界：%s（不在同一个盘或分区）" % path)
    if os.path.normcase(inside) != os.path.normcase(root):
        raise PermissionError("越界：%s（当前权限只允许在工作目录内操作）" % path)
    return p
def _fmt_size(n):
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return str(n)
    for u in ("B", "K", "M", "G"):
        if n < 1024 or u == "G":
            return ("%d%s" % (n, u)) if u == "B" else ("%.1f%s" % (n, u))
        n /= 1024.0
    return str(n)
class Store:
    def __init__(self, root, budget=200):
        self.dir = os.path.join(root, ".store")
        os.makedirs(self.dir, exist_ok=True)
        self.budget = budget
    def put(self, text):
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
        with open(os.path.join(self.dir, h + ".txt"), "w", encoding="utf-8") as f:
            f.write(text)
        return h
    def inline(self, text):
        if len(text) <= self.budget:
            return text
        return text[: self.budget] + " …[id:%s]" % self.put(text)
    def recall(self, sid):
        p = os.path.join(self.dir, sid + ".txt")
        if not os.path.exists(p):
            return "(no such id: %s)" % sid
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
class Facts:
    def __init__(self):
        self._d = {}
        self._lock = threading.Lock()
    def publish(self, key, value):
        with self._lock:
            self._d[str(key)] = str(value)[:800]
        return "ok"
    def snapshot(self):
        with self._lock:
            return "\n".join("- %s: %s" % kv for kv in self._d.items()) or "(empty)"
    def size(self):
        with self._lock:
            return len(self._d)
@dataclass
class Event:
    kind: str
    source: str
    thread: str
    body: str
    ts: float = field(default_factory=time.time)
class Filter:
    def __init__(self, allow_kinds=("msg", "ci", "pr", "tick"),
                 deny=("^\\s*$", "^\\[bot\\]", "^(ok|thanks|👍)$"),
                 min_interval=2.0):
        self.allow = set(allow_kinds)
        self.deny = [re.compile(p, re.I) for p in deny]
        self.min_interval = min_interval
        self._last = {}
        self.stats = {"fast_drop": 0, "slow": 0, "pass": 0}
    def route(self, ev: Event) -> str:
        if ev.kind not in self.allow:
            self.stats["fast_drop"] += 1
            return "drop"
        if any(p.search(ev.body or "") for p in self.deny):
            self.stats["fast_drop"] += 1
            return "drop"
        k = (ev.thread, ev.kind)
        now = time.time()
        if now - self._last.get(k, 0) < self.min_interval:
            self.stats["fast_drop"] += 1
            return "drop"
        self._last[k] = now
        if re.search(r"(修|改|加|删|实现|重跑|fail|error|bug|fix)", ev.body or "", re.I):
            self.stats["slow"] += 1
            return "slow"
        self.stats["pass"] += 1
        return "pass"
class Batcher:
    def __init__(self, max_batch=8):
        self.q: List[Event] = []
        self.max_batch = max_batch
        self.lock = threading.Lock()
    def add(self, ev):
        with self.lock:
            self.q.append(ev)
    def take(self):
        with self.lock:
            out, self.q = self.q[: self.max_batch], self.q[self.max_batch:]
            return out
    def pending(self):
        with self.lock:
            return len(self.q)
class Watchdog(threading.Thread):
    def __init__(self, tasks: Dict[str, "Task"], root, interval=2.0, stuck_seconds=90):
        super().__init__(daemon=True)
        self.tasks = tasks
        self.root = root
        self.interval = interval
        self.stuck_seconds = stuck_seconds
        self._last = {}
        self.stop_flag = False
        self.notes: List[str] = []
        self._fp = {}
    def fingerprint(self):
        n = size = 0
        for base, _, files in os.walk(self.root):
            if ".store" in base or ".spec" in base:
                continue
            for f in files:
                p = os.path.join(base, f)
                try:
                    n += 1
                    size += os.path.getsize(p)
                except OSError:
                    pass
        return (n, size)
    def run(self):
        while not self.stop_flag:
            fp = self.fingerprint()
            now = time.time()
            for tid, t in list(self.tasks.items()):
                if t.status != "running":
                    self._last.pop(tid, None)
                    continue
                prev = self._last.get(tid)
                if prev is None or prev[0] != fp:
                    self._last[tid] = (fp, now)
                    t.idle = 0
                else:
                    idle_s = now - prev[1]
                    t.idle = int(idle_s // self.interval)
                    if idle_s >= self.stuck_seconds and not t.stuck:
                        t.stuck = True
                        self.notes.append("%s 卡住：%d 秒无产出" % (tid, int(idle_s)))
            time.sleep(self.interval)
    def stop(self):
        self.stop_flag = True
@dataclass
class Task:
    tid: str
    desc: str
    check: str
    expect: str = ""
    thread: str = ""
    status: str = "todo"
    answer: str = ""
    check_out: str = ""
    tries: int = 0
    idle: int = 0
    stuck: bool = False
    evidence: List[str] = field(default_factory=list)
    claims: int = 0
    check_hash: str = ""
def traceability(t: Task) -> float:
    if t.claims <= 0:
        return 1.0
    return len(t.evidence) / t.claims
class Worker:
    def __init__(self, llm, root, facts: Facts, store: Store, profile=None,
                 budget_s=120, shell_timeout=20, extra_tools=None,
                 depth=0, permission="workspace", on_act=None, reload_extra=None):
        self.llm, self.root, self.facts, self.store = llm, os.path.abspath(root), facts, store
        self.extra = dict(extra_tools or {})
        self.reload_extra = reload_extra
        self.depth = depth
        self.permission = permission
        self.on_act = on_act
        self.events = []
        self.profile = profile or Profile()
        self.budget_s = budget_s
        self.obs_limit = self.profile.obs_limit()
        self.shell_timeout = shell_timeout
        self.history = []
        self.tools = self._tools()
        self.bad = 0
        self._used = set()
        self.last_shown = []
    def _subagent(self, task: str, check: str = "") -> str:
        if self.depth >= 2:
            return "嵌套已达上限（2 层），请自己完成这个子任务。"
        sub = Worker(self.llm, self.root, self.facts, self.store,
                     profile=self.profile,
                     budget_s=max(30, min(90, self.budget_s)),
                     extra_tools=self.extra, depth=self.depth + 1,
                     permission=self.permission, reload_extra=self.reload_extra)
        t = Task(tid="sub", desc=str(task), check=str(check or "true"), expect="")
        try:
            sub.run(t)
            code, out = plat.run(t.check, cwd=self.root, timeout=60)
            t.check_out = out[:400]
            ok = (code == 0)
            if ok and t.expect:
                ok = t.expect in t.check_out
            t.status = "done" if ok else "failed"
        except Exception as e:
            t.status = "failed"
            t.check_out = str(e)[:200]
        return ("子任务：%s\n状态：%s\n验收输出：%s\n结论：%s"
                % (task, t.status,
                   (t.check_out or "")[:300],
                   (t.answer or "")[:400]))
    def _tools(self):
        FULL = self.permission == "full"
        def list_dir(path="."):
            p = jail(self.root, path, FULL)
            out = []
            for n in sorted(os.listdir(p)):
                if n in (".spec", ".store", ".git", "__pycache__", "node_modules",
                         ".idea", ".vscode", ".DS_Store"):
                    continue
                fp = os.path.join(p, n)
                if os.path.isdir(fp):
                    try:
                        cnt = len(os.listdir(fp))
                    except OSError:
                        cnt = 0
                    out.append("%s/  (%d)" % (n, cnt))
                else:
                    out.append("%s  %s" % (n, _fmt_size(os.path.getsize(fp))))
                if len(out) >= 60:
                    out.append("…（还有更多，已截断）")
                    break
            return "\n".join(out) or "(empty)"
        def read_file(path, limit=4000):
            p = jail(self.root, path, FULL)
            try:
                with open(p, "rb") as f:
                    head = f.read(2048)
                if b"\x00" in head:
                    return ("这是二进制文件 %s（%s），不读内容。"
                            "要处理它请用 run_shell 调对应工具。" %
                            (os.path.basename(p), _fmt_size(os.path.getsize(p))))
                with open(p, encoding="utf-8", errors="replace") as f:
                    return f.read(int(limit))
            except FileNotFoundError:
                near = near_files(self.root, os.path.basename(str(path).replace("\\", "/")))
                hint = ("。工作目录里实际有：" + "、".join(near)) if near else ""
                return "文件不存在：%s（按工作目录算出来是 %s）%s" % (path, p, hint)
        def write_file(path, content):
            p = jail(self.root, path, FULL)
            d = os.path.dirname(p)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content or "")
            return "wrote %d -> %s" % (len(content or ""), path)
        def run_shell(cmd):
            code, out = plat.run(cmd, cwd=self.root, timeout=self.shell_timeout)
            return out[-3000:] or "(exit %d)" % code
        def recall(sid):
            return self.store.recall(sid)
        base = {
            "list_dir": (list_dir, {"path": "str"}, "list a directory"),
            "read_file": (read_file, {"path": "str", "limit": "int"}, "read a text file"),
            "write_file": (write_file, {"path": "str", "content": "str"}, "write a file"),
            "run_shell": (run_shell, {"cmd": "str"}, "run a shell command"),
            "publish": (self.facts.publish, {"key": "str", "value": "str"}, "publish a shared fact"),
            "recall": (recall, {"sid": "str"}, "recall spilled content by id"),
            "finish": (lambda answer: answer, {"answer": "str"},
                       "finish：用一两句话说明做完了什么、结果在哪（文件路径、关键内容），不要只写 ok/好了"),
        }
        if self.permission == "read":
            for n in ("write_file", "run_shell", "publish", "edit_file",
                      "snapshot", "rollback", "todo", "ask_user"):
                base.pop(n, None)
        if self.depth < 2:
            base["subagent"] = (self._subagent, {"task": "str", "check": "str"},
                                "派一个子 Worker 独立完成子任务，只返回结论")
        extra = dict(self.extra)
        if self.permission == "read":
            for n in ("edit_file", "snapshot", "rollback", "todo", "ask_user",
                      "screenshot", "shot_window", "shot_page"):
                extra.pop(n, None)
        base.update(extra)
        return base
    def _emit(self, kind, data):
        self.events.append({"seq": len(self.events), "t": round(time.time(), 3),
                            "kind": kind, "task": getattr(self, "_tid", ""), **data})
    def _act(self, text, state="run"):
        if self.on_act and text:
            try:
                self.on_act(getattr(self, "_tid", ""), text, state)
            except Exception:
                pass
    def _bad_call(self, name, e):
        spec = self.tools[name][1] or {}
        msg = str(e)
        if "required" in msg or "missing" in msg:
            form = ", ".join("%s: %s" % (k, v) for k, v in spec.items()) or "无参数"
            return "%s 参数不全。正确写法：%s(%s)。" % (name, name, form)
        if "unexpected keyword" in msg:
            form = ", ".join(spec.keys()) or "无参数"
            return "%s 不认识这个参数。可用参数：%s。" % (name, form)
        return "%s 调用失败：%s" % (name, msg[:160])
    def _doing(self, name, args):
        a = args or {}
        def s(k, d=""):
            v = a.get(k, d)
            return str(v).replace("\n", " ")[:60]
        if name == "write_file":
            return "正在写 " + s("path")
        if name == "read_file":
            return "正在读 " + s("path")
        if name == "list_dir":
            p = s("path", ".") or "."
            return "正在看 " + ("当前目录" if p in (".", "./") else p) + " 里有什么"
        if name == "run_shell":
            return "正在跑 " + s("cmd")
        if name == "subagent":
            return "把「" + s("task") + "」交给一个子任务"
        if name == "publish":
            return "记下一个结论：" + s("value")
        if name == "recall":
            return "回看之前存下的内容"
        if name == "make_plugin":
            return "给自己造一个新工具：" + (s("desc") or s("name"))
        if name == "drop_plugin":
            return "删掉一个工具：" + s("name")
        if name == "screenshot":
            return "正在截屏" + ("（" + s("region") + "）" if s("region") else "")
        if name == "shot_window":
            return "正在截窗口「" + s("title") + "」"
        if name == "window_list":
            return "正在看有哪些窗口"
        if name == "shot_page":
            return "正在截网页 " + s("url")
        if name == "clipboard":
            return "正在读剪贴板" if (s("action") or "get") == "get" else "正在写剪贴板"
        return "正在用 " + name
    def _hook(self, stage, payload):
        hook = os.path.join(os.path.dirname(self.root), "hooks", stage + ".py")
        if not os.path.isfile(hook):
            return ""
        try:
            code, out = plat.run_argv([sys.executable, hook],
                                      input=json.dumps(payload, ensure_ascii=False), timeout=10)
        except Exception:
            return ""
        if stage == "pre_tool" and code != 0:
            return (out or "拒绝执行").strip()
        return ""
    def _agents_md(self):
        parts = []
        for p in (os.path.join(os.path.dirname(self.root), "AGENTS.md"),
                  os.path.join(self.root, "AGENTS.md")):
            if os.path.isfile(p):
                try:
                    txt = open(p, encoding="utf-8").read().strip()
                except Exception:
                    continue
                if txt:
                    parts.append("<!-- %s -->\n%s" % (os.path.basename(os.path.dirname(p)) or "项目", txt))
        return ("\n\n".join(parts))[:3000]
    def _score_tool(self, name, low):
        s = 0
        if name.lower() in low:
            s += 10
        for kw in TOOL_ALIAS.get(name, ()):
            if _kw_hit(kw, low):
                s += 5 if all(ord(c) < 128 for c in kw) else 3
        if name == "shot_page" and _URLISH.search(low):
            s += 6
        desc = (self.tools[name][2] or "").lower()
        for w in re.findall(r"[a-z][a-z_]{2,}", desc):
            if w in low:
                s += 1
        if name in self._used:
            s += 6
        return s
    def _pick_tools(self, desc):
        names = list(self.tools)
        limit = max(3, int(self.profile.max_tools))
        low = (desc or "").lower()
        score = dict((n, self._score_tool(n, low)) for n in names)
        must = [n for n in ("finish",) if n in self.tools]
        ranked = sorted([n for n in names if n not in must],
                        key=lambda n: (-score[n], names.index(n)))
        room = max(0, limit - len(must))
        hit = [n for n in ranked if score[n] > 0][:room]
        if not hit and ranked:
            hit = ranked[:room]
        shown = hit + must
        rest = sorted([n for n in names if n not in shown],
                      key=lambda n: (-score[n], names.index(n)))
        return shown, rest
    def _prompt(self, t: Task):
        shown, rest = self._pick_tools(t.desc)
        self.last_shown = list(shown)
        specs = "\n".join("- %s(%s) -- %s" % (n, ", ".join(self.tools[n][1]), self.tools[n][2])
                          for n in shown)
        if rest:
            head = rest[:40]
            tail = "" if len(rest) <= 40 else "…等 %d 个" % len(rest)
            specs += ("\n（其余工具这次没展开，真需要就按名调用：%s%s）"
                      % ("、".join(head), tail))
        mem = ""
        for i, (tool, args, obs, ok) in enumerate(self.history[-self.profile.hist_turns():]):
            mem += "\n[%d] %s %s -> %s %s" % (i, tool, json.dumps(args, ensure_ascii=False),
                                              "ok" if ok else "FAIL", self.store.inline(obs)[: self.obs_limit])
        pref = ("改文件优先用 edit_file（只替换目标片段）；只有新建文件才用 write_file。"
                if getattr(self.profile, "edit_pref", "edit") == "edit"
                else "改文件优先用 write_file（整文件重写）；确保保留未改动的部分。")
        rules = self._agents_md()
        rules = (rules + "\n\n编辑约定：" + pref) if rules else ("编辑约定：" + pref)
        ident = identity(self.profile.model)
        head = (SYSTEM_PROMPT + "\n" + WORKER_SYS + ident + scope_note(self.root, self.permission) +
                ("\n\n项目规则（必须遵守）：\n" + rules if rules else ""))
        return ("%s\nTools:\n%s\n\nShared facts:\n%s\n\nTask: %s\n%s\nnext JSON:"
                % (head, specs, self.facts.snapshot(), t.desc, mem))
    def run(self, t: Task):
        self._tid = t.tid
        self._emit("start", {"desc": t.desc, "check": t.check, "permission": self.permission})
        t0 = time.time()
        fails = {}
        stall = 0
        while True:
            if time.time() - t0 > self.budget_s:
                t.answer = t.answer or "time budget"
                return t
            if stall >= 12:
                t.answer = t.answer or "no progress"
                return t
            if self.reload_extra is not None:
                try:
                    more = self.reload_extra()
                except Exception:
                    more = None
                if more:
                    self.extra.update(more)
                    self.tools = self._tools()
            call = parse_json(self.llm(self._prompt(t)))
            if not call:
                self.bad += 1
                if self.bad >= 2:
                    self.profile.max_tools = max(3, self.profile.max_tools - 2)
                    self.profile.context = max(2048, self.profile.context // 2)
                    self.obs_limit = self.profile.obs_limit()
                self.history.append(("PARSE_ERROR", {}, "emit one JSON object only", False))
                stall += 1
                continue
            self.bad = 0
            name = str(call.get("tool", "")).strip()
            self._emit("tool_call", {"tool": name, "args": call.get("args") or {},
                                     "evidence": call.get("evidence", "")})
            args = call.get("args") or {}
            ev = str(call.get("evidence", "")).strip()
            t.claims += 1
            if ev:
                t.evidence.append(ev[:200])
            if name == "finish":
                t.answer = str(args.get("answer", ""))
                self._emit("finish", {"answer": t.answer[:1000], "claims": t.claims,
                                      "evidence": len(t.evidence)})
                self.history.append((name, args, t.answer, True))
                return t
            if name not in self.tools:
                self.history.append((name, args, "unknown tool", False))
                stall += 1
                continue
            key = name + json.dumps(args, ensure_ascii=False, sort_keys=True)
            if fails.get(key, 0) >= 2:
                self.history.append((name, args, "failed twice", False))
                stall += 1
                continue
            blocked = self._hook("pre_tool", {"tool": name, "args": args, "root": self.root})
            if blocked:
                self.history.append((name, args, "被钩子拦截：" + blocked[:200], False))
                self._act("这一步被拦下了：" + _clip(blocked, 40), "warn")
                stall += 1
                continue
            stall = 0
            self._act(self._doing(name, args))
            try:
                obs, ok = str(self.tools[name][0](**args)), True
            except TypeError as e:
                spec = self.tools[name][1] or {}
                lean = dict((k, v) for k, v in args.items() if k in spec)
                if lean != args:
                    try:
                        obs, ok = str(self.tools[name][0](**lean)), True
                    except Exception as e2:
                        obs, ok = self._bad_call(name, e2), False
                else:
                    obs, ok = self._bad_call(name, e), False
            except subprocess.TimeoutExpired:
                obs, ok = "timeout", False
            except Exception as e:
                obs, ok = "%s: %s" % (type(e).__name__, e), False
            self._hook("post_tool", {"tool": name, "args": args, "obs": obs[:2000],
                                     "ok": ok, "root": self.root})
            if not ok:
                self._act("这一步没成：" + str(obs).replace("\n", " ")[:70], "warn")
            fails[key] = 0 if ok else fails.get(key, 0) + 1
            self._used.add(name)
            self.history.append((name, args, obs, ok))
            self._emit("tool_result", {"tool": name, "ok": ok, "obs": obs[:1000]})
class Router:
    def __init__(self, llm, root, workers=3, task_budget_s=120, retries=1,
                 trace_rate=0.5, spec_dir=".spec", profile=None, extra_tools=None,
                 permission="workspace", reload_extra=None):
        self.llm = llm
        self.profile = profile or Profile()
        self.extra_tools = dict(extra_tools or {})
        self.reload_extra = reload_extra
        self.permission = permission
        self.events = []
        self.root = os.path.abspath(root)
        self.n = workers
        self.task_budget_s = task_budget_s
        self.retries = retries
        self.trace_rate = trace_rate
        self.facts = Facts()
        self.store = Store(self.root)
        self.filter = Filter()
        self.batch = Batcher()
        self.tasks: Dict[str, Task] = {}
        self.subs: Dict[str, str] = {}
        self.log: List[str] = []
        self.spec = os.path.join(self.root, spec_dir)
        os.makedirs(self.spec, exist_ok=True)
    def say(self, s):
        self.log.append(s)
    def act(self, tid, text, state="run"):
        return None
    def dump_events(self, path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                for e in self.events:
                    f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
            return len(self.events)
        except Exception:
            return 0
    def plan(self, goal: str, hints: str = "") -> List[Task]:
        self.act("", "先看看这件事该拆成几步")
        scope = scope_note(self.root, self.permission)
        if self.permission == "full":
            scope += "\n拆任务时保留用户给的原路径，不要改写成工作目录。"
        elif self.permission == "read":
            scope += "\n如果用户要求写入，在 desc 里说明当前权限不足。"
        else:
            scope += "\n如果用户要求的位置在外面，改成在里面完成，并在 desc 里说明。"
        prompt = (SYSTEM_PROMPT + "\n" + ROUTER_SYS + identity(self.profile.model) + scope +
                  "\n\n目标：" + goal + "\n" + hints +
                  "\n只输出一个 JSON 对象。")
        obj = parse_obj(self.llm(prompt))
        if not obj:
            obj = parse_obj(self.llm(prompt + "\n上一次没有按格式输出。这次只输出那个 JSON 对象，"
                                              "不要解释，不要代码块。"))
        obj = obj or {}
        out = []
        for i, t in enumerate(obj.get("tasks", [])[:8]):
            desc = str(t.get("desc", "")).strip()
            if not desc:
                continue
            out.append(Task(tid="t%d" % (len(out) + 1), desc=desc,
                            check=str(t.get("check", "")).strip() or "true",
                            expect=str(t.get("expect", "")).strip()))
        if out:
            self.act("", "要做的：" + "；".join([_clip(x.desc, 30) for x in out[:3]]))
        return out
    def precheck(self, t: Task) -> str:
        t.check_hash = hashlib.sha1(t.check.encode()).hexdigest()[:8]
        ok, out = self._run_check(t)
        t.check_out = out
        return "vacuous" if ok else "ok"
    def _run_check(self, t: Task):
        try:
            code, out = plat.run(t.check, cwd=self.root, timeout=60)
            if code != 0:
                soft = plat.soft_text_check(t.check, cwd=self.root)
                if soft:
                    t.check_out = (out + "\n（命令按系统代码页没匹配到，按文件实际编码复核：已找到）").strip()
                    return True, t.check_out[-1500:]
                return False, out[-1500:]
            return ((t.expect in out) if t.expect else True), out[-1500:]
        except Exception as e:
            return False, "%s: %s" % (type(e).__name__, e)
    def verify(self, t: Task) -> bool:
        ok, out = self._run_check(t)
        t.check_out = out
        return ok
    def _verdict(self, t: Task, passed: bool) -> str:
        name = (t.desc or t.tid).replace("\n", " ").strip()
        if len(name) > 28:
            name = name[:28] + "…"
        if passed:
            return "「%s」做好了" % name
        why = ""
        for line in (t.check_out or "").splitlines():
            line = line.strip()
            if line and "复核：已找到" not in line:
                why = line
                break
        why = _clip(why, 60)
        return ("「%s」没做成，%s" % (name, why)) if why else ("「%s」没做成" % name)
    def run(self, tasks: List[Task]) -> Dict:
        t0 = time.time()
        for t in tasks:
            self.tasks[t.tid] = t
            if t.thread:
                self.subs[t.thread] = t.tid
            st = self.precheck(t)
            if st == "vacuous":
                t.status = "vacuous"
                self.say("%s 验收空转：开始前就已经通过，不派 Worker" % t.tid)
                self.act(t.tid, "「%s」本来就满足，不用做" % t.desc, "skip")
        live = [t for t in tasks if t.status == "todo"]
        self.say("待执行 %d 条（%d 条被阴性对照拦下）" % (len(live), len(tasks) - len(live)))
        if live:
            self.act("", "拆成了 %d 件事，开始做" % len(live))
        wd = Watchdog(self.tasks, self.root)
        wd.start()
        try:
            for attempt in range(self.retries + 1):
                if not live:
                    break
                for i in range(0, len(live), self.n):
                    batch = live[i:i + self.n]
                    ths = []
                    workers = []
                    for t in batch:
                        t.status = "running"
                        w = Worker(self.llm, self.root, self.facts, self.store,
                                   profile=self.profile, budget_s=self.task_budget_s,
                                   extra_tools=self.extra_tools,
                                   permission=self.permission,
                                   on_act=self.act,
                                   reload_extra=self.reload_extra)
                        th = threading.Thread(target=w.run, args=(t,))
                        workers.append(w)
                        th.start()
                        ths.append((th, t))
                    for th, t in ths:
                        th.join()
                        t.tries += 1
                        passed = self.verify(t)
                        tr = traceability(t)
                        if passed and t.claims >= 2 and tr < self.trace_rate:
                            t.status = "failed"
                            self.say("%s check 通过但可追溯率 %.2f < %.2f，判不可信"
                                     % (t.tid, tr, self.trace_rate))
                        else:
                            t.status = "done" if passed else "failed"
                        self.act(t.tid, self._verdict(t, passed), "done" if passed else "bad")
                        tag = t.tid if attempt == 0 else "%s·重试%d" % (t.tid, attempt)
                        self.say("%s -> %-7s 追溯 %.2f  %s"
                                 % (tag, t.status, tr, (t.answer or "")[:40]))
                live = [t for t in tasks if t.status == "failed"
                        and t.tries <= self.retries
                        and not any(h in (t.answer or "") for h in NO_RETRY_HINTS)]
                for w in workers:
                    self.events.extend(w.events)
        finally:
            wd.stop()
        for n in wd.notes:
            self.say("watchdog: " + n)
        ok = not any(t.status == "failed" for t in tasks)
        return {"ok": ok, "tasks": [t.__dict__ for t in tasks],
                "filter": self.filter.stats, "seconds": round(time.time() - t0, 1)}
    def feed(self, ev: Event) -> str:
        tid = self.subs.get(ev.thread)
        if tid:
            self.say("直通 %s -> %s" % (ev.thread, tid))
            return "direct"
        verdict = self.filter.route(ev)
        if verdict == "drop":
            return "dropped"
        self.batch.add(ev)
        return "batched"
    def drain(self):
        evs = self.batch.take()
        if evs:
            self.say("批处理 %d 条事件" % len(evs))
        return evs
if __name__ == "__main__":
    root = tempfile.mkdtemp(prefix="sa2_")
    open(os.path.join(root, "a.txt"), "w", encoding="utf-8").write("hello\n")
    open(os.path.join(root, "b.txt"), "w", encoding="utf-8").write("world\n")
    show = (lambda n: "type " + n) if plat.IS_WIN else (lambda n: "cat " + n)
    tasks = [
        Task("t1", "把 a.txt 内容写进 out_a.txt", show("out_a.txt"), "hello", thread="th1"),
        Task("t2", "把 b.txt 内容写进 out_b.txt", show("out_b.txt"), "world", thread="th2"),
        Task("t3", "写 ok.txt 内容 done", show("ok.txt"), "done"),
        Task("t4", "空转验收（应被拦下）", plat.check_file("a.txt"), ""),
    ]
    def llm(p):
        if "out_a.txt" in p:
            if "wrote" in p:
                return '{"thought":"done","tool":"finish","args":{"answer":"ok"},"evidence":"out_a.txt"}'
            return ('{"thought":"copy","tool":"write_file","args":{"path":"out_a.txt","content":"hello\\n"},'
                    '"evidence":"read a.txt"}')
        if "out_b.txt" in p:
            if "wrote" in p:
                return '{"thought":"done","tool":"finish","args":{"answer":"ok"},"evidence":"out_b.txt"}'
            return ('{"thought":"copy","tool":"write_file","args":{"path":"out_b.txt","content":"world\\n"},'
                    '"evidence":"read b.txt"}')
        if "ok.txt" in p:
            if "wrote" in p:
                return '{"thought":"done","tool":"finish","args":{"answer":"ok"},"evidence":"ok.txt"}'
            return '{"thought":"mk","tool":"write_file","args":{"path":"ok.txt","content":"done\\n"},"evidence":"spec"}'
        return '{"thought":"x","tool":"finish","args":{"answer":"n/a"}}'
    r = Router(llm, root, workers=3)
    out = r.run(tasks)
    print("ok=%s  %.1fs" % (out["ok"], out["seconds"]))
    for t in out["tasks"]:
        print("  %-3s %-8s 追溯 %.2f  %s" % (t["tid"], t["status"],
                                             traceability(Task(**t)) if False else
                                             (len(t["evidence"]) / t["claims"] if t["claims"] else 1.0),
                                             t["desc"][:28]))
    print("\n--- 事件层 ---")
    for ev in [Event("msg", "im", "th1", "改一下 out_a"),
               Event("msg", "im", "th9", "   "),
               Event("msg", "im", "th8", "有个 bug 需要修"),
               Event("msg", "im", "th8", "又一条")]:
        print("  %-28s -> %s" % (ev.body.strip()[:26], r.feed(ev)))
    print("  批处理取出:", len(r.drain()), "条")
    print("  过滤统计:", r.filter.stats)
    print("\n--- 日志 ---")
    for line in r.log:
        print(" ", line)
