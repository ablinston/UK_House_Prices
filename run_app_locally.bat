@echo off

CALL %~dp0venv\Scripts\activate.bat

shiny run --reload %~dp0app.py
