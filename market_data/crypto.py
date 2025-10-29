from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List

import requests


class CryptoMarketDataFetcher:
    """Fetch real-time crypto market data via Binance with CoinGecko fallback."""

    def __init__(self, cache_duration: int = 5) -> None:
        self.binance_base_url = "https://api.binance.com/api/v3"
        self.coingecko_base_url = "https://api.coingecko.com/api/v3"

        self.binance_symbols = {
            "BTC": "BTCUSDT",
            "ETH": "ETHUSDT",
            "SOL": "SOLUSDT",
            "BNB": "BNBUSDT",
            "XRP": "XRPUSDT",
            "DOGE": "DOGEUSDT",
        }

        self.coingecko_mapping = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "BNB": "binancecoin",
            "XRP": "ripple",
            "DOGE": "dogecoin",
        }

        self._cache: Dict[str, Dict[str, Dict]] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_duration = cache_duration

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_quotes(self, instruments: List[str]) -> Dict[str, Dict]:
        """Return up-to-date quotes for the requested crypto instruments."""
        normalized = [instrument.upper() for instrument in instruments]
        cache_key = "crypto_" + "_".join(sorted(normalized))

        if cache_key in self._cache:
            if time.time() - self._cache_time[cache_key] < self._cache_duration:
                return self._cache[cache_key]

        prices: Dict[str, Dict] = {}
        coins = [symbol for symbol in normalized if symbol in self.binance_symbols]
        try:
            prices.update(self._fetch_from_binance(coins))
        except Exception as exc:  # pragma: no cover - network failures
            print(f"[ERROR] Binance API failed: {exc}")
            prices.update(self._get_prices_from_coingecko(coins))

        # Ensure a consistent payload is returned even for unsupported symbols.
        for instrument in normalized:
            if instrument not in prices:
                prices[instrument] = self._empty_payload(instrument)

        self._cache[cache_key] = prices
        self._cache_time[cache_key] = time.time()
        return prices

    def get_market_data(self, coin: str) -> Dict:
        coin_id = self.coingecko_mapping.get(coin.upper(), coin.lower())
        try:
            response = requests.get(
                f"{self.coingecko_base_url}/coins/{coin_id}",
                params={"localization": "false", "tickers": "false", "community_data": "false"},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # pragma: no cover - network failures
            print(f"[ERROR] Failed to get market data for {coin}: {exc}")
            return {}

        market_data = data.get("market_data", {})
        return {
            "current_price": market_data.get("current_price", {}).get("usd", 0),
            "market_cap": market_data.get("market_cap", {}).get("usd", 0),
            "total_volume": market_data.get("total_volume", {}).get("usd", 0),
            "price_change_24h": market_data.get("price_change_percentage_24h", 0),
            "price_change_7d": market_data.get("price_change_percentage_7d", 0),
            "high_24h": market_data.get("high_24h", {}).get("usd", 0),
            "low_24h": market_data.get("low_24h", {}).get("usd", 0),
        }

    def get_historical_prices(self, coin: str, days: int = 7) -> List[Dict]:
        coin_id = self.coingecko_mapping.get(coin.upper(), coin.lower())
        try:
            response = requests.get(
                f"{self.coingecko_base_url}/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": days},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # pragma: no cover - network failures
            print(f"[ERROR] Failed to get historical prices for {coin}: {exc}")
            return []

        prices = []
        for price_data in data.get("prices", []):
            prices.append({"timestamp": price_data[0], "price": price_data[1]})
        return prices

    def calculate_technical_indicators(self, coin: str) -> Dict:
        historical = self.get_historical_prices(coin, days=14)
        if not historical or len(historical) < 14:
            return {}

        prices = [point["price"] for point in historical]
        sma_7 = sum(prices[-7:]) / 7 if len(prices) >= 7 else prices[-1]
        sma_14 = sum(prices[-14:]) / 14 if len(prices) >= 14 else prices[-1]

        changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [change if change > 0 else 0 for change in changes]
        losses = [-change if change < 0 else 0 for change in changes]

        avg_gain = sum(gains[-14:]) / 14 if gains else 0
        avg_loss = sum(losses[-14:]) / 14 if losses else 0

        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        return {
            "sma_7": sma_7,
            "sma_14": sma_14,
            "rsi_14": rsi,
            "current_price": prices[-1],
            "price_change_7d": ((prices[-1] - prices[0]) / prices[0]) * 100 if prices[0] else 0,
        }

    def get_default_instruments(self) -> List[str]:
        return list(self.binance_symbols.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _fetch_from_binance(self, coins: List[str]) -> Dict[str, Dict]:
        if not coins:
            return {}

        symbols = [self.binance_symbols[coin] for coin in coins if coin in self.binance_symbols]
        symbols_param = "[" + ",".join(f'"{symbol}"' for symbol in symbols) + "]"

        response = requests.get(
            f"{self.binance_base_url}/ticker/24hr",
            params={"symbols": symbols_param},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()

        now_iso = _utc_now()
        prices: Dict[str, Dict] = {}
        for item in data:
            symbol = item.get("symbol")
            if not symbol:
                continue
            for coin, binance_symbol in self.binance_symbols.items():
                if binance_symbol != symbol:
                    continue
                payload = {
                    "symbol": coin,
                    "price": float(item.get("lastPrice", 0) or 0),
                    "change_24h": float(item.get("priceChangePercent", 0) or 0),
                    "change_pct": float(item.get("priceChangePercent", 0) or 0),
                    "change_amount": float(item.get("priceChange", 0) or 0),
                    "volume": float(item.get("volume", 0) or 0),
                    "turnover": float(item.get("quoteVolume", 0) or 0),
                    "high": float(item.get("highPrice", 0) or 0),
                    "low": float(item.get("lowPrice", 0) or 0),
                    "open": float(item.get("openPrice", 0) or 0),
                    "prev_close": float(item.get("prevClosePrice", 0) or 0),
                    "market": "CRYPTO",
                    "market_type": "crypto",
                    "board": "Crypto",
                    "suspension": False,
                    "is_st": False,
                    "limit_up_price": None,
                    "limit_down_price": None,
                    "fundamentals": {},
                    "timestamp": now_iso,
                    "source": "binance",
                }
                prices[coin] = payload
                break
        return prices

    def _get_prices_from_coingecko(self, coins: List[str]) -> Dict[str, Dict]:
        if not coins:
            return {}

        coin_ids = [self.coingecko_mapping.get(coin, coin.lower()) for coin in coins]
        try:
            response = requests.get(
                f"{self.coingecko_base_url}/simple/price",
                params={
                    "ids": ",".join(coin_ids),
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # pragma: no cover - network failures
            print(f"[ERROR] CoinGecko fallback failed: {exc}")
            data = {}

        now_iso = _utc_now()
        prices: Dict[str, Dict] = {}
        for coin in coins:
            coin_id = self.coingecko_mapping.get(coin, coin.lower())
            payload = data.get(coin_id)
            if not payload:
                prices[coin] = self._empty_payload(coin)
                continue
            prices[coin] = {
                "symbol": coin,
                "price": float(payload.get("usd", 0) or 0),
                "change_24h": float(payload.get("usd_24h_change", 0) or 0),
                "change_pct": float(payload.get("usd_24h_change", 0) or 0),
                "change_amount": 0.0,
                "volume": 0.0,
                "turnover": 0.0,
                "high": None,
                "low": None,
                "open": None,
                "prev_close": None,
                "market": "CRYPTO",
                "market_type": "crypto",
                "board": "Crypto",
                "suspension": False,
                "is_st": False,
                "limit_up_price": None,
                "limit_down_price": None,
                "fundamentals": {},
                "timestamp": now_iso,
                "source": "coingecko",
            }
        return prices

    def _empty_payload(self, instrument: str) -> Dict:
        now_iso = _utc_now()
        return {
            "symbol": instrument,
            "price": 0.0,
            "change_24h": 0.0,
            "change_pct": 0.0,
            "change_amount": 0.0,
            "volume": 0.0,
            "turnover": 0.0,
            "high": None,
            "low": None,
            "open": None,
            "prev_close": None,
            "market": "CRYPTO",
            "market_type": "crypto",
            "board": "Crypto",
            "suspension": False,
            "is_st": False,
            "limit_up_price": None,
            "limit_down_price": None,
            "fundamentals": {},
            "timestamp": now_iso,
            "source": "cache",
        }


def _utc_now() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
