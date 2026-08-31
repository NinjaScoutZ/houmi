@echo off
setlocal EnableDelayedExpansion
REM GODKILLER write-guard — portable PreToolUse wrapper (no machine-specific paths)
REM Optional machine pin (gitignored): godkiller-write-guard.local.cmd
if exist "%~dp0godkiller-write-guard.local.cmd" (
  call "%~dp0godkiller-write-guard.local.cmd"
  exit /b !ERRORLEVEL!
)
where godkiller-write-guard >nul 2>&1
if !ERRORLEVEL!==0 (
  godkiller-write-guard --stdin
  exit /b !ERRORLEVEL!
)
where py >nul 2>&1
if !ERRORLEVEL!==0 (
  py -3 -m godkiller_mcp.write_guard --stdin
  exit /b !ERRORLEVEL!
)
where python >nul 2>&1
if !ERRORLEVEL!==0 (
  python -m godkiller_mcp.write_guard --stdin
  exit /b !ERRORLEVEL!
)
where python3 >nul 2>&1
if !ERRORLEVEL!==0 (
  python3 -m godkiller_mcp.write_guard --stdin
  exit /b !ERRORLEVEL!
)
echo GODKILLER write-guard: run godkiller-bootstrap again, or put Python/Scripts on PATH. 1>&2
exit /b 2
