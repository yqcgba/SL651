@echo off
chcp 65001 >nul
title SL651 报文模拟工具 - 打包为EXE

echo ================================================
echo   SL651 报文模拟工具 - 打包为独立EXE
echo ================================================
echo.

cd /d "%~dp0"

REM 安装 PyInstaller
echo [1/3] 安装 PyInstaller...
pip install pyinstaller -q
echo [完成] PyInstaller 已安装

REM 安装 Pillow (图标生成需要)
echo [2/3] 确认依赖...
pip install flask pillow -q
echo [完成] Flask/Pillow 已安装

REM 自动生成图标
echo [3/4] 生成水文主题图标...
python make_icon.py
echo [完成] 图标已生成

REM 打包
echo [4/4] 开始打包为独立EXE（保留控制台窗口，需要几分钟）...
python -m PyInstaller --onefile --console --icon "app.ico" --add-data "templates;templates" --name "SL651_Simulator" --version-file "version_info.txt" app.py
echo [完成] 打包完成!

REM 清理临时文件
echo [清理] 删除临时构建文件...
rmdir /s /q build 2>nul
del /q SL651_Simulator.spec 2>nul

echo.
echo ================================================
echo   打包完成!  EXE 文件在 dist\ 目录下
echo   >> dist\SL651_Simulator.exe
echo.
echo   将该 EXE 文件复制到任意 Windows 电脑，
echo   双击即可运行，无需安装 Python 和任何依赖!
echo ================================================
echo.

pause
