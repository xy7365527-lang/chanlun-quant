@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ========================================
REM 设置 Python 3.11 环境（解决 PyArmor 兼容性问题）
REM ========================================

echo ========================================
echo 缠论量化 - Python 3.11 环境设置
echo ========================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

REM 检查是否已有 Python 3.11 虚拟环境
if exist ".venv311\Scripts\activate.bat" (
    echo [✓] 发现已有 Python 3.11 虚拟环境
    goto ACTIVATE
)

REM 检查系统是否安装了 Python 3.11
echo [1/4] 检查 Python 3.11 安装...
py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo [✗] 未找到 Python 3.11
    echo.
    echo 请先安装 Python 3.11：
    echo   1. 访问 https://www.python.org/downloads/
    echo   2. 下载并安装 Python 3.11.x
    echo   3. 安装时勾选 "Add Python to PATH"
    echo.
    echo 或使用 uv 安装：
    echo   script\bin\uv.exe python install 3.11
    echo.
    pause
    exit /b 1
)
echo [✓] 找到 Python 3.11

REM 创建虚拟环境
echo.
echo [2/4] 创建 Python 3.11 虚拟环境...
py -3.11 -m venv .venv311
if errorlevel 1 (
    echo [✗] 创建虚拟环境失败
    pause
    exit /b 1
)
echo [✓] 虚拟环境创建成功

:ACTIVATE
REM 激活虚拟环境
echo.
echo [3/4] 激活虚拟环境...
call .venv311\Scripts\activate.bat
if errorlevel 1 (
    echo [✗] 激活虚拟环境失败
    pause
    exit /b 1
)
echo [✓] 虚拟环境已激活

REM 检查并安装依赖
echo.
echo [4/4] 检查依赖包...
pip show chanlun >nul 2>&1
if errorlevel 1 (
    echo 正在安装依赖包（这可能需要几分钟）...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [✗] 依赖安装失败
        pause
        exit /b 1
    )
    echo [✓] 依赖安装完成
) else (
    echo [✓] 依赖包已安装
)

REM 设置 PYTHONPATH
set "PYTHONPATH=%ROOT_DIR%src"
echo.
echo ========================================
echo 环境设置完成！
echo ========================================
echo.
echo Python 版本: 
python --version
echo.
echo 虚拟环境: .venv311
echo PYTHONPATH: %PYTHONPATH%
echo.
echo ----------------------------------------
echo 下一步：
echo   1. 创建 .env 文件并填写配置
echo      （参考 QUICKSTART.md 中的模板）
echo.
echo   2. 使用 PowerShell 运行（推荐）：
echo      .\run_ta_selector.ps1
echo.
echo   3. 或使用批处理运行：
echo      run_ta_selector.bat
echo ----------------------------------------
echo.
pause

