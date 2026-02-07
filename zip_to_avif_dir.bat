@echo off

if "%~1"=="" (
    echo Drag and drop a DIRECTORY onto this bat file.
    pause
    exit /b
)

if not exist "%~1\" (
    echo ERROR: "%~1" is not a directory.
    pause
    exit /b
)

echo Directory: %~1
echo.

wsl python3 ~/bin/zip_to_avif_dir.py "%~1" 70 4 2000

echo.
pause
