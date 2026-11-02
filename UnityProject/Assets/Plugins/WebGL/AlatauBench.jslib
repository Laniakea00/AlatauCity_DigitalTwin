// Bench mode (?bench=1, Scripts/DigitalTwin/Bench/AlatauBench.cs): the results go to window.__alatau.bench with the browser's own
// memory figures (JS heap: Chrome's performance.memory; wasm heap: the size of Unity's memory). kind: start | state | view | done.
// The page hears each step as the window event "alatau-bench" (the build check posts the views to tools/webgl_check from it).
mergeInto(LibraryManager.library, {
  AlatauBenchPush: function (kindPtr, jsonPtr) {
    var kind = UTF8ToString(kindPtr), d;
    try { d = JSON.parse(UTF8ToString(jsonPtr)); } catch (e) { d = { error: String(e) }; }
    var A = window.__alatau = window.__alatau || {}, b = A.bench, MB = 1048576, k;
    var mb = function (v) { return Math.round(v / MB * 10) / 10; };
    if (kind === "start" || !b) {
      b = A.bench = d; b.views = []; b.done = false;
      var g = A.gpu || {};
      b.gpu = g.renderer || ""; b.gpuVendor = g.vendor || "";
      if (!b.gpu) try { var x = GLctx, ext = x.getExtension("WEBGL_debug_renderer_info"); b.gpu = String(x.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : x.RENDERER)); } catch (e) {}
      b.ua = navigator.userAgent; b.dpr = window.devicePixelRatio || 1; b.url = location.href; b.build = A.build || "";
      b.started = new Date().toISOString();
    }
    if (kind === "view") {
      var m = performance.memory;
      d.jsHeapUsedMB = m ? mb(m.usedJSHeapSize) : -1; d.jsHeapTotalMB = m ? mb(m.totalJSHeapSize) : -1;
      d.wasmHeapMB = mb(HEAPU8.buffer.byteLength);
      d.pageVisible = document.visibilityState === "visible";
      b.views.push(d);
    } else if (kind === "state" || kind === "done") {
      for (k in d) b[k] = d[k];
    }
    if (kind === "done") {
      var s = b.summary = b.summary || {}, w = 0, j = 0;
      for (var i = 0; i < b.views.length; i++) { w = Math.max(w, b.views[i].wasmHeapMB || 0); j = Math.max(j, b.views[i].jsHeapUsedMB || 0); }
      s.peakWasmHeapMB = w; s.peakJsHeapUsedMB = j;
      b.done = true;
      console.log("[Alatau] bench " + JSON.stringify(b));
    }
    try { window.dispatchEvent(new CustomEvent("alatau-bench", { detail: { kind: kind, i: b.views.length - 1 } })); } catch (e) {}
  }
});
