import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    import akshare as ak  # type: ignore
except ImportError:  # pragma: no cover
    ak = None


@dataclass(frozen=True)
class AShareSymbol:
    symbol: str
    code: str
    market: str
    name: str
    board: str
    is_st: bool


class AShareMarketData:
    """Light-weight wrapper around AkShare helpers for mainland A-share data."""

    def __init__(self, cache_ttl: int = 8):
        self._cache_ttl = cache_ttl
        self._spot_cache: Optional[Tuple[float, "pd.DataFrame"]] = None
        self._symbol_cache: Optional[Tuple[float, List[AShareSymbol]]] = None

    # ------------------------------------------------------------------
    # Public APIs
    # ------------------------------------------------------------------
    def list_symbols(self, board: Optional[str] = None) -> List[Dict]:
        """Return supported instruments with derived board metadata."""
        symbols = self._load_symbols()
        results = []
        board_normalized = board.lower() if board else None

        for item in symbols:
            if board_normalized and item.board.lower() != board_normalized:
                continue
            results.append(
                {
                    "symbol": item.symbol,
                    "code": item.code,
                    "market": item.market,
                    "name": item.name,
                    "board": item.board,
                    "is_st": item.is_st,
                }
            )
        return results

    def get_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """Fetch latest quotes and enrich with board/limit/fundamental metadata."""
        df = self._load_spot_dataframe()
        if df is None:
            # Graceful fallback when AkShare is unavailable.
            return {
                symbol: {
                    "symbol": symbol,
                    "price": 0.0,
                    "change_pct": 0.0,
                    "change_amount": 0.0,
                    "board": self._infer_board(symbol)[0],
                    "market": self._infer_board(symbol)[1],
                    "is_st": False,
                    "limit_up_price": None,
                    "limit_down_price": None,
                    "suspension": False,
                    "fundamentals": {},
                }
                for symbol in symbols
            }

        indexed = df.set_index("代码")
        quotes: Dict[str, Dict] = {}

        for raw_symbol in symbols:
            code, market = self._normalize_symbol(raw_symbol)
            board, exchange = self._infer_board(raw_symbol)
            payload = {
                "symbol": f"{code}.{market}",
                "code": code,
                "market": market,
                "board": board,
                "exchange": exchange,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "price": 0.0,
                "change_pct": 0.0,
                "change_amount": 0.0,
                "volume": 0.0,
                "amount": 0.0,
                "is_st": False,
                "suspension": False,
                "limit_up_price": None,
                "limit_down_price": None,
                "fundamentals": {},
            }

            if code in indexed.index:
                row = indexed.loc[code]
                try:
                    price = float(row.get("最新价", 0) or 0)
                except Exception:  # pragma: no cover - robust parsing
                    price = 0.0
                payload.update(
                    {
                        "price": price,
                        "change_pct": _safe_float(row.get("涨跌幅")),
                        "change_amount": _safe_float(row.get("涨跌额")),
                        "volume": _safe_float(row.get("成交量")),
                        "amount": _safe_float(row.get("成交额")),
                        "high": _safe_float(row.get("最高")),
                        "low": _safe_float(row.get("最低")),
                        "open": _safe_float(row.get("今开")),
                        "prev_close": _safe_float(row.get("昨收")),
                        "turnover_rate": _safe_float(row.get("换手率")),
                        "amplitude": _safe_float(row.get("振幅")),
                        "pe": _safe_float(row.get("市盈率-动态")),
                        "pe_static": _safe_float(row.get("市盈率-静态")),
                        "pb": _safe_float(row.get("市净率")),
                        "market_cap": _safe_float(row.get("总市值")),
                        "float_market_cap": _safe_float(row.get("流通市值")),
                    }
                )

                name = str(row.get("名称", ""))
                payload["name"] = name
                payload["is_st"] = "ST" in name.upper()

                # Estimate suspension: volume equals 0 or price equals 0
                payload["suspension"] = bool(price == 0 or payload["volume"] == 0)

                limit_ratio = 0.05 if payload["is_st"] else 0.10
                if price:
                    payload["limit_up_price"] = round(price * (1 + limit_ratio), 4)
                    payload["limit_down_price"] = round(price * (1 - limit_ratio), 4)

                payload["fundamentals"] = {
                    "pe_dynamic": payload.pop("pe"),
                    "pe_static": payload.pop("pe_static"),
                    "pb": payload.get("pb"),
                    "turnover_rate": payload.get("turnover_rate"),
                    "amplitude": payload.get("amplitude"),
                    "market_cap": payload.get("market_cap"),
                    "float_market_cap": payload.get("float_market_cap"),
                }
            quotes[raw_symbol] = payload

        return quotes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_spot_dataframe(self):
        if ak is None:
            return None
        import pandas as pd  # type: ignore

        cached = self._spot_cache
        now = time.time()
        if cached and now - cached[0] < self._cache_ttl:
            return cached[1]

        try:
            df = ak.stock_zh_a_spot_em()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - network failures
            print(f"[WARN] Failed to fetch A-share spot data via AkShare: {exc}")
            return None

        if not isinstance(df, pd.DataFrame):  # pragma: no cover - defensive
            return None

        self._spot_cache = (now, df)
        return df

    def _load_symbols(self) -> List[AShareSymbol]:
        cached = self._symbol_cache
        now = time.time()
        if cached and now - cached[0] < self._cache_ttl:
            return cached[1]

        df = self._load_spot_dataframe()
        records: List[AShareSymbol] = []
        if df is None:
            # Provide minimal fallback universe
            defaults = [
                ("600519", "SH", "Kweichow Moutai"),
                ("600036", "SH", "China Merchants Bank"),
                ("000001", "SZ", "Ping An Bank"),
                ("300750", "SZ", "CATL"),
            ]
            for code, market, name in defaults:
                board, _ = self._infer_board(f"{code}.{market}")
                records.append(
                    AShareSymbol(
                        symbol=f"{code}.{market}",
                        code=code,
                        market=market,
                        name=name,
                        board=board,
                        is_st=False,
                    )
                )
            self._symbol_cache = (now, records)
            return records

        for _, row in df.iterrows():
            code = str(row.get("代码", "")).strip()
            if not code:
                continue
            name = str(row.get("名称", "")).strip()
            board, market = self._infer_board(code)
            symbol = f"{code}.{market}"
            records.append(
                AShareSymbol(
                    symbol=symbol,
                    code=code,
                    market=market,
                    name=name,
                    board=board,
                    is_st="ST" in name.upper(),
                )
            )

        self._symbol_cache = (now, records)
        return records

    def _normalize_symbol(self, symbol: str) -> Tuple[str, str]:
        formatted = symbol.upper().replace("-", "")
        if "." in formatted:
            code, market = formatted.split(".", 1)
            market = market[:2]
            return code, market
        if formatted.startswith("SH") or formatted.startswith("SZ"):
            return formatted[2:], formatted[:2]
        # Default inference by prefix
        market = "SH" if formatted.startswith(("6", "9")) else "SZ"
        return formatted, market

    def _infer_board(self, symbol: str) -> Tuple[str, str]:
        code, market = self._normalize_symbol(symbol)
        if market == "SH":
            if code.startswith("688"):
                return "STAR Market", market
            if code.startswith("605") or code.startswith("603") or code.startswith("601") or code.startswith("600"):
                return "Shanghai Main Board", market
            if code.startswith("900"):
                return "Shanghai B Board", market
            return "Shanghai", market
        else:
            if code.startswith("300") or code.startswith("301"):
                return "ChiNext", market
            if code.startswith("002") or code.startswith("003"):
                return "Shenzhen SME Board", market
            if code.startswith("200"):
                return "Shenzhen B Board", market
            if code.startswith("000") or code.startswith("001"):
                return "Shenzhen Main Board", market
            return "Shenzhen", market


def _safe_float(value) -> float:
    try:
        return float(value)
    except Exception:  # pragma: no cover - robust parsing
        return 0.0
