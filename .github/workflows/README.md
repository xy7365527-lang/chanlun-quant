# GitHub Actions 自动代码审查

本目录包含两个自动代码审查工作流：

## 📋 工作流说明

### 1. `llm-review-pr.yml` - PR 审查（推荐）
**触发时机**: 当创建或更新 Pull Request 时

**功能**:
- 自动提取 PR 的代码差异
- 使用 LLM 进行深度代码审查
- 将审查结果作为评论发布到 PR

**优势**:
- 在代码合并前发现问题
- 审查结果直接关联到 PR
- 方便团队协作讨论

### 2. `llm-review-push.yml` - Push 审查
**触发时机**: 当代码推送到 master/main/develop 分支时

**功能**:
- 自动提取提交的代码差异
- 快速审查关键问题
- 生成审查报告并保存为 Artifact

**优势**:
- 实时监控主分支代码质量
- 适合个人项目或直接推送场景

## 🔧 配置步骤

### 第 1 步: 添加 API Key

1. 进入仓库的 **Settings** → **Secrets and variables** → **Actions**
2. 点击 **New repository secret**
3. 添加以下密钥：
   - **Name**: `OPENAI_API_KEY`
   - **Secret**: 你的 OpenAI API Key（或兼容的 API Key）

### 第 2 步: 选择使用的工作流

- **团队协作项目**: 启用 `llm-review-pr.yml`（强烈推荐）
- **个人项目**: 可以同时启用两个，或只用 `llm-review-push.yml`

### 第 3 步: 自定义配置（可选）

#### 修改模型

编辑 workflow 文件，找到以下部分并修改模型名称：

```python
"model": "gpt-4",  # 改为你使用的模型，如 gpt-4-turbo, gpt-3.5-turbo 等
```

#### 修改 API 端点

如果使用非 OpenAI 的兼容端点（如 Azure OpenAI、国内模型等），修改：

```python
response = requests.post(
    "https://your-api-endpoint.com/v1/chat/completions",  # 修改为你的端点
    # ...
)
```

#### 调整审查严格程度

修改 `temperature` 参数：
- `0.0-0.3`: 严格、一致（推荐用于代码审查）
- `0.4-0.7`: 平衡
- `0.8-1.0`: 创新、多样

#### 修改触发分支

编辑 `llm-review-push.yml` 中的分支列表：

```yaml
on:
  push:
    branches:
      - master
      - main
      - develop
      - your-branch  # 添加其他分支
```

## 📊 使用示例

### PR 审查流程

1. 创建 PR 或推送新的提交到 PR
2. GitHub Actions 自动触发审查
3. 几分钟后，审查结果作为评论出现在 PR 中
4. 根据建议修改代码
5. 再次推送，重新审查

### Push 审查流程

1. 推送代码到主分支
2. GitHub Actions 自动触发审查
3. 在 Actions 标签页查看审查日志
4. 下载 Artifact 获取详细报告

## 🛡️ 安全与隐私

### 注意事项

- ⚠️ **代码会发送到 LLM API**: 确保符合公司/组织的安全政策
- ⚠️ **私有仓库**: 评估代码外传的合规性
- ✅ **API Key 安全**: 使用 GitHub Secrets 存储，永不硬编码

### 安全建议

1. **使用私有部署的模型**: 如果代码敏感，考虑自建 LLM 服务
2. **限制审查范围**: 可以在 workflow 中添加文件过滤，只审查非敏感文件
3. **定期轮换 API Key**: 建议每季度更新一次

## 🚀 高级功能

### 1. 只审查特定文件类型

在获取 diff 后添加过滤：

```yaml
- name: 获取PR差异
  run: |
    git diff --unified=3 origin/${{ github.base_ref }}...HEAD -- '*.py' > pr.diff
```

### 2. 设为必需检查

在仓库的 **Settings** → **Branches** → **Branch protection rules** 中：
- 勾选 "Require status checks to pass before merging"
- 选择 "LLM代码审查（PR）"

### 3. 添加静态分析工具

可以并行运行其他工具（如 ruff、mypy）：

```yaml
- name: 运行 Ruff 检查
  run: |
    pip install ruff
    ruff check . --output-format=github
```

## 🔍 故障排查

### 问题: Workflow 不触发

**检查**:
- 是否正确提交了 workflow 文件到 `.github/workflows/` 目录
- 仓库的 Actions 是否已启用（Settings → Actions）

### 问题: API 调用失败

**检查**:
- `OPENAI_API_KEY` 是否正确设置
- API Key 是否有足够的配额
- 网络是否能访问 API 端点

### 问题: 审查结果不准确

**优化**:
- 增加 `max_tokens` 以获得更详细的审查
- 调整 prompt 以强调特定审查点
- 尝试更强大的模型（如 gpt-4）

## 📝 许可

这些 workflow 配置文件可以自由使用和修改。

## 🤝 贡献

欢迎提出改进建议！

