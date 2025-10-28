# GitHub Actions AI 代码审查配置指南

## 概述

本项目已配置自动化AI代码审查系统,在每次代码推送和Pull Request时自动触发。

## 配置的工作流

### 1. `code-review.yml` - 基础代码审查
- **触发时机**: Push 到主分支或创建 Pull Request
- **功能**: 使用 OpenAI GPT-4 进行代码审查
- **审查内容**: Python, JavaScript, TypeScript 等文件

### 2. `advanced-review.yml` - 高级审查与质量检查
- **触发时机**: Pull Request 事件
- **功能**: 
  - AI 智能代码审查(针对缠论量化交易特点)
  - 代码格式检查 (Black)
  - 代码规范检查 (Flake8)
  - 安全漏洞扫描

## 必需配置

### 在 GitHub 仓库中添加以下 Secrets:

1. **OPENAI_API_KEY** (必需)
   - 路径: Settings → Secrets and variables → Actions → New repository secret
   - 值: 你的 OpenAI API Key
   - 获取: https://platform.openai.com/api-keys

2. **OPENAI_API_BASE** (可选)
   - 如果使用自定义 API 端点或代理
   - 默认: https://api.openai.com/v1

3. **SAFETY_API_KEY** (可选)
   - 用于安全漏洞扫描
   - 获取: https://pyup.io/

## 使用方法

### 方式一: 直接推送代码
```bash
git add .
git commit -m "你的提交信息"
git push origin master
```

### 方式二: 创建 Pull Request (推荐)
```bash
# 创建新分支
git checkout -b feature/new-feature

# 提交更改
git add .
git commit -m "添加新功能"

# 推送到远程
git push origin feature/new-feature

# 然后在 GitHub 上创建 Pull Request
```

## AI 审查的重点

针对本项目(缠论量化交易系统),AI 会特别关注:

1. **缠论算法逻辑**
   - 笔、线段、中枢的识别逻辑
   - 买卖点判断的准确性

2. **交易策略**
   - 风险控制机制
   - 仓位管理逻辑
   - 止损止盈设置

3. **代码质量**
   - Python 最佳实践
   - 性能优化机会
   - 代码可读性和维护性

4. **安全性**
   - API 密钥管理
   - 数据验证
   - 异常处理

## 查看审查结果

### Pull Request 评论
AI 审查结果会以评论形式出现在 PR 的 "Files changed" 标签页中,直接标注在相关代码行。

### Actions 日志
访问 `Actions` 标签页查看完整的工作流执行日志和总结。

## 高级配置

### 自定义审查规则

编辑 `.github/workflows/advanced-review.yml` 中的 `system_message`:

```yaml
system_message: |
  你是一位资深的量化交易和Python开发专家。
  请重点关注以下方面:
  1. 你的自定义审查要点...
```

### 调整触发条件

修改工作流中的 `on` 部分:

```yaml
on:
  push:
    branches:
      - master
    paths:
      - 'chanlun_quant/**'  # 只监控特定目录
```

### 排除特定文件

在 `path_filters` 中添加排除规则:

```yaml
path_filters: |
  **/*.py
  !tests/**
  !**/legacy/**
```

## 费用说明

- OpenAI API 调用会产生费用
- GPT-3.5-turbo: 约 $0.002/1K tokens
- GPT-4: 约 $0.03/1K tokens
- 建议设置 API 使用限额

## 故障排查

### 1. 工作流不运行
- 检查 Secrets 是否正确配置
- 确认分支名称是否匹配触发条件
- 查看 Actions 标签页的错误日志

### 2. API 调用失败
- 验证 OPENAI_API_KEY 是否有效
- 检查 API 配额是否用尽
- 确认网络连接(如果使用自托管 runner)

### 3. 审查质量不佳
- 尝试使用 GPT-4 模型(更准确但更贵)
- 优化 system_message 提示词
- 增加更多上下文信息

## 替代方案

如果不想使用 OpenAI,可以考虑:

1. **GitHub Copilot 代码审查**
2. **CodeRabbit** (专门的 AI 代码审查工具)
3. **SonarCloud** (传统静态分析)
4. **DeepCode** (基于 AI 的代码分析)

## 参考资源

- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [OpenAI API 文档](https://platform.openai.com/docs)
- [项目特定配置](./workflows/)

---

配置时间: 2025-10-28
维护者: 请根据实际使用情况调整配置

