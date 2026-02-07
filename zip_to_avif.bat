@echo off
if "%~1"=="" (
    echo アーカイブファイルをこのバッチファイルにドラッグ＆ドロップしてください。
    echo 対応形式: zip, rar, 7z, cbz, cbr
    pause
    exit /b
)

set "EXT=%~x1"
if /i "%EXT%"==".zip" goto OK
if /i "%EXT%"==".rar" goto OK
if /i "%EXT%"==".7z" goto OK
if /i "%EXT%"==".cbz" goto OK
if /i "%EXT%"==".cbr" goto OK
echo エラー: 未対応の形式です (%EXT%)
echo 対応形式: zip, rar, 7z, cbz, cbr
pause
exit /b

:OK
set "INPUT=%~1"
set "OUTPUT=%~dpn1_avif.zip"
echo 入力: %INPUT%
echo 出力: %OUTPUT%
wsl python3 ~/bin/zip_to_avif_gpu.py "%INPUT%" "%OUTPUT%" 75
pause
