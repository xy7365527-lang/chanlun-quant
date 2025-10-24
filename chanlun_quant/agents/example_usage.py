#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TradingAgents 使用示例

这个脚本演示如何使用 TAOrchestrator 和 AgentsAdapter 进行股票分析。
"""

import warnings
import json

# 抑制 Pydantic V1 警告
warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality")

from chanlun_quant.agents.orchestrators.ta_orchestrator import TAOrchestrator, TAConfig
from chanlun_quant.agents.adapter import AgentsAdapter


def example_basic_usage():
    """基本使用示例"""
    print("="*60)
    print("示例 1: 基本使用")
    print("="*60)
    
    # 1. 创建配置（使用默认 SiliconFlow + DeepSeek）
    config = TAConfig()
    
    # 2. 创建编排器
    orchestrator = TAOrchestrator(config)
    
    # 3. 创建适配器
    adapter = AgentsAdapter(orchestrator)
    
    # 4. 分析股票（需要实际的 API 密钥才能运行）
    try:
        result = adapter.ask_json(
            "分析这只股票的交易机会",
            symbol="AAPL",
            trade_date="2024-01-15"
        )
        
        # 5. 处理结果
        print(f"\n决策: {result['decision']}")
        print(f"投资计划: {result['investment_plan'][:100]}...")
        
        # 完整结果（JSON 格式）
        print("\n完整结果（JSON）:")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:500] + "...")
        
    except Exception as e:
        print(f"\n注意: 需要有效的 API 密钥才能运行。错误: {e}")


def example_custom_config():
    """自定义配置示例"""
    print("\n" + "="*60)
    print("示例 2: 自定义配置")
    print("="*60)
    
    # 自定义配置
    config = TAConfig(
        # 使用不同的 API 端点
        api_base="https://api.openai.com/v1",
        api_key="your-api-key-here",
        model="gpt-4",
        
        # 调整参数
        temperature=0.3,
        timeout=180,
    )
    
    orchestrator = TAOrchestrator(config)
    adapter = AgentsAdapter(orchestrator)
    
    print("已创建自定义配置的 orchestrator")
    print(f"  Provider: {config.provider}")
    print(f"  Model: {config.model}")
    print(f"  API Base: {config.api_base}")


def example_from_env():
    """从环境变量加载配置"""
    print("\n" + "="*60)
    print("示例 3: 从环境变量加载配置")
    print("="*60)
    
    # 设置环境变量（实际使用时应该在 shell 中设置）
    # export CLQ_TA_API_KEY="your-key"
    # export CLQ_TA_MODEL="gpt-4"
    
    config = TAConfig.from_env()
    orchestrator = TAOrchestrator(config)
    
    print("已从环境变量加载配置")
    print("  环境变量前缀: CLQ_TA_")
    print("  支持的变量: CLQ_TA_API_KEY, CLQ_TA_MODEL, 等")


def example_direct_ask():
    """直接使用 orchestrator.ask() 方法"""
    print("\n" + "="*60)
    print("示例 4: 直接使用 ask() 方法")
    print("="*60)
    
    config = TAConfig()
    orchestrator = TAOrchestrator(config)
    
    try:
        # 直接调用 ask()，返回 dict
        result = orchestrator.ask(
            "分析股票",
            symbol="TSLA",
            trade_date="2024-01-20"
        )
        
        print(f"返回类型: {type(result)}")
        print(f"是否为字典: {isinstance(result, dict)}")
        if isinstance(result, dict):
            print(f"包含的键: {list(result.keys())}")
            
    except Exception as e:
        print(f"注意: {e}")


if __name__ == "__main__":
    print("\nTradingAgents 使用示例")
    print("="*60)
    print("注意: 这些示例需要有效的 API 密钥才能完整运行")
    print("="*60)
    
    # 运行示例
    example_basic_usage()
    example_custom_config()
    example_from_env()
    example_direct_ask()
    
    print("\n" + "="*60)
    print("示例完成")
    print("="*60)

