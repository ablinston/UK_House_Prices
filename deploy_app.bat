@echo off

REM Activate the virtual environment so rsconnect is available
CALL %~dp0venv\Scripts\activate.bat

SET DEPLOY_DIR=C:\tmp_deploy

REM Clean up any previous deploy folder
if exist "%DEPLOY_DIR%" rd /s /q "%DEPLOY_DIR%"
mkdir "%DEPLOY_DIR%"

REM Copy only the files and folders the app needs using robocopy
REM /E = include subdirectories (even empty), /NFL /NDL /NJH /NJS = quiet output
robocopy "%~dp0app"                "%DEPLOY_DIR%\app"                /E /NFL /NDL /NJH /NJS
robocopy "%~dp0data"               "%DEPLOY_DIR%\data"               /E /NFL /NDL /NJH /NJS
robocopy "%~dp0functions"          "%DEPLOY_DIR%\functions"          /E /NFL /NDL /NJH /NJS
copy "%~dp0app.py"           "%DEPLOY_DIR%\" >nul
copy "%~dp0global.py"        "%DEPLOY_DIR%\" >nul
copy "%~dp0config.yaml"      "%DEPLOY_DIR%\" >nul
copy "%~dp0requirements.txt" "%DEPLOY_DIR%\" >nul

REM Deploy from the clean folder as a new deployment
rsconnect deploy shiny "%DEPLOY_DIR%" --name ablinston --title UK_House_Prices --new

REM Clean up
rd /s /q "%DEPLOY_DIR%"

pause
