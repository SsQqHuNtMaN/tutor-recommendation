@echo off
setlocal

cd /d "%~dp0"

set "HOST=127.0.0.1"
if "%VIEWER_HOST%" neq "" set "HOST=%VIEWER_HOST%"

set "PORT=8765"
if "%VIEWER_PORT%" neq "" set "PORT=%VIEWER_PORT%"
if "%~1" neq "" set "PORT=%~1"

set "PYTHONIOENCODING=utf-8"
set "URL=http://%HOST%:%PORT%/"

set "PYTHON_BIN="
set "FIRST_PYTHON_CANDIDATE="

if defined VIEWER_PYTHON call :try_python "%VIEWER_PYTHON%"
if not defined PYTHON_BIN if defined CONDA_PREFIX call :try_python "%CONDA_PREFIX%\python.exe"
if not defined PYTHON_BIN call :try_conda_base
if not defined PYTHON_BIN call :try_common_conda_paths
if not defined PYTHON_BIN call :try_path_python

if not defined PYTHON_BIN (
  echo A Python environment with pandas and openpyxl was not found.
  if defined FIRST_PYTHON_CANDIDATE echo First Python checked: %FIRST_PYTHON_CANDIDATE%
  echo.
  echo Please install the dependencies into your conda base environment:
  echo   conda install pandas openpyxl
  echo.
  echo Or set VIEWER_PYTHON to the Python executable that has these packages:
  echo   set VIEWER_PYTHON=D:\Conda\python.exe
  echo   start_viewer.bat
  pause
  exit /b 1
)

echo Using Python: %PYTHON_BIN%

"%PYTHON_BIN%" -c "import json,sys,urllib.request; base=sys.argv[1].rstrip('/'); health=json.load(urllib.request.urlopen(base + '/api/health', timeout=0.5)); session=json.load(urllib.request.urlopen(base + '/api/session', timeout=0.5)); raise SystemExit(0 if health.get('apiVersion') == 2 and session.get('token') else 1)" "%URL%" >nul 2>nul
if not errorlevel 1 (
  echo Teacher viewer is already running: %URL%
  if "%VIEWER_NO_BROWSER%" neq "1" start "" "%URL%"
  exit /b 0
)

"%PYTHON_BIN%" -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1].rstrip('/') + '/api/health', timeout=0.5)" "%URL%" >nul 2>nul
if not errorlevel 1 (
  echo An older or incompatible viewer is already using %URL%
  echo Close its terminal or stop that viewer process, then run start_viewer.bat again.
  pause
  exit /b 1
)

echo Starting teacher viewer: %URL%
if "%VIEWER_NO_BROWSER%" neq "1" start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process '%URL%'"
"%PYTHON_BIN%" viewer_server.py --host "%HOST%" --port "%PORT%"

if errorlevel 1 pause
exit /b %ERRORLEVEL%

:try_python
if defined PYTHON_BIN exit /b 0
set "CANDIDATE=%~1"
if not defined CANDIDATE exit /b 1
if not defined FIRST_PYTHON_CANDIDATE set "FIRST_PYTHON_CANDIDATE=%CANDIDATE%"
"%CANDIDATE%" -c "import pandas, openpyxl" >nul 2>nul
if errorlevel 1 exit /b 1
set "PYTHON_BIN=%CANDIDATE%"
exit /b 0

:try_conda_base
for /f "delims=" %%I in ('conda info --base 2^>nul') do (
  if exist "%%I\python.exe" call :try_python "%%I\python.exe"
  if defined PYTHON_BIN exit /b 0
)
exit /b 1

:try_common_conda_paths
call :try_python "%USERPROFILE%\miniconda3\python.exe"
if defined PYTHON_BIN exit /b 0
call :try_python "%USERPROFILE%\anaconda3\python.exe"
if defined PYTHON_BIN exit /b 0
call :try_python "D:\Conda\python.exe"
if defined PYTHON_BIN exit /b 0
call :try_python "C:\ProgramData\miniconda3\python.exe"
if defined PYTHON_BIN exit /b 0
call :try_python "C:\ProgramData\anaconda3\python.exe"
if defined PYTHON_BIN exit /b 0
exit /b 1

:try_path_python
for /f "delims=" %%I in ('where python 2^>nul') do (
  call :try_python "%%I"
  if defined PYTHON_BIN exit /b 0
)
exit /b 1
