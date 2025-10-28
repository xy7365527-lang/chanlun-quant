# 🤖 Codex 代码审查 - 快速开始

## ⚡ 立即使用（3 步）

### 步骤 1: 确保已配置 OpenAI API Key
如果还没有配置，请查看 `配置OpenAI_API_密钥说明.txt`

### 步骤 2: 创建 Pull Request
```bash
# 使用便捷脚本
git_create_pr.bat

# 或手动操作
git checkout -b feature/your-feature
git add .
git commit -m "你的改动"
git push origin feature/your-feature
# 然后在 GitHub 创建 PR
```

### 步骤 3: 等待 Codex 自动审查
- ⏱️ 通常 2-3 分钟内完成
- 📊 在 PR 评论区查看审查结果
- 💡 收到改进建议或 👍

---

## 🎯 主要功能

### ✅ 自动审查
- 创建 PR 时自动触发
- 更新 PR 时自动重新审查
- 无需任何操作

### 💬 智能对话
在 PR 评论中提及 `@codex` 来：

**完整审查**:
```
@codex 请审查这个 PR
```

**提问**:
```
@codex 这段代码的性能如何？
```

**特定检查**:
```
@codex 帮我检查风险控制逻辑
```

---

## 📝 使用示例

### 场景 1: 新功能开发
```bash
# 开发新策略
git checkout -b feature/bollinger-strategy
# ... 编写代码 ...
git push origin feature/bollinger-strategy
# 创建 PR，Codex 自动审查
```

### 场景 2: Bug 修复
```bash
# 修复 bug
git checkout -b fix/segment-calculation
# ... 修复代码 ...
git push origin fix/segment-calculation
# 创建 PR，Codex 检查修复是否正确
```

### 场景 3: 代码优化
```bash
# 性能优化
git checkout -b perf/optimize-backtest
# ... 优化代码 ...
git push
# 在 PR 评论: @codex 性能提升了吗？
```

---

## 🎨 Codex 审查重点

### 缠论算法 ✓
- 笔、线段、中枢识别逻辑
- 买卖点判断准确性
- 分型、包含关系处理

### 交易策略 ✓
- 风险控制机制
- 仓位管理
- 止损止盈逻辑

### 代码质量 ✓
- Python 最佳实践
- 性能优化
- 可读性和维护性

### 安全性 ✓
- 数据验证
- 异常处理
- API 密钥安全

---

## 💡 实用技巧

### 1. 获取详细解释
```
@codex 能详细解释一下这个算法吗？
```

### 2. 性能分析
```
@codex 这段代码的时间复杂度是多少？能优化吗？
```

### 3. 最佳实践检查
```
@codex 这段代码符合 Python 最佳实践吗？
```

### 4. 风险评估
```
@codex 这个交易策略有什么风险？
```

### 5. 测试建议
```
@codex 应该为这段代码写什么测试？
```

---

## 📊 审查结果类型

### 👍 通过（代码质量好）
```
✅ 通过审查
- `your_file.py` - 👍 代码看起来不错
```

### 💡 改进建议
```
💡 改进建议

📄 your_file.py
1. 性能优化 (第 45 行) - 建议使用列表推导式
2. 类型提示 (第 23 行) - 添加返回类型提示
3. 边界检查 (第 78 行) - 缺少空列表检查
```

---

## 🔧 常用命令速查

### 提及 Codex
| 命令 | 作用 |
|------|------|
| `@codex` | 触发完整审查 |
| `@codex 请审查` | 同上 |
| `@codex 性能如何？` | 性能分析 |
| `@codex 有 bug 吗？` | Bug 检查 |
| `@codex 如何优化？` | 优化建议 |

### Git 工作流
```bash
# 创建分支
git checkout -b feature/name

# 提交代码
git add .
git commit -m "message"

# 推送
git push origin feature/name

# 在 GitHub 创建 PR
# Codex 自动开始工作！
```

---

## ❓ 常见问题

**Q: Codex 多久会回复？**  
A: 通常 2-3 分钟，取决于代码量

**Q: 需要付费吗？**  
A: 需要 OpenAI API Key，按使用量付费（小 PR 约 $0.05-0.15）

**Q: 可以禁用吗？**  
A: 在 PR 标题添加 `[skip codex]`

**Q: 建议准确吗？**  
A: 基于 GPT-4，准确率高，但建议人工复核

---

## 📚 更多文档

- 📖 完整使用指南: `.github/CODEX_USAGE.md`
- ⚙️ 配置说明: `AI_CODE_REVIEW_配置步骤.md`
- 🔑 API 配置: `配置OpenAI_API_密钥说明.txt`

---

## 🚀 现在就试试！

1. 运行 `git_create_pr.bat` 创建一个测试 PR
2. 等待 Codex 审查
3. 在评论中输入 `@codex 你好` 测试交互

**让 AI 帮助您写出更好的代码！** 🎉

