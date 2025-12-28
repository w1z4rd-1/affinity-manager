@echo off
REM Build obfuscated single-file EXE using PyInstaller via PyArmor
REM Usage: double-click this file (requires internet to fetch pyinstaller/pyarmor)

setlocal
cd /d "%~dp0"

echo === Streaming Affinity Manager - Build (PyInstaller + PyArmor) ===

echo Updating pip...
py -m pip install --upgrade pip

echo Checking/Installing pyinstaller...
py - <<PY
import importlib, sys, subprocess
def ensure(pkg):
    try:
        importlib.import_module(pkg)
        print("OK")
    except ImportError:
        sys.exit(1)
ensure("pyinstaller")
PY
if errorlevel 1 (
    py -m pip install pyinstaller
    if errorlevel 1 goto :fail
)

echo Checking/Installing pyarmor...
py - <<PY
import importlib, sys
try:
    importlib.import_module("pyarmor")
    print("OK")
except ImportError:
    sys.exit(1)
PY
if errorlevel 1 (
    py -m pip install pyarmor
    if errorlevel 1 goto :fail
)

echo Packing with PyArmor (includes PyInstaller)...
pyarmor pack -e " --noconsole --onefile --name StreamingAffinityManager " streaming_affinity_gui.py
if errorlevel 1 goto :fail

echo.
echo Build complete! Find the EXE at: dist\StreamingAffinityManager.exe
goto :eof

:fail
echo.
echo Build failed. See messages above.
exit /b 1

