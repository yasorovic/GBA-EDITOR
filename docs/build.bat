@echo off
"%~dp0..\.venv-docs\Scripts\python.exe" -m sphinx -b html -W --keep-going "%~dp0." "%~dp0_build\html"
if errorlevel 1 exit /b 1
start "" "%~dp0_build\html\index.html"
