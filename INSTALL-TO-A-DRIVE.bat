@echo off
setlocal EnableExtensions
title ADios - Install to A:\VibeCode\ADios
cd /d "%~dp0"

set "TARGET=A:\VibeCode\ADios"

echo.
echo  ADios - Copy to A:\VibeCode\ADios
echo  by AlexRabbit
echo.
echo  Source: %CD%
echo  Target: %TARGET%
echo.

if not exist "A:\VibeCode\" (
    echo  Creating A:\VibeCode ...
    mkdir "A:\VibeCode" 2>nul
)
if not exist "%TARGET%\" (
    echo  Creating %TARGET% ...
    mkdir "%TARGET%" 2>nul
)

echo  Copying files...
xcopy /E /Y /I "%CD%\*" "%TARGET%\" >nul 2>&1
if exist "%CD%\adios-publish\" (
    xcopy /E /Y /I "%CD%\adios-publish\*" "%TARGET%\" >nul
)

if exist "%TARGET%\ADios.bat" (
    echo  [OK] Files copied to %TARGET%
    echo.
    echo  Next: double-click %TARGET%\ADios.bat
) else (
    echo  [ERROR] Copy failed. Run this bat from the extracted ADios-publish folder.
)
echo.
pause
