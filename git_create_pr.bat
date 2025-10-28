@echo off
chcp 65001 >nul
echo ========================================
echo    创建 Pull Request (推荐方式)
echo ========================================
echo.

echo 当前分支:
git branch --show-current
echo.

set /p BRANCH_NAME="请输入新分支名称 (如 feature/new-strategy): "
if "%BRANCH_NAME%"=="" (
    echo [错误] 分支名称不能为空
    pause
    exit /b 1
)

echo.
echo [1/6] 创建并切换到新分支...
git checkout -b %BRANCH_NAME%
if errorlevel 1 (
    echo [错误] 创建分支失败
    pause
    exit /b 1
)

echo.
echo [2/6] 当前待提交的更改:
git status --short
echo.

set /p COMMIT_MSG="请输入提交信息: "
if "%COMMIT_MSG%"=="" (
    echo [错误] 提交信息不能为空
    pause
    exit /b 1
)

echo.
echo [3/6] 添加文件...
git add .

echo [4/6] 提交更改...
git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    echo [错误] 提交失败
    pause
    exit /b 1
)

echo [5/6] 推送分支到远程...
git push -u origin %BRANCH_NAME%
if errorlevel 1 (
    echo [错误] 推送失败
    pause
    exit /b 1
)

echo.
echo [6/6] ✅ 分支已推送!
echo.
echo 📝 现在请在 GitHub 上创建 Pull Request:
echo.
echo    1. 访问: https://github.com/xy7365527-lang/chanlun-quant
echo    2. 点击 "Compare & pull request" 按钮
echo    3. 填写 PR 描述
echo    4. 创建 PR 后,AI 将自动进行代码审查
echo.
echo 🤖 AI 将审查以下方面:
echo    - 缠论算法逻辑正确性
echo    - 交易策略风险控制
echo    - 代码性能和优化机会
echo    - Python 最佳实践
echo    - 潜在安全问题
echo.

pause

