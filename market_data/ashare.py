from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

try:  # pragma: no cover - optional dependency
    import akshare as ak  # type: ignore
except ImportError:  # pragma: no cover - AkShare not available at runtime
    ak = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import pandas as pd  # type: ignore
except ImportError:  # pragma: no cover - Pandas not available at runtime
    pd = None  # type: ignore


class AShareMarketDataFetcher:
    """AkShare-backed fetcher for mainland A-share market data."""

    def __init__(
        self,
        spot_cache_ttl: int = 8,
        fundamentals_cache_ttl: int = 300,
    ) -> None:
        self._spot_cache_ttl = spot_cache_ttl
        self._fundamentals_cache_ttl = fundamentals_cache_ttl

        self._spot_cache: Optional[Tuple[float, "pd.DataFrame"]] = None
        self._fundamentals_cache: Dict[str, Tuple[float, Dict]] = {}
        self._last_snapshot: Dict[str, Dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """Fetch the latest market quotes for the supplied symbols."""
        normalized: List[Tuple[str, str, str, str]] = []
        for symbol in symbols:
            original = str(symbol).upper().strip()
            code, market, standard_symbol = _normalize_symbol(original)
            normalized.append((original, code, market, standard_symbol))

        df = self._load_spot_dataframe()
        indexed = None
        if df is not None:
            indexed = df.set_index("代码")

        now_iso = _utc_now()
        results: Dict[str, Dict] = {}

        for requested_symbol, code, market, standard_symbol in normalized:
            board = _infer_board(code, market)
            exchange = "SSE" if market == "SH" else "SZSE"
            baseline = self._empty_payload(
                raw_symbol=requested_symbol,
                code=code,
                market=market,
                board=board,
                exchange=exchange,
                timestamp=now_iso,
            )

            quote = None
            if indexed is not None and code in indexed.index:
                row = indexed.loc[code]
                if isinstance(row, pd.DataFrame):  # pragma: no cover - duplicates
                    row = row.iloc[0]
                quote = self._quote_from_row(
                    row=row,
                    symbol=standard_symbol,
                    base_payload=baseline,
                    timestamp=now_iso,
                )

            if quote is None:
                fallback = self._last_snapshot.get(standard_symbol) or self._last_snapshot.get(requested_symbol)
                if fallback:
                    quote = {
                        **fallback,
                        "timestamp": fallback.get("timestamp", now_iso),
                        "stale": True,
                        "source": fallback.get("source", "cache"),
                    }
                else:
                    quote = baseline

            results[requested_symbol] = quote
            self._last_snapshot[standard_symbol] = quote
            self._last_snapshot[requested_symbol] = quote

        return results

    def is_trading_day(self, when: Optional[datetime] = None) -> bool:
        if ak is None:
            return _is_weekday(when)
        calendar = self._load_trading_calendar()
        probe_date = (when or datetime.now(timezone.utc)).date()
        return probe_date in calendar

    def is_trading_session_now(self, when: Optional[datetime] = None) -> bool:
        now_cn = _ensure_cn_time(when)
        if not self.is_trading_day(now_cn):
            return False
        return _is_china_trading_session(now_cn.time())

    def get_default_instruments(self) -> List[str]:
        return [
            "600519.SH",  # Kweichow Moutai
            "600036.SH",  # China Merchants Bank
            "000001.SZ",  # Ping An Bank
            "300750.SZ",  # CATL
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _quote_from_row(self, row, symbol: str, base_payload: Dict, timestamp: str) -> Dict:
        price = _safe_float(row.get("最新价"))
        change_pct = _safe_float(row.get("涨跌幅"))
        change_amount = _safe_float(row.get("涨跌额"))
        volume = _safe_float(row.get("成交量"))
        turnover = _safe_float(row.get("成交额"))
        high = _safe_float(row.get("最高"))
        low = _safe_float(row.get("最低"))
        open_price = _safe_float(row.get("今开"))
        prev_close = _safe_float(row.get("昨收"))
        turnover_rate = _safe_float(row.get("换手率"))
        amplitude = _safe_float(row.get("振幅"))
        pe_dynamic = _safe_float(row.get("市盈率-动态"))
        pe_static = _safe_float(row.get("市盈率-静态"))
        pb = _safe_float(row.get("市净率"))
        market_cap = _safe_float(row.get("总市值"))
        float_market_cap = _safe_float(row.get("流通市值"))
        limit_up = _safe_float(row.get("涨停价")) or None
        limit_down = _safe_float(row.get("跌停价")) or None
        name = (row.get("名称") or "").strip()

        fundamentals = {
            "pe_dynamic": pe_dynamic,
            "pe_static": pe_static,
            "pb": pb,
            "turnover_rate": turnover_rate,
            "amplitude": amplitude,
            "market_cap_billion": _to_billion(market_cap),
            "float_market_cap_billion": _to_billion(float_market_cap),
        }

        external_fundamentals = self._load_fundamentals(symbol)
        fundamentals = {**fundamentals, **external_fundamentals}

        quote = {
            **base_payload,
            "price": price,
            "change_pct": change_pct,
            "change_amount": change_amount,
            "change_24h": change_pct,
            "volume": volume,
            "turnover": turnover,
            "turnover_billion": _to_billion(turnover),
            "high": high,
            "low": low,
            "open": open_price,
            "prev_close": prev_close,
            "limit_up_price": limit_up,
            "limit_down_price": limit_down,
            "fundamentals": fundamentals,
            "timestamp": timestamp,
            "source": "akshare",
            "name": name,
        }

        st_flag = "ST" in name.upper()
        suspension_flag = self._derive_suspension(row, price, volume)
        quote["is_st"] = st_flag
        quote["suspension"] = suspension_flag
        quote["trading_status"] = "suspended" if suspension_flag else "active"

        # Propagate top-level market caps in billions for convenience.
        quote["market_cap_billion"] = fundamentals.get("market_cap_billion")
        quote["float_market_cap_billion"] = fundamentals.get("float_market_cap_billion")

        return quote

    def _load_spot_dataframe(self):
        if ak is None or pd is None:  # pragma: no cover - dependency missing
            return None
        now = time.time()
        cached = self._spot_cache
        if cached and now - cached[0] < self._spot_cache_ttl:
            return cached[1]
        try:
            df = ak.stock_zh_a_spot_em()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - network failures
            print(f"[WARN] Failed to fetch A-share spot data: {exc}")
            return None
        if not isinstance(df, pd.DataFrame) or df.empty:  # pragma: no cover - defensive
            return None
        self._spot_cache = (now, df)
        return df

    def _load_fundamentals(self, symbol: str) -> Dict:
        if ak is None or pd is None:  # pragma: no cover - dependency missing
            return {}
        now = time.time()
        cached = self._fundamentals_cache.get(symbol)
        if cached and now - cached[0] < self._fundamentals_cache_ttl:
            return cached[1]
        code = symbol.split(".")[0]
        fundamentals: Dict[str, float] = {}
        try:
            df = ak.stock_individual_info_em(symbol=code)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - network failures
            print(f"[WARN] Failed to fetch fundamentals for {symbol}: {exc}")
            self._fundamentals_cache[symbol] = (now, fundamentals)
            return fundamentals
        if not isinstance(df, pd.DataFrame) or df.empty:
            self._fundamentals_cache[symbol] = (now, fundamentals)
            return fundamentals
        try:
            info_map = {str(item).strip(): value for item, value in zip(df["item"], df["value"])}
        except Exception:  # pragma: no cover - defensive
            info_map = {}
        fundamentals.update(
            {
                "market_cap_billion": _to_billion(info_map.get("总市值")),
                "float_market_cap_billion": _to_billion(info_map.get("流通市值")),
                "pe_dynamic": _safe_float(info_map.get("市盈率-动态")),
                "pe_static": _safe_float(info_map.get("市盈率-静态")),
                "pb": _safe_float(info_map.get("市净率")),
            }
        )
        self._fundamentals_cache[symbol] = (now, fundamentals)
        return fundamentals

    def _load_trading_calendar(self) -> set:
        cache_entry = getattr(self, "_calendar_cache", None)
        today = datetime.now(timezone.utc).date()
        if cache_entry:
            cached_date, days = cache_entry
            if cached_date == today:
                return days
        days: set = set()
        if ak is not None and pd is not None:
            try:
                df = ak.tool_trade_date_hist_sina()  # type: ignore[attr-defined]
                if isinstance(df, pd.DataFrame) and not df.empty:
                    for value in df.iloc[:, 0]:
                        try:
                            days.add(pd.to_datetime(value).date())
                        except Exception:  # pragma: no cover - defensive
                            continue
            except Exception as exc:  # pragma: no cover - network failures
                print(f"[WARN] Failed to load trading calendar: {exc}")
        if not days:
            days = _generate_weekday_set(today)
        self._calendar_cache = (today, days)
        return days

    def _derive_suspension(self, row, price: float, volume: float) -> bool:
        status_field = (row.get("状态") or "").strip()
        if status_field:
            return status_field != "交易"
        if price == 0 or volume == 0:
            return True
        suspension_flag = row.get("是否停牌")
        if suspension_flag is not None:
            return str(suspension_flag).strip() not in {"否", "0", "False", "false"}
        return False

    def _empty_payload(
        self,
        raw_symbol: str,
        code: str,
        market: str,
        board: str,
        exchange: str,
        timestamp: str,
    ) -> Dict:
        standard_symbol = f"{code}.{market}"
        return {
            "symbol": standard_symbol,
            "requested_symbol": raw_symbol,
            "code": code,
            "market": market,
            "market_type": "a_share",
            "exchange": exchange,
            "board": board,
            "price": 0.0,
            "change_pct": 0.0,
            "change_24h": 0.0,
            "change_amount": 0.0,
            "volume": 0.0,
            "turnover": 0.0,
            "turnover_billion": 0.0,
            "high": None,
            "low": None,
            "open": None,
            "prev_close": None,
            "limit_up_price": None,
            "limit_down_price": None,
            "fundamentals": {},
            "market_cap_billion": None,
            "float_market_cap_billion": None,
            "suspension": False,
            "is_st": False,
            "trading_status": "unknown",
            "timestamp": timestamp,
            "source": "cache",
        }


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def _normalize_symbol(symbol: str) -> Tuple[str, str, str]:
    formatted = symbol.upper().replace("-", "").strip()
    if "." in formatted:
        code, market = formatted.split(".", 1)
        market = market[:2]
        return code, market, f"{code}.{market}"
    if formatted.startswith("SH") or formatted.startswith("SZ"):
        market = formatted[:2]
        code = formatted[2:]
        return code, market, f"{code}.{market}"
    if formatted.startswith(("0", "2", "3")):
        market = "SZ"
    elif formatted.startswith(("6", "9", "5")):
        market = "SH"
    else:
        market = "SH"
    code = formatted
    return code, market, f"{code}.{market}"


def _infer_board(code: str, market: str) -> str:
    if market == "SH":
        if code.startswith("688"):
            return "STAR Market"
        if code.startswith("50") or code.startswith("51") or code.startswith("52"):
            return "ETF"
        if code.startswith(("600", "601", "603", "605")):
            return "Shanghai Main Board"
        if code.startswith("900"):
            return "Shanghai B Board"
        return "Shanghai Others"
    else:
        if code.startswith(("300", "301")):
            return "ChiNext"
        if code.startswith("159") or code.startswith("150") or code.startswith("16"):
            return "ETF"
        if code.startswith(("000", "001")):
            return "Shenzhen Main Board"
        if code.startswith(("002", "003")):
            return "Shenzhen SME Board"
        if code.startswith("200"):
            return "Shenzhen B Board"
        return "Shenzhen Others"


def _safe_float(value) -> float:
    try:
        if value in ("", None):
            return 0.0
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value.endswith("%"):
                value = value[:-1]
        return float(value)
    except Exception:  # pragma: no cover - defensive
        return 0.0


def _utc_now() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_cn_time(when: Optional[datetime]) -> datetime:
    tz = timezone(timedelta(hours=8))
    if when is None:
        return datetime.now(tz)
    if when.tzinfo is None:
        return when.replace(tzinfo=tz)
    return when.astimezone(tz)


def _is_weekday(when: Optional[datetime]) -> bool:
    probe = when or datetime.now(timezone.utc)
    return probe.weekday() < 5


def _generate_weekday_set(anchor: datetime.date) -> set:
    start = anchor - timedelta(days=30)
    end = anchor + timedelta(days=365)
    return {start + timedelta(days=i) for i in range((end - start).days + 1) if (start + timedelta(days=i)).weekday() < 5}


def _is_china_trading_session(current_time) -> bool:
    morning = (datetime.min + timedelta(hours=9, minutes=30)).time()
    morning_close = (datetime.min + timedelta(hours=11, minutes=30)).time()
    afternoon = (datetime.min + timedelta(hours=13)).time()
    afternoon_close = (datetime.min + timedelta(hours=15)).time()
    return (morning <= current_time < morning_close) or (afternoon <= current_time < afternoon_close)


def _to_billion(value) -> Optional[float]:
    numeric = _safe_float(value)
    if numeric == 0:
        return 0.0
    # AkShare spot endpoints typically express market cap in Chinese Yuan 100 millions (亿元).
    # Convert 亿元 to billions: 1 亿 = 0.1 十亿 (billion).
    if abs(numeric) < 1e6:
        return round(numeric / 10, 4)
    return round(numeric / 1e9, 4)
