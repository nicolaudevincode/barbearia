@echo off
REM Abre o site no computador: http://localhost:8000
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -m pip install -q -r requirements.txt
  py app.py
  goto :fim
)

where python >nul 2>nul
if %errorlevel%==0 (
  python -m pip install -q -r requirements.txt
  python app.py
  goto :fim
)

echo.
echo  Python nao encontrado.
echo  Instale em https://www.python.org/downloads/ e marque "Add python.exe to PATH".
echo.
pause

:fim