# ========================================
# 从 .env 文件加载环境变量到当前 PowerShell 会话
# 用法：. .\load_env.ps1
# ========================================

param(
    [string]$EnvFile = ".env"
)

if (-not (Test-Path $EnvFile)) {
    Write-Host "错误: 找不到环境变量文件 '$EnvFile'" -ForegroundColor Red
    Write-Host ""
    Write-Host "请创建 .env 文件并填写配置，参考模板：" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "# 必填项" -ForegroundColor Cyan
    Write-Host "CLQ_TA_API_KEY=sk-your-openai-api-key-here" -ForegroundColor Gray
    Write-Host "OPENAI_API_KEY=`${CLQ_TA_API_KEY}" -ForegroundColor Gray
    Write-Host "CLQ_MKD_FACTORY=chanlun_quant.integration.market_data:make_market_datas" -ForegroundColor Gray
    Write-Host ""
    Write-Host "# 可选项" -ForegroundColor Cyan
    Write-Host "CLQ_TA_MODEL=gpt-4o-mini" -ForegroundColor Gray
    Write-Host "CLQ_TA_BASE_URL=https://api.openai.com/v1" -ForegroundColor Gray
    Write-Host "CLQ_FREQ=d" -ForegroundColor Gray
    Write-Host "CLQ_MAX_CANDIDATES=80" -ForegroundColor Gray
    Write-Host "CLQ_TOP_K=2" -ForegroundColor Gray
    Write-Host ""
    Write-Host "完整模板请查看 QUICKSTART.md" -ForegroundColor Yellow
    exit 1
}

Write-Host "正在从 '$EnvFile' 加载环境变量..." -ForegroundColor Green

$envVars = @{}
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    
    # 跳过空行和注释
    if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
        return
    }
    
    # 解析 KEY=VALUE
    if ($line -match '^([^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        
        # 去除引号
        $value = $value -replace '^["'']|["'']$', ''
        
        # 处理变量引用 ${VAR}
        while ($value -match '\$\{([^}]+)\}') {
            $refKey = $matches[1]
            if ($envVars.ContainsKey($refKey)) {
                $value = $value -replace "\`$\{$refKey\}", $envVars[$refKey]
            } elseif (Test-Path "env:$refKey") {
                $value = $value -replace "\`$\{$refKey\}", (Get-Item "env:$refKey").Value
            } else {
                # 如果找不到引用的变量，保持原样或置空
                $value = $value -replace "\`$\{$refKey\}", ""
            }
        }
        
        # 设置环境变量
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
        $envVars[$key] = $value
        Write-Host "  设置: $key = $value" -ForegroundColor Gray
    }
}

Write-Host "✓ 环境变量加载完成" -ForegroundColor Green
Write-Host ""
Write-Host "重要提示：" -ForegroundColor Yellow
Write-Host "  1. 确保已激活 Python 3.10 或 3.11 虚拟环境" -ForegroundColor Cyan
Write-Host "  2. 确保 IB Gateway + Redis + IB Worker 已启动" -ForegroundColor Cyan
Write-Host "  3. 确认 OPENAI_API_KEY 已正确设置" -ForegroundColor Cyan
Write-Host ""

# 验证关键环境变量
$criticalVars = @(
    "OPENAI_API_KEY",
    "CLQ_TA_API_KEY",
    "CLQ_MKD_FACTORY"
)

$missing = @()
foreach ($var in $criticalVars) {
    if (-not (Test-Path "env:$var") -or [string]::IsNullOrWhiteSpace((Get-Item "env:$var").Value)) {
        $missing += $var
    }
}

if ($missing.Count -gt 0) {
    Write-Host "警告: 以下关键环境变量未设置或为空：" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""
}

