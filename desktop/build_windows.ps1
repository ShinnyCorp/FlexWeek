#Requires -Version 5.1
# Build the FlexWeek Windows desktop shell (onedir standalone).
#
# Mirror of desktop/build_linux.sh: the FastAPI backend is compiled into the
# desktop process, so dist\FlexWeek-Windows
# runs with no Python install and no separate server. The window is native Qt
# widgets. Onefile is not used because Qt plugins ship as a folder (see DESKTOP.md).
#
# This script never deletes or overwrites existing artifacts. Nuitka compiles
# into a unique staging folder under build\, and the finished onedir is only
# moved to dist\FlexWeek-Windows when that path does not exist yet. On failure
# the staging folder is kept and its location is printed.
#
# No silent downloads by default: --assume-yes-for-downloads is not passed, so
# Nuitka asks before fetching anything (e.g. dependency walker, which Windows
# standalone mode requires). Pass -AssumeYesForDownloads to approve those
# prompts non-interactively — intended for CI, where a prompt would hang. For
# Python 3.13+ the compiler must be MSVC; Nuitka's MinGW64 download does not
# support those versions.

param(
    [switch]$AssumeYesForDownloads
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Fail([string]$Message, [int]$Code = 1) {
    Write-Host "ERROR: $Message"
    exit $Code
}

$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$BuildDir = Join-Path $Root 'build'
$DistDir = Join-Path $Root 'dist'
$Destination = Join-Path $DistDir 'FlexWeek-Windows'

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    Fail "No venv interpreter at $VenvPython. Create a Python 3.14 venv and install both requirements files:`n  py -3.14 -m venv .venv`n  .venv\Scripts\python -m pip install -r requirements.txt -r requirements-desktop.txt"
}

$Version = @(& $VenvPython --version)[0]
if ($LASTEXITCODE -ne 0) {
    Fail ".venv interpreter could not report a version (exit $LASTEXITCODE)." $LASTEXITCODE
}
if ($Version -notmatch '^Python 3\.14(?:\.|$)') {
    Fail "Expected Python 3.14 (spec.md pins it), got '$Version'. Recreate .venv with Python 3.14."
}

$NuitkaVersion = @(& $VenvPython -m nuitka --version)[0]
if ($LASTEXITCODE -ne 0) {
    Fail "Nuitka is not importable through $VenvPython (exit $LASTEXITCODE). Install the build tooling:`n  .venv\Scripts\python -m pip install -r requirements-desktop.txt" $LASTEXITCODE
}
if ($NuitkaVersion -notmatch '^4\.2\.1') {
    Write-Warning "Nuitka $NuitkaVersion found, but requirements-desktop.txt pins 4.2.1. Continuing; the pinned version is the tested one."
}

# MSVC is found via vswhere, so cl does not have to be on PATH; this only
# warns when no compiler is visible at all.
if (-not (Get-Command gcc, cc, cl -ErrorAction SilentlyContinue)) {
    Write-Warning "No C compiler (gcc/cc/cl) visible on PATH. If Nuitka cannot find MSVC it will ask before downloading anything; approve nothing for MinGW64 (it does not support Python 3.13+). Install Visual Studio 2022 or Build Tools with the C++ workload instead."
}

if (Test-Path -LiteralPath $Destination) {
    Fail "Destination $Destination already exists. Move or delete it yourself and rerun; this script does not remove or overwrite existing artifacts."
}

$Stage = Join-Path $BuildDir ('windows-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $Stage) {
    Fail "Staging folder $Stage unexpectedly exists; rerun to pick a fresh timestamp."
}
New-Item -ItemType Directory -Path $Stage -Force | Out-Null

# Makes the desktop and backend packages resolvable during the build, exactly
# like the PYTHONPATH export in build_linux.sh.
$PreviousPythonPath = $env:PYTHONPATH

$NuitkaArgs = @(
    '--mode=standalone',
    '--follow-imports',
    '--enable-plugins=pyside6',
    '--include-package=desktop.native',
    '--include-package=backend',
    # The window's icon and the Inter faces, found beside the code as they are in a checkout.
    "--include-data-dir=$(Join-Path $Root 'desktop\assets')=desktop/assets",
    '--nofollow-import-to=desktop.tests,backend.tests',
    '--nofollow-import-to=PySide6.QtWebEngineCore,PySide6.QtWebEngineWidgets,PySide6.QtWebEngineQuick',
    # Type-checking tools and uvicorn extras desktop/server.py never enables;
    # the same list as build_linux.sh.
    '--nofollow-import-to=mypy,pydantic.mypy,uvloop,httptools,watchfiles,websockets,yaml',
    '--msvc=latest',
    '--noinclude-dlls=*.cpp.o',
    '--noinclude-dlls=*.qsb',
    '--include-qt-plugins=multimedia,networkinformation,platforminputcontexts,position,qmllint,qmltooling,vectorimageformats',
    '--noinclude-qt-plugins=printsupport',
    '--include-windows-runtime-dlls=yes',
    '--output-filename=FlexWeek.exe',
    "--output-dir=$Stage",
    "--windows-icon-from-ico=$(Join-Path $Root 'desktop\assets\logo.png')",
    '--windows-console-mode=disable'
)
if ($AssumeYesForDownloads) {
    $NuitkaArgs += '--assume-yes-for-downloads'
}

Write-Host "Compiling into $Stage..."
try {
    $env:PYTHONPATH = $Root
    & $VenvPython -m nuitka (Join-Path $PSScriptRoot 'main.py') @NuitkaArgs
    $BuildExitCode = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $PreviousPythonPath
}
if ($BuildExitCode -ne 0) {
    Fail "Nuitka failed with exit code $BuildExitCode. Staging kept for inspection at $Stage" $BuildExitCode
}

$Built = Join-Path $Stage 'main.dist'
if (-not (Test-Path -LiteralPath $Built -PathType Container)) {
    Fail "Nuitka exited 0 but $Built is missing. Staging kept for inspection at $Stage"
}

if (-not (Test-Path -LiteralPath $DistDir)) {
    New-Item -ItemType Directory -Path $DistDir | Out-Null
}
if (Test-Path -LiteralPath $Destination) {
    Fail "Destination $Destination appeared while building. Staging kept for inspection at $Stage; move or delete the destination yourself, then rerun."
}

$BuiltExe = Join-Path $Built 'FlexWeek.exe'
if (-not (Test-Path -LiteralPath $BuiltExe -PathType Leaf)) {
    Fail "Nuitka exited 0 but $BuiltExe is missing. Nothing published; staging kept at $Stage"
}

# Same trimming as desktop/finish_linux_bundle.sh: Qt tool translations are never
# loaded. Native builds have no Chromium locale packs; leftover WebEngine files
# are trimmed only if a follow-import leaked them.
Get-ChildItem -LiteralPath $Built -Recurse -File -Filter '*.qm' | Remove-Item
Get-ChildItem -LiteralPath $Built -Recurse -File -Filter '*.pak' |
    Where-Object { $_.Directory.Name -eq 'qtwebengine_locales' -and $_.Name -ne 'en-US.pak' } | Remove-Item
Get-ChildItem -LiteralPath $Built -Recurse -File -Filter '*.debug.pak' | Remove-Item
Get-ChildItem -LiteralPath $Built -Recurse -File -Filter 'qtwebengine_devtools_resources*.pak' | Remove-Item

# Every imported DLL must be in the bundle or part of Windows 10 1809+. System
# DLLs such as icuuc.dll are checked for, never copied (see check_bundle.py).
try {
    $env:PYTHONPATH = $Root
    & $VenvPython -m desktop.check_bundle windows $Built
    $CheckExitCode = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $PreviousPythonPath
}
if ($CheckExitCode -ne 0) {
    Fail "Bundle check failed. Nothing published; staging kept at $Stage" $CheckExitCode
}

# Directory.Move refuses an existing destination, including one created after
# the check above; Move-Item could instead nest the bundle into that directory.
try {
    [System.IO.Directory]::Move($Built, $Destination)
} catch {
    Fail "Could not publish the bundle: $($_.Exception.Message). Staging kept at $Stage"
}
$Exe = Join-Path $Destination 'FlexWeek.exe'
Copy-Item -LiteralPath (Join-Path $Root 'LICENSE') -Destination (Join-Path $Destination 'LICENSE.txt')
Copy-Item -LiteralPath (Join-Path $Root 'desktop\assets\logo.png') -Destination (Join-Path $Destination 'flexweek.png')
try {
    $env:PYTHONPATH = $Root
    & $VenvPython -m desktop.readme (Join-Path $Root 'desktop\windows\README.txt') (Join-Path $Destination 'README.txt')
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not write README.txt into the bundle" $LASTEXITCODE
    }
} finally {
    $env:PYTHONPATH = $PreviousPythonPath
}

Write-Host ''
Write-Host "Built: $Exe"
$Bytes = (Get-ChildItem -LiteralPath $Destination -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ('Size: {0:N0} MB' -f ($Bytes / 1MB))
Write-Host "Nuitka's intermediate files (main.build) remain in $Stage and can be deleted manually."
