@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "release\数学知识织网-2.2.1-Windows\数学知识织网.exe" (
    start "" "release\数学知识织网-2.2.1-Windows\数学知识织网.exe"
    exit /b
)
if exist "release\数学知识织网-2.2.0-Windows\数学知识织网.exe" (
    start "" "release\数学知识织网-2.2.0-Windows\数学知识织网.exe"
    exit /b
)
if exist "release\数学知识织网-2.1.1-Windows\数学知识织网.exe" (
    start "" "release\数学知识织网-2.1.1-Windows\数学知识织网.exe"
    exit /b
)
if exist "release\数学知识织网-2.1.0-Windows\数学知识织网.exe" (
    start "" "release\数学知识织网-2.1.0-Windows\数学知识织网.exe"
    exit /b
)
if exist "release\数学知识织网-Windows\数学知识织网.exe" (
    start "" "release\数学知识织网-Windows\数学知识织网.exe"
    exit /b
)
if exist "dist\数学知识织网\数学知识织网.exe" (
    start "" "dist\数学知识织网\数学知识织网.exe"
    exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "main.py"
    exit /b
)
echo Please extract the portable release first, or follow README to install Python dependencies.
pause
