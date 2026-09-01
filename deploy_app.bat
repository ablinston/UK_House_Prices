@echo off

REM ============================================================================
REM shinyapps.io deploy
REM
REM "existing deployment has mode '<unknown>'"
REM   The app on the server is corrupted. rsconnect CANNOT fix it with --app-id.
REM   You MUST: shinyapps.io -^> Applications -^> Archive (or Delete) EVERY app
REM   named uk_house_prices or uk_house_prices1, then deploy with DEPLOY_MODE=new.
REM
REM "Application exists with name: uk_house_prices1"
REM   A leftover app is using that name. Archive it too, then use new.
REM
REM After ONE successful deploy with new:
REM   1. Open your app on shinyapps.io -^> Settings -^> copy Application ID
REM   2. Set DEPLOY_MODE=update and APP_ID=that number below
REM   3. Future deploys overwrite the live app (no extra "1" in the URL)
REM ============================================================================
SET DEPLOY_MODE=new
SET APP_ID=9916255

echo.
if /i "%DEPLOY_MODE%"=="new" (
    echo Deploy mode: NEW ^(creates uk_house_prices — archive all old uk_house_prices* apps first^)
) else (
    echo Deploy mode: UPDATE app-id %APP_ID%
)
echo.

REM Activate the virtual environment so rsconnect is available
CALL %~dp0venv\Scripts\activate.bat

REM rsconnect reads app.py and REQUIRES these paths in the bundle. .dvc pointers alone are not enough.
set "ROOT=%~dp0"
set "DATAERR="
if not exist "%ROOT%data\lad_list.parquet" (
    echo   - missing: data\lad_list.parquet
    set DATAERR=1
)
if not exist "%ROOT%data\uk_hpi_data.parquet" (
    echo   - missing: data\uk_hpi_data.parquet
    set DATAERR=1
)
if not exist "%ROOT%data\uk_cpi.parquet" (
    echo   - missing: data\uk_cpi.parquet
    set DATAERR=1
)
if not exist "%ROOT%data\uk_lads.geojson" (
    echo   - missing: data\uk_lads.geojson
    set DATAERR=1
)
if not exist "%ROOT%data\uk_lads_highres.geojson" (
    echo   - missing: data\uk_lads_highres.geojson
    set DATAERR=1
)
if defined DATAERR (
    echo.
    echo ERROR: Required data files are not on disk ^(git/DVC often only has .dvc stubs^).
    echo Materialize them, then deploy again:
    echo   dvc pull
    echo   or run the pipeline: python src\00_pipeline.py
    echo.
    pause
    exit /b 1
)

SET DEPLOY_DIR=C:\tmp_deploy

REM Clean up any previous deploy folder
if exist "%DEPLOY_DIR%" rd /s /q "%DEPLOY_DIR%"
mkdir "%DEPLOY_DIR%"

REM Copy only the files and folders the app needs using robocopy
REM /E = subdirs, /XD = exclude __pycache__ (bytecode breaks shinyapps manifest)
REM /NFL /NDL /NJH /NJS = quiet output
REM Static assets live in www\ (not app\, which clashes with app.py for rsconnect)
robocopy "%~dp0www"                "%DEPLOY_DIR%\www"                /E /XD __pycache__ /NFL /NDL /NJH /NJS
robocopy "%~dp0data"               "%DEPLOY_DIR%\data"               /E /XD __pycache__ /NFL /NDL /NJH /NJS
robocopy "%~dp0functions"          "%DEPLOY_DIR%\functions"          /E /XD __pycache__ /NFL /NDL /NJH /NJS
copy "%~dp0app.py"           "%DEPLOY_DIR%\" >nul
copy "%~dp0global.py"        "%DEPLOY_DIR%\" >nul
copy "%~dp0config.yaml"      "%DEPLOY_DIR%\" >nul
copy "%~dp0requirements.txt" "%DEPLOY_DIR%\" >nul
copy /Y "%~dp0www\custom.css" "%DEPLOY_DIR%\www\custom.css" >nul 2>&1

REM Not for runtime: dotfiles + DVC pointers confuse shinyapps (manifest lists them; upload omits them)
if exist "%DEPLOY_DIR%\data\.gitignore" del /q "%DEPLOY_DIR%\data\.gitignore"
del /q "%DEPLOY_DIR%\data\*.dvc" 2>nul
set "PS_DEPLOY=%DEPLOY_DIR%"
powershell -NoProfile -Command "Get-ChildItem -LiteralPath $env:PS_DEPLOY -Recurse -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq '.gitignore' } | Remove-Item -Force -ErrorAction SilentlyContinue"
powershell -NoProfile -Command "Get-ChildItem -LiteralPath $env:PS_DEPLOY -Recurse -Force -ErrorAction SilentlyContinue | Where-Object { $_.Extension -eq '.dvc' } | Remove-Item -Force -ErrorAction SilentlyContinue"
set PS_DEPLOY=

REM Remove any stray __pycache__ / .pyc (belt and suspenders)
if exist "%DEPLOY_DIR%\www\__pycache__"       rd /s /q "%DEPLOY_DIR%\www\__pycache__"
if exist "%DEPLOY_DIR%\functions\__pycache__" rd /s /q "%DEPLOY_DIR%\functions\__pycache__"
if exist "%DEPLOY_DIR%\__pycache__"          rd /s /q "%DEPLOY_DIR%\__pycache__"

if not exist "%DEPLOY_DIR%\www\custom.css" (
    echo ERROR: www\custom.css was not copied to the deploy folder. Check www\custom.css exists.
    pause
    exit /b 1
)

set "DATAERR="
if not exist "%DEPLOY_DIR%\data\lad_list.parquet"       set DATAERR=1
if not exist "%DEPLOY_DIR%\data\uk_hpi_data.parquet"   set DATAERR=1
if not exist "%DEPLOY_DIR%\data\uk_cpi.parquet"        set DATAERR=1
if not exist "%DEPLOY_DIR%\data\uk_lads.geojson"       set DATAERR=1
if not exist "%DEPLOY_DIR%\data\uk_lads_highres.geojson" set DATAERR=1
if defined DATAERR (
    echo ERROR: Data files did not copy into the deploy folder. Check disk space and paths.
    pause
    exit /b 1
)

if /i "%DEPLOY_MODE%"=="new" (
    rsconnect deploy shiny "%DEPLOY_DIR%" --name ablinston --title UK_House_Prices --new
) else (
    rsconnect deploy shiny "%DEPLOY_DIR%" --name ablinston --title UK_House_Prices --app-id %APP_ID%
)

REM Clean up
rd /s /q "%DEPLOY_DIR%"

pause
