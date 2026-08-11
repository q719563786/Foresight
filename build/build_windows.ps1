param(
    [switch]$Describe
)

$ErrorActionPreference = "Stop"

$dependencies = @(
    "pyinstaller==6.21.0",
    "pywebview==6.2.1",
    "pystray==0.19.5",
    "Pillow==12.3.0"
)

if ($Describe) {
    [pscustomobject]@{
        Dependencies = $dependencies
        Gui = "edgechromium"
    } | ConvertTo-Json -Compress
    exit 0
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvRoot = Join-Path $projectRoot ".venv-build"
$pythonExe = Join-Path $venvRoot "Scripts\python.exe"
$specFile = Join-Path $PSScriptRoot "yuanjian.spec"
$workPath = Join-Path $projectRoot "build-artifacts"
$distPath = Join-Path $projectRoot "dist"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    py -3 -m venv $venvRoot
}

& $pythonExe -m pip install --disable-pip-version-check $dependencies
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed" }

& $pythonExe -m PyInstaller --noconfirm --clean --workpath $workPath --distpath $distPath $specFile
if ($LASTEXITCODE -ne 0) { throw "YuanJian Windows build failed" }

$exePath = Join-Path $distPath "YuanJian\YuanJian.exe"
if (-not (Test-Path -LiteralPath $exePath)) { throw "YuanJian.exe was not found" }
Write-Output $exePath
