# TradingAgents Integration for chanlun-quant

## 概述

TAOrchestrator 是 TradingAgents 框架的轻量级封装，已成功集成到 chanlun-quant 项目中。

## 快速开始

```python
from chanlun_quant.agents.orchestrators.ta_orchestrator import TAOrchestrator, TAConfig
from chanlun_quant.agents.adapter import AgentsAdapter

# 创建配置（使用默认 SiliconFlow + DeepSeek 配置）
config = TAConfig()

# 实例化编排器
orchestrator = TAOrchestrator(config)

# 创建适配器
adapter = AgentsAdapter(orchestrator)

# 使用适配器进行 JSON 查询（需要提供 symbol 和 trade_date）
result = adapter.ask_json(
    "分析这只股票的交易机会",
    symbol="AAPL",
    trade_date="2024-01-15"
)

# 返回的是 dict 格式，包含完整的分析结果
print(f"决策: {result['decision']}")  # BUY/SELL/HOLD
print(f"市场报告: {result['analysis']['market_report']}")
print(f"投资计划: {result['investment_plan']}")
```

### 参数说明

`ask_json()` 方法接受以下参数：

- `prompt` (str): 自然语言提示（可选，当前版本主要依赖 symbol 和 trade_date）
- `symbol` (str): 股票代码，例如 "AAPL", "TSLA" 等
- `trade_date` (str): 交易日期，格式为 "YYYY-MM-DD"，例如 "2024-01-15"

如果不提供 `symbol`，系统会尝试从 prompt 中提取或使用默认值 "AAPL"。
如果不提供 `trade_date`，系统会使用当天日期。

### 返回格式

```python
{
    "symbol": "AAPL",
    "trade_date": "2024-01-15",
    "decision": "BUY",  # 最终决策: BUY/SELL/HOLD
    "analysis": {
        "market_report": "技术分析报告...",
        "sentiment_report": "情绪分析报告...",
        "news_report": "新闻分析报告...",
        "fundamentals_report": "基本面分析报告..."
    },
    "investment_plan": "投资计划详情...",
    "final_trade_decision": "最终交易决策详情...",
    "trader_plan": "交易员计划...",
    "debate": {  # 多智能体辩论结果
        "bull_conclusion": "看涨方结论...",
        "bear_conclusion": "看跌方结论...",
        "judge_decision": "裁判决定..."
    }
}
```

## 已安装的依赖

以下核心依赖已安装：

- `langchain-openai` - OpenAI 兼容的 LLM 提供者
- `langchain-anthropic` - Anthropic Claude 支持
- `langchain-google-genai` - Google Gemini 支持
- `langgraph` - LangGraph 多智能体框架
- `langchain-core` - LangChain 核心库
- `yfinance` - 金融数据获取
- `stockstats` - 股票技术指标
- `dataclasses-json` - 数据类 JSON 序列化
- 以及其他必要的依赖包

## Python 3.14 兼容性说明

由于 chromadb 与 Python 3.14 存在兼容性问题，我们创建了一个简化的内存实现：

- `external/trading_agents/tradingagents/agents/utils/memory_simple.py` - 使用 numpy 和 OpenAI embeddings 的简单向量搜索实现
- 自动回退机制：如果 chromadb 导入失败，会自动使用简化版本

### 抑制 Pydantic V1 警告

如果你想抑制 "Core Pydantic V1 functionality isn't compatible with Python 3.14" 警告（不影响功能），可以在代码开头添加：

```python
import warnings
warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality")
```

## 配置选项

TAConfig 支持以下主要配置项：

```python
config = TAConfig(
    # LLM 配置
    provider="openai",  # 或 "anthropic", "google"
    api_base="https://api.siliconflow.com/v1",
    api_key="your-api-key",
    model="deepseek-ai/DeepSeek-V3.2-Exp",
    temperature=0.2,
    
    # 输出格式
    enforce_json=True,
    output_schema=DEFAULT_OUTPUT_SCHEMA,  # 可自定义
)
```

### 从环境变量加载配置

```python
# 设置环境变量 CLQ_TA_API_KEY, CLQ_TA_MODEL 等
config = TAConfig.from_env()
orchestrator = TAOrchestrator(config)
```

## 实现的功能

1. **自动路径管理** - `ta_orchestrator.py` 自动将 `external` 目录添加到 Python 路径
2. **模块别名** - 自动创建 `tradingagents` 模块别名以支持内部绝对导入
3. **依赖回退** - chromadb 不可用时自动使用简化实现
4. **JSON 输出** - AgentsAdapter 确保输出为有效的 JSON 格式

## 文件结构

```
chanlun_quant/agents/
├── __init__.py
├── adapter.py                    # AgentsAdapter 包装器
├── orchestrators/
│   ├── __init__.py
│   └── ta_orchestrator.py        # TAOrchestrator 和 TAConfig
└── README.md                     # 本文件

external/trading_agents/
├── tradingagents/
│   ├── __init__.py               # 添加的模块初始化文件
│   ├── agents/
│   │   ├── __init__.py           # 修改：添加 fallback 机制
│   │   └── utils/
│   │       └── memory_simple.py  # 新增：简化的内存实现
│   └── graph/
│       └── trading_graph.py      # 修改：添加 fallback 机制
└── __init__.py                   # 添加的包初始化文件
```

## 故障排除

### 如果遇到导入错误

确保已安装所有必要的依赖：

```bash
pip install langchain-openai langchain-anthropic langchain-google-genai langgraph yfinance stockstats dataclasses-json
```

### 如果 API 调用失败

检查 API 密钥和端点配置：

```python
import os
os.environ['OPENAI_API_KEY'] = 'your-api-key'
```

## 未来改进

- 完整的 chromadb 支持（等待 Python 3.14 兼容性修复）
- 更多数据源集成
- 自定义智能体配置

