# Codex 代码审查配置说明

## 功能说明

本项目已启用 Codex AI 代码审查功能。当你创建 Pull Request 时，Codex 会自动：
- 审查代码变更
- 提供改进建议
- 发现潜在的 bug 和代码质量问题
- 当代码质量良好时自动回复 👍

## 配置步骤

### 1. 添加 OpenAI API Key

在 GitHub 仓库设置中添加密钥：

1. 进入仓库的 **Settings** → **Secrets and variables** → **Actions**
2. 点击 **New repository secret**
3. 添加以下密钥：
   - Name: `OPENAI_API_KEY`
   - Value: 你的 OpenAI API 密钥

### 2. 确保 GitHub Actions 权限

1. 进入仓库的 **Settings** → **Actions** → **General**
2. 在 "Workflow permissions" 部分：
   - 选择 **Read and write permissions**
   - 勾选 **Allow GitHub Actions to create and approve pull requests**

## 使用方法

### 自动审查
当你创建或更新 Pull Request 时，Codex 会自动运行审查。

### 手动触发审查
在 PR 评论中提及 `@codex` 可以手动请求审查，例如：
```
@codex 请审查这段代码
```

或
```
@codex review this change
```

### 特定任务
你也可以给 Codex 分配特定任务：
```
@codex 检查这段代码的性能问题
@codex 审查安全性
@codex 建议重构方案
```

## 审查范围

当前配置会审查以下文件类型：
- Python 文件 (*.py)
- JavaScript/TypeScript 文件 (*.js, *.ts, *.jsx, *.tsx)

会自动排除：
- `__pycache__` 目录
- `node_modules` 目录
- `dist` 和 `build` 目录
- 编译文件和锁文件

## 审查级别

当前设置为 **normal** 级别，平衡了审查严格度和实用性。

可选级别：
- `strict`: 严格模式，会指出所有潜在问题
- `normal`: 正常模式（当前）
- `lenient`: 宽松模式，只指出重要问题

## 注意事项

1. 首次运行可能需要几分钟
2. 确保你的 OpenAI API 账户有足够的配额
3. 审查结果会以评论形式出现在 PR 中
4. 你可以在 Actions 标签页查看详细日志

## 费用说明

使用 Codex 会消耗 OpenAI API 配额。建议：
- 监控 API 使用情况
- 根据需要调整 `review-level`
- 可以通过 `exclude-patterns` 排除不需要审查的文件

## 故障排查

如果 Codex 没有运行：
1. 检查 Actions 标签页的错误日志
2. 确认 `OPENAI_API_KEY` 已正确设置
3. 确认 GitHub Actions 有足够的权限
4. 查看工作流文件 `.github/workflows/codex-review.yml` 是否正确

## 自定义配置

如需调整审查配置，编辑 `.github/workflows/codex-review.yml` 文件：
- 修改 `include-patterns` 和 `exclude-patterns`
- 调整 `review-level`
- 更改 `language` 设置
- 禁用/启用 `auto-approve`

