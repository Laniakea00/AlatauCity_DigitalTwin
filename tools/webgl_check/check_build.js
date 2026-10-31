#!/usr/bin/env node
// Alatau City · WebGL build check.
// Serves a WebGL build folder locally (HEAD, Range, ETag, like GitHub Pages), opens it in Chromium through Playwright,
// waits until the twin starts or fails, collects console errors, page errors, WebGL/shader errors and GPU context loss,
// takes a screenshot and prints PASS or FAIL (exit code 0 / 1; 2 = the check itself could not run).
//
//   node tools/webgl_check/check_build.js <build folder | build .zip> [options]
//     --out <dir>          where report.json, console.log and the screenshots go (default: ./webgl_check_out)
//     --timeout <s>        max seconds for download + start (default 900)
//     --settle <s>         seconds to watch the running twin after start (default 25)
//     --template <dir>     copy this WebGL template's files over the build first (index.html rendered like render_web_template.py)
//     --gpu <mode>         swiftshader (default, works headless anywhere) | angle-gl | angle-d3d11 (Windows) | default
//     --channel chrome     use the installed Google Chrome instead of Playwright's Chromium
//     --headed             show the browser window
//     --port <n>           local port (default: a free one)
//     --throttle <MB/s>    serve the build slowly, to see the cover and its progress (default: full speed)
//
// The page publishes its own state in window.__alatau (state, progress, errors, gpu); the template in
// UnityProject/Assets/WebGLTemplates/Alatau fills it. A build with an older template still gets checked from the console.
"use strict";
const fs = require("fs"), path = require("path"), http = require("http"), crypto = require("crypto"), os = require("os");
const { execFileSync } = require("child_process");

// ---------- arguments ----------
const argv = process.argv.slice(2), opt = { out: "webgl_check_out", timeout: 900, settle: 25, gpu: "swiftshader", headed: false, port: 0 };
let target = null;
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === "--out") opt.out = argv[++i];
  else if (a === "--timeout") opt.timeout = +argv[++i];
  else if (a === "--settle") opt.settle = +argv[++i];
  else if (a === "--template") opt.template = argv[++i];
  else if (a === "--gpu") opt.gpu = argv[++i];
  else if (a === "--channel") opt.channel = argv[++i];
  else if (a === "--headed") opt.headed = true;
  else if (a === "--port") opt.port = +argv[++i];
  else if (a === "--throttle") opt.throttle = +argv[++i];
  else if (a === "-h" || a === "--help") { console.log(fs.readFileSync(__filename, "utf8").split("\n").slice(1).filter((l, i, a) => a.slice(0, i + 1).every(x => x.startsWith("//"))).join("\n")); process.exit(0); }
  else target = a;
}
if (!target) { console.error("usage: node check_build.js <build folder | .zip> [--out dir] [--template dir]"); process.exit(2); }
fs.mkdirSync(opt.out, { recursive: true });

// ---------- the build folder (a zip is unpacked into the out folder) ----------
let root = path.resolve(target);
if (/\.zip$/i.test(root)) {
  const dir = path.join(path.resolve(opt.out), "build");
  fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  execFileSync("unzip", ["-q", root, "-d", dir]);
  root = dir;
}
if (!fs.existsSync(path.join(root, "index.html"))) {   // zip with a top folder
  const sub = fs.readdirSync(root).map(n => path.join(root, n)).find(p => fs.existsSync(path.join(p, "index.html")));
  if (!sub) { console.error("no index.html in " + root); process.exit(2); }
  root = sub;
}
const loader = fs.existsSync(path.join(root, "Build")) && fs.readdirSync(path.join(root, "Build")).find(n => /\.loader\.js$/.test(n));
if (!loader) { console.error("no Build/*.loader.js in " + root); process.exit(2); }

// ---------- optional: our template over the build ----------
if (opt.template) {
  const prefix = loader.replace(/\.loader\.js$/, ""), files = fs.readdirSync(path.join(root, "Build"));
  const pick = re => files.find(n => re.test(n)) || "";
  const v = { PRODUCT_NAME: "Alatau City · Digital Twin", COMPANY_NAME: "qTwin", PRODUCT_VERSION: "1.0", LOADER_FILENAME: loader,
    DATA_FILENAME: pick(/\.data(\.\w+)?$/), FRAMEWORK_FILENAME: pick(/\.framework\.js(\.\w+)?$/), CODE_FILENAME: pick(/\.wasm(\.\w+)?$/) };
  const flags = { USE_WASM: true, USE_THREADS: false, MEMORY_FILENAME: false, SYMBOLS_FILENAME: false };
  const keep = [true], out = [];
  for (const line of fs.readFileSync(path.join(opt.template, "index.html"), "utf8").split(/\r?\n/)) {
    const s = line.trim();
    if (s.startsWith("#if ")) { keep.push(keep[keep.length - 1] && flags[s.slice(4).trim()]); continue; }
    if (s === "#endif") { keep.pop(); continue; }
    if (keep[keep.length - 1]) out.push(line);
  }
  const html = out.join("\n").replace(/\{\{\{\s*JSON\.stringify\((\w+)\)\s*\}\}\}/g, (m, k) => JSON.stringify(v[k]))
                              .replace(/\{\{\{\s*(\w+)\s*\}\}\}/g, (m, k) => v[k]);
  fs.writeFileSync(path.join(root, "index.html"), html);
  for (const n of fs.readdirSync(opt.template))
    if (n !== "index.html" && !n.endsWith(".meta") && fs.statSync(path.join(opt.template, n)).isFile()) fs.copyFileSync(path.join(opt.template, n), path.join(root, n));
  console.log("template " + opt.template + " → " + root + " (prefix " + prefix + ")");
}

// ---------- static server: HEAD, Range, ETag (GitHub Pages behaves the same) ----------
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "application/javascript", ".json": "application/json", ".css": "text/css",
  ".png": "image/png", ".jpg": "image/jpeg", ".mp4": "video/mp4", ".webm": "video/webm", ".wasm": "application/wasm", ".svg": "image/svg+xml" };
const checkPosts = [];
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (u === "/__check" && req.method === "POST") {               // the template's check mode reports here as well
    let b = ""; req.on("data", d => b += d); req.on("end", () => { try { checkPosts.push(JSON.parse(b)); } catch (e) {} res.end("ok"); }); return;
  }
  let f = path.join(root, path.normalize(u).replace(/^([/\\])+/, ""));
  if (!f.startsWith(root)) { res.writeHead(403); return res.end(); }
  if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, "index.html");
  if (!fs.existsSync(f)) { res.writeHead(404); return res.end("not found"); }
  const st = fs.statSync(f), size = st.size, etag = '"' + crypto.createHash("md5").update(f + st.mtimeMs + size).digest("hex") + '"';
  const h = { "Content-Type": TYPES[path.extname(f).toLowerCase()] || "application/octet-stream", "Accept-Ranges": "bytes", "ETag": etag, "Cache-Control": "no-cache" };
  const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || "");
  if (m) {
    let from = m[1] === "" ? size - +m[2] : +m[1], to = m[1] !== "" && m[2] !== "" ? Math.min(+m[2], size - 1) : size - 1;
    if (from > to || from >= size) { res.writeHead(416, { "Content-Range": "bytes */" + size }); return res.end(); }
    res.writeHead(206, Object.assign(h, { "Content-Range": `bytes ${from}-${to}/${size}`, "Content-Length": to - from + 1 }));
    if (req.method === "HEAD") return res.end();
    return pipe(fs.createReadStream(f, { start: from, end: to }), res);
  }
  res.writeHead(200, Object.assign(h, { "Content-Length": size }));
  if (req.method === "HEAD") return res.end();
  pipe(fs.createReadStream(f), res);
});
// --throttle: one shared budget for all requests, like a slow line
let budgetT = Date.now(), budget = 0;
function pipe(src, res) {
  if (!opt.throttle) return src.pipe(res);
  let pending = 0, ended = false;
  src.on("data", chunk => {
    src.pause(); pending++;
    const now = Date.now(); budget = Math.max(budget - (now - budgetT) / 1000 * opt.throttle * 1048576, 0); budgetT = now;
    budget += chunk.length;
    setTimeout(() => { res.write(chunk); pending--; if (ended && !pending) res.end(); src.resume(); }, budget / (opt.throttle * 1048576) * 1000);
  });
  src.on("end", () => { ended = true; if (!pending) res.end(); }); src.on("error", () => res.destroy());
}

// ---------- what counts as a failure ----------
const FATAL = [
  /context ?lost|CONTEXT_LOST/i,
  /link(ing)? (error|failed)|failed to link|LINK_STATUS|program (failed|not) .*link/i,
  /shader.*(compil|error)|compile.*shader|GLSL/i,
  /GPU process (exited|crashed)|gpu process crash/i,
  /RuntimeError|unreachable executed|memory access out of bounds|Out of memory|abort\(/i,
  /An abnormal situation has occurred|error occurred running the Unity content/i,
];
const fatalText = s => FATAL.some(r => r.test(s));

// the browser's own log (GPU process crashes, ANGLE errors): Playwright prints it under DEBUG=pw:browser; keep it in a file
const blog = [], GPU_CRASH = /GPU process exited unexpectedly|GPU process has crashed|GPU state invalid|Lost (UI )?shared context|context_lost/i;
let onBrowserLine = () => {};
process.env.DEBUG = (process.env.DEBUG ? process.env.DEBUG + "," : "") + "pw:browser";
const realErr = process.stderr.write.bind(process.stderr);
process.stderr.write = (chunk, ...rest) => {
  const s = String(chunk);
  if (s.indexOf("pw:browser") < 0) return realErr(chunk, ...rest);
  for (const line of s.split("\n")) if (line.trim()) { blog.push(line.replace(/^\S+ pw:browser /, "")); onBrowserLine(line); }
  return true;
};

(async () => {
  let chromium;
  try { ({ chromium } = require("playwright")); } catch (e) { console.error("playwright is not available: " + e.message); process.exit(2); }
  await new Promise(r => server.listen(opt.port, "127.0.0.1", r));
  const url = `http://127.0.0.1:${server.address().port}/?check=1`;
  const gpuArgs = {
    swiftshader: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
    "angle-gl": ["--use-angle=gl", "--ignore-gpu-blocklist"],
    "angle-d3d11": ["--use-angle=d3d11", "--ignore-gpu-blocklist"],
    default: [],
  }[opt.gpu] || [];
  const t0 = Date.now(), log = [], errors = [], fatal = [];
  const note = (kind, text) => { const line = `[${((Date.now() - t0) / 1000).toFixed(1).padStart(6)}s] ${kind.padEnd(8)} ${text}`; log.push(line); return line; };
  const browser = await chromium.launch({ headless: !opt.headed, channel: opt.channel,
    args: gpuArgs.concat(["--autoplay-policy=no-user-gesture-required", "--enable-logging=stderr", "--v=0"]) });
  let gpuCrashAt = 0;
  onBrowserLine = line => {
    if (!GPU_CRASH.test(line)) return;
    const m = /\] (.*)$/.exec(line), t = "GPU process: " + (m ? m[1] : line).trim().slice(0, 200);
    note("gpu", t); fatal.push(t); if (!gpuCrashAt) gpuCrashAt = Date.now();
  };
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  // keep every GLSL program the page links (vertex + fragment source, time), to find the one that kills the GPU process
  await page.addInitScript(() => {
    if (!window.WebGL2RenderingContext) return;
    const P = WebGL2RenderingContext.prototype, src = new WeakMap(), typ = new WeakMap(), att = new WeakMap(), list = window.__checkPrograms = [];
    const cs = P.createShader, ss = P.shaderSource, as = P.attachShader, lp = P.linkProgram;
    // a short trail of the GL calls that allocate or compile (no draws): what the GPU was doing when it died
    const trail = window.__checkTrail = [], dims = a => Array.prototype.slice.call(a, 0, 9).map(x => typeof x === "number" ? x : x == null ? "null" : x.byteLength != null ? "[" + x.byteLength + " B]" : typeof x).join(",");
    ["texImage2D", "texStorage2D", "texStorage3D", "texImage3D", "compressedTexImage2D", "compressedTexSubImage2D", "texSubImage2D", "texSubImage3D", "compressedTexImage3D", "compressedTexSubImage3D", "copyTexSubImage2D", "bufferData", "renderbufferStorage",
     "renderbufferStorageMultisample", "framebufferTexture2D", "generateMipmap", "blitFramebuffer", "readPixels", "linkProgram", "compileShader", "clear"].forEach(n => {
      const f = P[n]; if (!f) return;
      P[n] = function () { trail.push(Date.now() + " " + n + "(" + dims(arguments) + ")"); if (trail.length > 4000) trail.splice(0, 1000); return f.apply(this, arguments); };
    });
    const draws = ["drawArrays", "drawElements", "drawArraysInstanced", "drawElementsInstanced"];
    draws.forEach(n => { const f = P[n]; P[n] = function () { const l = trail[trail.length - 1]; if (l && l.indexOf(" draw×") > 0) trail[trail.length - 1] = l.replace(/draw×(\d+)/, (m, k) => "draw×" + (+k + 1)); else trail.push(Date.now() + " draw×1"); return f.apply(this, arguments); }; });
    P.createShader = function (type) { const sh = cs.call(this, type); if (sh) typ.set(sh, type); return sh; };
    P.shaderSource = function (sh, text) { src.set(sh, text); return ss.call(this, sh, text); };
    P.attachShader = function (pr, sh) { const a = att.get(pr) || []; a.push(sh); att.set(pr, a); return as.call(this, pr, sh); };
    P.linkProgram = function (pr) {
      const a = att.get(pr) || [], pick = t => { const sh = a.find(x => typ.get(x) === t); return sh ? src.get(sh) || "" : ""; };
      if (list.length < 5000) list.push({ t: Date.now(), vs: pick(0x8B31), fs: pick(0x8B30) });
      return lp.call(this, pr);
    };
  });
  page.on("console", m => {
    const t = m.type(), s = m.text();
    note(t, s.slice(0, 2000));
    if (t === "error") { errors.push(s); if (fatalText(s)) fatal.push(s); }
    else if (t === "warning" && /WebGL|GL_INVALID|shader|link/i.test(s) && fatalText(s)) fatal.push(s);
  });
  page.on("pageerror", e => { const s = "pageerror: " + (e.stack || e.message); note("pageerr", s); errors.push(s); fatal.push(s); });
  page.on("crash", () => { note("crash", "the page crashed"); fatal.push("page crashed (renderer or GPU process)"); });
  page.on("requestfailed", r => { if (!/cover\.(mp4|webm|jpg)/.test(r.url())) note("netfail", r.url() + " " + (r.failure() || {}).errorText); });

  const shot = async name => { const p = path.join(opt.out, name); try { await page.screenshot({ path: p }); note("shot", p); } catch (e) { note("shot", "failed " + e.message); } return p; };
  const state = () => page.evaluate(() => window.__alatau ? { state: window.__alatau.state, progress: window.__alatau.progress, errors: window.__alatau.errors.length, fatal: window.__alatau.fatal } : null).catch(() => null);

  console.log("serving " + root + " at " + url + " · gpu " + opt.gpu + (opt.channel ? " · " + opt.channel : ""));
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(1500);
  await shot("check_cover.png");

  // wait for start or failure
  let st = null, lastPct = -1, started = false, t50 = false;
  const deadline = Date.now() + opt.timeout * 1000;
  while (Date.now() < deadline) {
    st = await state();
    if (st && st.progress !== lastPct && Math.floor(st.progress * 10) !== Math.floor(lastPct * 10)) { console.log(`  progress ${Math.round(st.progress * 100)} %`); }
    if (st) lastPct = st.progress;
    if (st && !t50 && st.progress >= 0.5) { t50 = true; await shot("check_progress50.png"); }
    if (st && st.state === "running") { started = true; await page.waitForTimeout(1500); await shot("check_started.png"); break; }
    if (st && st.state === "failed") break;
    if (fatal.length && !st) break;                                   // old template: no state, but a fatal console line
    if (!st) {                                                        // old template: started when the loading overlay is hidden
      const hidden = await page.evaluate(() => { const o = document.getElementById("overlay"); return !!o && (o.style.display === "none" || o.classList.contains("hide")); }).catch(() => false);
      if (hidden) { started = true; break; }
    }
    await page.waitForTimeout(1000);
  }
  const startSec = (Date.now() - t0) / 1000;
  if (started) {
    console.log(`  started after ${startSec.toFixed(0)} s, watching ${opt.settle} s`);
    await page.waitForTimeout(opt.settle * 1000);
    st = await state();
  }
  await shot("check_final.png");
  const info = await page.evaluate(() => window.__alatau ? { gpu: window.__alatau.gpu, errors: window.__alatau.errors, fatal: window.__alatau.fatal, state: window.__alatau.state } : null).catch(() => null);

  // GPU process died: replay every program the page linked, newest first, one per fresh page (compile + link + one draw,
  // because SwiftShader and ANGLE translate some shaders only at the first draw), and name the one that crashes it again
  const grab = async name => { const out = []; try { const n = await page.evaluate(k => (window[k] || []).length, name);
    for (let i = 0; i < n; i += 40) out.push(...await page.evaluate(([k, i]) => window[k].slice(i, i + 40), [name, i])); } catch (e) { note("check", name + " unavailable: " + e.message); } return out; };
  const crashAt = gpuCrashAt;
  const programs = crashAt ? await grab("__checkPrograms") : [], trail = crashAt ? await grab("__checkTrail") : [];
  await page.close().catch(() => {});
  let culprit = null;
  if (crashAt) {
    const dir = path.join(opt.out, "shaders"); fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "gl_trail.txt"), trail.map(l => { const t = +l.split(" ")[0]; return ((t - crashAt) / 1000).toFixed(3).padStart(8) + " s  " + l.slice(l.indexOf(" ") + 1); }).join("\n") + "\n");
    const seen = new Set(), cand = [];
    for (const x of programs.filter(x => x.t <= crashAt).reverse()) { const k = x.vs + "\u0000" + x.fs; if (seen.has(k)) continue; seen.add(k); cand.push(x); if (cand.length >= 150) break; }
    cand.slice(0, 3).forEach((x, i) => { fs.writeFileSync(path.join(dir, `last${i}.vert`), x.vs); fs.writeFileSync(path.join(dir, `last${i}.frag`), x.fs); });
    console.log(`  GPU process crashed; replaying ${cand.length} linked programs one by one (newest first)`);
    for (let i = 0; i < cand.length && !culprit; i++) {
      gpuCrashAt = 0;
      const pg = await browser.newPage();
      const r = await pg.evaluate(async x => {
        const gl = document.createElement("canvas").getContext("webgl2");
        if (!gl) return "no-webgl2";
        ["EXT_texture_compression_bptc", "WEBGL_compressed_texture_s3tc", "EXT_color_buffer_float"].forEach(e => gl.getExtension(e));
        const mk = (type, text) => { const s = gl.createShader(type); gl.shaderSource(s, text); gl.compileShader(s); return s; };
        const p = gl.createProgram(); gl.attachShader(p, mk(gl.VERTEX_SHADER, x.vs)); gl.attachShader(p, mk(gl.FRAGMENT_SHADER, x.fs));
        gl.linkProgram(p);
        if (!gl.getProgramParameter(p, gl.LINK_STATUS)) return gl.isContextLost() ? "lost" : "link-failed: " + gl.getProgramInfoLog(p);
        gl.useProgram(p); gl.drawArrays(gl.TRIANGLES, 0, 3);
        const px = new Uint8Array(4); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
        await new Promise(r => setTimeout(r, 250));
        return gl.isContextLost() ? "lost" : "ok";
      }, cand[i]).catch(e => "error: " + e.message);
      await new Promise(r => setTimeout(r, 250));
      if (r === "lost" || gpuCrashAt) {
        culprit = { vert: path.join(dir, "crash.vert"), frag: path.join(dir, "crash.frag"), result: r, linked_ms_before_crash: crashAt - cand[i].t, replayed: i + 1 };
        fs.writeFileSync(culprit.vert, cand[i].vs); fs.writeFileSync(culprit.frag, cand[i].fs);
      }
      await pg.close().catch(() => {});
    }
    if (culprit) { fatal.push("GPU process crash reproduced by one shader program: " + culprit.frag + " (+ .vert)"); console.log("  culprit found: " + culprit.frag); }
    else console.log("  no single program reproduces the crash (state- or memory-dependent); last programs and the GL trail are in " + dir);
  }
  await browser.close(); server.close();

  if (info && info.fatal) fatal.push("page: " + info.fatal);
  const timedOut = !started && !(st && st.state === "failed") && !fatal.length;
  const pass = started && !fatal.length && (!st || st.state === "running");
  const report = { result: pass ? "PASS" : "FAIL", build: root, gpu_mode: opt.gpu, channel: opt.channel || "playwright-chromium",
    started, start_seconds: started ? Math.round(startSec) : null, timed_out: timedOut, final_state: st && st.state,
    page_gpu: info && info.gpu, fatal: Array.from(new Set(fatal)).slice(0, 30), console_errors: Array.from(new Set(errors)).slice(0, 60),
    page_errors: info && info.errors, programs_linked: programs.length, gpu_crash_culprit: culprit,
    check_posts: checkPosts.map(c => Object.assign({}, c, { shot: c.shot ? "(jpeg, " + c.shot.length + " chars)" : "" })) };
  fs.writeFileSync(path.join(opt.out, "report.json"), JSON.stringify(report, null, 2));
  fs.writeFileSync(path.join(opt.out, "console.log"), log.join("\n") + "\n");
  fs.writeFileSync(path.join(opt.out, "browser.log"), blog.join("\n") + "\n");

  console.log("");
  console.log("GPU      " + (info && info.gpu ? info.gpu.renderer + " · " + info.gpu.version : "unknown"));
  console.log("start    " + (started ? Math.round(startSec) + " s" : timedOut ? "timed out after " + opt.timeout + " s" : "did not start"));
  console.log("errors   " + report.console_errors.length + " console error(s), " + report.fatal.length + " fatal");
  for (const f of report.fatal.slice(0, 8)) console.log("  FATAL  " + f.split("\n")[0].slice(0, 220));
  for (const e of report.console_errors.filter(e => !report.fatal.includes(e)).slice(0, 8)) console.log("  error  " + e.split("\n")[0].slice(0, 220));
  console.log("report   " + path.resolve(opt.out, "report.json"));
  console.log(pass ? "PASS" : "FAIL");
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error("check could not run: " + (e.stack || e)); try { server.close(); } catch (x) {} process.exit(2); });
