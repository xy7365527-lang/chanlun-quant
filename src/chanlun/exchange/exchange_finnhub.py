"""
US Finnhub data adapter.
"""

import datetime
import time
from typing import Dict, List, Union

import pandas as pd
import pytz
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random

from chanlun import config, fun
from chanlun.exchange.exchange import Exchange, Tick


class FinnhubRequestError(Exception):
    """Custom error for Finnhub request failures."""


@fun.singleton
class ExchangeFinnhub(Exchange):
    """
    Exchange implementation backed by Finnhub REST APIs.
    """

    def __init__(self):
        super().__init__()

        if getattr(config, "FINNHUB_APIKEY", "") == "":
            raise FinnhubRequestError("FINNHUB_APIKEY is not configured")

        self.api_key = config.FINNHUB_APIKEY
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "chanlun-pro"})
        self.tz = pytz.timezone("America/New_York")

        self._all_stocks: List[Dict[str, str]] = []
        self._market_status_cache: Union[bool, None] = None
        self._market_status_updated_at: float = 0.0

    def default_code(self) -> str:
        return "AAPL"

    def support_frequencys(self) -> dict:
        return {
            "m": "Month",
            "w": "Week",
            "d": "Day",
            "240m": "4H",
            "120m": "2H",
            "60m": "1H",
            "30m": "30m",
            "15m": "15m",
            "5m": "5m",
            "1m": "1m",
        }

    def all_stocks(self):
        if len(self._all_stocks) > 0:
            return self._all_stocks

        params = {"exchange": "US"}
        data = self._request("stock/symbol", params)
        stocks = []
        if isinstance(data, list):
            for item in data:
                symbol = item.get("symbol")
                name = item.get("description") or ""
                if symbol:
                    stocks.append({"code": symbol.upper(), "name": name})
        self._all_stocks = stocks
        return self._all_stocks

    def now_trading(self):
        current = time.time()
        if (
            self._market_status_cache is not None
            and current - self._market_status_updated_at < 60
        ):
            return self._market_status_cache

        try:
            data = self._request("stock/market-status", {"exchange": "US"})
            status = bool(data.get("isOpen", False)) if isinstance(data, dict) else False
        except FinnhubRequestError:
            # fallback to timetable check if API limited
            status = self._is_session_time()

        self._market_status_cache = status
        self._market_status_updated_at = current
        return status

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_random(min=1, max=5),
        retry=retry_if_exception_type(FinnhubRequestError),
    )
    def klines(
        self,
        code: str,
        frequency: str,
        start_date: str = None,
        end_date: str = None,
        args=None,
    ) -> Union[pd.DataFrame, None]:
        if args is None:
            args = {}

        resolution_map = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "30m": "30",
            "60m": "60",
            "120m": "120",
            "240m": "240",
            "d": "D",
            "w": "W",
            "m": "M",
        }

        if frequency not in resolution_map:
            raise FinnhubRequestError(f"Unsupported frequency: {frequency}")

        end_dt = self._parse_datetime(end_date) or datetime.datetime.utcnow()
        start_dt = self._parse_datetime(start_date)

        if start_dt is None:
            # default lookback windows tuned for coverage
            if frequency == "1m":
                start_dt = end_dt - datetime.timedelta(days=7)
            elif frequency == "5m":
                start_dt = end_dt - datetime.timedelta(days=14)
            elif frequency in ["15m", "30m", "60m", "120m", "240m"]:
                start_dt = end_dt - datetime.timedelta(days=90)
            elif frequency == "d":
                start_dt = end_dt - datetime.timedelta(days=365 * 5)
            elif frequency == "w":
                start_dt = end_dt - datetime.timedelta(days=365 * 10)
            else:  # monthly
                start_dt = end_dt - datetime.timedelta(days=365 * 15)

        params = {
            "symbol": code.upper(),
            "resolution": resolution_map[frequency],
            "from": int(start_dt.timestamp()),
            "to": int(end_dt.timestamp()),
        }

        data = self._request("stock/candle", params)
        if not isinstance(data, dict) or data.get("s") != "ok":
            return None

        timestamps = data.get("t", [])
        opens = data.get("o", [])
        highs = data.get("h", [])
        lows = data.get("l", [])
        closes = data.get("c", [])
        volumes = data.get("v", [])

        if len(timestamps) == 0:
            return None

        tz = self.tz
        rows = []
        for idx in range(len(timestamps)):
            ts = datetime.datetime.fromtimestamp(timestamps[idx], tz=pytz.utc).astimezone(tz)
            rows.append(
                {
                    "code": code.upper(),
                    "date": ts,
                    "open": opens[idx],
                    "close": closes[idx],
                    "high": highs[idx],
                    "low": lows[idx],
                    "volume": volumes[idx],
                }
            )

        df = pd.DataFrame(rows)
        df.sort_values("date", inplace=True)

        if frequency in ["m", "w", "d"]:
            df["date"] = df["date"].apply(lambda d: d.replace(hour=9, minute=30))

        return df

    def ticks(self, codes: List[str]) -> Dict[str, Tick]:
        ticks: Dict[str, Tick] = {}
        for code in codes:
            try:
                quote = self._request("quote", {"symbol": code.upper()})
            except FinnhubRequestError:
                continue
            if not isinstance(quote, dict):
                continue
            ticks[code] = Tick(
                code=code.upper(),
                last=quote.get("c", 0.0) or 0.0,
                buy1=quote.get("b", 0.0) or quote.get("c", 0.0) or 0.0,
                sell1=quote.get("a", 0.0) or quote.get("c", 0.0) or 0.0,
                high=quote.get("h", 0.0) or 0.0,
                low=quote.get("l", 0.0) or 0.0,
                open=quote.get("o", 0.0) or 0.0,
                volume=quote.get("v", 0.0) or 0.0,
            )
        return ticks

    def stock_info(self, code: str) -> Union[Dict, None]:
        code_upper = code.upper()
        for item in self.all_stocks():
            if item["code"] == code_upper:
                return item
        return None

    def stock_owner_plate(self, code: str):
        return {}

    def plate_stocks(self, code: str):
        return []

    def balance(self):
        raise FinnhubRequestError("Finnhub adapter does not support balance queries")

    def positions(self, code: str = ""):
        raise FinnhubRequestError("Finnhub adapter does not support positions")

    def order(self, code: str, o_type: str, amount: float, args=None):
        raise FinnhubRequestError("Finnhub adapter does not support trading")

    def _request(self, path: str, params: Dict) -> Union[Dict, List, None]:
        url = f"https://finnhub.io/api/v1/{path}"
        query = dict(params or {})
        query["token"] = self.api_key

        response = self.session.get(url, params=query, timeout=10)
        if response.status_code != 200:
            raise FinnhubRequestError(
                f"Finnhub request failed: {response.status_code} {response.text}"
            )

        data = response.json()
        if isinstance(data, dict) and data.get("error"):
            raise FinnhubRequestError(f"Finnhub error: {data.get('error')}")

        return data

    def _parse_datetime(self, dt_str: Union[str, None]) -> Union[datetime.datetime, None]:
        if dt_str is None or dt_str == "":
            return None
        if isinstance(dt_str, datetime.datetime):
            return dt_str
        try:
            if len(dt_str) == 10:
                return datetime.datetime.strptime(dt_str, "%Y-%m-%d")
            return datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    def _is_session_time(self) -> bool:
        now = datetime.datetime.now(self.tz)
        if now.weekday() >= 5:
            return False
        open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
        close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return open_time <= now <= close_time
