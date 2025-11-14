## 旧版 `src/chanlun` 策略清单与依赖概览

| 模块 | 主要策略/脚本 | 关键依赖 | 迁移状态 | 备注 |
|------|----------------|----------|----------|------|
| `strategy/strategy_a_d_mmd_test.py` | A 股多周期买卖点回测 | `BackTest`, `ExchangeTDX`, SQLite 历史K线 | ✅ 已迁移 | 需大量行情数据与 PyArmor |
| `strategy/strategy_test.py` | 简单 K 线颜色策略 | 同上 | ✅ 已迁移 | 可作为迁移练手目标 |
| `backtesting/backtest.py` | 多进程回测主控 | `BackTestTrader`, `BackTestKlines` | 待迁移 | 依赖 Redis/DB/多进程 |
| `backtesting/backtest_trader.py` | 回测交易撮合 | 交易费用/分仓逻辑 | 待迁移 | 与成本递减策略存在功能重叠 |
| `backtesting/backtest_klines.py` | 数据读取/转换 | `ExchangeDB`, SQLite, Redis 缓存 | 待迁移 | 与新版 BacktestRunner 功能重叠 |
| `exchange/exchange_db.py` | DB 行情适配器 | SQLAlchemy + SQLite/MySQL | 待复用 | 新版仍可重复利用 |
| `exchange/exchange_tdx*.py` | 通达信行情接口 | PyTDX、本地 TDX 数据目录 | 待复用 | 若继续使用需保留 |

`configs/legacy_strategies.yaml` 与 `script/run_legacy_strategy.py` 可用于批量维护、执行迁移任务。单策略场景建议继续复用 `run_strategy_test_migration.py`、`run_strategy_ad_mmd_migration.py` 等示例脚本。

### 运行旧版回测所需环境

1. Python 3.11 + PyArmor 运行时；
2. SQLite/MySQL 历史 K 线库（表结构参考 `ExchangeDB.klines_tables`）；
3. 可选：Redis 队列（用于 IB/分布式任务）；
4. TDX/API 行情源（如需实时/增量数据）。

### 迁移建议

1. **短期**：挑选 `strategy_a_d_mmd_test` 迁移至 `chanlun_quant` 的 `TradeRhythmEngine` + `BacktestRunner`，复用新版成本递减与 IB 接口；
2. **中期**：将 `BackTestKlines` 的历史行情读取逻辑抽象为 `DataFeed` 实现，供新版回测重用；
3. **长期**：保留 `exchange_db` 等通用组件，其余 PyArmor 脚本逐步下线。

### 迁移路线图

1. **建立兼容层**：在 `chanlun_quant.runtime` 中实现与旧版 `BackTestTrader` 接口兼容的适配器，先支持最常用的买卖点策略。
2. **数据统一入口**：以 `HistoricalDataFeed` 为核心，编写脚本将旧版 SQLite 历史数据批量转换为新版 `Bar` 序列，确保多周期、级联映射一致。
3. **策略重写/包装**：为每个旧策略编写 shim（例如将旧的 `Strategy.open/close` 包装为新版信号），逐步替换 PyArmor 依赖。
4. **回测校验**：针对迁移后的策略，使用 `script/run_demo_backtest.py` 或自定义单测对照旧回测结果，确保收益/交易次数差异在可接受范围。
5. **清理遗留依赖**：待新版完全覆盖后，逐步移除旧版多进程、Redis 队列等基础设施。

### 旧→新接口适配思路

| 旧版接口 | 行为 | 新版承载模块 | 适配方式 |
|----------|------|--------------|----------|
| `Strategy.open/close` | 根据 `MarketDatas` 返回 `Operation` 列表 | `TradeRhythmEngine` + 自定义 signal adapter | 将 `Operation` 转换为结构化信号（type、qty、price），由 `on_signal` 统一调度 |
| `BackTestTrader` | 负责资金、手续费、仓位记录 | `HoldingManager` + `SimulatedBroker/IBBroker` | 在 `LiveTradingLoop._execute_plan` 后注入旧策略需要的成本字段 |
| `MarketDatas` / `BackTestKlines` | 读取缠论数据、支持多周期转换 | `HistoricalDataFeed` + 预处理 SQL | 复用 SQLite 表，提供 `get_bars(level, lookback)`，必要时在 analyzer 中调用 `cl.CL` 重算结构 |
| `BackTest` 主流程 | 多进程回测、进度条、结果存盘 | `BacktestRunner` | 以脚本形式包装，提供参数兼容的 CLI（比如 `script/run_demo_backtest.py`） |
| PyArmor 包装的旧脚本 | 回测入口、策略配置 | 文档化或转为 yaml | 将配置转为 `.json/.yaml`，由新版 CLI 读取，减少 PyArmor 依赖 |

### 统一历史行情读取方案

1. **数据源确认**  
   - 旧版默认使用 `chanlun.db.DB` (SQLite) 按 `table=f"{market}_klines_{code}"` 组织。  
   - 确保 `script/fetch_us_bars_ib.py`、`chanlun/db.py` 写入的字段包含 `dt, open, high, low, close, v, f`，可被新版解析。

2. **转换管线**  
   - 新增 `chanlun_quant/integration/datafeed.py`（建议）：提供 `load_legacy_bars(symbol, freqs, market)`，内部调用 `DB().klines_load(...)` 并返回 `Dict[str, List[Bar]]`。  
   - 对于 A 股/期货场景，可继续使用 TDX/Redis 抓取逻辑，但统一在转换层输出 `Bar` dataclass。

3. **复用现有组件**  
   - `HistoricalDataFeed` 已支持多周期队列与逐步推进，只需在初始化时传入上一步转换后的 `bars_by_level`。  
   - Live 场景可通过实现 `LegacyDataFeed(DataFeed)`，在 `next()` 内部调用原 `exchange_*` 拉取实时 K 线。

4. **校验工具**  
   - 编写 `tests_legacy/test_legacy_datafeed_bridge.py`（待建），以 1~2 支证券的样本数据验证补齐指标（比如缺失 volume、复权）。  
   - 提供 CLI：`python script/export_legacy_bars.py --symbol SHFE.RB --freqs 5m,30m --out data/rb.json`，方便排查字段差异。

5. **性能与缓存**  
   - 在转换层增加可选的 `lru_cache` 或磁盘缓存，避免重复加载 SQLite。  
   - 若 Redis 仍被使用，可在 `LegacyDataFeed` 内选择性启用，保持对旧部署的兼容。

### 迁移验证指标计划

1. **核心指标**  
   - `annual_return`、`max_drawdown`、`win_rate`、`trade_count`、`avg_trade_pnl`。  
   - 统一采用新版 `BacktestResult.metrics`（待扩展）与旧版 `BackTest.result()` 导出的字段进行对照。

2. **样本数据集**  
   - 股票：`SZSE.000001`（连贯历史、体量大）。  
   - 期货：`SHFE.RB`（旧策略示例使用标的）。  
   - 美股：`AAPL`（通过 `fetch_us_bars_ib.py` 获取，验证跨市场一致性）。

3. **对照流程**  
   - Step1：运行旧版 `BackTest`，保存结果至 `legacy_results/{strategy}/{symbol}_{freq}.json`。  
   - Step2：运行新版 `script/run_quant_backtest.py`（或迁移后的策略脚本），保存为 `quant_results/...`。  
   - Step3：使用比对脚本（见下一节自动化计划）计算指标差异，阈值建议：收益率 ±3%，交易次数 ±1 次，胜率 ±5%。

4. **回归频率**  
   - 每完成一个策略迁移后执行一次全量对照；  
   - 后续维护中引入 CI 工作流（如 GitHub Actions）在夜间对重点策略运行缩减样本集。

### 自动化比对脚本规划

1. **CLI 入口**：`script/compare_legacy_results.py --strategy strategy_a_d_mmd_test --symbol SHFE.RB --freq 5m`。  
   - 参数包含旧/新结果路径、阈值配置，默认读取 `configs/legacy_compare.yaml`。

2. **实现步骤**  
   - 读取旧版 `pkl/json`，解析关键指标；  
   - 读取新版 `BacktestResult`（可序列化为 JSON）；  
   - 计算差异并输出 Markdown/JSON 报告，含图表（可选使用 `pandas.DataFrame.plot` 保存 PNG）。

3. **集成 CI**  
   - 新增 GitHub Actions Workflow：  
     ```yaml
     on:
       workflow_dispatch:
       schedule:
         - cron: "0 17 * * 0"
     jobs:
       compare:
         runs-on: ubuntu-latest
         steps:
           - uses: actions/checkout@v4
           - uses: actions/setup-python@v5
             with:
               python-version: "3.11"
           - run: pip install -r requirements.txt
           - run: python script/compare_legacy_results.py --all
         ```
   - 结果上传至 workflow artifact 或 PR 注释，便于审核。

4. **扩展方向**  
   - 支持多策略批量对比 `--all`，并输出聚合差异表；  
   - 提供 Slack/飞书 Webhook 通知；  
   - 后续接入 `pytest`，将阈值对比转为断言以便 CI 阻断异常。

已实现：`script/compare_legacy_results.py` + `configs/legacy_compare.yaml`。示例：

```bash
python script/compare_legacy_results.py \
  --legacy legacy_results/strategy_test.json \
  --quant quant_results/strategy_test.json \
  --output reports/strategy_test.md
```

配置还支持 `cases` 批量对照与 `--metrics` 动态阈值覆写。

- GitHub Actions 工作流：`.github/workflows/legacy-compare.yml`，按周计划与手动触发，执行单元测试并产出对照报告。
- 本地/CI 批量回归脚本：`script/run_regression_suite.py`，读取 `configs/legacy_compare.yaml` cases，输出 Markdown/JSON 报告。

### 上线顺序与回归安排

1. **阶段一（样例验证）**  
   - 迁移 `strategy_test`：作为最简示例验证接口适配；  
   - 迁移 `strategy_a_d_mmd_test`：对标最常用 A 股策略，跑通全链路；  
   - 在 `tests` 中新增对应单测，确保 `TradeRhythmEngine` 信号与旧结果一致。

2. **阶段二（高优先级策略）**  
   - `strategy_a_xd_trade_model`, `strategy_last_zs_3mmd`, `strategy_futures_xd_mmd`：涵盖不同市场（A 股/期货）。  
   - 引入 `compare_legacy_results.py --batch high_priority.yaml` 批量对比。

3. **阶段三（剩余策略 & 优化）**  
   - 处理 `optimization/` 下脚本，将可复用逻辑沉淀至新版 `selectors` 或 `analysis`。  
   - 清理已不再维护的策略，记录在 `docs/deprecated_strategies.md`。

4. **回归节奏**  
   - 每阶段完成后执行一次全量回测对比；  
   - 正式上线前安排一周灰度（新版与旧版并行观测）；  
   - 上线后每月例行回归一次，确保数据接口更新未破坏兼容。

5. **沟通与培训**  
   - 提供迁移 checklist 与脚本使用手册；  
   - 安排一次内部分享会，讲解新框架 `TradeRhythmEngine` + LLM 协作流程；  
   - 收集用户反馈，纳入下一轮优化计划。

### 旧组件下线计划

| 组件 | 当前用途 | 下线策略 | 目标时间 |
|------|----------|----------|----------|
| PyArmor 加密脚本 | 保护旧版策略源码 | 将核心策略迁移至新版公开模块，保留历史版本在私有仓库 | 阶段二完成后 |
| 旧版多进程回测 (`BackTest.run_process`) | 大规模回测 | 以 `BacktestRunner` + `multiprocessing.Pool` 重写，提供 CLI 参数 `--workers` | 阶段三 |
| Redis 队列 | 数据缓存、任务派发 | 若新版不需实时分发，可用本地缓存替代；保留配置项兼容 | 阶段三 |
| TDX 行情爬取脚本 | A 股行情补充 | 迁至独立 repo，并提供 REST/CSV 导出，逐步由 API 数据替代 | 阶段三 |
| 老版启动脚本 (`start_ib_tasks.bat` 等) | 调度、环境初始化 | 在新版中提供 `uv`/`poetry` 方案，文档化新流程 | 全流程完成后 |

> 建议保留一个 “legacy” 分支，收纳完成迁移后仍需访问的 PyArmor 包，与主干完全解耦；待确认业务侧无需求后彻底归档。详见 `docs/legacy_retirement.md`。

### 策略拆解备忘

#### `strategy_a_d_mmd_test`
- **场景**：沪深 A 股，聚焦日线级别买卖点，借助 `cd_d.get_bis()`、`mmds` 列表识别多类买卖点。  
- **开仓**：仅处理向下笔（`bi_d.type == "down"`），检测笔上的买点或线段背驰，通过 `Operation` 输出 `pos_rate` 固定仓位。  
- **持仓管理**：`close()` 中依据线段走势与 `loss_rate` 控制止损，允许在买点缺失或指数背离时减仓。  
- **依赖**：`MarketDatas.get_cl_data`（多周期），`self.zs_code`（指数共振过滤），需要历史笔/段数据与 PyArmor 支持的加密模块。

#### `strategy_test`
- **场景**：示例级策略，单周期，依据 K 线颜色决定买卖。  
- **开仓**：最后一根 K 线收阳视为买入信号，收阴视为“买入”带 `1sell` 标签的对冲操作。  
- **平仓**：结合 `check_loss` 与 K 线颜色对调仓方向做半仓止盈/止损。  
- **意义**：逻辑简单、无外部依赖，适合作为新版接口映射的首个样例，可直接通过 `LegacyStrategyAdapter` 接入新版框架：

  ```python
  from chanlun.strategy.strategy_test import StrategyTest
  from chanlun_quant.strategy import LegacyStrategyAdapter, TradeRhythmEngine

  legacy = StrategyTest()
  adapter = LegacyStrategyAdapter(symbol="SHFE.RB", strategy=legacy)
  trade_engine = TradeRhythmEngine(initial_capital=100_000)
  ```

  随后每个回测步迭代调用 `adapter.step(market_data)` 获取信号，并用 `trade_engine.on_signal()` 生成执行计划，再通过 `adapter.register_fill()` 同步 legacy POSITION。

#### `strategy_a_d_mmd_test`
- **场景**：A 股日线买卖点（辅以周线与指数过滤），依赖缠论结构、买卖点与多重指标。  
- **迁移现状**：  
  * `script/run_strategy_ad_mmd_migration.py` 结合 `LegacyMarketDataBridge` + `LegacyStrategyAdapter`，在 `TradeRhythmEngine`/`BacktestRunner` 上复用原策略；  
  * `LegacyMarketDataBridge` 通过 `web_batch_get_cl_datas` 计算缠论数据，支持主标的与指数多周期输入；  
  * `AdapterSimulatedBroker` 确保成交回写旧 `POSITION`。  
- **注意事项**：运行脚本需准备 SQLite 历史库（周期至少含 `w`、`d`），并确保指数数据同步；如需调整 `filter_key` 或仓位参数，可直接传入脚本参数。

### 迁移进度跟踪

- `configs/legacy_strategies.yaml`：记录策略清单、迁移状态与默认参数，可被 `script/run_legacy_strategy.py --case <name>` 直接调用。
- `script/run_legacy_strategy.py`：通用迁移执行器，支持从 YAML 读取参数或命令行覆写，便于批量迁移/回归。

- 培训与操作手册：`docs/migration_playbook.md` 提供命令示例与培训提纲。

