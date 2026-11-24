# Scene Filter launcher for Windows (Windows PowerShell 5.1 or newer).
# First run downloads Python, the detector and ffmpeg into %LOCALAPPDATA%\Scene Filter (about 700 MB),
# then opens the app in your browser. This console window stays open while it runs; closing it quits.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is very slow with its progress bar on
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$SetupVersion = 1   # bump when requirements change so existing installs update
$Src     = $PSScriptRoot
$Support = Join-Path $env:LOCALAPPDATA 'Scene Filter'
$EnvDir  = Join-Path $Support 'env'
$BinDir  = Join-Path $Support 'bin'
$Uv      = Join-Path $BinDir 'uv.exe'
$Python  = Join-Path $EnvDir 'Scripts\python.exe'
$Ready   = Join-Path $Support ".ready-$SetupVersion"

$env:UV_PYTHON_INSTALL_DIR = Join-Path $Support 'python'
$env:UV_CACHE_DIR          = Join-Path $Support 'cache'
$env:SCENE_FILTER_OUTPUT   = Join-Path ([Environment]::GetFolderPath('MyVideos')) 'Scene Filter'
$env:SCENE_FILTER_MODELS   = Join-Path $Support 'models'   # the accurate detector is downloaded here on first scan
$env:GRADIO_TEMP_DIR       = Join-Path $Support 'dropped-movies'  # dropped movies are copied here; cleared on start
$env:GRADIO_ANALYTICS_ENABLED = 'False'
$env:PYTHONDONTWRITEBYTECODE  = '1'
$env:PYTHONIOENCODING         = 'utf-8'
# The starter (run.py) keeps the app up to date: where to keep versions, and how to install packages.
$env:SCENE_FILTER_SUPPORT     = $Support
$env:SCENE_FILTER_UV          = $Uv

function Fail($msg) {
    Write-Host ''
    Write-Host $msg -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $BinDir, $env:SCENE_FILTER_OUTPUT | Out-Null
Write-Host 'Scene Filter' -ForegroundColor Cyan
Write-Host ''

if (-not (Test-Path $Ready)) {
    Write-Host 'Setting up for the first time. This takes a few minutes and needs internet.' -ForegroundColor Yellow
    if (-not (Test-Path $Uv)) {
        Write-Host 'Downloading the setup tool...'
        # The x86-64 build also runs on ARM Windows PCs (through Windows' built-in emulation).
        $zip = Join-Path $Support 'uv.zip'
        try {
            Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile $zip
            $tmp = Join-Path $Support 'uv-unpack'
            if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
            Expand-Archive -Path $zip -DestinationPath $tmp -Force
            Get-ChildItem -Path $tmp -Recurse -Filter '*.exe' | Copy-Item -Destination $BinDir -Force
            Remove-Item -Recurse -Force $tmp, $zip
        } catch {
            Fail "Scene Filter couldn't download its setup tool. Check your internet connection and try again.`n$($_.Exception.Message)"
        }
        if (-not (Test-Path $Uv)) { Fail "Scene Filter's setup tool didn't unpack correctly. Try again." }
    }
    if (Test-Path $EnvDir) { Remove-Item -Recurse -Force $EnvDir }
    Write-Host 'Setting up Python...'
    # Always the x86-64 Python that the setup tool downloads itself: every package the app needs exists for it.
    & $Uv venv --python-preference only-managed --python cpython-3.12-windows-x86_64-none $EnvDir
    if ($LASTEXITCODE -ne 0) { Fail "Scene Filter couldn't set up Python." }
    Write-Host 'Downloading the detector and video tools (the big part)...'
    & $Uv pip install --python $Python -r (Join-Path $Src 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { Fail "Scene Filter couldn't download the packages it needs. Check your internet connection and try again." }
    Get-ChildItem -Path $Support -Filter '.ready-*' -Force | Remove-Item -Force
    New-Item -ItemType File -Path $Ready | Out-Null
    Write-Host 'Setup finished.' -ForegroundColor Green
    Write-Host ''
}

if (Test-Path $env:GRADIO_TEMP_DIR) { Remove-Item -Recurse -Force $env:GRADIO_TEMP_DIR -ErrorAction SilentlyContinue }
Write-Host 'Scene Filter is opening in your browser.' -ForegroundColor Green
Write-Host 'Keep this window open while you use it. Closing it quits Scene Filter (and stops any scan or save in progress).'
Write-Host "Filtered movies and timestamp lists are saved in: $($env:SCENE_FILTER_OUTPUT)"
Write-Host ''
& $Python (Join-Path $Src 'run.py')
exit $LASTEXITCODE
