import datetime
from typing import Dict, Optional

from chanlun import utils, zixuan
from chanlun.db import db
from chanlun.exchange.exchange_ib import ExchangeIB
from chanlun.execution.ib_order_executor import (
    IBOrderExecutor,
    TradeExecutionOptions,
)
from chanlun.backtesting.base import Operation, POSITION
from chanlun.backtesting.backtest_trader import BackTestTrader


class TraderIBStock(BackTestTrader):
    """
    US stock live trader powered by Interactive Brokers.
    """

    def __init__(self, name: str, log=None):
        super().__init__(name=name, mode="online", market="us", log=log)
        self.ex = ExchangeIB()
        self.executor = IBOrderExecutor(self.ex)
        self.max_positions = 6
        self.cash_reserve_ratio = 0.1
        self.min_shares = 1

        self.zx = zixuan.ZiXuan("us")
        self.default_zx_group = (
            self.zx.zx_names[0] if len(self.zx.zx_names) > 0 else ""
        )

    def _available_funds(self) -> float:
        balance = self.ex.balance() or {}
        return (
            balance.get("AvailableFunds")
            or balance.get("ExcessLiquidity")
            or balance.get("NetLiquidation")
            or 0.0
        )

    def _position_map(self) -> Dict[str, Dict]:
        positions = self.ex.positions() or []
        return {
            str(p["code"]).upper(): p
            for p in positions
            if float(p.get("position", 0)) != 0
        }

    def open_buy(self, code: str, opt: Operation, amount: float = None):
        code = code.upper()
        pos_map = self._position_map()
        if code in pos_map and pos_map[code].get("position", 0) > 0:
            return False

        long_positions = [
            p for p in pos_map.values() if float(p.get("position", 0)) > 0
        ]
        if len(long_positions) >= self.max_positions:
            return False

        available = self._available_funds()
        if available <= 0:
            return False

        slots = max(self.max_positions - len(long_positions), 1)
        budget = (available * (1 - self.cash_reserve_ratio)) / slots
        if budget <= 0:
            return False

        ticks = self.ex.ticks([code])
        tick = ticks.get(code)
        if tick is None or tick.last <= 0:
            return False

        shares = int(budget / tick.last)
        if shares < self.min_shares:
            shares = self.min_shares

        stock_info = self.ex.stock_info(code) or {}
        stock_name = stock_info.get("name", code)

        current_snapshot = self.executor.fetch_position(code)

        result = self.executor.execute(
            TradeExecutionOptions(
                symbol=code,
                amount=shares,
                side="long",
                note=opt.msg,
            )
        )

        closed_res = result.get("closed")
        if closed_res and current_snapshot:
            close_side = "buy" if current_snapshot.side == "short" else "sell"
            utils.send_fs_msg(
                "us",
                "US Trader",
                f"CLOSE {code} {current_snapshot.side} @ {closed_res.get('price')} amount {closed_res.get('amount')} ({opt.msg})",
            )
            db.order_save(
                "us",
                code,
                stock_name,
                close_side,
                float(closed_res.get("price", 0)),
                float(closed_res.get("amount", 0)),
                opt.msg,
                datetime.datetime.now(),
            )

        order_res = result.get("opened")
        if not order_res:
            utils.send_fs_msg(
                "us", "US Trader", f"{code} buy order failed ({opt.msg})"
            )
            return False

        price = float(order_res.get("price", tick.last))
        filled = float(order_res.get("amount", shares))

        utils.send_fs_msg(
            "us",
            "US Trader",
            f"BUY {code} ({stock_name}) @ {price:.2f} for {filled} shares ({opt.msg})",
        )

        if self.default_zx_group:
            self.zx.add_stock(self.default_zx_group, code, stock_name)

        db.order_save(
            "us",
            code,
            stock_name,
            "buy",
            price,
            filled,
            opt.msg,
            datetime.datetime.now(),
        )

        return {"price": price, "amount": filled}

    def open_sell(self, code: str, opt: Operation, amount: float = None):
        # short selling not supported in default setup
        return False

    def close_buy(self, code: str, pos: POSITION, opt: Operation):
        code = code.upper()
        snapshot = self.executor.fetch_position(code)
        if snapshot is None:
            return {"price": pos.price, "amount": pos.amount}

        order_res = self.executor.close(code, 100.0)
        if not order_res:
            utils.send_fs_msg(
                "us", "US Trader", f"{code} sell order failed ({opt.msg})"
            )
            return False

        price = float(order_res.get("price", pos.price))
        filled = float(order_res.get("amount", snapshot.size))

        utils.send_fs_msg(
            "us",
            "US Trader",
            f"SELL {code} @ {price:.2f} for {filled} shares ({opt.msg})",
        )

        if self.default_zx_group:
            self.zx.del_stock(self.default_zx_group, code)

        stock_info = self.ex.stock_info(code) or {}
        stock_name = stock_info.get("name", code)

        db.order_save(
            "us",
            code,
            stock_name,
            "sell",
            price,
            filled,
            opt.msg,
            datetime.datetime.now(),
        )

        return {"price": price, "amount": filled}

    def close_sell(self, code: str, pos: POSITION, opt: Operation):
        # short covering not implemented
        return False
