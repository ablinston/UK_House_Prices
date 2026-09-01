@echo off
REM ============================================================================
REM Preview the static site locally, exactly as it will be served in production.
REM
REM This is a plain static file server - there is no build step and no app
REM process. If web\data is empty, generate it first:
REM     venv\Scripts\python.exe src\06_export_web_data.py
REM ============================================================================

CALL %~dp0venv\Scripts\activate.bat

if not exist "%~dp0web\data\meta.json" (
    echo.
    echo ERROR: web\data\meta.json is missing, so the site has no data to show.
    echo Generate it with:
    echo     venv\Scripts\python.exe src\06_export_web_data.py
    echo.
    pause
    exit /b 1
)

echo.
echo   UK House Prices - local preview
echo   Open http://localhost:8000
echo   Press Ctrl+C to stop.
echo.

python -m http.server 8000 --directory "%~dp0web"
