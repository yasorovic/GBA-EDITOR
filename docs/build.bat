@echo off
"%~dp0..\.venv-docs\Scripts\python.exe" -m sphinx -b html -W --keep-going "%~dp0." "%~dp0_build\html"
if errorlevel 1 exit /b 1

rem Le theme clair/sombre est memorise par le navigateur : en file:// il ne suit pas d'une page a l'autre.
rem Le site est donc servi en http local. Le serveur reste dans sa fenetre : la fermer l'arrete.
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if errorlevel 1 start "Documentation Backstage - serveur local" "%~dp0..\.venv-docs\Scripts\python.exe" -m http.server 8000 --bind 127.0.0.1 -d "%~dp0_build\html"
start "" "http://localhost:8000/"
