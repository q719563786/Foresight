$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvRoot = Join-Path $projectRoot ".venv-build"
$pythonExe = Join-Path $venvRoot "Scripts\python.exe"
$specFile = Join-Path $PSScriptRoot "yuanjian.spec"
$workPath = Join-Path $projectRoot "build-artifacts"
$distPath = Join-Path $projectRoot "dist"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    py -3 -m venv $venvRoot
}

& $pythonExe -m pip install --disable-pip-version-check "pyinstaller==6.21.0"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller installation failed" }

& $pythonExe -m PyInstaller --noconfirm --clean --workpath $workPath --distpath $distPath $specFile
if ($LASTEXITCODE -ne 0) { throw "YuanJian Windows build failed" }

$exePath = Join-Path $distPath "YuanJian\YuanJian.exe"
if (-not (Test-Path -LiteralPath $exePath)) { throw "YuanJian.exe was not found" }
Write-Output $exePath
