# AI 代码审查自动化配置步骤

## 🎯 快速开始 (3分钟配置)

### 步骤 1: 获取 OpenAI API Key

1. 访问 https://platform.openai.com/api-keys
2. 登录或注册账号
3. 点击 "Create new secret key"
4. 复制生成的 API Key (以 `sk-` 开头)

### 步骤 2: 在 GitHub 配置 Secret

1. 打开你的 GitHub 仓库: https://github.com/xy7365527-lang/chanlun-quant
2. 点击 `Settings` (设置)
3. 在左侧菜单找到 `Secrets and variables` → `Actions`
4. 点击 `New repository secret`
5. 添加以下配置:
   - **Name**: `OPENAI_API_KEY`
   - **Value**: 粘贴你的 API Key
6. 点击 `Add secret`

### 步骤 3: 推送配置文件到 GitHub

运行以下命令(或使用提供的批处理脚本):

```bash
# 添加新创建的配置文件
git add .github/

# 提交
git commit -m "添加 AI 代码审查工作流配置"

# 推送到 GitHub
git push origin master
```

或者直接运行:
```bash
git_push_with_review.bat
```

### 步骤 4: 验证配置

1. 推送代码后,访问: https://github.com/xy7365527-lang/chanlun-quant/actions
2. 查看是否有工作流运行
3. 如果看到绿色的对勾 ✅ 说明配置成功!

## 📖 使用方法

### 方法一: 直接推送 (适合小改动)

使用提供的脚本:
```bash
git_push_with_review.bat
```

或手动执行:
```bash
git add .
git commit -m "你的提交信息"
git push origin master
```

### 方法二: 创建 Pull Request (推荐)

使用提供的脚本:
```bash
git_create_pr.bat
```

这种方式的优势:
- ✅ AI 会在代码合并前进行审查
- ✅ 可以在审查后修改代码
- ✅ 保持主分支的稳定性
- ✅ 更详细的审查报告

## 🤖 AI 会审查什么?

本项目的 AI 审查专门针对**缠论量化交易系统**优化,会重点检查:

### 1. 缠论算法逻辑
- ✓ 笔的识别是否正确
- ✓ 线段划分是否准确
- ✓ 中枢判断逻辑
- ✓ 买卖点识别规则

### 2. 交易策略
- ✓ 风险控制机制
- ✓ 仓位管理逻辑
- ✓ 止损止盈设置
- ✓ 资金管理策略

### 3. 代码质量
- ✓ Python 编码规范
- ✓ 性能优化建议
- ✓ 代码可读性
- ✓ 潜在 Bug

### 4. 安全性
- ✓ API 密钥安全
- ✓ 数据验证
- ✓ 异常处理
- ✓ 依赖漏洞

## 📊 查看审查结果

### 在 Push 后
1. 访问: https://github.com/xy7365527-lang/chanlun-quant/actions
2. 点击最新的工作流运行
3. 查看 "Summary" 中的审查摘要

### 在 Pull Request 中
1. 打开你的 PR
2. 切换到 `Files changed` 标签
3. AI 的审查意见会直接标注在代码行上
4. 在 `Conversation` 标签查看总体评论

## 💰 费用说明

OpenAI API 调用按使用量收费:
- **GPT-3.5-turbo**: ~$0.002 / 1K tokens (便宜,适合频繁审查)
- **GPT-4**: ~$0.03 / 1K tokens (贵但更准确)

**预估费用**:
- 小型提交 (< 100 行): $0.01 - $0.05
- 中型提交 (100-500 行): $0.05 - $0.20
- 大型提交 (> 500 行): $0.20 - $1.00

**建议**:
- 在 OpenAI 后台设置月度使用限额
- 日常使用 GPT-3.5,重要功能用 GPT-4
- 避免频繁提交大量文件

## 🔧 高级配置

### 使用国内 API 代理

如果访问 OpenAI API 有困难,可以使用代理:

1. 在 GitHub Secrets 添加:
   - **Name**: `OPENAI_API_BASE`
   - **Value**: 你的代理地址(如 `https://api.openai-proxy.com/v1`)

2. 常见国内代理服务:
   - API2D: https://api2d.com
   - OpenAI-SB: https://openai-sb.com
   - 自建代理

### 调整 AI 模型

编辑 `.github/workflows/code-review.yml`:

```yaml
model: gpt-4  # 改为 gpt-3.5-turbo 以降低费用
```

### 自定义审查重点

编辑 `.github/workflows/advanced-review.yml`:

```yaml
system_message: |
  你是一位资深的量化交易专家。
  请特别关注:
  1. [你的自定义要点]
  2. [你的自定义要点]
```

## ❓ 常见问题

### Q1: 工作流没有运行?
**A**: 检查:
1. Secrets 是否正确配置
2. 工作流文件是否已推送
3. 分支名是否匹配 (master/main)

### Q2: API 调用失败?
**A**: 可能原因:
1. API Key 无效或过期
2. API 配额用尽
3. 网络问题(尝试使用代理)

### Q3: 审查质量不理想?
**A**: 尝试:
1. 使用 GPT-4 模型
2. 优化 system_message 提示词
3. 将大的改动拆分成小的 PR

### Q4: 如何暂停 AI 审查?
**A**: 两种方法:
1. 在提交信息中添加 `[skip ci]`
2. 临时禁用工作流: Settings → Actions → Disable workflow

## 📚 相关文档

- [详细配置说明](.github/README_AI_REVIEW.md)
- [工作流配置](.github/workflows/)
- [Pull Request 模板](.github/PULL_REQUEST_TEMPLATE.md)

## 🆘 需要帮助?

如有问题,请:
1. 查看 [GitHub Actions 日志](https://github.com/xy7365527-lang/chanlun-quant/actions)
2. 检查工作流配置文件
3. 参考 [GitHub Actions 文档](https://docs.github.com/en/actions)

---

**配置完成后,每次推送代码都会自动触发 AI 审查,帮助你提高代码质量! 🚀**

