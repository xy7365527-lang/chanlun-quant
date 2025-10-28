@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ========================================
REM 运行 TradingAgents MA Selector (批处理版本)
REM ========================================

echo ========================================
echo  TradingAgents MA Selector
echo ========================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

REM 检查虚拟环境
if not exist ".venv311\Scripts\python.exe" (
    echo [X] 未找到 Python 3.11 虚拟环境
    echo 请先运行 setup_py311_env.bat 创建环境
    pause
    exit /b 1
)

echo [✓] 使用虚拟环境: .venv311

REM 检查 .env 文件
if not exist ".env" (
    echo [X] 未找到 .env 文件
    echo.
    echo 请创建 .env 文件，包含以下必填项：
    echo.
    echo CLQ_TA_API_KEY=sk-your-openai-api-key-here
    echo OPENAI_API_KEY=%%CLQ_TA_API_KEY%%
    echo CLQ_MKD_FACTORY=chanlun_quant.integration.market_data:make_market_datas
    echo.
    echo 完整模板请查看 QUICKSTART.md
    pause
    exit /b 1
)

REM 加载 .env 文件到环境变量
echo [✓] 加载环境变量...
for /f "usebackq tokens=* delims=" %%a in (".env") do (
    set "line=%%a"
    REM 跳过空行和注释
    if not "!line!"=="" (
        echo !line! | findstr /r "^#" >nul
        if errorlevel 1 (
            REM 处理 KEY=VALUE 格式
            for /f "tokens=1,* delims==" %%b in ("!line!") do (
                set "key=%%b"
                set "value=%%c"
                REM 去除前后空格和引号
                set "value=!value:"=!"
                set "value=!value:'=!"
                REM 处理变量引用 ${VAR}
                set "value=!value:${CLQ_TA_API_KEY}=%CLQ_TA_API_KEY%!"
                set "!key!=!value!"
            )
        )
    )
)

REM 确保关键变量已设置
if "%OPENAI_API_KEY%"=="" (
    echo [X] OPENAI_API_KEY 未设置
    echo 请检查 .env 文件
    pause
    exit /b 1
)

if "%CLQ_MKD_FACTORY%"=="" (
    echo [X] CLQ_MKD_FACTORY 未设置
    echo 请检查 .env 文件
    pause
    exit /b 1
)

REM 设置 Python 环境
set "PYTHONPATH=%ROOT_DIR%src"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

REM 解析参数（简化版，仅支持基本参数）
set "FREQ=d"
set "MAX_CANDIDATES=40"
set "TOP_K=2"
set "SAVE_CSV="

:parse_args
if "%~1"=="" goto run
if /i "%~1"=="--freq" (
    set "FREQ=%~2"
    shift
    shift
    goto parse_args
)
if /i "%~1"=="--max-candidates" (
    set "MAX_CANDIDATES=%~2"
    shift
    shift
    goto parse_args
)
if /i "%~1"=="--top-k" (
    set "TOP_K=%~2"
    shift
    shift
    goto parse_args
)
if /i "%~1"=="--save-csv" (
    set "SAVE_CSV=--save-csv"
    shift
    goto parse_args
)
shift
goto parse_args

:run
echo.
echo ========================================
echo  启动参数
echo ========================================
echo 周期: %FREQ%
echo 候选数: %MAX_CANDIDATES%
echo 锁定数: %TOP_K%
echo.

echo ========================================
echo  开始执行
echo ========================================
echo.

REM 运行 Python 脚本
.venv311\Scripts\python.exe examples\wire_ta_selector.py ^
    --freq %FREQ% ^
    --max-candidates %MAX_CANDIDATES% ^
    --top-k %TOP_K% ^
    %SAVE_CSV%

if errorlevel 1 (
    echo.
    echo [X] 执行失败
    pause
    exit /b 1
)

echo.
echo [✓] 执行完成
pause

