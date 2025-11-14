# Legacy 策略迁移指南

## 1. 总览
- 目标：将 `src/chanlun` 旧策略迁移至 `chanlun_quant` 体系，统一回测、对照、上线流程。
- 工具链：
  - `script/run_legacy_strategy.py`：通用迁移执行器；
  - `script/compare_legacy_results.py`：指标对照工具；
  - `script/run_regression_suite.py`：批量对照回归；
  - `configs/legacy_strategies.yaml`、`configs/legacy_compare.yaml`：策略/对照配置。

## 2. CLI 使用手册
### 2.1 运行迁移策略
```bash
python script/run_legacy_strategy.py \
  --strategy chanlun.strategy.strategy_test:StrategyTest \
  --symbol SHFE.RB \
  --market futures \
  --freqs 5m \
  --limit 500
```
- 支持 `--strategy-kwargs '{"mode": "test"}'`；
- 可通过 `--config configs/legacy_strategies.yaml --case strategy_a_d_mmd_test` 直接读取预设参数。

### 2.2 指标对照
```bash
python script/compare_legacy_results.py \
  --legacy legacy_results/a_d_mmd_legacy.json \
  --quant quant_results/a_d_mmd_quant.json \
  --output reports/a_d_mmd_compare.md
```
- `--all`：使用配置文件内所有 `cases`；
- `--metrics '{"annual_return":0.02}'`：动态覆写阈值。

### 2.3 回归套件
```bash
python script/run_regression_suite.py \
  --config configs/legacy_compare.yaml \
  --output reports/legacy_regression.md
```
- 自动遍历 `cases`，输出 Markdown/JSON 报告；
- 结合 `.github/workflows/legacy-compare.yml` 可实现定期回归。

## 3. 培训材料提纲
1. **背景与目标**（10min）
   - Legacy/新版差异、迁移动机、交付边界。
2. **工具实操**（30min）
   - `run_legacy_strategy.py` 参数讲解与现场演示；
   - `compare_legacy_results.py` 与 `run_regression_suite.py` 差异分析；
   - CI 工作流、测试用例结构说明。
3. **迁移步骤梳理**（20min）
   - 评估依赖 → 衔接数据源 → 运行迁移脚本 → 指标对照 → 回归汇报。
4. **退役策略**（10min）
   - `docs/legacy_retirement.md` 要点、分支规划。
5. **问答 & 下一步行动**（10min）

附录可结合上方命令示例制作幻灯或内部 wiki。
