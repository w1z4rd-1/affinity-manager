<# 
Builds an obfuscated, single-file EXE using PyInstaller via PyArmor.

Steps performed:
1) Ensure pip, pyinstaller, pyarmor are installed (auto-installs if missing)
2) Obfuscate + pack: streaming_affinity_gui.py -> dist/StreamingAffinityManager.exe

Usage:
  powershell -ExecutionPolicy Bypass -File build_exe.ps1

Note:
  - Requires internet to pull PyInstaller/PyArmor if not already installed.
  - Output EXE: .\dist\StreamingAffinityManager.exe
#>

$ErrorActionPreference = "Stop"

function Ensure-Package($name) {
    Write-Host "Checking $name..." -ForegroundColor Cyan
    $installed = python - <<'PY'
import importlib, sys
pkg = sys.argv[1]
try:
    importlib.import_module(pkg)
    print("OK")
except ImportError:
    print("MISS")
PY
    if ($LASTEXITCODE -ne 0) { throw "Python check failed for $name" }
    if ($installed.Trim() -eq "MISS") {
        Write-Host "Installing $name..." -ForegroundColor Yellow
        py -m pip install --upgrade $name
        if ($LASTEXITCODE -ne 0) { throw "Failed to install $name" }
    }
}

Write-Host "=== Streaming Affinity Manager - Build (PyInstaller + PyArmor) ===" -ForegroundColor Green

# 1) Ensure dependencies
py -m pip install --upgrade pip
Ensure-Package "pyinstaller"
Ensure-Package "pyarmor"

# 2) Pack with obfuscation
Write-Host "Packing with PyArmor (includes PyInstaller)..." -ForegroundColor Green
pyarmor pack `
  -e "--noconsole --onefile --name StreamingAffinityManager" `
  streaming_affinity_gui.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild complete! Find the EXE at: dist\\StreamingAffinityManager.exe" -ForegroundColor Green
} else {
    Write-Host "`nBuild failed. Check the log above." -ForegroundColor Red
}

