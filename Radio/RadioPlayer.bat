@echo off
setlocal
cd /d "%~dp0"

set "PYEXE="
set "PYWEXE="

if exist ".venv\Scripts\python.exe" (
    set "PYEXE=.venv\Scripts\python.exe"
    set "PYWEXE=.venv\Scripts\pythonw.exe"
) else if exist ".venv-1\Scripts\python.exe" (
    set "PYEXE=.venv-1\Scripts\python.exe"
    set "PYWEXE=.venv-1\Scripts\pythonw.exe"
) else (
    where py >nul 2>&1
    if errorlevel 1 (
        echo Python no esta instalado. Instala Python 3.10+ y vuelve a intentar.
        pause
        endlocal
        exit /b 1
    )
    set "PYEXE=py"
    set "PYWEXE=pyw"
)

call :ensure_requirements
if errorlevel 1 (
    echo No se pudieron instalar las dependencias.
    pause
    endlocal
    exit /b 1
)

if /i "%PYWEXE%"=="pyw" (
    start "" /b pyw "radio_player.py"
) else if exist "%PYWEXE%" (
    start "" /b "%PYWEXE%" "radio_player.py"
) else (
    start "" /b "%PYEXE%" "radio_player.py"
)

endlocal
exit /b 0

:ensure_requirements
if not exist "requirements.txt" exit /b 0

for %%A in (requirements.txt) do if %%~zA EQU 0 exit /b 0

echo Instalando dependencias...
"%PYEXE%" -m pip --version >nul 2>&1
if errorlevel 1 "%PYEXE%" -m ensurepip --upgrade >nul 2>&1

"%PYEXE%" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

exit /b 0
