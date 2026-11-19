@echo off
setlocal enabledelayedexpansion
title Compilatore IPTV List Checker -> EXE

set "SCRIPT_NAME=iptv_checker.py"
set "EXE_NAME=IPTV_List_Checker"
set "ICON_FILE=icona.ico"

cd /d "%~dp0"

if not exist "%SCRIPT_NAME%" (
    echo [ERRORE] File "%SCRIPT_NAME%" non trovato nella cartella corrente!
    pause
    exit /b 1
)

if exist "%EXE_NAME%.exe" del /f /q "%EXE_NAME%.exe"

set "PY_CMD="
if exist "%LOCALAPPDATA%\Python\bin\python.exe" set "PY_CMD="%LOCALAPPDATA%\Python\bin\python.exe""

if "%PY_CMD%"=="" (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
        if exist "%%D\python.exe" set "PY_CMD="%%D\python.exe""
    )
)

if "%PY_CMD%"=="" (
    for /d %%D in ("C:\Python*") do (
        if exist "%%D\python.exe" set "PY_CMD="%%D\python.exe""
    )
)

if "%PY_CMD%"=="" (
    echo [ERRORE] Nessuna installazione valida di Python trovata.
    pause
    exit /b 1
)

echo Python rilevato: %PY_CMD%
%PY_CMD% -m PyInstaller --version >nul 2>&1
if errorlevel 1 %PY_CMD% -m pip install pyinstaller

set "ICON_PARAM="
if exist "%ICON_FILE%" set "ICON_PARAM=--icon="%ICON_FILE%""

%PY_CMD% -m PyInstaller --noconsole --onefile --clean %ICON_PARAM% --name "%EXE_NAME%" "%SCRIPT_NAME%"
if errorlevel 1 (
    echo [ERRORE] Compilazione fallita.
    pause
    exit /b 1
)

if exist "dist\%EXE_NAME%.exe" move /y "dist\%EXE_NAME%.exe" ".\%EXE_NAME%.exe" >nul
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "%EXE_NAME%.spec" del /f /q "%EXE_NAME%.spec"
if exist "__pycache__" rmdir /s /q "__pycache__"

echo ========================================================
echo   COMPILAZIONE COMPLETATA: %EXE_NAME%.exe
echo ========================================================
pause
