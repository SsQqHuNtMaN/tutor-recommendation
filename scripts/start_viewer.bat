@echo off
setlocal

cd /d "%~dp0.."

set "HOST=127.0.0.1"
if "%VIEWER_HOST%" neq "" set "HOST=%VIEWER_HOST%"

set "PORT=8765"
if "%VIEWER_PORT%" neq "" set "PORT=%VIEWER_PORT%"
if "%~1" neq "" set "PORT=%~1"

set "PYTHONIOENCODING=utf-8"
set "URL=http://%HOST%:%PORT%/"

rem Reuse an already-running current Viewer before looking for Python.
powershell -NoProfile -Command "try { $health=Invoke-RestMethod -UseBasicParsing -TimeoutSec 1 '%URL%api/health'; $session=Invoke-RestMethod -UseBasicParsing -TimeoutSec 1 '%URL%api/session'; if ($health.apiVersion -eq 7 -and $session.token) { exit 0 } } catch {}; exit 1" >nul 2>nul
if not errorlevel 1 (
  echo Teacher viewer is already running: %URL%
  if "%VIEWER_NO_BROWSER%" neq "1" start "" "%URL%"
  exit /b 0
)

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
  echo   scripts\start_viewer.bat
  pause
  exit /b 1
)

echo Using Python: %PYTHON_BIN%

set "PREFERRED_PORT=%PORT%"
set "AVAILABLE_PORT="
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "PORT_FILE=%TEMP%\tutor_viewer_port_%RANDOM%_%RANDOM%.tmp"
"%PYTHON_BIN%" -m tutor_recommendation.viewer_launcher --host "%HOST%" --start-port "%PORT%" >"%PORT_FILE%" 2>nul
if not errorlevel 1 set /p "AVAILABLE_PORT="<"%PORT_FILE%"
del /q "%PORT_FILE%" >nul 2>nul
if not defined AVAILABLE_PORT (
  echo No available Viewer port was found between %PORT% and the next 99 ports.
  pause
  exit /b 1
)
set "PORT=%AVAILABLE_PORT%"
set "URL=http://%HOST%:%PORT%/"

if not "%PORT%"=="%PREFERRED_PORT%" (
  echo Port %PREFERRED_PORT% is already in use by an older Viewer or another program.
  echo The current Viewer will use %URL% without stopping the existing process.
)

echo Starting teacher viewer: %URL%
if "%VIEWER_NO_BROWSER%" neq "1" start "" powershell -NoProfile -WindowStyle Hidden -Command "$url='%URL%'; for ($i=0; $i -lt 60; $i++) { try { $health=Invoke-RestMethod -UseBasicParsing -TimeoutSec 1 ($url + 'api/health'); if ($health.apiVersion -eq 7) { Start-Process $url; exit 0 } } catch {}; Start-Sleep -Milliseconds 250 }; exit 1"
"%PYTHON_BIN%" tutor.py view --host "%HOST%" --port "%PORT%"

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
