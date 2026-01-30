@echo off
echo 正在复制必要的DLL文件...
echo.

REM 源目录
set ANACONDA_PATH=D:\anaconda3_win10
set QT_BIN_PATH=%ANACONDA_PATH%\Library\bin
set PYQT5_PATH=%ANACONDA_PATH%\Lib\site-packages\PyQt5\Qt5\bin

REM 目标目录
set DIST_DIR=D:\Git_Warehouse\XNS_refSys\refsys\dist

echo 从 %QT_BIN_PATH% 复制文件到 %DIST_DIR%
echo.

REM 复制核心Qt DLL
copy "%QT_BIN_PATH%\Qt5Core.dll" "%DIST_DIR%"
copy "%QT_BIN_PATH%\Qt5Gui.dll" "%DIST_DIR%"
copy "%QT_BIN_PATH%\Qt5Widgets.dll" "%DIST_DIR%"

REM 复制conda版本的DLL（如果有）
if exist "%QT_BIN_PATH%\Qt5Core_conda.dll" (
    copy "%QT_BIN_PATH%\Qt5Core_conda.dll" "%DIST_DIR%"
)
if exist "%QT_BIN_PATH%\Qt5Gui_conda.dll" (
    copy "%QT_BIN_PATH%\Qt5Gui_conda.dll" "%DIST_DIR%"
)
if exist "%QT_BIN_PATH%\Qt5Widgets_conda.dll" (
    copy "%QT_BIN_PATH%\Qt5Widgets_conda.dll" "%DIST_DIR%"
)

REM 复制其他必要的库
copy "%QT_BIN_PATH%\platforms\qwindows.dll" "%DIST_DIR%\platforms\"
md "%DIST_DIR%\platforms" 2>nul

REM 复制Python DLL
copy "%ANACONDA_PATH%\python311.dll" "%DIST_DIR%"

echo 完成！
pause