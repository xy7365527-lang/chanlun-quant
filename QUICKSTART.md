# 快速启动指南

## 核心脚本速览

### IB 实盘演练

- 行情订阅：`python -m script.ib_stream_demo --symbol AAPL --seconds 30`
- Paper 下单：`python -m script.ib_paper_trade --symbol AAPL --side buy --quantity 1`
- LiveTradingLoop 演示：`python -m script.run_live_loop_llm --symbol AAPL --steps 5`

### LLM 接入验证

1. 设置环境变量 `CLQ_LLM_PROVIDER/CLQ_LLM_API_BASE/CLQ_LLM_MODEL/CLQ_LLM_API_KEY`
2. 运行 `python -m script.llm_sanity` 确认返回合法 JSON

### Trading Agents REST 适配器

- 本地联调示例：`python -m script.trading_agents_e2e --symbol AAPL`
- 生产环境将 `CLQ_TA_ADAPTER_CLASS` 指向 `chanlun_quant.agents.adapters.rest.RESTTradingAgentAdapter` 并设置 `CLQ_TA_KWARGS_JSON`

## 问题背景

在运行 TradingAgents MA Selector 时，可能会遇到两个关键错误：

1. **PyArmor 兼容性问题**：当前项目使用 PyArmor 加密，仅支持 Python 3.10/3.11，无法在 Python 3.14 上运行
2. **环境变量未设置**：LangChain 需要 `OPENAI_API_KEY`，但环境变量未正确导出

## 解决方案

### 第一步：设置 Python 3.11 环境

运行批处理脚本自动创建虚拟环境：

```batch
setup_py311_env.bat
```

该脚本会：
- 检查系统是否安装 Python 3.11
- 创建 `.venv311` 虚拟环境
- 安装所有依赖包
- 设置 `PYTHONPATH`

### 第二步：配置环境变量

1. 在项目根目录创建 `.env` 文件（不要提交到 Git）

2. 填写以下配置内容：

```env
# ==============================================
# TradingAgents 多智能体配置（LangChain）
# ==============================================
# 必填：OpenAI API Key（或兼容接口的 key）
CLQ_TA_API_KEY=sk-your-openai-api-key-here
# 兼容 LangChain 的标准环境变量
OPENAI_API_KEY=${CLQ_TA_API_KEY}

# 可选：TradingAgents 基础 URL（默认 OpenAI）
CLQ_TA_BASE_URL=https://api.openai.com/v1
# 或者使用兼容服务，如：
# CLQ_TA_BASE_URL=https://api.siliconflow.cn/v1

# 可选：TradingAgents LLM 模型名称
CLQ_TA_MODEL=gpt-4o-mini

# ==============================================
# 市场数据与选股配置
# ==============================================
# 必填：Market Data 工厂函数
CLQ_MKD_FACTORY=chanlun_quant.integration.market_data:make_market_datas

# 可选：候选池聚合器
# CLQ_CANDIDATE_RUNNER=chanlun_quant.selectors.candidate_aggregator:merge_candidates

# 可选：基本面数据提供者
# CLQ_FUNDA_PROVIDER=chanlun_quant.integration.fundamentals:get_fundamentals

# ==============================================
# 选股参数
# ==============================================
CLQ_FREQ=d
CLQ_MAX_CANDIDATES=80
CLQ_TOP_K=2
CLQ_MIN_SCORE=0.0
CLQ_SAVE_CSV=1

# ==============================================
# 日志级别
# ==============================================
CLQ_LOG_LEVEL=INFO

# ==============================================
# Python 环境设置
# ==============================================
PYTHONIOENCODING=utf-8
PYTHONUTF8=1
```

### 第三步：运行选股脚本

#### 方法 A：使用 PowerShell 脚本（推荐）

```powershell
# 使用默认参数（日线，40个候选，选2个）
.\run_ta_selector.ps1

# 自定义参数
.\run_ta_selector.ps1 -Freq d -MaxCandidates 80 -TopK 5 -SaveCsv

# 回测模式（指定截止日期）
.\run_ta_selector.ps1 -Freq d -MaxCandidates 40 -TopK 2 -AsOf "2025-10-22"
```

#### 方法 B：手动运行

1. 激活虚拟环境：

```batch
.venv311\Scripts\activate.bat
```

2. 加载环境变量（PowerShell）：

```powershell
. .\load_env.ps1
```

3. 设置 PYTHONPATH：

```batch
set PYTHONPATH=F:\Cursor\chanlun\src
```

4. 运行脚本：

```batch
python examples\wire_ta_selector.py --freq d --max-candidates 40 --top-k 2
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--freq` | 分析周期（d=日线, w=周线, 30m=30分钟） | d |
| `--max-candidates` | 进入评分的候选数量上限 | 80 |
| `--top-k` | 最终锁定标的数量 | 2 |
| `--min-score` | 最低评分阈值 | 0.0 |
| `--as-of` | 回测截止日期（YYYY-MM-DD） | 留空=最新 |
| `--save-csv` | 保存结果为 CSV | False |
| `--ta-yaml` | TradingAgents YAML 配置路径 | 留空=从ENV读取 |

## 前置依赖检查

在运行前，请确保：

1. **IB Gateway 已启动**（如果使用 IB 数据源）
2. **Redis 服务已启动**（如果使用 Redis 缓存）
3. **IB Worker 进程已启动**（如果使用分布式数据获取）

检查 IB Worker：

```batch
start_ib_tasks.bat
```

## 常见问题

### Q1: 提示找不到 Python 3.11

**解决方案：**

- 访问 https://www.python.org/downloads/
- 下载并安装 Python 3.11.x（推荐 3.11.9）
- 安装时勾选 "Add Python to PATH"

或使用 uv 安装：

```batch
script\bin\uv.exe python install 3.11
```

### Q2: 提示 OPENAI_API_KEY 未设置

**解决方案：**

确保 `.env` 文件中正确设置：

```env
CLQ_TA_API_KEY=sk-your-real-key
OPENAI_API_KEY=${CLQ_TA_API_KEY}
```

然后在 PowerShell 中重新加载：

```powershell
. .\load_env.ps1
```

### Q3: 提示找不到 market_datas 模块

**解决方案：**

确保环境变量中设置了工厂函数：

```env
CLQ_MKD_FACTORY=chanlun_quant.integration.market_data:make_market_datas
```

检查文件是否存在：

```
chanlun_quant/integration/market_data.py
```

### Q4: PyArmor 运行时错误

**原因：**

项目使用 PyArmor 加密，只支持 Python 3.10/3.11。

**解决方案：**

必须使用 Python 3.10 或 3.11，运行 `setup_py311_env.bat` 创建兼容环境。

## 项目结构

```
chanlun/
├── .env                              # 环境变量配置（需手动创建，模板见本文档）
├── QUICKSTART.md                    # 快速启动指南（本文档）
├── setup_py311_env.bat              # Python 3.11 环境设置脚本
├── load_env.ps1                     # PowerShell 环境变量加载脚本
├── run_ta_selector.ps1              # PowerShell 运行脚本（推荐）
├── run_ta_selector.bat              # 批处理运行脚本
├── .venv311/                        # Python 3.11 虚拟环境
├── chanlun_quant/
│   ├── agents/                      # TradingAgents 适配器
│   ├── integration/                 # 数据集成层
│   │   ├── market_data.py          # 市场数据工厂
│   │   └── fundamentals.py         # 基本面数据
│   ├── selectors/                   # 选股器
│   │   ├── llm_ma_selector.py      # 主选股器
│   │   └── candidate_aggregator.py # 候选池聚合
│   └── indicators/                  # 技术指标
│       └── ma_system.py            # 均线系统
├── examples/
│   └── wire_ta_selector.py         # 主入口脚本
└── configs/
    └── ta_orchestrator.yaml        # TradingAgents 配置
```

## 调试技巧

### 查看详细日志

修改 `.env` 文件：

```env
CLQ_LOG_LEVEL=DEBUG
```

### 测试环境变量加载

```powershell
. .\load_env.ps1
$env:OPENAI_API_KEY  # 应该显示你的 API Key
$env:CLQ_MKD_FACTORY # 应该显示工厂函数路径
```

### 验证 Python 版本

```batch
.venv311\Scripts\python.exe --version
# 应该输出: Python 3.11.x
```

### 测试导入

```batch
.venv311\Scripts\python.exe -c "import chanlun; print('OK')"
```

如果提示 PyArmor 错误，说明 Python 版本不对。

## 性能优化建议

1. **减少候选数量**：`--max-candidates 20` 可加快评分速度
2. **使用缓存**：确保 Redis 启动以缓存 K线数据
3. **并行处理**：`CLQ_TA_PARALLEL=true` 启用并行评分（需配置 YAML）
4. **使用更快的模型**：`CLQ_TA_MODEL=gpt-3.5-turbo` 或本地模型

## 获取帮助

查看脚本帮助：

```batch
python examples\wire_ta_selector.py --help
```

查看 TradingAgents 文档：

```
chanlun_quant/agents/README.md
```

