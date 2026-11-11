import base64
import json
import os
import re
import sys
import threading
import uuid
ROOT = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(ROOT, "ui", "local_models.json")
REG_LOCK = threading.RLock()
FAMILY = (
    ("qwen", r"qwen|通义|qwen2|qwen3"),
    ("llama", r"llama|meta-llama|alpaca|vicuna"),
    ("deepseek", r"deepseek|deepseek-v|deepseek-r"),
    ("glm", r"chatglm|glm-|智谱|codegeex"),
    ("mistral", r"mistral|mixtral"),
    ("gemma", r"gemma"),
    ("phi", r"phi-?[234]|microsoft/phi"),
    ("yi", r"yi-|01-ai|lingyi"),
    ("baichuan", r"baichuan"),
    ("internlm", r"internlm|书生"),
    ("bert", r"bert|roberta"),
    ("t5", r"\bt5\b|flan-t5"),
    ("whisper", r"whisper"),
    ("llava", r"llava|internvl|minicpm-v|qwen-vl|vision"),
    ("gpt", r"gpt2|gpt-j|gpt-neo"),
)
QUANTS = (
    ("IQ2_XXS", r"iq2_xxs"), ("IQ2_XS", r"iq2_xs"),
    ("Q2_K", r"q2_k"), ("Q3_K_M", r"q3_k_m"), ("Q3_K_S", r"q3_k_s"),
    ("Q4_0", r"q4_0"), ("Q4_K_M", r"q4_k_m"), ("Q4_K_S", r"q4_k_s"),
    ("Q5_K_M", r"q5_k_m"), ("Q5_0", r"q5_0"),
    ("Q6_K", r"q6_k"), ("Q8_0", r"q8_0"),
    ("AWQ", r"awq"), ("GPTQ", r"gptq"), ("FP8", r"fp8"),
    ("INT4", r"int4"), ("INT8", r"int8"),
    ("BF16", r"bf16|bfloat16"), ("FP16", r"fp16|float16"),
    ("FP32", r"fp32|float32"),
)
HEAD_EXT = (".json", ".gguf", ".safetensors", ".bin", ".pt", ".onnx",
            ".model", ".txt", ".yaml", ".yml", ".toml", ".md")
def _b64head(v):
    try:
        raw = base64.b64decode(str(v or "")[:2048])
    except Exception:
        return b""
    return raw[:64]
def _norm_entries(entries):
    out = []
    for e in (entries or [])[:3000]:
        if not isinstance(e, dict):
            continue
        p = str(e.get("path") or "").replace("\\", "/")[:300]
        if not p or p.startswith("/") or ".." in p.split("/"):
            continue
        name = p.rsplit("/", 1)[-1]
        try:
            size = max(0, int(e.get("size") or 0))
        except Exception:
            size = 0
        out.append({"path": p, "name": name, "lower": name.lower(),
                    "size": size, "head": _b64head(e.get("head")),
                    "text": str(e.get("text") or "")[:200000]})
    return out
def _slug(name):
    s = re.sub(r"[^a-z0-9._-]+", "-", str(name or "").lower()).strip("-.")
    return (s or "local-model")[:64]
def _cfg_of(files):
    for f in files:
        if f["lower"] == "config.json" and f["text"].strip().startswith("{"):
            try:
                d = json.loads(f["text"])
                return d if isinstance(d, dict) else {}
            except Exception:
                return {}
    return {}
def _tok_cfg(files):
    for f in files:
        if f["lower"] == "tokenizer_config.json" and f["text"].strip().startswith("{"):
            try:
                d = json.loads(f["text"])
                return d if isinstance(d, dict) else {}
            except Exception:
                return {}
    return {}
def _family(hay, cfg):
    s = (hay + " " + str(cfg.get("model_type") or "") + " "
         + " ".join(str(x) for x in (cfg.get("architectures") or []))).lower()
    for key, pat in FAMILY:
        if re.search(pat, s):
            return key
    return "unknown"
def _params(hay):
    m = re.search(r"(?:^|[^0-9])(\d+(?:\.\d+)?)\s*[bB](?![a-zA-Z])", hay)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass
    return 0.0
def _quant(hay):
    u = hay.upper().replace("-", "_")
    for label, pat in QUANTS:
        if re.search(pat, u, re.I):
            return label
    return ""
def _context(hay, cfg):
    for k in ("max_position_embeddings", "n_positions", "seq_length",
              "max_sequence_length", "n_ctx", "context_length"):
        v = cfg.get(k)
        if isinstance(v, int) and 512 <= v <= 4_000_000:
            return v
    m = re.search(r"(?:^|[^0-9])(\d{2,4})[kK](?![a-zA-Z])", hay)
    if m:
        return min(4_000_000, int(m.group(1)) * 1024)
    return 32768
def inspect_manifest(entries, name_hint=""):
    files = _norm_entries(entries)
    if not files:
        return {"ok": False, "error": "没有读到文件；请拖入模型文件夹本身",
                "formats": [], "confidence": 0.0}
    names = [f["lower"] for f in files]
    hay = " ".join([str(name_hint or "")] + [f["path"] for f in files]).lower()
    formats = set()
    weight_files = []
    for f in files:
        n = f["lower"]
        if n.endswith(".gguf"):
            formats.add("GGUF")
            weight_files.append(f["path"])
            if "mmproj" in n:
                formats.add("Multimodal")
        if n.endswith(".safetensors"):
            formats.add("SafeTensors")
            weight_files.append(f["path"])
        if n.endswith((".bin", ".pt", ".pth", ".model")):
            formats.add("PyTorch")
            weight_files.append(f["path"])
        if n.endswith(".onnx"):
            formats.add("ONNX")
            weight_files.append(f["path"])
        if n.endswith((".engine", ".plan")):
            formats.add("TensorRT-LLM")
            weight_files.append(f["path"])
        if n in ("modelfile", "modelfile.txt"):
            formats.add("Ollama")
        if n == "config.json":
            formats.add("HuggingFace")
        if n == "adapter_config.json":
            formats.add("LoRA")
        if n == "quantize_config.json":
            formats.add("Quantized")
        if n in ("preprocessor_config.json", "processor_config.json") or "mmproj" in n:
            formats.add("Multimodal")
        if n == "tokenizer_config.json":
            formats.add("Tokenizer")
        if n == "params.json":
            formats.add("MetaWeights")
        if f["head"][:4] == b"GGUF":
            formats.add("GGUF")
    cfg = _cfg_of(files)
    tok = _tok_cfg(files)
    family = _family(hay, cfg)
    params = _params(hay)
    quant = _quant(hay)
    ctx = _context(hay, cfg)
    multimodal = ("Multimodal" in formats or family in ("llava", "whisper")
                  or bool(re.search(r"vl|vision|mmproj|clip", hay)))
    adapter = "LoRA" in formats
    template = str(tok.get("chat_template") or "")[:400]
    if not template:
        template = {"qwen": "chatml", "llama": "llama3", "deepseek": "deepseek",
                    "glm": "chatglm", "mistral": "mistral", "gemma": "gemma",
                    "phi": "phi3", "yi": "chatml", "baichuan": "baichuan",
                    "internlm": "internlm"}.get(family, "auto")
    if "Ollama" in formats:
        backend, base = "Ollama", "http://127.0.0.1:11434/v1"
        command = "ollama create %s -f Modelfile && ollama run %s" % ("<name>", "<name>")
    elif "GGUF" in formats or "MetaWeights" in formats:
        backend, base = "llama.cpp / LM Studio", "http://127.0.0.1:8080/v1"
        command = ("llama-server -m <model.gguf> --ctx-size %d --host 127.0.0.1 "
                   "--port 8080" % ctx)
    elif "TensorRT-LLM" in formats:
        backend, base = "TensorRT-LLM / Triton", "http://127.0.0.1:8000/v1"
        command = "trtllm-serve serve <model-dir> --backend pytorch"
    elif "ONNX" in formats:
        backend, base = "ONNX Runtime / LocalAI", "http://127.0.0.1:8080/v1"
        command = "local-ai run --models-dir <model-dir>"
    else:
        backend, base = "vLLM / Transformers", "http://127.0.0.1:8000/v1"
        command = ("vllm serve <model-dir> --served-model-name <name> "
                   "--max-model-len %d" % ctx)
    root = str(name_hint or "").strip()
    if not root:
        first = files[0]["path"].split("/")[0]
        root = first if len(files) > 1 else first.rsplit(".", 1)[0]
    slug = _slug(root)
    conf = 0.34 + min(0.24, 0.08 * len(formats))
    if weight_files:
        conf += 0.26
    if any(f["head"][:4] == b"GGUF" for f in files):
        conf += 0.08
    if cfg:
        conf += 0.14
    if family != "unknown":
        conf += 0.08
    conf = round(min(0.97, conf), 2)
    warnings = []
    if not weight_files:
        warnings.append("未发现权重文件（.gguf / .safetensors / .bin / .onnx），只生成接入配置")
    if adapter:
        warnings.append("检测到适配器（LoRA），需要配合基座模型一起加载")
    if multimodal:
        warnings.append("检测到多模态组件，确认推理后端支持对应模态")
    if quant:
        warnings.append("量化格式 %s，需后端支持" % quant)
    if len(files) >= 3000:
        warnings.append("文件清单达到上限，仅解析前 3000 项")
    return {
        "ok": True, "name": root, "model": slug,
        "formats": sorted(formats), "family": family,
        "params_b": params, "quant": quant, "context": ctx,
        "multimodal": multimodal, "adapter": adapter,
        "template": template, "backend": backend, "base_url": base,
        "command": command, "file_count": len(files),
        "weight_files": weight_files[:8],
        "config": {k: cfg.get(k) for k in
                   ("model_type", "architectures", "torch_dtype", "hidden_size",
                    "num_hidden_layers", "vocab_size") if k in cfg},
        "confidence": conf, "warnings": warnings,
    }
def _load():
    try:
        with open(REGISTRY, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except Exception:
        return []
def _save(items):
    tmp = REGISTRY + "." + uuid.uuid4().hex[:8] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items[:100], f, ensure_ascii=False, indent=1)
    os.replace(tmp, REGISTRY)
def list_models():
    return _load()
def register_model(info, override=None):
    if not isinstance(info, dict) or not info.get("model"):
        return {"ok": False, "error": "缺少模型信息"}
    with REG_LOCK:
        return _register_locked(info, override)
def _register_locked(info, override):
    o = dict(info)
    for k in ("file_count", "weight_files", "config", "warnings", "confidence",
              "formats", "command", "template", "context", "params_b", "quant",
              "family", "backend", "base_url", "multimodal", "adapter", "name"):
        o.setdefault(k, info.get(k))
    if isinstance(override, dict):
        for k in ("base_url", "model", "provider", "api_key"):
            if override.get(k):
                o[k] = str(override[k])[:300]
    o["id"] = str(o.get("model") or "local-model")[:64]
    o["provider"] = str(o.get("provider") or "custom")
    o["api_key"] = str(o.get("api_key") or "")
    o["base_url"] = str(o.get("base_url") or "http://127.0.0.1:8000/v1")
    o.pop("head", None)
    o.pop("text", None)
    items = [x for x in _load() if str(x.get("id")) != o["id"]]
    items.insert(0, o)
    _save(items)
    return {"ok": True, "model": o, "total": len(items)}
def unregister_model(mid):
    mid = str(mid or "")[:64]
    with REG_LOCK:
        items = [x for x in _load() if str(x.get("id")) != mid]
        _save(items)
    return {"ok": True, "total": len(items)}
def main():
    if "--stdin" not in sys.argv:
        print(json.dumps({"error": "use --stdin"}, ensure_ascii=False))
        return
    try:
        d = json.loads(sys.stdin.read() or "{}")
    except Exception as e:
        print(json.dumps({"error": "bad json: %s" % e}, ensure_ascii=False))
        return
    a = str(d.get("action") or "inspect")
    if a == "inspect":
        r = inspect_manifest(d.get("entries"), str(d.get("name") or ""))
    elif a == "register":
        r = register_model(d.get("info") or {}, d.get("override"))
    elif a == "list":
        r = {"ok": True, "models": list_models()}
    elif a == "unregister":
        r = unregister_model(d.get("id"))
    else:
        r = {"error": "unknown action"}
    print(json.dumps(r, ensure_ascii=False))
if __name__ == "__main__":
    main()
