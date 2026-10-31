<#
  Alatau City - WebGL build check on Windows, in the real Chrome (ANGLE on Direct3D 11: where the site died on 28.10).
  No Node, no Python, nothing to install: PowerShell serves the build folder on localhost (HEAD, Range, ETag, like
  GitHub Pages), opens it in Chrome (or Edge) with a throw-away profile, and waits for the page's own report
  (the template's check mode, ?check=1, posts its state, errors, GPU and a canvas snapshot to /__check).
  Chrome's own log is scanned for a GPU process crash. Prints PASS or FAIL; exit code 0 / 1 (2 = could not run).

  Run (double-click check_build_windows.cmd, or):
    powershell -ExecutionPolicy Bypass -File tools\webgl_check\check_build_windows.ps1 [-Build <folder or .zip>] [-Timeout 900]
  Default build folder: UnityProject\Builds\WebGL next to this repo. Results: <build>\..\webgl_check\ (report.json, shot.jpg, chrome_debug.log).
#>
param(
  [string]$Build = "",
  [int]$Timeout = 900,
  [int]$Port = 8765,
  [string]$Browser = "",
  [switch]$KeepOpen
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

# ---------- run ----------
$profileDir = Join-Path $env:TEMP ("alatau_check_" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
$url = "http://localhost:$Port/?check=1"
$chromeArgs = @("--user-data-dir=`"$profileDir`"", "--no-first-run", "--no-default-browser-check", "--use-angle=d3d11", "--force_high_performance_gpu", "--enable-logging", "--v=0",
          "--autoplay-policy=no-user-gesture-required", "--window-size=1600,900", "--new-window", $url)
Write-Host "serving $Build at $url"
Write-Host "browser $Browser (ANGLE D3D11, discrete GPU)"
$proc = Start-Process -FilePath $Browser -ArgumentList $chromeArgs -PassThru
$log = Join-Path $profileDir "chrome_debug.log"
$t0 = Get-Date; $report = $null; $gpuCrash = @(); $task = $listener.GetContextAsync()
while (((Get-Date) - $t0).TotalSeconds -lt $Timeout) {
  if ($task.Wait(500)) {
    $ctx = $task.Result; $task = $listener.GetContextAsync()
    if ($ctx.Request.HttpMethod -eq "POST" -and $ctx.Request.Url.AbsolutePath -eq "/__check") {
      $sr = New-Object IO.StreamReader($ctx.Request.InputStream, [Text.Encoding]::UTF8); $body = $sr.ReadToEnd(); $sr.Close()
      $ctx.Response.StatusCode = 200; $ctx.Response.Close()
      $report = $body | ConvertFrom-Json
      break
    }
    Serve $ctx
  }
  if (Test-Path $log) {
    $hits = Select-String -Path $log -Pattern "GPU process exited unexpectedly|GPU process has crashed|GPU state invalid|Stack overflow|STATUS_STACK_OVERFLOW" -ErrorAction SilentlyContinue
    if ($hits) { $gpuCrash = @($hits | ForEach-Object { $_.Line.Trim() }) }
  }
  if ($proc.HasExited -and -not $KeepOpen) { break }
}
$secs = [int]((Get-Date) - $t0).TotalSeconds
Start-Sleep -Milliseconds 800
if (Test-Path $log) {
  Copy-Item $log (Join-Path $out "chrome_debug.log") -Force
  $hits = Select-String -Path $log -Pattern "GPU process exited unexpectedly|GPU process has crashed|GPU state invalid|Stack overflow|STATUS_STACK_OVERFLOW" -ErrorAction SilentlyContinue
  if ($hits) { $gpuCrash = @($hits | ForEach-Object { $_.Line.Trim() }) }
}
if (-not $KeepOpen) {
  try { & taskkill /PID $proc.Id /T /F 2>$null | Out-Null } catch { }
  Start-Sleep -Milliseconds 500
  Remove-Item -Recurse -Force $profileDir -ErrorAction SilentlyContinue
}
$listener.Stop()

# ---------- verdict ----------
$fatal = @()
if (-not $report) { $fatal += $(if ($secs -ge $Timeout) { "timed out after $Timeout s without a report from the page" } else { "the browser closed before the page reported" }) }
else {
  if ($report.state -ne "running") { $fatal += "page state: $($report.state) - $($report.fatal)" }
  foreach ($e in @($report.errors)) {
    if ($e.kind -match "^(gl-link|gl-compile|fatal-)" -or $e.msg -match "GLSL compilation failed|failed to link|Shader error|RuntimeError|memory access out of bounds") {
      $fatal += "$($e.kind): $(($e.msg -split "`n")[0])"
    }
  }
  if ($report.shot -and $report.shot.StartsWith("data:image/jpeg;base64,")) {
    [IO.File]::WriteAllBytes((Join-Path $out "shot.jpg"), [Convert]::FromBase64String($report.shot.Substring(23)))
    $report.shot = "shot.jpg"
  }
}
$fatal += $gpuCrash | ForEach-Object { "GPU process: $_" }
$pass = ($fatal.Count -eq 0)
$summary = [ordered]@{ result = $(if ($pass) { "PASS" } else { "FAIL" }); build = $Build; browser = $Browser; seconds = $secs; fatal = $fatal; page = $report }
$summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $out "report.json")

Write-Host ""
if ($report -and $report.gpu) { Write-Host ("GPU      " + $report.gpu.renderer) }
Write-Host ("start    " + $(if ($report -and $report.startSeconds) { "$($report.startSeconds) s" } else { "-" }))
Write-Host ("errors   " + $(if ($report) { @($report.errors).Count } else { 0 }) + " recorded, " + $fatal.Count + " fatal")
$fatal | Select-Object -First 10 | ForEach-Object { Write-Host ("  FATAL  " + $_.Substring(0, [Math]::Min(220, $_.Length))) }
Write-Host "report   $(Join-Path $out 'report.json')"
Write-Host $(if ($pass) { "PASS" } else { "FAIL" })
if ($pass) { exit 0 } else { exit 1 }
