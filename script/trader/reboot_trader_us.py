#:  -*- coding: utf-8 -*-
import time
import traceback

from chanlun import fun
from chanlun.cl_interface import Config
from chanlun.exchange.exchange_ib import ExchangeIB
from chanlun.strategy.strategy_demo import StrategyDemo
from chanlun.trader.online_market_datas import OnlineMarketDatas
from chanlun.trader.trader_ib import TraderIBStock

logger = fun.get_logger("trader_us.log")

logger.info("启动美股 IB 自动化交易脚本")

try:
    ex = ExchangeIB()

    run_codes = ["AAPL", "MSFT", "NVDA", "META", "TSLA", "AMZN"]
    frequencys = ["60m"]

    cl_config = {
        "fx_qj": Config.FX_QJ_K.value,
        "fx_bh": Config.FX_BH_YES.value,
        "bi_type": Config.BI_TYPE_NEW.value,
        "bi_bzh": Config.BI_BZH_YES.value,
        "bi_fx_cgd": Config.BI_FX_CHD_NO.value,
        "bi_qj": Config.BI_QJ_DD.value,
        "xd_qj": Config.XD_QJ_DD.value,
        "zsd_bzh": Config.ZSD_BZH_NO.value,
        "zsd_qj": Config.ZSD_QJ_DD.value,
        "zs_bi_type": Config.ZS_TYPE_DN.value,
        "zs_xd_type": Config.ZS_TYPE_DN.value,
        "zs_qj": Config.ZS_QJ_CK.value,
        "zs_wzgx": Config.ZS_WZGX_ZGD.value,
    }

    p_redis_key = "trader_us_stock"

    trader = TraderIBStock("USStock", log=logger.info)
    trader.load_from_pkl(p_redis_key)

    data = OnlineMarketDatas("us", frequencys, ex, cl_config)
    strategy = StrategyDemo()

    trader.set_strategy(strategy)
    trader.set_data(data)

    logger.info("Run symbols: %s", run_codes)

    interval_seconds = 15 * 60

    while True:
        try:
            seconds = int(time.time())

            if ex.now_trading() is False:
                time.sleep(60)
                continue

            if seconds % interval_seconds != 0:
                time.sleep(1)
                continue

            symbols = trader.position_codes() + run_codes
            symbols = list({code.upper() for code in symbols})

            for code in symbols:
                try:
                    trader.run(code)
                except Exception:
                    logger.error(traceback.format_exc())

            data.clear_cache()
            trader.save_to_pkl(p_redis_key)

        except Exception:
            logger.error(traceback.format_exc())

except Exception:
    logger.error(traceback.format_exc())
finally:
    logger.info("Done")

