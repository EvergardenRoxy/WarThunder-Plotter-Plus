@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Run scripts\setup.bat first.
    exit /b 1
)

set "PYINSTALLER_CONFIG_DIR=%CD%\.venv\pyinstaller-cache"
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --noconsole ^
    --name WarThunderPlotterPlus --paths "." ^
    --add-data "wt_plotter/web/templates:wt_plotter/web/templates" ^
    --add-data "wt_plotter/web/static:wt_plotter/web/static" ^
    --add-data "wt_plotter/i18n/locales:wt_plotter/i18n/locales" ^
    --add-data "data/maps:data/maps" ^
    "wt_plotter/__main__.py"
if errorlevel 1 exit /b 1

move /y "dist\WarThunderPlotterPlus.exe" "dist\WarThunderPlotterPlus-portable.exe" >nul
exit /b %errorlevel%
