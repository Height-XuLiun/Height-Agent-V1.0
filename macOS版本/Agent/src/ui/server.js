const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { spawn, execFile, execFileSync } = require('child_process');
const HERE = __dirname;
const PORT = Number(process.env.SA_PORT || 5000);
const BAD_PORTS = new Set([1, 7, 9, 11, 13, 15, 17, 19, 21, 22, 23, 25, 37, 42, 43, 53,
  69, 77, 79, 87, 95, 101, 102, 103, 104, 109, 110, 111, 113, 115, 117, 119, 123, 135,
  137, 139, 143, 161, 179, 389, 427, 465, 512, 513, 514, 515, 526, 530, 531, 532, 540,
  548, 554, 556, 563, 587, 601, 636, 989, 990, 993, 995, 1719, 1720, 1723, 2049, 3659,
  4045, 5060, 5061, 6000, 6566, 6665, 6666, 6667, 6668, 6669, 6697, 10080]);
const HOST = process.env.SA_HOST || (process.argv.includes('--lan') ? '0.0.0.0' : '127.0.0.1');
const LOCAL_ONLY = ['127.0.0.1', 'localhost', '::1'].includes(HOST);
const TOKEN = process.env.SA_TOKEN || crypto.randomBytes(6).toString('hex');
const IS_WIN = process.platform === 'win32';
function pickPython() {
  const forced = (process.env.SA_PYTHON || '').trim();
  if (forced) return [forced];
  const cands = IS_WIN ? [['py', ['-3']], ['python', []], ['python3', []]]
                       : [['python3', []], ['python', []]];
  for (const [bin, pre] of cands) {
    try {
      const out = execFileSync(bin, pre.concat(['-c', 'import sys;print(sys.version_info[0])']),
        { timeout: 8000, encoding: 'utf8', windowsHide: true });
      if (String(out).trim() === '3') return [bin].concat(pre);
    } catch (e) {}
  }
  return IS_WIN ? ['python'] : ['python3'];
}
const PYARGV = pickPython();
const PY = PYARGV[0];
const PY_PRE = PYARGV.slice(1);
const JOBS = new Map();
const STOPPED = new Set();
const SESS_FILE = path.join(HERE, 'sessions.json');
const SESS_BAK = path.join(HERE, 'sessions.bak.json');
const SESS_FLAG = path.join(HERE, 'sessions.cleared');
function readSessions(f) {
  try {
    const j = JSON.parse(fs.readFileSync(f, 'utf8'));
    return Array.isArray(j) ? j : [];
  } catch (e) { return []; }
}
function writeSessions(data) {
  const old = readSessions(SESS_FILE);
  if (old.length) {
    try { fs.writeFileSync(SESS_BAK, JSON.stringify(old, null, 1), 'utf8'); } catch (e) {}
  }
  const tmp = SESS_FILE + '.' + Math.random().toString(16).slice(2, 10) + '.tmp';
  try {
    fs.writeFileSync(tmp, JSON.stringify(data.slice(0, 60), null, 1), 'utf8');
    fs.renameSync(tmp, SESS_FILE);
  } finally {
    try { if (fs.existsSync(tmp)) fs.unlinkSync(tmp); } catch (e) {}
  }
}
let PLUGINS = [];
let bridge = null;
let bridgeBuf = '';
function lanIPs() {
  const out = [];
  const all = os.networkInterfaces();
  for (const k of Object.keys(all)) {
    for (const a of all[k] || []) {
      if (a.family === 'IPv4' && !a.internal) out.push(a.address);
    }
  }
  return out;
}
function pyArgs(script) {
  return PY_PRE.concat([path.join(HERE, script)]);
}
function startBridge() {
  bridge = spawn(PY, pyArgs('bridge.py'), {
    cwd: path.dirname(HERE),
    env: Object.assign({}, process.env, { PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' }),
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  });
  bridge.stdout.setEncoding('utf8');
  bridge.stdout.on('data', (chunk) => {
    bridgeBuf += chunk;
    let i;
    while ((i = bridgeBuf.indexOf('\n')) >= 0) {
      const line = bridgeBuf.slice(0, i).trim();
      bridgeBuf = bridgeBuf.slice(i + 1);
      if (!line) continue;
      let msg;
      try { msg = JSON.parse(line); } catch (e) { continue; }
      onBridge(msg);
    }
  });
  bridge.stderr.setEncoding('utf8');
  bridge.stderr.on('data', (d) => {
    const s = String(d).trim();
    if (s) console.error('[bridge]', s.slice(0, 400));
  });
  bridge.on('error', (e) => {
    console.error('[bridge] 启动失败:', e.message);
    bridge = null;
  });
  bridge.on('exit', (code) => {
    if (code !== 0) console.error('[bridge] 退出，code =', code);
    bridge = null;
    for (const [id, job] of JOBS) {
      if (job.done) continue;
      pushJob(id, { t: '错误：Agent 进程已退出（' + code + '）' });
      finishJob(id);
    }
  });
}
function errCN(raw) {
  const s = String(raw || '');
  if (/[\u4e00-\u9fff]/.test(s)) return s;
  const m = s.match(/\b(400|401|402|403|404|408|409|422|429|500|502|503|504)\b/);
  const map = {
    400: '请求被拒绝，检查模型 ID 和消息格式', 401: 'API Key 无效或已过期',
    402: 'API额度已耗尽', 403: '没有权限调用该模型',
    404: '接口地址不对，检查是否以 /v1 结尾', 408: '请求超时，服务商没有响应',
    409: '请求冲突，稍后再试', 422: '请求被拒绝，检查模型 ID 和消息格式',
    429: '调用太频繁或额度已用尽，稍后再试', 500: '模型服务商内部出错',
    502: '模型服务商网关出错', 503: '模型服务商暂时不可用', 504: '模型服务商响应超时'
  };
  if (m && map[m[1]]) return map[m[1]];
  if (/timeout|timed out/i.test(s)) return '请求超时，服务商没有响应';
  if (/refused|enotfound|getaddrinfo|econnrefused/i.test(s)) return '连不上接口地址，检查是否填对';
  return '接口调用失败，检查 Key 和接口地址';
}
function onBridge(msg) {
  if (msg.t && !msg.job) { console.log('[bridge]', msg.t); return; }
  if (msg.job && STOPPED.has(msg.job)) return;
  const job = JOBS.get(msg.job);
  if (!job) return;
  if (msg.usage) pushJob(msg.job, { usage: msg.usage });
  if (msg.think) pushJob(msg.job, { think: msg.think });
  if (msg.act) pushJob(msg.job, { act: msg.act });
  if (msg.note) pushJob(msg.job, { note: msg.note });
  if (msg.t) pushJob(msg.job, { t: msg.t });
  if (msg.error) {
    job.error = msg.error;
    pushJob(msg.job, { t: '错误：' + errCN(msg.error) });
    finishJob(msg.job);
  }
  if (msg.done) {
    job.result = msg.result;
    finishJob(msg.job);
  }
}
function newJob() {
  const id = Math.random().toString(16).slice(2, 10);
  JOBS.set(id, { subs: new Set(), buf: [], done: false, result: null, error: null, ts: Date.now() });
  return id;
}
function pushJob(id, evt) {
  const job = JOBS.get(id);
  if (!job) return;
  job.buf.push(evt);
  job.subs.forEach((fn) => { try { fn(evt); } catch (e) {} });
}
function finishJob(id) {
  const job = JOBS.get(id);
  if (!job || job.done) return;
  job.done = true;
  const evt = { done: true, result: job.result };
  job.subs.forEach((fn) => { try { fn(evt); } catch (e) {} });
  job.subs.clear();
}
setInterval(() => {
  const now = Date.now();
  for (const [id, job] of JOBS) {
    if (job.done && now - job.ts > 600000) JOBS.delete(id);
  }
}, 60000);
function ensureBridge() {
  if (!bridge || bridge.killed) startBridge();
  return bridge;
}
function loadPlugins(cb) {
  execFile(PY, pyArgs('pluglist.py'), { timeout: 20000, windowsHide: true }, (err, stdout) => {
    if (err) { PLUGINS = []; return cb(PLUGINS); }
    try { PLUGINS = JSON.parse(stdout || '{}').plugins || []; } catch (e) { PLUGINS = []; }
    cb(PLUGINS);
  });
}
function pyTool(args, input, cb) {
  const p = spawn(PY, pyArgs('pluglist.py').concat(args), { windowsHide: true });
  let out = '';
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    let d = {};
    try { d = JSON.parse(out || '{}'); } catch (e) { d = { ok: false, msg: '解析失败' }; }
    cb(d);
  };
  p.stdout.on('data', (c) => { out += c; });
  p.stderr.on('data', () => {});
  p.on('close', finish);
  p.on('error', () => { done = true; cb({ ok: false, msg: 'Python 没跑起来' }); });
  try { p.stdin.end(input || ''); } catch (e) {}
  setTimeout(() => { if (!done) { done = true; try { p.kill(); } catch (e) {} cb({ ok: false, msg: '超时' }); } }, 25000);
}
function bridgeOnce(payload, cb) {
  const p = spawn(PY, pyArgs('bridge.py'), { windowsHide: true });
  let out = '';
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    let msg = null;
    out.split('\n').forEach((line) => {
      if (!line.trim() || msg) return;
      try {
        const m = JSON.parse(line);
        if (typeof m.title === 'string' || m.mkgen) msg = m;
      } catch (e) {}
    });
    cb(msg || {});
  };
  p.stdout.on('data', (c) => { out += c; });
  p.stderr.on('data', () => {});
  p.on('close', finish);
  p.on('error', () => { if (!done) { done = true; cb({}); } });
  try { p.stdin.end(JSON.stringify(payload) + '\n'); } catch (e) {}
  setTimeout(() => { if (!done) { done = true; try { p.kill(); } catch (e) {} cb({}); } }, 30000);
}
function send(res, code, body, ctype, headers) {
  const b = Buffer.isBuffer(body) ? body : Buffer.from(String(body), 'utf8');
  res.writeHead(code, Object.assign({
    'Content-Type': (ctype || 'application/json') + '; charset=utf-8',
    'Content-Length': b.length,
    'Cache-Control': 'no-store',
  }, headers || {}));
  res.end(b);
}
function localModelCall(payload, cb) {
  const script = path.join(path.dirname(HERE), 'localmodel.py');
  let child;
  try {
    child = spawn(PY, PY_PRE.concat([script, '--stdin']), { windowsHide: true });
  } catch (e) {
    return cb({ error: String((e && e.message) || e).slice(0, 160) });
  }
  let out = '', err = '', done = false;
  const finish = (r) => {
    if (done) return;
    done = true; clearTimeout(timer); cb(r);
  };
  const timer = setTimeout(() => {
    try { child.kill(); } catch (e) {}
    finish({ error: '解析超时' });
  }, 15000);
  child.stdout.on('data', (c) => { if (out.length < 8 * 1024 * 1024) out += c; });
  child.stderr.on('data', (c) => { if (err.length < 4096) err += c; });
  child.on('error', (e) => finish({ error: String((e && e.message) || e).slice(0, 160) }));
  child.on('close', () => {
    try {
      finish(JSON.parse(String(out).trim().split('\n').pop() || '{}'));
    } catch (e) {
      finish({ error: '解析失败: ' + String(err || e.message || e).slice(0, 160) });
    }
  });
  child.stdin.on('error', () => {});
  try { child.stdin.end(JSON.stringify(payload)); }
  catch (e) { finish({ error: '输入序列化失败' }); }
}
function readBody(req, cb) {
  const MAX = 8 * 1024 * 1024;
  let raw = '', n = 0, over = false;
  req.on('data', (c) => {
    n += c.length;
    if (n > MAX) { over = true; return; }
    raw += c;
  });
  req.on('end', () => {
    if (over) return cb(null);
    try { cb(JSON.parse(raw || '{}')); } catch (e) { cb(null); }
  });
}
const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://127.0.0.1');
  const p = u.pathname;
  const ip = String(req.socket.remoteAddress || '').replace(/^::ffff:/, '');
  const remoteLocal = ip === '' || ip === '127.0.0.1' || ip === '::1';
  const qk = u.searchParams.get('k');
  if (!LOCAL_ONLY && qk === TOKEN) {
    res.setHeader('Set-Cookie', 'sa_k=' + TOKEN + '; Path=/; SameSite=Lax; Max-Age=31536000');
  }
  if (!LOCAL_ONLY && !remoteLocal) {
    const ck = String(req.headers.cookie || '');
    const ok = qk === TOKEN || ck.split(';').some((c) => c.trim() === 'sa_k=' + TOKEN);
    if (!ok) {
      return send(res, 401,
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        + '<body style="font:15px/1.8 system-ui;padding:32px">需要访问令牌。'
        + '请用启动日志里带 <code>?k=</code> 的地址打开一次。</body>', 'text/html');
    }
  }
  if (req.method === 'GET' && p === '/api/info') {
    return send(res, 200, JSON.stringify({
      os: process.platform, arch: process.arch, node: process.version,
      python: PYARGV.join(' '), host: HOST, port: PORT,
      lan: lanIPs(), secure: !LOCAL_ONLY,
    }));
  }
  if (req.method === 'GET' && (p === '/' || p === '/index.html')) {
    fs.readFile(path.join(HERE, 'index.html'), (err, buf) => {
      if (err) return send(res, 500, 'index.html 读取失败', 'text/plain');
      send(res, 200, buf, 'text/html');
    });
    return;
  }
  if (req.method === 'GET' && p.startsWith('/logos/')) {
    const fp = path.join(HERE, 'logos', path.basename(p));
    const ct = { '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon',
                 '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp' }
                 [path.extname(fp).toLowerCase()] || 'application/octet-stream';
    return fs.readFile(fp, (err, buf) => {
      if (err) return send(res, 404, 'not found', 'text/plain');
      send(res, 200, buf, ct);
    });
  }
  if (req.method === 'GET' && p === '/backdrop.js') {
    return fs.readFile(path.join(HERE, 'backdrop.js'), (err, buf) => {
      if (err) return send(res, 404, 'not found', 'text/plain');
      send(res, 200, buf, 'application/javascript');
    });
  }
  if (req.method === 'GET' && p === '/manifest.webmanifest') {
    return fs.readFile(path.join(HERE, 'manifest.webmanifest'), (err, buf) => {
      if (err) return send(res, 404, 'not found', 'text/plain');
      send(res, 200, buf, 'application/manifest+json');
    });
  }
  if (req.method === 'GET' && p.startsWith('/icons/')) {
    const fp = path.join(HERE, 'icons', path.basename(p));
    return fs.readFile(fp, (err, buf) => {
      if (err) return send(res, 404, 'not found', 'text/plain');
      send(res, 200, buf, 'image/png');
    });
  }
  if (req.method === 'GET' && p.startsWith('/fonts/')) {
    const fp = path.join(HERE, 'fonts', path.basename(p));
    return fs.readFile(fp, (err, buf) => {
      if (err) return send(res, 404, 'not found', 'text/plain');
      const ext = path.extname(fp);
      const ct = ext === '.css' ? 'text/css' : 'font/woff2';
      send(res, 200, buf, ct);
    });
  }
  if (req.method === 'GET' && p.startsWith('/vendor/')) {
    const fp = path.join(HERE, p.replace(/^\/+/, ''));
    const root = path.join(HERE, 'vendor');
    if (!path.resolve(fp).startsWith(path.resolve(root) + path.sep)) {
      return send(res, 403, 'forbidden', 'text/plain');
    }
    return fs.readFile(fp, (err, buf) => {
      if (err) return send(res, 404, 'not found', 'text/plain');
      const ext = path.extname(fp).toLowerCase();
      const ct = { '.js': 'application/javascript', '.css': 'text/css',
        '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf',
        '.svg': 'image/svg+xml' }[ext] || 'application/octet-stream';
      send(res, 200, buf, ct);
    });
  }
  if (req.method === 'GET' && p === '/file') {
    const raw = path.resolve(HERE, String(u.searchParams.get('path') || '').trim());
    const roots = [path.join(HERE, 'workspace')].concat(
      ['Desktop', 'Pictures', 'Downloads'].map((d) => path.join(os.homedir(), d)));
    const inside = roots.some((r) => {
      const rr = path.resolve(r);
      return raw === rr || raw.startsWith(rr + path.sep);
    });
    if (!inside) return send(res, 403, 'forbidden', 'text/plain');
    const ext = path.extname(raw).toLowerCase();
    const cts = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
      '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp' };
    if (!cts[ext]) return send(res, 403, 'not an image', 'text/plain');
    return fs.readFile(raw, (err, buf) => {
      if (err) return send(res, 404, 'not found', 'text/plain');
      if (buf.length > 32 * 1024 * 1024) return send(res, 413, 'too large', 'text/plain');
      send(res, 200, buf, cts[ext]);
    });
  }
  if (req.method === 'GET' && p === '/plugins') {
    return loadPlugins((list) => send(res, 200, JSON.stringify(list)));
  }
  if (req.method === 'GET' && p === '/plugin-src') {
    const name = u.searchParams.get('name') || '';
    return pyTool(['src', name], '', (d) => {
      send(res, d.ok ? 200 : 404, JSON.stringify(d));
    });
  }
  if (req.method === 'POST' && p === '/mkplugin') {
    return readBody(req, (data) => {
      if (!data) return send(res, 400, '{"error":"bad json"}');
      pyTool(['make', String(data.name || ''), String(data.desc || '')],
        String(data.code || ''), (d) => {
          if (d.plugins) PLUGINS = d.plugins;
          send(res, 200, JSON.stringify(d));
        });
    });
  }
  if (req.method === 'POST' && p === '/rmplugin') {
    return readBody(req, (data) => {
      if (!data) return send(res, 400, '{"error":"bad json"}');
      pyTool(['drop', String(data.name || '')], '', (d) => {
        if (d.plugins) PLUGINS = d.plugins;
        send(res, 200, JSON.stringify(d));
      });
    });
  }
  if (req.method === 'POST' && p === '/plugin-install') {
    return readBody(req, (data) => {
      if (!data) return send(res, 400, '{"error":"bad json"}');
      pyTool(['install', String(data.src || data.url || ''), String(data.desc || '')], '', (d) => {
        if (d.plugins) PLUGINS = d.plugins;
        send(res, 200, JSON.stringify(d));
      });
    });
  }
  if (p === '/sessions') {
    const f = SESS_FILE;
    if (req.method === 'GET') {
      const cleared = fs.existsSync(SESS_FLAG);
      let data = readSessions(f);
      if (!data.length && !cleared) {
        data = readSessions(SESS_BAK);
        if (data.length) { try { writeSessions(data); } catch (e) {} }
      }
      return send(res, 200, JSON.stringify(data), 'application/json',
                  cleared ? { 'X-SA-Cleared': '1' } : null);
    }
    if (req.method === 'POST') {
      return readBody(req, (data) => {
        if (!Array.isArray(data)) return send(res, 400, '{"error":"expect array"}');
        if (data.length > 60) return send(res, 413, '{"error":"too many sessions"}');
        for (const item of data) {
          if (!item || typeof item !== 'object' || Array.isArray(item))
            return send(res, 400, '{"error":"bad session item"}');
          if (JSON.stringify(item).length > 512 * 1024)
            return send(res, 413, '{"error":"session too large"}');
        }
        const force = /[?&]force=(1|true|yes)/.test(req.url || '');
        const replace = /[?&]replace=(1|true|yes)/.test(req.url || '');
        if (!data.length && !force) {
          const kept = readSessions(f);
          if (kept.length) {
            return send(res, 409, JSON.stringify({ ok: false, reason: 'refuse-empty', kept: kept.length }));
          }
        }
        if (data.length && !replace) {
          const old = readSessions(f);
          if (old.length) {
            const idx = new Map();
            const key = (s) => (s && typeof s === 'object') ? (s.id || ('t:' + String(s.title))) : String(Math.random());
            old.forEach((s) => idx.set(key(s), s));
            data.forEach((s) => idx.set(key(s), s));
            data = Array.from(idx.values()).sort((a, b) => ((b && b.ts) || 0) - ((a && a.ts) || 0)).slice(0, 60);
          }
        }
        try {
          writeSessions(data);
          if (!data.length && force) fs.writeFileSync(SESS_FLAG, 'cleared by user\n', 'utf8');
          else if (fs.existsSync(SESS_FLAG)) fs.unlinkSync(SESS_FLAG);
          send(res, 200, '{"ok":true}');
        } catch (e) {
          send(res, 500, JSON.stringify({ error: String(e) }));
        }
      });
    }
  }
  if (req.method === 'POST' && p === '/config') {
    return readBody(req, (data) => {
      if (!data) return send(res, 400, '{"error":"bad json"}');
      try {
        const f = path.join(HERE, 'config.json');
        let old = {};
        try { const t = fs.readFileSync(f, 'utf8'); const j = JSON.parse(t); if (j && typeof j === 'object') old = j; } catch (e) {}
        for (const k of Object.keys(data)) {
          old[k] = data[k];
        }
        const text = JSON.stringify(old, null, 2);
        if (text.length > 256 * 1024) return send(res, 413, '{"error":"config too large"}');
        const tmp = f + '.' + Math.random().toString(16).slice(2, 10) + '.tmp';
        try {
          fs.writeFileSync(tmp, text, 'utf8');
          fs.renameSync(tmp, f);
        } finally {
          try { if (fs.existsSync(tmp)) fs.unlinkSync(tmp); } catch (e) {}
        }
        send(res, 200, '{"ok":true}');
      } catch (e) {
        send(res, 500, JSON.stringify({ error: String(e) }));
      }
    });
  }
  if (req.method === 'GET' && p === '/config') {
    const f = path.join(HERE, 'config.json');
    fs.readFile(f, 'utf8', (err, txt) => {
      if (err) return send(res, 200, '{}');
      try { JSON.parse(txt); } catch (e) { return send(res, 200, '{}'); }
      send(res, 200, txt);
    });
    return;
  }
  if (req.method === 'POST' && p === '/run') {
    return readBody(req, (data) => {
      if (!data) return send(res, 400, '{"error":"bad json"}');
      const id = newJob();
      const b = ensureBridge();
      try {
        b.stdin.write(JSON.stringify({
          job: id,
          config: data.config || {},
          tasks: data.tasks || [],
          goal: data.goal || '',
        }) + '\n');
      } catch (e) {
        pushJob(id, { t: '错误：' + errCN(e.message) });
        finishJob(id);
      }
      send(res, 200, JSON.stringify({ id }));
    });
  }
  if (req.method === 'POST' && p === '/title') {
    return readBody(req, (data) => {
      const text = String((data && data.text) || '');
      if (!text.trim()) return send(res, 200, '{"title":""}');
      bridgeOnce({ title: true, config: (data && data.config) || {}, text }, (m) => {
        send(res, 200, JSON.stringify({ title: (m && m.title) || '' }));
      });
    });
  }
  if (req.method === 'POST' && p === '/mkgen') {
    return readBody(req, (data) => {
      const d = data || {};
      bridgeOnce({
        mkgen: true, config: d.config || {},
        name: d.name || '', desc: d.desc || '', how: d.how || '',
      }, (m) => {
        send(res, 200, JSON.stringify({
          ok: !!(m && m.ok), msg: (m && m.msg) || '没生成出来',
          code: (m && m.code) || '', plugins: [],
        }));
      });
    });
  }
  if (req.method === 'POST' && p === '/models') {
    return readBody(req, (data) => {
      const base = String((data && data.base_url) || '').replace(/\/+$/, '');
      const key = String((data && data.api_key) || '');
      if (!base) return send(res, 200, '{"error":"缺接口地址"}');
      const anth = String((data && data.provider) || '').toLowerCase() === 'anthropic'
        || /anthropic/i.test(base);
      let target;
      try { target = new URL(base + '/models' + (anth ? '?limit=100' : '')); } catch (e) {
        return send(res, 200, '{"error":"地址无效"}');
      }
      const lib = target.protocol === 'https:' ? require('https') : require('http');
      const headers = anth
        ? { 'x-api-key': key, 'anthropic-version': '2023-06-01', Accept: 'application/json' }
        : { Authorization: 'Bearer ' + key, Accept: 'application/json' };
      const rq = lib.request({
        hostname: target.hostname, port: target.port || (target.protocol === 'https:' ? 443 : 80),
        path: target.pathname + target.search, method: 'GET',
        headers,
        timeout: 20000,
      }, (r) => {
        let raw = '';
        r.on('data', (c) => { raw += c; });
        r.on('end', () => {
          if (r.statusCode >= 400) {
            return send(res, 200, JSON.stringify({ error: 'HTTP ' + r.statusCode }));
          }
          try {
            const d = JSON.parse(raw);
            const arr = Array.isArray(d) ? d : (d.data || d.models || []);
            const ids = arr.map((x) => (typeof x === 'string' ? x : (x.id || x.name || '')))
                           .filter(Boolean).sort();
            send(res, 200, JSON.stringify({ models: ids }));
          } catch (e) {
            send(res, 200, '{"error":"返回不是 JSON"}');
          }
        });
      });
      rq.on('error', (e) => send(res, 200, JSON.stringify({ error: String(e.message || e) })));
      rq.on('timeout', () => { rq.destroy(); send(res, 200, '{"error":"超时"}'); });
      rq.end();
    });
  }
  if (req.method === 'POST' && p.startsWith('/localmodel/')) {
    return readBody(req, (data) => {
      if (!data) return send(res, 400, '{"error":"bad json"}');
      const act = p.split('/').pop();
      let payload;
      if (act === 'inspect') payload = { action: 'inspect', entries: data.entries, name: data.name };
      else if (act === 'register') payload = { action: 'register', info: data.info, override: data.override };
      else if (act === 'list') payload = { action: 'list' };
      else if (act === 'unregister') payload = { action: 'unregister', id: data.id };
      else return send(res, 400, '{"error":"unknown action"}');
      localModelCall(payload, (result) => send(res, 200, JSON.stringify(result)));
    });
  }
  if (req.method === 'POST' && p === '/extract') {
    return readBody(req, (data) => {
      if (!data || !data.data) return send(res, 200, '{"error":"没有文件内容"}');
      const name = String(data.name || 'file');
      const ext = path.extname(name).toLowerCase();
      const buf = Buffer.from(String(data.data), 'base64');
      if (buf.length > 24 * 1024 * 1024) return send(res, 200, '{"error":"文件超过 24MB"}');
      const tmp = path.join(os.tmpdir(), 'sa_up_' + Date.now() + '_' + Math.random().toString(16).slice(2, 6) + ext);
      try { fs.writeFileSync(tmp, buf); } catch (e) {
        return send(res, 200, JSON.stringify({ error: '写临时文件失败' }));
      }
      execFile(PY, pyArgs('extract.py').concat([tmp]),
        { timeout: 60000, maxBuffer: 32 * 1024 * 1024, windowsHide: true },
        (err, stdout, stderr) => {
          fs.unlink(tmp, () => {});
          if (err) {
            return send(res, 200, JSON.stringify({ error: String(stderr || err.message).slice(0, 200) }));
          }
          send(res, 200, stdout || '{"error":"空结果"}');
        });
    });
  }
  if (req.method === 'POST' && p === '/stop') {
    return readBody(req, (data) => {
      const id = String((data && data.id) || '');
      if (id) STOPPED.add(id);
      try {
        ensureBridge().stdin.write(JSON.stringify({ job: id, stop: true }) + '\n');
      } catch (e) {}
      send(res, 200, '{"ok":true}');
    });
  }
  if (req.method === 'POST' && p === '/chat') {
    return readBody(req, (data) => {
      if (!data) return send(res, 400, '{"error":"bad json"}');
      const id = newJob();
      const b = ensureBridge();
      try {
        b.stdin.write(JSON.stringify({
          job: id, chat: true,
          config: data.config || {},
          messages: data.messages || [],
          goal: String(data.goal || '').slice(0, 300),
          web: !!data.web,
        }) + '\n');
      } catch (e) {
        pushJob(id, { t: '错误：' + errCN(e.message) });
        finishJob(id);
      }
      send(res, 200, JSON.stringify({ id }));
    });
  }
  if (req.method === 'GET' && p === '/stream') {
    const id = u.searchParams.get('id');
    const job = JOBS.get(id);
    res.writeHead(200, {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    });
    res.flushHeaders();
    if (!job) {
      res.write('data: ' + JSON.stringify({ t: '任务不存在' }) + '\n\n');
      return res.end();
    }
    let closed = false;
    const push = (evt) => {
      if (closed) return;
      try { res.write('data: ' + JSON.stringify(evt) + '\n\n'); } catch (e) { closed = true; }
    };
    job.buf.forEach(push);
    if (job.done) {
      push({ done: true, result: job.result });
      closed = true;
      return res.end();
    }
    const sub = (evt) => {
      push(evt);
      if (evt.done) { closed = true; res.end(); }
    };
    job.subs.add(sub);
    const ping = setInterval(() => {
      if (closed) return;
      try { res.write(': ping\n\n'); } catch (e) { closed = true; }
    }, 15000);
    req.on('close', () => {
      closed = true;
      clearInterval(ping);
      job.subs.delete(sub);
    });
    return;
  }
  send(res, 404, '{"error":"not found"}');
});
function shutdown() {
  if (bridge && bridge.pid) {
    if (IS_WIN) {
      try {
        spawn('taskkill', ['/F', '/T', '/PID', String(bridge.pid)],
          { windowsHide: true, stdio: 'ignore' });
      } catch (e) {}
    } else {
      try { bridge.kill('SIGTERM'); } catch (e) {}
    }
  }
  setTimeout(() => process.exit(0), 150);
}
['SIGINT', 'SIGTERM', 'SIGHUP', 'SIGBREAK'].forEach((s) => {
  try { process.on(s, shutdown); } catch (e) {}
});
process.on('exit', () => {
  if (bridge) { try { bridge.kill(); } catch (e) {} }
});
server.on('error', (e) => {
  if (e.code === 'EADDRINUSE') {
    console.error('端口 ' + PORT + ' 已被占用。换端口：SA_PORT=' + (PORT + 1) + ' node ui/server.js');
  } else {
    console.error('服务启动失败：', e.message);
  }
  process.exit(1);
});
loadPlugins(() => {
  server.listen(PORT, HOST, () => {
    console.log('平台 ' + process.platform + ' ' + process.arch
      + ' | Node ' + process.version + ' | Python ' + PYARGV.join(' '));
    console.log('http://127.0.0.1:' + PORT + '/');
    if (BAD_PORTS.has(PORT)) {
      console.log('警告：' + PORT + ' 在浏览器黑名单里，Chrome / Edge / Firefox 会拒绝连接'
        + '（ERR_UNSAFE_PORT）。curl 正常，网页打不开。');
      console.log('      换端口：SA_PORT=6688 node ui/server.js');
    }
    if (!LOCAL_ONLY) {
      for (const ip of lanIPs()) {
        console.log('局域网/手机  http://' + ip + ':' + PORT + '/?k=' + TOKEN);
      }
    }
    console.log('插件:', PLUGINS.map((p) => (p.tools || []).join(',')).filter(Boolean).join(' ') || '无');
  });
});
