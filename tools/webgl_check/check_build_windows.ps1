<#
  Alatau City - WebGL build check on Windows, in the real Chrome (ANGLE on Direct3D 11: where the site died on 28.10).
  No Node, no Python, nothing to install: PowerShell serves the build folder on localhost (HEAD, Range, ETag, like
  GitHub Pages), opens it in Chrome (or Edge) with a throw-away profile, and waits for the page's own report
  (the template's check mode, ?check=1, posts its state, errors, GPU and a canvas snapshot to /__check).
  Chrome's own log is scanned for a GPU process crash. Prints PASS or FAIL; exit code 0 / 1 (2 = could not run).

  Speed baseline (on by default): the page is opened with ?check=1&bench=1, the twin visits 10 fixed views
  (UnityProject\Assets\Scripts\DigitalTwin\Bench\AlatauBench.cs) and the report comes after the last one. Chrome runs
  twice: on the discrete GPU (--force_high_performance_gpu) and on the integrated one (--force_low_power_gpu). Each run
  writes bench_<dgpu|igpu>_<date>.json; the first complete run of each GPU is also kept as bench_<gpu>_baseline.json and
  later runs are compared with it. -NoBench gives the old check: one run, discrete GPU, ?check=1.

  Run (double-click check_build_windows.cmd, or):
    powershell -ExecutionPolicy Bypass -File tools\webgl_check\check_build_windows.ps1 [-Build <folder or .zip>] [-Timeout 900] [-NoBench]
  Default build folder: UnityProject\Builds\WebGL next to this repo. Results: <build>\..\webgl_check\ (report.json, shot.jpg,
  chrome_debug.log for the discrete GPU; report_igpu.json, shot_igpu.jpg, chrome_debug_igpu.log for the integrated one; bench_*.json).
  -Timeout is per Chrome run.
#>
param(
  [string]$Build = "",
  [int]$Timeout = 900,
  [int]$Port = 8765,
  [string]$Browser = "",
  [switch]$KeepOpen,
  [switch]$NoBench
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $Build) { $Build = Join-Path $repo "UnityProject\Builds\WebGL" }
if (-not (Test-Path $Build)) { Write-Host "no build at $Build"; exit 2 }
$Build = (Resolve-Path $Build).Path
$out = Join-Path (Split-Path $Build -Parent) "webgl_check"
New-Item -ItemType Directory -Force -Path $out | Out-Null
if ($Build -like "*.zip") {
  $dir = Join-Path $out "build"
  if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
  [System.IO.Compression.ZipFile]::ExtractToDirectory($Build, $dir)
  $Build = $dir
}
if (-not (Test-Path (Join-Path $Build "index.html"))) { Write-Host "no index.html in $Build"; exit 2 }
if (-not (Select-String -Path (Join-Path $Build "index.html") -Pattern "__alatau" -Quiet)) {
  # an older build: check it with the current template (UnityProject\Assets\WebGLTemplates\Alatau) on a copy
  $tpl = Join-Path $repo "UnityProject\Assets\WebGLTemplates\Alatau"
  if (-not (Test-Path (Join-Path $tpl "index.html"))) { Write-Host "this index.html has no check mode and the template was not found"; exit 2 }
  $copy = Join-Path $out "build"
  if ($Build -ne $copy) { if (Test-Path $copy) { Remove-Item -Recurse -Force $copy }; Copy-Item -Recurse $Build $copy; $Build = $copy }
  $bd = Join-Path $Build "Build"; $names = @(Get-ChildItem $bd | ForEach-Object { $_.Name })
  $pick = { param($re) $names | Where-Object { $_ -match $re } | Select-Object -First 1 }
  $v = @{ PRODUCT_NAME = "Alatau City - Digital Twin"; COMPANY_NAME = "qTwin"; PRODUCT_VERSION = "1.0";
          LOADER_FILENAME = (& $pick '\.loader\.js$'); DATA_FILENAME = (& $pick '\.data(\.\w+)?$');
          FRAMEWORK_FILENAME = (& $pick '\.framework\.js(\.\w+)?$'); CODE_FILENAME = (& $pick '\.wasm(\.\w+)?$') }
  $flags = @{ USE_WASM = $true; USE_THREADS = $false; MEMORY_FILENAME = $false; SYMBOLS_FILENAME = $false }
  $keep = New-Object System.Collections.Stack; $keep.Push($true); $lines = New-Object System.Collections.Generic.List[string]
  foreach ($line in [IO.File]::ReadAllLines((Join-Path $tpl "index.html"), [Text.Encoding]::UTF8)) {
    $t = $line.Trim()
    if ($t.StartsWith("#if ")) { $keep.Push($keep.Peek() -and $flags[$t.Substring(4).Trim()]); continue }
    if ($t -eq "#endif") { [void]$keep.Pop(); continue }
    if ($keep.Peek()) { $lines.Add($line) }
  }
  $html = [string]::Join("`n", $lines)
  $html = [regex]::Replace($html, '\{\{\{\s*JSON\.stringify\((\w+)\)\s*\}\}\}', { param($m) '"' + $v[$m.Groups[1].Value] + '"' })
  $html = [regex]::Replace($html, '\{\{\{\s*(\w+)\s*\}\}\}', { param($m) $v[$m.Groups[1].Value] })
  [IO.File]::WriteAllText((Join-Path $Build "index.html"), $html, (New-Object Text.UTF8Encoding($false)))
  Get-ChildItem $tpl -File | Where-Object { $_.Name -ne "index.html" -and $_.Extension -ne ".meta" } | ForEach-Object { Copy-Item $_.FullName $Build -Force }
  Write-Host "older build: checking it with the current template on a copy in $Build"
}

# ---------- the browser ----------
if (-not $Browser) {
  $cands = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
             "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
             "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe")
  $Browser = $cands | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}
if (-not $Browser) { Write-Host "Chrome or Edge not found"; exit 2 }

# ---------- local server ----------
$types = @{ ".html" = "text/html; charset=utf-8"; ".js" = "application/javascript"; ".json" = "application/json"; ".jpg" = "image/jpeg";
            ".png" = "image/png"; ".mp4" = "video/mp4"; ".webm" = "video/webm"; ".wasm" = "application/wasm"; ".css" = "text/css" }
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
try { $listener.Start() } catch { Write-Host "cannot listen on port ${Port}: $($_.Exception.Message) (try -Port 8899)"; exit 2 }

function Serve($ctx) {
  $req = $ctx.Request; $res = $ctx.Response
  try {
    $rel = [Uri]::UnescapeDataString($req.Url.AbsolutePath).TrimStart("/").Replace("/", "\")
    if ($rel -eq "") { $rel = "index.html" }
    $f = [IO.Path]::GetFullPath((Join-Path $Build $rel))
    if (-not $f.StartsWith($Build) -or -not (Test-Path $f -PathType Leaf)) { $res.StatusCode = 404; return }
    $fi = Get-Item $f; $size = $fi.Length
    $ext = $fi.Extension.ToLower(); $res.ContentType = $(if ($types.ContainsKey($ext)) { $types[$ext] } else { "application/octet-stream" })
    $res.Headers.Add("Accept-Ranges", "bytes"); $res.Headers.Add("ETag", '"' + $size + "-" + $fi.LastWriteTimeUtc.Ticks + '"')
    $res.Headers.Add("Cache-Control", "no-cache")
    $from = 0; $to = $size - 1
    $range = $req.Headers["Range"]
    if ($range -and $range -match "^bytes=(\d+)-(\d*)$") {
      $from = [int64]$Matches[1]; if ($Matches[2]) { $to = [Math]::Min([int64]$Matches[2], $size - 1) }
      if ($from -gt $to) { $res.StatusCode = 416; return }
      $res.StatusCode = 206; $res.Headers.Add("Content-Range", "bytes $from-$to/$size")
    }
    $res.ContentLength64 = $to - $from + 1
    if ($req.HttpMethod -eq "HEAD") { return }
    $fs = [IO.File]::OpenRead($f)
    try {
      $fs.Position = $from; $left = $to - $from + 1; $buf = New-Object byte[] 262144
      while ($left -gt 0) { $n = $fs.Read($buf, 0, [int][Math]::Min([int64]$buf.Length, $left)); if ($n -le 0) { break }; $res.OutputStream.Write($buf, 0, $n); $left -= $n }
    } finally { $fs.Close() }
  } catch { } finally { try { $res.Close() } catch { } }
}


# numbers in the output always with a dot, whatever the language of Windows
function Fmt([string]$f) {
  $a = New-Object object[] $args.Count
  for ($i = 0; $i -lt $args.Count; $i++) { $x = $args[$i]; if ($null -ne $x) { $x = $x.psobject.BaseObject }; $a[$i] = $x }
  [string]::Format([Globalization.CultureInfo]::InvariantCulture, $f, $a)
}

# Windows' view of the browser's memory: private bytes of the processes of one run (the tab's renderer, the GPU process, the rest)
function Measure-Chrome($profileDir, $rootPid) {
  $m = [ordered]@{ rendererMB = 0.0; gpuMB = 0.0; browserMB = 0.0; otherMB = 0.0; totalMB = 0.0; processes = 0 }
  try {
    $exe = [IO.Path]::GetFileName($Browser)
    $procs = @(Get-CimInstance Win32_Process -Filter "Name='$exe'" -ErrorAction Stop | Where-Object { $_.ProcessId -eq $rootPid -or $_.ParentProcessId -eq $rootPid -or ($_.CommandLine -and $_.CommandLine.Contains($profileDir)) })
    foreach ($p in $procs) {
      $gp = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
      if (-not $gp) { continue }
      $mb = $gp.PrivateMemorySize64 / 1MB; $cl = [string]$p.CommandLine
      $k = $(if ($cl -match "--type=renderer") { "rendererMB" } elseif ($cl -match "--type=gpu-process") { "gpuMB" } elseif ($cl -notmatch "--type=") { "browserMB" } else { "otherMB" })
      $m[$k] = $m[$k] + $mb; $m["totalMB"] = $m["totalMB"] + $mb; $m["processes"] = $m["processes"] + 1
    }
  } catch { }
  foreach ($k in @("rendererMB", "gpuMB", "browserMB", "otherMB", "totalMB")) { $m[$k] = [Math]::Round($m[$k], 1) }
  $m
}

# ---------- one run: Chrome on one GPU until the page reports (with the bench: after its last view) ----------
$script:pending = $listener.GetContextAsync()
function Invoke-Run($tag, $gpuFlag, $gpuText) {
  $profileDir = Join-Path $env:TEMP ("alatau_check_" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
  $url = "http://localhost:$Port/?check=1" + $(if ($NoBench) { "" } else { "&bench=1" })
  $chromeArgs = @("--user-data-dir=`"$profileDir`"", "--no-first-run", "--no-default-browser-check", "--use-angle=d3d11", $gpuFlag, "--enable-logging", "--v=0",
            "--autoplay-policy=no-user-gesture-required", "--window-size=1600,900", "--new-window")
  # the bench: exact JS heap figures, and no slowing down of the page when its window is covered or not in front
  if (-not $NoBench) { $chromeArgs += @("--enable-precise-memory-info", "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows") }
  $chromeArgs += $url
  Write-Host ""
  Write-Host "[$tag] serving $Build at $url"
  Write-Host "[$tag] browser $Browser (ANGLE D3D11, $gpuText)"
  $proc = Start-Process -FilePath $Browser -ArgumentList $chromeArgs -PassThru
  $log = Join-Path $profileDir "chrome_debug.log"
  $t0 = Get-Date; $report = $null; $gpuCrash = @(); $os = @{}; $scan = Get-Date
  while (((Get-Date) - $t0).TotalSeconds -lt $Timeout) {
    if ($script:pending.Wait(500)) {
      $ctx = $script:pending.Result; $script:pending = $listener.GetContextAsync()
      $path = $ctx.Request.Url.AbsolutePath
      if ($ctx.Request.HttpMethod -eq "POST" -and ($path -eq "/__check" -or $path -eq "/__bench")) {
        $sr = New-Object IO.StreamReader($ctx.Request.InputStream, [Text.Encoding]::UTF8); $body = $sr.ReadToEnd(); $sr.Close()
        $ctx.Response.StatusCode = 200; $ctx.Response.Close()
        if ($path -eq "/__check") { $report = $body | ConvertFrom-Json; break }
        # one bench view is measured: add what Windows says about the browser's memory right now
        try {
          $bv = $body | ConvertFrom-Json; $mem = Measure-Chrome $profileDir $proc.Id; $os["$($bv.i)"] = $mem
          Write-Host (Fmt "[{0}] view {1,2} {2,-18} avg {3,6:0.0} ms  p95 {4,6:0.0} ms  tab {5,6:0} MB  gpu process {6,6:0} MB" $tag ($bv.i + 1) $bv.view.id $bv.view.avgMs $bv.view.p95Ms $mem.rendererMB $mem.gpuMB)
        } catch { }
        continue
      }
      Serve $ctx
    }
    # Chrome's log, every 5 s (reading it more often takes CPU from the measured page)
    if (((Get-Date) - $scan).TotalSeconds -ge 5 -and (Test-Path $log)) {
      $scan = Get-Date
      $hits = Select-String -Path $log -Pattern "GPU process exited unexpectedly|GPU process has crashed|GPU state invalid|Stack overflow|STATUS_STACK_OVERFLOW" -ErrorAction SilentlyContinue
      if ($hits) { $gpuCrash = @($hits | ForEach-Object { $_.Line.Trim() }) }
    }
    if ($proc.HasExited -and -not $KeepOpen) { break }
  }
  $secs = [int]((Get-Date) - $t0).TotalSeconds
  Start-Sleep -Milliseconds 800
  $sfx = $(if ($tag -eq "dgpu") { "" } else { "_" + $tag })
  if (Test-Path $log) {
    Copy-Item $log (Join-Path $out ("chrome_debug" + $sfx + ".log")) -Force
    $hits = Select-String -Path $log -Pattern "GPU process exited unexpectedly|GPU process has crashed|GPU state invalid|Stack overflow|STATUS_STACK_OVERFLOW" -ErrorAction SilentlyContinue
    if ($hits) { $gpuCrash = @($hits | ForEach-Object { $_.Line.Trim() }) }
  }
  if (-not $KeepOpen) {
    try { & taskkill /PID $proc.Id /T /F 2>$null | Out-Null } catch { }
    Start-Sleep -Milliseconds 500
    Remove-Item -Recurse -Force $profileDir -ErrorAction SilentlyContinue
  }
  @{ tag = $tag; flag = $gpuFlag; report = $report; gpuCrash = $gpuCrash; secs = $secs; os = $os; sfx = $sfx }
}

# ---------- verdict of one run ----------
function Get-Fatal($r) {
  $fatal = @(); $report = $r.report
  if (-not $report) { $fatal += $(if ($r.secs -ge $Timeout) { "timed out after $Timeout s without a report from the page" } else { "the browser closed before the page reported" }) }
  else {
    if ($report.state -ne "running") { $fatal += "page state: $($report.state) - $($report.fatal)" }
    foreach ($e in @($report.errors)) {
      if ($e.kind -match "^(gl-link|gl-compile|fatal-)" -or $e.msg -match "GLSL compilation failed|failed to link|Shader error|RuntimeError|memory access out of bounds") {
        $fatal += "$($e.kind): $(($e.msg -split "`n")[0])"
      }
    }
  }
  foreach ($c in @($r.gpuCrash)) { if ($c) { $fatal += "GPU process: $c" } }
  $fatal
}

# ---------- the bench of one run: file, baseline, table ----------
function Save-Bench($r, $pass) {
  $b = $null; if ($r.report) { $b = $r.report.bench }
  if (-not $b) {
    if (-not $NoBench) { Write-Host "bench    none: this build has no bench mode, or the page reported before it (see the errors)" }
    return $null
  }
  foreach ($v in @($b.views)) { $m = $r.os["$($v.i)"]; if ($m) { $v | Add-Member -NotePropertyName os -NotePropertyValue (New-Object PSObject -Property $m) -Force } }
  $ver = ""; try { $ver = (Get-Item $Browser).VersionInfo.ProductVersion } catch { }
  $b | Add-Member -NotePropertyName run -NotePropertyValue ([pscustomobject][ordered]@{ tag = $r.tag; flag = $r.flag; browser = $Browser; browserVersion = $ver;
       date = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss"); computer = $env:COMPUTERNAME; build = $Build; result = $(if ($pass) { "PASS" } else { "FAIL" }) }) -Force
  $json = $b | ConvertTo-Json -Depth 8
  $file = Join-Path $out ("bench_" + $r.tag + "_" + (Get-Date).ToString("yyyyMMdd_HHmm") + ".json")
  [IO.File]::WriteAllText($file, $json, (New-Object Text.UTF8Encoding($false)))
  $views = @($b.views)
  Write-Host (Fmt "bench    {0}  ({1}, {2} views in {3:0} s, state {4})" $file $b.screen $views.Count $b.runSeconds $b.state)
  if (-not $b.done -or $b.state -ne "done" -or $views.Count -ne $b.viewCount) { Write-Host (Fmt "bench    INCOMPLETE: {0} of {1} views, state {2}{3}" $views.Count $b.viewCount $b.state $(if ($b.notReady) { ", not loaded: " + $b.notReady } else { "" })) }
  # the baseline: the first complete bench of this GPU; later runs are compared with it
  $basePath = Join-Path $out ("bench_" + $r.tag + "_baseline.json"); $base = $null
  if (Test-Path $basePath) { try { $base = [IO.File]::ReadAllText($basePath) | ConvertFrom-Json } catch { Write-Host "baseline $basePath cannot be read" } }
  elseif ($b.done -and $b.state -eq "done" -and $views.Count -eq $b.viewCount -and $pass) {
    [IO.File]::WriteAllText($basePath, $json, (New-Object Text.UTF8Encoding($false)))
    Write-Host "baseline saved: $basePath (later runs on this GPU are compared with it; delete it to take a new one)"
  }
  $bv = @{}; if ($base) { foreach ($v in @($base.views)) { $bv[[string]$v.id] = $v } }
  # the table: frame time (ms) between frames, main-thread work (cpu), memory (MB), what is drawn; 'vs base' = avg frame time
  Write-Host ""
  Write-Host (Fmt "{0,-18} {1,6} {2,6} {3,6} {4,6} {5,5} {6,5} {7,6} {8,6} {9,6} {10,5} {11,5} {12,5} {13,8}" "view" "avg" "p50" "p95" "max" "cpu" "jsMB" "wasmMB" "tabMB" "gpuMB" "cars" "ppl" "lamps" "vs base")
  $sa = 0.0; $sp = 0.0; $n = 0; $worse = @()
  foreach ($v in $views) {
    $tab = $null; $gpu = $null; if ($v.os) { $tab = $v.os.rendererMB; $gpu = $v.os.gpuMB }
    $d = ""; $o = $bv[[string]$v.id]
    if ($o -and [double]$o.avgMs -gt 0) {
      $pa = 100.0 * ([double]$v.avgMs - [double]$o.avgMs) / [double]$o.avgMs; $d = Fmt "{0:+0;-0;0} %" $pa
      $pp = $(if ([double]$o.p95Ms -gt 0) { 100.0 * ([double]$v.p95Ms - [double]$o.p95Ms) / [double]$o.p95Ms } else { 0.0 })
      if ($pa -gt 10 -or $pp -gt 10) { $worse += [string]$v.id }
    }
    Write-Host (Fmt "{0,-18} {1,6:0.0} {2,6:0.0} {3,6:0.0} {4,6:0.0} {5,5:0.0} {6,5:0} {7,6:0} {8,6:0} {9,6:0} {10,5} {11,5} {12,5} {13,8}" $v.id $v.avgMs $v.p50Ms $v.p95Ms $v.maxMs $v.cpuAvgMs $v.jsHeapUsedMB $v.wasmHeapMB $tab $gpu $v.cars $v.people $v.lamps $d)
    if ($v.avgMs) { $sa += [double]$v.avgMs; $sp += [double]$v.p95Ms; $n++ }
  }
  if ($n -gt 0) {
    $peak = { param($list, $get) $mx = 0.0; foreach ($x in $list) { $y = & $get $x; if ($null -ne $y -and [double]$y -gt $mx) { $mx = [double]$y } }; $mx }
    $pw = & $peak $views { param($x) $x.wasmHeapMB }; $pj = & $peak $views { param($x) $x.jsHeapUsedMB }
    $pt = & $peak $views { param($x) if ($x.os) { $x.os.rendererMB } }; $pg = & $peak $views { param($x) if ($x.os) { $x.os.gpuMB } }
    $pm = & $peak $views { param($x) $x.maxMs }
    Write-Host (Fmt "{0,-18} {1,6:0.0} {2,6} {3,6:0.0} {4,6:0.0} {5,5} {6,5:0} {7,6:0} {8,6:0} {9,6:0}   (mean of the views; memory: peak)" "all" ($sa / $n) "" ($sp / $n) $pm "" $pj $pw $pt $pg)
    if ($base) {
      $bn = 0; $ba = 0.0; $bp = 0.0; foreach ($v in @($base.views)) { if ($v.avgMs) { $ba += [double]$v.avgMs; $bp += [double]$v.p95Ms; $bn++ } }
      $bt = & $peak @($base.views) { param($x) if ($x.os) { $x.os.rendererMB } }; $bw = & $peak @($base.views) { param($x) $x.wasmHeapMB }
      if ($bn -gt 0 -and $ba -gt 0) {
        Write-Host (Fmt "vs base  {0} ({1}): mean avg {2:+0.0;-0.0;0.0} %, mean p95 {3:+0.0;-0.0;0.0} %, wasm heap {4:+0;-0;0} MB, tab {5:+0;-0;0} MB" $basePath $base.run.date (100.0 * ($sa / $n - $ba / $bn) / ($ba / $bn)) (100.0 * ($sp / $n - $bp / $bn) / [Math]::Max($bp / $bn, 0.001)) ($pw - $bw) ($pt - $bt))
        if ($worse.Count -gt 0) { Write-Host ("slower    more than 10 % slower than the baseline (avg or p95): " + ($worse -join ", ")) } else { Write-Host "slower    no view is more than 10 % slower than the baseline" }
      }
    }
  }
  $file
}

# ---------- run: discrete GPU (as before), then the integrated one ----------
$runs = @(@{ tag = "dgpu"; flag = "--force_high_performance_gpu"; text = "discrete GPU" })
if (-not $NoBench -and -not $KeepOpen) { $runs += @{ tag = "igpu"; flag = "--force_low_power_gpu"; text = "integrated GPU" } }
$results = @()
foreach ($run in $runs) { $one = @(Invoke-Run $run.tag $run.flag $run.text); $results += $one[$one.Count - 1]; Start-Sleep -Seconds 2 }
$listener.Stop()

$allPass = $true; $gpuNames = @{}
foreach ($r in $results) {
  $report = $r.report
  $fatal = @(Get-Fatal $r)
  $pass = ($fatal.Count -eq 0); if (-not $pass) { $allPass = $false }
  if ($report -and $report.shot -and $report.shot.StartsWith("data:image/jpeg;base64,")) {
    $shot = "shot" + $r.sfx + ".jpg"
    [IO.File]::WriteAllBytes((Join-Path $out $shot), [Convert]::FromBase64String($report.shot.Substring(23)))
    $report.shot = $shot
  }
  $summary = [ordered]@{ result = $(if ($pass) { "PASS" } else { "FAIL" }); run = $r.tag; build = $Build; browser = $Browser; seconds = $r.secs; fatal = $fatal; page = $report }
  $reportFile = Join-Path $out ("report" + $r.sfx + ".json")
  $summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $reportFile

  Write-Host ""
  Write-Host ("==== " + $r.tag + ": " + $(if ($pass) { "PASS" } else { "FAIL" }))
  if ($report -and $report.gpu) { Write-Host ("GPU      " + $report.gpu.renderer); $gpuNames[$r.tag] = [string]$report.gpu.renderer }
  Write-Host ("start    " + $(if ($report -and $report.startSeconds) { "$($report.startSeconds) s" } else { "-" }))
  Write-Host ("errors   " + $(if ($report) { @($report.errors).Count } else { 0 }) + " recorded, " + $fatal.Count + " fatal")
  $fatal | Select-Object -First 10 | ForEach-Object { Write-Host ("  FATAL  " + $_.Substring(0, [Math]::Min(220, $_.Length))) }
  Write-Host "report   $reportFile"
  $benchFile = Save-Bench $r $pass
}
if ($gpuNames.ContainsKey("igpu") -and $gpuNames.ContainsKey("dgpu") -and $gpuNames["igpu"] -eq $gpuNames["dgpu"]) {
  Write-Host ""
  Write-Host "WARNING  both runs used the same GPU: Chrome did not switch (Windows graphics settings or a laptop on one GPU); the igpu numbers are not the integrated GPU's"
}
Write-Host ""
Write-Host $(if ($allPass) { "PASS" } else { "FAIL" })
if ($allPass) { exit 0 } else { exit 1 }
