import json
import os
import time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "workspace")
LEDGER = os.path.join(os.path.dirname(HERE), "cost.json")
PRICES = {
    "deepseek-flash": (0.5, 2.0),
    "deepseek-v4-pro": (4.0, 12.0),
    "deepseek-v4-flash": (0.5, 2.0),
    "claude-sonnet-5-5": (21.0, 105.0),
    "claude-opus-5-5": (105.0, 525.0),
    "claude-haiku-5-5": (5.0, 25.0),
    "claude-fable-5-1": (21.0, 105.0),
    "gpt-5": (9.0, 72.0),
    "gpt-5-mini": (1.8, 14.4),
    "gpt-5-nano": (0.4, 3.2),
    "gpt-5.1": (9.0, 72.0),
    "gpt-4o-mini": (1.1, 4.3),
    "qwen-flash": (0.3, 1.2),
    "qwen-plus": (2.0, 6.0),
    "qwen3.8-flash": (0.3, 1.2),
    "qwen3.8-max": (16.0, 64.0),
    "qwen3.7-plus": (2.0, 6.0),
    "kimi-k3": (4.0, 16.0),
    "kimi-k2.7-code": (4.0, 16.0),
    "glm-5.2": (4.0, 16.0),
    "glm-5.3": (6.0, 24.0),
    "glm-4-flash": (0.0, 0.0),
}
def _price(model):
    m = str(model or "").strip().lower()
    if m in PRICES:
        return PRICES[m], m
    for k in sorted(PRICES, key=len, reverse=True):
        if k in m or m in k:
            return PRICES[k], k
    return None, m
def cost_estimate(model, tokens_in=0, tokens_out=0, calls=1):
    p, key = _price(model)
    if p is None:
        return ("单价表里没有 %s。按输入 4 元、输出 16 元 / 百万 token 粗算：\n%s"
                % (model, _fmt(4.0 * float(tokens_in or 0) / 1e6
                               + 16.0 * float(tokens_out or 0) / 1e6)))
    ti = float(tokens_in or 0) * max(1, int(calls or 1))
    to = float(tokens_out or 0) * max(1, int(calls or 1))
    cin = p[0] * ti / 1e6
    cout = p[1] * to / 1e6
    return "\n".join([
        "%s（按 %s 的价）" % (model, key),
        "输入 %s token × %.2f 元/百万 = %.4f 元" % (_fmt(ti), p[0], cin),
        "输出 %s token × %.2f 元/百万 = %.4f 元" % (_fmt(to), p[1], cout),
        "单次合计：%.4f 元" % (cin + cout),
        "跑 %d 次：%.3f 元" % (max(1, int(calls or 1)), cin + cout),
    ])
def cost_log(model, tokens_in=0, tokens_out=0, note=""):
    p, _ = _price(model)
    if p is None:
        p = (4.0, 16.0)
    amt = p[0] * float(tokens_in or 0) / 1e6 + p[1] * float(tokens_out or 0) / 1e6
    rec = {"ts": int(time.time()), "model": str(model or ""),
           "in": int(tokens_in or 0), "out": int(tokens_out or 0),
           "cost": round(amt, 6), "note": str(note or "")[:80]}
    data = []
    try:
        with open(LEDGER, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
    data.append(rec)
    data = data[-500:]
    try:
        with open(LEDGER, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        return "记不下来：%s" % e
    return "记下了：%.4f 元（累计 %d 笔，共 %.3f 元）" % (
        amt, len(data), sum(x.get("cost", 0) for x in data))
def cost_report(days=7):
    try:
        with open(LEDGER, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return "还没有记账。用 cost_log 记一笔试试。"
    if not isinstance(data, list) or not data:
        return "还没有记账。"
    cutoff = time.time() - max(1, int(days or 7)) * 86400
    rows = [x for x in data if x.get("ts", 0) >= cutoff]
    if not rows:
        return "最近 %d 天没有记录" % int(days or 7)
    total = sum(x.get("cost", 0) for x in rows)
    by_model = {}
    for x in rows:
        by_model.setdefault(x.get("model", "?"), [0, 0.0])
        by_model[x.get("model", "?")][0] += 1
        by_model[x.get("model", "?")][1] += x.get("cost", 0)
    lines = ["最近 %d 天：%d 笔，合计 %.3f 元" % (int(days or 7), len(rows), total)]
    for m, (n, c) in sorted(by_model.items(), key=lambda x: -x[1][1]):
        lines.append("  %-26s %3d 笔  %.3f 元（%.0f%%）"
                     % (m, n, c, c * 100.0 / total if total else 0))
    avg = total / len(rows)
    lines.append("平均每笔 %.4f 元" % avg)
    return "\n".join(lines)
def _fmt(n):
    n = float(n or 0)
    if n < 1000:
        return "%d" % n
    if n < 1000000:
        return "%.1fK" % (n / 1000.0)
    return "%.2fM" % (n / 1000000)
def cost_models():
    lines = ["%-24s %10s %10s" % ("模型", "输入", "输出")]
    for k in sorted(PRICES, key=lambda x: PRICES[x][1]):
        lines.append("%-24s %8.2f %8.2f" % (k, PRICES[k][0], PRICES[k][1]))
    return "单价：元 / 百万 token\n" + "\n".join(lines)
TOOLS = {
    "cost_estimate": (cost_estimate, {"model": "str", "tokens_in": "int",
                                      "tokens_out": "int", "calls": "int"},
                      "按模型单价估一次调用花多少钱"),
    "cost_log": (cost_log, {"model": "str", "tokens_in": "int",
                            "tokens_out": "int", "note": "str"},
                 "记一笔花费，方便回头看"),
    "cost_report": (cost_report, {"days": "int"}, "看最近几天花了多少"),
    "cost_models": (cost_models, {}, "列出单价表"),
}
