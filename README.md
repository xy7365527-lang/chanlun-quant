# chanlun-quant

量化交易研究与执行框架，继承自 chanlun-pro，并引入：

- **多级别缠论结构识别** 与成本递减策略调度；
- **实盘 IB 集成**：基于 `ib_insync` 的实时行情、下单链路；
- **外部 LLM 协同决策**：可配置 OpenAI/Azure/硅基流动等；
- **Trading Agents**：REST 适配器与统一研究请求协议；
- **脚本化示例**：快速验证行情、LLM、研究服务。

## 快速上手

1. 安装依赖并创建 Python 3.11 虚拟环境：
   ```bash
   setup_py311_env.bat
   ```
2. 运行回测演示（使用 IB 历史数据）：
   ```bash
   python -m script.run_quant_backtest --symbol AAPL
   ```
3. 执行包含 LLM 的实时循环（离线历史数据驱动）：
   ```bash
   python -m script.run_live_loop_llm --symbol AAPL --steps 5
   ```

更多细节请参考 [QUICKSTART.md](QUICKSTART.md)。

