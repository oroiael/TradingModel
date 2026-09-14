@echo off
rem ---------------------------------------------------------------------------
rem  One overnight job, wrapped for Task Scheduler.
rem
rem     run_job.cmd <job> [flags...]
rem
rem  Task Scheduler cannot redirect output and does not set a working directory
rem  you can rely on, so this does both, picks the venv interpreter, and appends
rem  to a per-job log. Its exit code is the job's, because the scheduler's only
rem  reading of a run is the return code.
rem ---------------------------------------------------------------------------
setlocal

set "JOB=%~1"
if "%JOB%"=="" (
  echo usage: run_job.cmd ^<job^> [flags]
  exit /b 2
)

rem The repository root is two directories up from this file.
pushd "%~dp0..\.."
set "REPO=%CD%"

if not exist "%REPO%\overnight\out" mkdir "%REPO%\overnight\out"

rem Prefer the project venv; fall back to whatever python is on PATH.
set "PY=%REPO%\env\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

set "LOG=%REPO%\overnight\out\%JOB%.log"

echo.>> "%LOG%"
echo ======== %DATE% %TIME% ======== >> "%LOG%"
"%PY%" "%REPO%\overnight\run.py" --job %JOB% %2 %3 %4 %5 >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo [exit %RC%] >> "%LOG%"

popd
endlocal & exit /b %RC%
