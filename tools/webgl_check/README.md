# WebGL build check

Run it after every WebGL build, before the zip goes to a GitHub Release.

## Here (Linux, headless Chromium + Playwright)

```
node tools/webgl_check/check_build.js UnityProject/Builds/WebGL --out /tmp/webgl_check
node tools/webgl_check/check_build.js alatau-webgl.zip --out /tmp/webgl_check
```

The last line is `PASS` or `FAIL`. The exit code is 0 for PASS, 1 for FAIL and 2 when the check could not run.
The `--out` folder holds `report.json`, `console.log`, `browser.log` and screenshots: `check_cover.png`, `check_progress50.png`, `check_started.png` and `check_final.png`.

What counts as FAIL:
- the twin did not start before `--timeout`;
- a GPU context loss;
- a GPU process crash, read from Chromium's own log;
- a shader that fails to compile or link;
- a Wasm abort or an uncaught page error.

When the GPU process dies, the script replays the GL programs linked before the crash one by one in fresh pages.
- If one of them crashes the GPU process again, it is saved as `shaders/crash.vert` and `shaders/crash.frag`.
- `shaders/gl_trail.txt` is always saved. It lists the GL calls that allocate or compile, with times relative to the crash.

Options:
- `--template UnityProject/Assets/WebGLTemplates/Alatau` checks an older build with the current loading page. It changes the build folder.
- `--throttle 2` serves the build at 2 MB/s, so the cover and its progress can be watched.
- `--settle 25` sets how many seconds to watch the running twin.
- `--gpu swiftshader|angle-gl|angle-d3d11|default` picks the GL backend. Use `--channel chrome` to run the installed Chrome.

Headless Chromium here draws with SwiftShader, a software GPU, so it is slower than a real GPU and stricter. A FAIL here should still be confirmed on Windows.

## On the Windows laptop (real Chrome, ANGLE on Direct3D 11)

Double-click `tools\webgl_check\check_build_windows.cmd`. It needs no Node, no Python and no install.

You can also run it with arguments:

```
powershell -ExecutionPolicy Bypass -File tools\webgl_check\check_build_windows.ps1 [-Build UnityProject\Builds\WebGL] [-Timeout 900] [-Port 8765]
```

What it does:
1. It serves the build on `http://localhost:8765/?check=1`.
2. It opens Chrome (or Edge) with a throw-away profile and `--use-angle=d3d11`.
3. It waits for the page's own report. The page posts its state, errors, GPU name and a canvas snapshot to `/__check`. This happens about 20 s after the start, or at once on a failure.
4. It scans `chrome_debug.log` for a GPU process crash.

The results go to `UnityProject\Builds\webgl_check\`: `report.json`, `shot.jpg` and `chrome_debug.log`.

A build made with an older loading page is checked on a copy that gets the current template.

Do not run it while someone else is presenting from the same Chrome profile. It uses its own profile, but it does open a Chrome window.

## Errors on the live site

The template keeps every error in `window.__alatau.errors`, together with the GPU name. The live site sends them nowhere; this check reads them from the page.
