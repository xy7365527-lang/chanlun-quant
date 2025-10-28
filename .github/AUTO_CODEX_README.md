# 🤖 自动 Codex 审查配置

## 🎯 功能说明

本仓库已配置为**每次创建 Pull Request 时自动触发 Codex AI 代码审查**。

## 🚀 自动化流程

### 1️⃣ PR 模板自动填充

创建 PR 时，系统会自动使用模板（`.github/PULL_REQUEST_TEMPLATE.md`），其中已包含：
- ✅ @codex 审查请求
- ✅ 审查重点清单
- ✅ 自检清单
- ✅ 标准化的 PR 描述格式

### 2️⃣ 自动添加审查评论

PR 创建后，GitHub Actions 会自动：
- ✅ 在 PR 中添加一条欢迎评论
- ✅ 评论中包含 @codex 触发器
- ✅ 说明审查范围和重点
- ✅ 提供使用提示

### 3️⃣ Codex 自动审查

触发后，Codex 会自动：
- ✅ 分析所有代码变更
- ✅ 提供详细的审查意见
- ✅ 标注潜在问题
- ✅ 给出改进建议
- ✅ 代码质量良好时自动点赞 👍

## 📋 工作流文件

本配置包含以下文件：

1. **`.github/PULL_REQUEST_TEMPLATE.md`**
   - PR 模板，自动包含 @codex 请求

2. **`.github/workflows/auto-codex-comment.yml`**
   - 自动评论工作流，确保触发 Codex

3. **`.github/workflows/codex-review.yml`**
   - Codex 审查主工作流

## 🎬 使用演示

### 创建 PR 时：

1. **点击 "New Pull Request"**
   ```
   ↓ 系统自动填充模板
   ```

2. **PR 描述中已包含**：
   ```markdown
   @codex 请审查本次代码变更，关注以下方面：
   1. 代码质量
   2. 性能问题
   3. 安全性
   ...
   ```

3. **提交 PR 后**：
   - 🤖 自动评论添加到 PR
   - ⚙️ Codex 开始审查
   - 💬 2-5 分钟后收到反馈

## 💬 手动触发示例

在 PR 评论中随时可以使用：

```markdown
@codex 请重点检查性能优化部分

@codex 审查 chanlun_quant/strategy/trade_rhythm.py 文件

@codex 这个算法实现有没有更好的方式？

@codex 检查是否有安全漏洞
```

## ⚙️ 配置要求

确保已完成以下配置（仅需配置一次）：

### 必需配置：

1. **添加 OpenAI API 密钥**
   - 位置：Settings → Secrets → Actions
   - 名称：`OPENAI_API_KEY`
   - 值：你的 OpenAI API 密钥

2. **GitHub Actions 权限**
   - 位置：Settings → Actions → General
   - 选择：Read and write permissions
   - 勾选：Allow GitHub Actions to create and approve pull requests

### 可选配置：

在 `.github/workflows/codex-review.yml` 中可调整：
- `review-level`: strict / normal / lenient
- `auto-approve`: true / false
- `include-patterns`: 要审查的文件类型
- `exclude-patterns`: 要排除的文件/目录

## 🔍 查看审查结果

1. **在 PR 评论中**：Codex 会添加详细的审查评论
2. **在 Actions 标签页**：查看完整的审查日志
3. **在 Files changed 中**：可能会看到行内评论

## 📊 审查内容

Codex 会自动检查：

| 类别 | 检查内容 |
|------|---------|
| 🎨 代码质量 | 编码规范、命名规范、代码结构 |
| ⚡ 性能 | 算法复杂度、内存使用、优化建议 |
| 🔒 安全 | SQL 注入、XSS、敏感信息泄露 |
| 🐛 Bug | 逻辑错误、空指针、边界条件 |
| 🧪 测试 | 测试覆盖率、测试质量 |
| 📚 文档 | 注释完整性、API 文档 |

## 💰 费用说明

- 使用你自己的 OpenAI API 密钥
- 每次审查消耗少量 tokens
- 建议设置 API 使用上限
- 可通过调整 `review-level` 控制成本

## 🛠️ 故障排查

### Codex 没有响应？

1. ✅ 检查 `OPENAI_API_KEY` 是否正确设置
2. ✅ 确认 Actions 权限已启用
3. ✅ 查看 Actions 标签页的错误日志
4. ✅ 确认 API 配额充足

### 审查太慢？

- 大型 PR 可能需要更长时间
- 可以针对特定文件请求审查
- 考虑将大型 PR 拆分

### 想要更严格/宽松的审查？

编辑 `.github/workflows/codex-review.yml`：
```yaml
review-level: strict  # 或 normal / lenient
```

## 📞 需要帮助？

- 查看主配置文档：`.github/CODEX_SETUP.md`
- 查看 GitHub Actions 日志
- 检查 OpenAI API 状态

---

✨ **享受 AI 驱动的代码审查体验！**

