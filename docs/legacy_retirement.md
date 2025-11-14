# Legacy 组件退役说明

## PyArmor 加密脚本
- **现状**：旧版策略及工具使用 PyArmor 加密，仅兼容 Python 3.10/3.11。
- **计划**：
  - 在 `legacy` 分支保留完整加密产物，主干仅保留明文迁移结果；
  - 新策略全部迁移至 `chanlun_quant`，使用单元测试 + 对照脚本保障一致性；
  - 对外发布时提供 `legacy/README.md`，说明使用范围与支持窗口。

## 批处理/启动脚本
- **现状**：`*.bat`、`*.ps1` 脚本散落在根目录及 `script/`，部分依赖固定路径。
- **替代**：
  - 提供 `python script/run_legacy_strategy.py --case <name>` 通用入口；
  - 新建 `scripts/README.md` 统一说明参数、虚拟环境初始化流程；
  - 对需要保留的批处理脚本，仅在 `legacy` 分支保留，以免污染主分支。

## Redis 队列
- **现状**：旧回测/数据抓取任务依赖 Redis 用于缓存与任务分发。
- **替代方案**：
  - 回测、对照任务改为本地文件缓存或 SQLite，减少实时依赖；
  - 如需分布式任务，统一封装在 `chanlun_quant/runtime` 内部，默认禁用 Redis；
  - 将 Redis 相关启动脚本、配置集中迁移到 `legacy/redis/`。

## 分支与目录规划
- 主分支：仅保留新版迁移代码、文档、CI 配置；
- `legacy` 分支：保留 PyArmor 加密脚本、批处理脚本、Redis 配置等；
- `docs/legacy_retirement.md`（本文）：描述退役策略与交付清单；
- TODO：创建 `legacy/README.md` 与迁移 checklist，确保后续迭代有据可循。
