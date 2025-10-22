import datetime
import os
import time
import traceback

from chanlun import fun
from chanlun.ai.decision_engine import request_trading_decision
from chanlun.ai.market_state_ib import (
    collect_account_snapshot,
    collect_market_snapshot,
    collect_chanlun_snapshot,
)
from chanlun.execution.ib_order_executor import IBOrderExecutor, TradeExecutionOptions

logger = fun.get_logger("ai_reboot_ib.log")

SYMBOLS = [s.strip().upper() for s in os.getenv("IB_AI_SYMBOLS", "AAPL,MSFT").split(",") if s.strip()]
LOOP_INTERVAL = int(os.getenv("IB_AI_INTERVAL", "900"))
DEFAULT_AMOUNT_USD = float(os.getenv("IB_AI_AMOUNT_USD", "5000"))
MAX_LEVERAGE = float(os.getenv("IB_AI_MAX_LEVERAGE", "2"))
ALLOW_SHORT = os.getenv("IB_AI_ALLOW_SHORT", "false").lower() in {"1", "true", "yes"}

executor = IBOrderExecutor()
exchange = executor.exchange
start_time = datetime.datetime.utcnow()

logger.info("IB AI trading loop start - symbols=%s", SYMBOLS)

try:
    while True:
        loop_start = time.time()
        for symbol in SYMBOLS:
            try:
                market_snapshot = collect_market_snapshot(symbol, exchange)
                if market_snapshot is None:
                    logger.warning("No market snapshot for %s", symbol)
                    continue

                account_snapshot = collect_account_snapshot(exchange)
                chanlun_snapshot = collect_chanlun_snapshot(symbol, exchange)

                decision = request_trading_decision(
                    symbol,
                    start_time,
                    market_snapshot=market_snapshot,
                    account_snapshot=account_snapshot,
                    chanlun_snapshot=chanlun_snapshot,
                )

                logger.info("Decision for %s: %s", symbol, decision)

                if decision.operation == "HOLD":
                    if decision.stop_loss or decision.take_profit:
                        executor.adjust_stops(
                            TradeExecutionOptions(
                                symbol=symbol,
                                amount=0,
                                side="long",
                                stop_loss=decision.stop_loss,
                                take_profit=decision.take_profit,
                            )
                        )
                    continue

                last_price = market_snapshot.last_price
                leverage = min(max(decision.leverage or 1.0, 1.0), MAX_LEVERAGE)
                budget = decision.amount or DEFAULT_AMOUNT_USD
                if budget <= 0:
                    budget = DEFAULT_AMOUNT_USD

                shares = budget * leverage / max(last_price, 1e-6)
                if shares < 1:
                    logger.warning("Shares below minimum for %s", symbol)
                    continue

                side = "long"
                if decision.operation == "SELL":
                    if decision.amount is None and decision.percentage:
                        executor.close(symbol, decision.percentage)
                        continue
                    if not ALLOW_SHORT:
                        executor.close(symbol, decision.percentage or 100.0)
                        continue
                    side = "short"

                executor.execute(
                    TradeExecutionOptions(
                        symbol=symbol,
                        amount=shares,
                        side=side,
                        leverage=leverage,
                        percentage=decision.percentage,
                        stop_loss=decision.stop_loss,
                        take_profit=decision.take_profit,
                        note=decision.reasoning,
                    )
                )

            except Exception:
                logger.error("Error processing %s\n%s", symbol, traceback.format_exc())

        elapsed = time.time() - loop_start
        sleep_time = max(LOOP_INTERVAL - elapsed, 5)
        time.sleep(sleep_time)

except KeyboardInterrupt:
    logger.info("IB AI trading loop stopped by user")
except Exception:
    logger.error("IB AI trading loop fatal error\n%s", traceback.format_exc())
