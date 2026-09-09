@echo off

REM Navigate to the project directory
cd /d %~dp0

REM Remove the old docker image
docker rmi uk_house_prices

REM Create new docker image
docker build -t ablinston/uk_house_prices .
