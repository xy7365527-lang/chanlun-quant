# ========================================
# 运行 TradingAgents MA Selector
# 自动加载环境变量并启动选股流程
# ========================================

param(
    [string]$Freq = "d",
    [int]$MaxCandidates = 40,
    [int]$TopK = 2,
    [string]$AsOf = "",
    [switch]$SaveCsv
)

# 设置控制台编码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " TradingAgents MA Selector" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查虚拟环境
if (-not (Test-Path ".venv311\Scripts\python.exe")) {
    Write-Host "[✗] 未找到 Python 3.11 虚拟环境" -ForegroundColor Red
    Write-Host "请先运行 setup_py311_env.bat 创建环境" -ForegroundColor Yellow
    exit 1
}

# 激活虚拟环境（设置 PATH）
$venvPath = Resolve-Path ".venv311"
$env:VIRTUAL_ENV = $venvPath
$env:PATH = "$venvPath\Scripts;$env:PATH"

Write-Host "[✓] 使用虚拟环境: .venv311" -ForegroundColor Green

# 检查 Python 版本
$pythonVersion = & ".venv311\Scripts\python.exe" --version 2>&1
if ($pythonVersion -notmatch "3\.(10|11)") {
    Write-Host "[✗] Python 版本不兼容: $pythonVersion" -ForegroundColor Red
    Write-Host "需要 Python 3.10 或 3.11（PyArmor 限制）" -ForegroundColor Yellow
    exit 1
}
Write-Host "[✓] Python 版本: $pythonVersion" -ForegroundColor Green

# 加载 .env 文件
if (Test-Path ".env") {
    Write-Host "[✓] 加载环境变量..." -ForegroundColor Green
    . .\load_env.ps1
    if ($LASTEXITCODE -ne 0) {
        exit 1
    }
} else {
    Write-Host "[✗] 未找到 .env 文件" -ForegroundColor Red
    Write-Host "请先创建 .env 文件：" -ForegroundColor Yellow
    Write-Host "  copy .env.example .env" -ForegroundColor Cyan
    Write-Host "然后编辑 .env 填写配置" -ForegroundColor Yellow
    exit 1
}

# 设置 PYTHONPATH
$rootDir = Get-Location
$env:PYTHONPATH = "$rootDir\src"

# 构建命令参数
$args = @(
    "examples\wire_ta_selector.py",
    "--freq", $Freq,
    "--max-candidates", $MaxCandidates,
    "--top-k", $TopK
)

if ($AsOf) {
    $args += "--as-of", $AsOf
}

if ($SaveCsv) {
    $args += "--save-csv"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 启动参数" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "周期: $Freq" -ForegroundColor Gray
Write-Host "候选数: $MaxCandidates" -ForegroundColor Gray
Write-Host "锁定数: $TopK" -ForegroundColor Gray
if ($AsOf) {
    Write-Host "截止日期: $AsOf" -ForegroundColor Gray
}
Write-Host "保存CSV: $SaveCsv" -ForegroundColor Gray
Write-Host ""

# 运行 Python 脚本
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 开始执行" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

& ".venv311\Scripts\python.exe" @args

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[✗] 执行失败，退出码: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "[✓] 执行完成" -ForegroundColor Green

