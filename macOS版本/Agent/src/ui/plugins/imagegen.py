import base64
import json
import os
import time
import urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "..", "config.json")
def _cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
def image_gen(prompt: str, size: str = "1024x1024", model: str = "") -> str:
    c = _cfg()
    base = (c.get("base_url") or "").rstrip("/")
    key = c.get("api_key") or ""
    if not base or not key:
        return "没配置接口地址或 Key，先在设置里填好再生成"
    mdl = model or c.get("image_model") or "gpt-image-1"
    body = json.dumps({"model": mdl, "prompt": prompt,
                       "size": size or "1024x1024", "n": 1}).encode()
    req = urllib.request.Request(
        base + "/images/generations", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        d = json.loads(op.open(req, timeout=180).read())
    except Exception as e:
        return "生成失败：%s" % str(e)[:180]
    items = d.get("data") or []
    if not items:
        return "接口没返回图片：%s" % json.dumps(d, ensure_ascii=False)[:220]
    it = items[0]
    out_dir = os.path.join(HERE, "..", "workspace")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "gen-%s.png" % time.strftime("%Y%m%d-%H%M%S"))
    try:
        if it.get("b64_json"):
            with open(path, "wb") as f:
                f.write(base64.b64decode(it["b64_json"]))
        elif it.get("url"):
            with open(path, "wb") as f:
                f.write(op.open(it["url"], timeout=180).read())
        else:
            return "返回格式不认识，既没有 b64_json 也没有 url"
    except Exception as e:
        return "存图失败：%s" % str(e)[:160]
    return "已生成图片：%s" % os.path.abspath(path)
TOOLS = {
    "image_gen": (image_gen, {"prompt": "str", "size": "str", "model": "str"},
                  "按文字生成图片，返回本地文件路径"),
}
