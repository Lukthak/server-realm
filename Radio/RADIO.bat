@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" /b ".venv\Scripts\pythonw.exe" "radio_player.py"
) else if exist ".venv-1\Scripts\pythonw.exe" (
    start "" /b ".venv-1\Scripts\pythonw.exe" "radio_player.py"
) else (
    start "" /b pyw "radio_player.py"
)

endlocal
exit /b
