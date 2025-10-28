===============================================
  环境设置工具 - 快速参考
===============================================

【两个阻断性错误的解决方案】

错误 1: PyArmor 不兼容 Python 3.14
   → 使用 Python 3.11 虚拟环境

错误 2: OPENAI_API_KEY 未设置
   → 创建 .env 并自动加载环境变量

===============================================
  快速开始（3 步）
===============================================

第 1 步：创建 Python 3.11 环境
   双击运行：setup_py311_env.bat

第 2 步：创建 .env 配置文件
   在项目根目录创建 .env 文件，填写：

   CLQ_TA_API_KEY=sk-your-openai-api-key-here
   OPENAI_API_KEY=${CLQ_TA_API_KEY}
   CLQ_MKD_FACTORY=chanlun_quant.integration.market_data:make_market_datas

第 3 步：运行选股
   PowerShell:  .\run_ta_selector.ps1
   批处理:      run_ta_selector.bat

===============================================
  工具文件说明
===============================================

setup_py311_env.bat     - 创建 Python 3.11 环境（一次性）
load_env.ps1            - 加载 .env 环境变量（PowerShell）
run_ta_selector.ps1     - PowerShell 运行脚本（推荐）
run_ta_selector.bat     - 批处理运行脚本

QUICKSTART.md           - 详细快速启动指南
环境配置指南.md         - 简洁使用指南
解决方案总结.md         - 技术细节和总结

===============================================
  常用命令
===============================================

【使用默认参数】
.\run_ta_selector.ps1

【自定义参数】
.\run_ta_selector.ps1 -Freq d -MaxCandidates 80 -TopK 5 -SaveCsv

【回测模式】
.\run_ta_selector.ps1 -AsOf "2025-10-22"

【批处理版本】
run_ta_selector.bat --freq d --max-candidates 40 --top-k 2

===============================================
  获取详细帮助
===============================================

快速上手：    环境配置指南.md
详细文档：    QUICKSTART.md
技术细节：    解决方案总结.md

===============================================

