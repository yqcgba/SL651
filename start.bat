@echo off
chcp 65001 >nul
title 水文监测数据模拟上传工具 V1.3

echo ================================================
echo   水文监测数据 模拟上传工具  V1.3
echo ================================================
echo.

cd /d "%~dp0"

REM 优先使用打包好的 EXE（无需安装任何依赖）
if exist "dist\SL651_Simulator.exe" (
    echo [启动] 使用独立EXE模式（无需Python环境）
    echo [访问] 浏览器将自动打开: http://127.0.0.1:5000
    echo.
    start "" "dist\SL651_Simulator.exe"
    goto :end
)

REM 否则使用 Python 运行
echo [检查] Python环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到Python，请先安装Python或使用 dist\SL651_Simulator.exe
    pause
    exit /b 1
)

REM 检查Flask是否安装
python -c "import flask" 2>nul
if %errorlevel% neq 0 (
    echo [安装] 正在安装依赖...
    pip install -r requirements.txt -q
    echo [完成] 依赖安装完成
    echo.
)

echo [启动] 正在启动Web服务...
echo [访问] 浏览器将自动打开: http://127.0.0.1:5000
echo.

python app.py

:end
echo.
pause
