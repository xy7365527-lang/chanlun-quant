@echo off
chcp 65001 >nul
echo ========================================
echo    GitHub 代码推送与 AI 审查工具
echo ========================================
echo.

REM 检查是否有未提交的更改
git status --short
if errorlevel 1 (
    echo [错误] Git 仓库状态检查失败
    pause
    exit /b 1
)

echo.
echo [1/5] 当前待提交的更改:
echo ----------------------------------------
git status --short
echo.

set /p CONFIRM="是否继续提交这些更改? (y/n): "
if /i not "%CONFIRM%"=="y" (
    echo 已取消操作
    pause
    exit /b 0
)

echo.
set /p COMMIT_MSG="请输入提交信息: "
if "%COMMIT_MSG%"=="" (
    echo [错误] 提交信息不能为空
    pause
    exit /b 1
)

echo.
echo [2/5] 添加文件到暂存区...
git add .
if errorlevel 1 (
    echo [错误] 添加文件失败
    pause
    exit /b 1
)

echo [3/5] 提交更改...
git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    echo [错误] 提交失败
    pause
    exit /b 1
)

echo.
echo [4/5] 推送到 GitHub...
git push origin master
if errorlevel 1 (
    echo [错误] 推送失败,可能需要先拉取远程更改
    echo 尝试执行: git pull --rebase origin master
    pause
    exit /b 1
)

echo.
echo [5/5] ✅ 代码已成功推送到 GitHub!
echo.
echo 📝 AI 代码审查将自动开始...
echo 👉 请访问 GitHub Actions 查看审查结果:
echo    https://github.com/xy7365527-lang/chanlun-quant/actions
echo.
echo ⏱️  预计审查时间: 2-5分钟
echo.

pause

