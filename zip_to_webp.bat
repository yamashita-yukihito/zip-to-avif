@echo off

if "%~1"=="" (
    echo Drag and drop an archive file onto this bat file.
    echo Supported: zip, rar, 7z, cbz, cbr
    pause
    exit /b
)

set "EXT=%~x1"
if /i "%EXT%"==".zip" goto OK
if /i "%EXT%"==".rar" goto OK
if /i "%EXT%"==".7z" goto OK
if /i "%EXT%"==".cbz" goto OK
if /i "%EXT%"==".cbr" goto OK
echo ERROR: Unsupported format (%EXT%)
echo Supported: zip, rar, 7z, cbz, cbr
pause
exit /b

:OK
set "INPUT=%~1"
set "OUTPUT=%~dpn1_webp.zip"
echo Input:  %INPUT%
echo Output: %OUTPUT%
echo.

wsl python3 ~/bin/zip_to_webp.py "%INPUT%" "%OUTPUT%" 75 4 2000

echo.
pause
