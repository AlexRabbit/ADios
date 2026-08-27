@echo off
setlocal EnableExtensions
title ADios Blocklist Builder - AlexRabbit
cd /d "%~dp0"

echo.
echo  ============================================
echo   ADios - Say Goodbye to Ads
echo   by AlexRabbit
echo  ============================================
echo.
echo  Building blocklists from config/lists ...
echo  This may take several minutes (DNS probe).
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.9 or newer is required.
    echo  Download: https://www.python.org/downloads/
    echo  During install, check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

python config\build_hosts.py
set BUILD_EXIT=%ERRORLEVEL%

echo.
if %BUILD_EXIT% neq 0 (
    echo  [FAILED] Build exited with code %BUILD_EXIT%.
) else (
    echo  [OK] Build complete.
    echo.
    echo  Output files in this folder:
    echo    hosts            - Windows / macOS / Linux system hosts
    echo    pihole-hosts     - Pi-hole gravity import
    echo    dnscrypt-hosts   - DNSCrypt-proxy blocked_names
    echo    adguardhosts.txt - AdGuard Home / uBlock syntax
    echo    remover.txt      - Dead domains removed from lists
    echo.
    echo  Config updated: config\remover, config\probe_cache
)
echo.
pause
exit /b %BUILD_EXIT%
