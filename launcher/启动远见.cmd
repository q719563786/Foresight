@echo off
setlocal
set "YUANJIAN_APP_DIR=%~dp0app"
set "PYTHONPATH=%YUANJIAN_APP_DIR%\src"
set "YUANJIAN_DATA_DIR=%LOCALAPPDATA%\YuanJian"
set "PYTHONDONTWRITEBYTECODE=1"
start "远见" pyw -3 -m yuanjian_app.application
endlocal
