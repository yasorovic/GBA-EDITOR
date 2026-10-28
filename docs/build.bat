@echo off
rem Sphinx ne supprime pas les pages dont la source a disparu : on repart d'un dossier vide.
if exist "%~dp0_build" rmdir /s /q "%~dp0_build"
"%~dp0..\.venv-docs\Scripts\python.exe" -m sphinx -b html -W --keep-going "%~dp0." "%~dp0_build\html"
if errorlevel 1 exit /b 1

rem Le theme clair/sombre est memorise par le navigateur : en file:// il ne suit pas d'une page a l'autre.
rem Le site est donc servi en http local. Le serveur reste dans sa fenetre : la fermer l'arrete.
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if errorlevel 1 start "Documentation Backstage - serveur local" "%~dp0..\.venv-docs\Scripts\python.exe" "%~dp0serve.py" "%~dp0_build\html"
start "" "http://localhost:8000/"
