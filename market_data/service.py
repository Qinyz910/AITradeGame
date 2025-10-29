from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from .ashare import AShareMarketDataFetcher
from .crypto import CryptoMarketDataFetcher


class MarketDataService:
    """Coordinate market data fetchers across supported markets."""

    def __init__(
        self,
        crypto_fetcher: Optional[CryptoMarketDataFetcher] = None,
        ashare_fetcher: Optional[AShareMarketDataFetcher] = None,
    ) -> None:
        self.crypto_fetcher = crypto_fetcher or CryptoMarketDataFetcher()
        self.ashare_fetcher = ashare_fetcher or AShareMarketDataFetcher()
        self._last_results: Dict[str, Dict[str, Dict]] = {"crypto": {}, "a_share": {}}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_current_prices(self, instruments: List[str], market_type: str = "crypto") -> Dict[str, Dict]:
        market_key = (market_type or "crypto").lower()
        fetcher = self._resolve_fetcher(market_key)
        if fetcher is None:
            return {}

        try:
            quotes = fetcher.get_quotes(instruments)
        except Exception as exc:  # pragma: no cover - defensive fallback
            print(f"[ERROR] Market data fetch failed for {market_key}: {exc}")
            quotes = self._last_results.get(market_key, {})
            if quotes:
                return quotes
            return self._empty_payloads(instruments, market_key)

        self._last_results[market_key] = quotes
        return quotes

    def get_market_data(self, instrument: str, market_type: str = "crypto") -> Dict:
        market_key = (market_type or "crypto").lower()
        if market_key == "crypto":
            return self.crypto_fetcher.get_market_data(instrument)
        return {}

    def get_historical_prices(self, instrument: str, days: int = 7, market_type: str = "crypto") -> List[Dict]:
        market_key = (market_type or "crypto").lower()
        if market_key == "crypto":
            return self.crypto_fetcher.get_historical_prices(instrument, days)
        return []

    def calculate_technical_indicators(self, instrument: str, market_type: str = "crypto") -> Dict:
        market_key = (market_type or "crypto").lower()
        if market_key == "crypto":
            return self.crypto_fetcher.calculate_technical_indicators(instrument)
        return {}

    def get_default_instruments(self, market_type: str = "crypto") -> List[str]:
        market_key = (market_type or "crypto").lower()
        if market_key == "a_share":
            return self.ashare_fetcher.get_default_instruments()
        return self.crypto_fetcher.get_default_instruments()

    def is_trading_day(self, when: Optional[datetime] = None, market_type: str = "crypto") -> bool:
        market_key = (market_type or "crypto").lower()
        if market_key == "a_share":
            return self.ashare_fetcher.is_trading_day(when)
        return True

    def is_trading_session_now(self, when: Optional[datetime] = None, market_type: str = "crypto") -> bool:
        market_key = (market_type or "crypto").lower()
        if market_key == "a_share":
            return self.ashare_fetcher.is_trading_session_now(when)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _resolve_fetcher(self, market_key: str):
        if market_key == "a_share":
            return self.ashare_fetcher
        if market_key == "crypto":
            return self.crypto_fetcher
        return None

    def _empty_payloads(self, instruments: List[str], market_key: str) -> Dict[str, Dict]:
        payloads: Dict[str, Dict] = {}
        for instrument in instruments:
            key = str(instrument).upper()
            if market_key == "a_share":
                code, market, _ = _normalize_symbol_for_service(key)
                board = _infer_board_for_service(code, market)
                exchange = "SSE" if market == "SH" else "SZSE"
                payloads[key] = self.ashare_fetcher._empty_payload(  # type: ignore[attr-defined]
                    raw_symbol=key,
                    code=code,
                    market=market,
                    board=board,
                    exchange=exchange,
                    timestamp=_utc_now_for_service(),
                )
            else:
                payloads[key] = self.crypto_fetcher._empty_payload(key)  # type: ignore[attr-defined]
        return payloads


# Helper functions used for fallback payload construction
from .ashare import _infer_board as _infer_board_for_service  # type: ignore F401
from .ashare import _normalize_symbol as _normalize_symbol_for_service  # type: ignore F401
from .ashare import _utc_now as _utc_now_for_service  # type: ignore F401
