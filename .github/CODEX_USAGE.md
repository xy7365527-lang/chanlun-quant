# 🤖 Codex 代码审查使用指南

## 功能概述

Codex 是一个基于 OpenAI GPT-4 的智能代码审查助手，专门为缠论量化交易系统优化。

### 主要功能

- ✅ **自动审查** - 每次创建或更新 Pull Request 时自动触发
- 💬 **智能对话** - 在 PR 评论中提及 `@codex` 来提问或请求审查
- 🎯 **专业分析** - 针对缠论算法、交易策略、风险控制的专业审查
- 👍 **快速反馈** - 代码质量好时简单回复 👍，有问题时提供详细建议

---

## 使用方法

### 1️⃣ 自动审查（无需操作）

当您创建或更新 Pull Request 时，Codex 会自动：
1. 分析所有代码改动
2. 检查算法逻辑、性能、安全性
3. 在 PR 中发布审查意见

**示例**:
```bash
git checkout -b feature/new-strategy
git add .
git commit -m "添加新的交易策略"
git push origin feature/new-strategy
# 在 GitHub 创建 PR，Codex 自动开始审查
```

---

### 2️⃣ 手动请求审查

在 Pull Request 的评论中提及 `@codex` 来手动触发审查：

#### 完整审查
```
@codex 请审查这个 PR
```

#### 针对性问题
```
@codex 这个函数的性能如何？有优化建议吗？
```

```
@codex 这段代码的风险控制是否合理？
```

```
@codex 帮我检查一下线段识别的逻辑
```

---

### 3️⃣ 代码内提问

您可以在代码审查评论中提及 `@codex` 来询问特定代码：

1. 在 PR 的 "Files changed" 标签页
2. 点击代码行号旁的 `+` 按钮
3. 输入评论并提及 `@codex`

**示例**:
```
@codex 为什么这里要用递归？有更好的方法吗？
```

---

## 审查重点

Codex 会特别关注以下方面：

### 🎯 缠论算法
- 笔的识别逻辑是否正确
- 线段划分是否符合规则
- 中枢判断的准确性
- 买卖点识别的可靠性

### 💰 交易策略
- 风险控制机制
- 仓位管理逻辑
- 止损止盈设置
- 资金管理策略

### 🚀 代码质量
- Python 最佳实践
- 性能优化机会
- 代码可读性
- 潜在的 Bug

### 🔒 安全性
- API 密钥管理
- 数据验证
- 异常处理
- 依赖安全

---

## 审查结果示例

### ✅ 代码通过审查
```
## 🤖 Codex 代码审查

### ✅ 通过审查 (3 个文件)
- `chanlun_quant/core/stroke.py` - 👍 代码看起来不错
- `chanlun_quant/strategy/baseline.py` - 👍 逻辑清晰，风控合理
- `tests/test_stroke.py` - 👍 测试覆盖充分
```

### 💡 有改进建议
```
## 🤖 Codex 代码审查

### 💡 改进建议 (1 个文件)

#### 📄 `chanlun_quant/core/segment.py`

1. **性能优化** (第 45-52 行)
   当前使用循环遍历所有笔来查找线段，建议使用二分查找优化。
   
2. **边界检查** (第 78 行)
   缺少对空列表的检查，可能导致 IndexError。
   建议添加: `if not segments: return None`
   
3. **类型提示** (第 23 行)
   建议添加返回类型提示以提高代码可读性。
```

---

## 高级用法

### 请求特定类型的审查

```
@codex 请重点审查这段代码的性能
```

```
@codex 帮我检查是否有安全隐患
```

```
@codex 这个算法的时间复杂度是多少？能优化吗？
```

### 请求解释

```
@codex 能解释一下这个函数的工作原理吗？
```

```
@codex 为什么要这样设计？有什么好处？
```

### 请求最佳实践建议

```
@codex 这段代码符合 Python 最佳实践吗？
```

```
@codex 如何让这段代码更加 Pythonic？
```

---

## 配置说明

### 必需配置

在 GitHub 仓库的 Secrets 中配置：

| Secret 名称 | 说明 | 必需 |
|------------|------|------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | ✅ 是 |
| `OPENAI_API_BASE` | API 端点（使用代理时） | ❌ 否 |

### 触发条件

Codex 会在以下情况下运行：

- ✅ 创建新的 Pull Request
- ✅ 更新 Pull Request（push 新提交）
- ✅ 重新打开 Pull Request
- ✅ 评论中提及 `@codex`

### 审查的文件类型

Codex 会审查以下类型的文件：
- `.py` - Python
- `.js`, `.ts`, `.tsx` - JavaScript/TypeScript
- `.java` - Java
- `.go` - Go
- `.cpp`, `.c`, `.h` - C/C++

---

## 费用说明

Codex 使用 GPT-4 模型，费用取决于代码量：

| PR 大小 | 预估费用 |
|---------|---------|
| 小型 (< 100 行) | $0.05 - $0.15 |
| 中型 (100-500 行) | $0.15 - $0.50 |
| 大型 (> 500 行) | $0.50 - $2.00 |

**建议**:
- 将大的 PR 拆分成多个小的 PR
- 在 OpenAI 后台设置月度使用限额
- 定期检查 API 使用情况

---

## 常见问题

### Q: Codex 没有响应？
**A**: 检查：
1. PR 中是否有代码文件改动
2. GitHub Secrets 是否正确配置
3. 查看 Actions 日志排查错误

### Q: 如何禁用自动审查？
**A**: 在提交信息或 PR 标题中添加 `[skip codex]`

### Q: Codex 的建议准确吗？
**A**: Codex 提供的建议基于 AI 分析，大多数情况下准确，但建议结合人工判断。

### Q: 可以用其他模型吗？
**A**: 可以修改 `.github/scripts/codex_reviewer.py` 中的 `model` 参数：
- `gpt-4` - 最准确（推荐）
- `gpt-3.5-turbo` - 更便宜但略逊

---

## 示例工作流

### 典型的 PR 流程

```bash
# 1. 创建功能分支
git checkout -b feature/macd-indicator

# 2. 编写代码
vim chanlun_quant/indicators/macd.py

# 3. 提交代码
git add .
git commit -m "添加 MACD 指标"

# 4. 推送并创建 PR
git push origin feature/macd-indicator
# 在 GitHub 创建 PR

# 5. Codex 自动开始审查（2-3 分钟）

# 6. 查看审查意见，如有疑问可以提问
# 在 PR 评论中: @codex 为什么建议用 numpy？

# 7. 根据建议修改代码
vim chanlun_quant/indicators/macd.py

# 8. 提交改进
git add .
git commit -m "根据 Codex 建议优化 MACD 计算"
git push

# 9. Codex 自动重新审查
# 10. 审查通过后合并 PR
```

---

## 技术细节

### 审查流程

```
PR 创建/更新
    ↓
检测代码改动
    ↓
提取变更文件和 diff
    ↓
使用 GPT-4 分析每个文件
    ↓
生成审查意见
    ↓
发布到 PR 评论
```

### 提示词优化

Codex 使用专门优化的提示词，针对：
- 缠论量化交易系统
- Python 编码规范
- 性能和安全性

可以在 `.github/scripts/codex_reviewer.py` 中自定义提示词。

---

## 更多资源

- 📖 [配置文档](.github/README_AI_REVIEW.md)
- 🔧 [工作流配置](.github/workflows/codex-review.yml)
- 🐍 [审查脚本](.github/scripts/codex_reviewer.py)
- 💬 [问题反馈](https://github.com/xy7365527-lang/chanlun-quant/issues)

---

**开始使用 Codex，让 AI 帮助您提高代码质量！** 🚀

