"""Market data package exposing crypto and A-share fetchers."""

from .crypto import CryptoMarketDataFetcher
from .ashare import AShareMarketDataFetcher
from .service import MarketDataService

# Backwards compatibility alias
MarketDataFetcher = MarketDataService

__all__ = [
    "CryptoMarketDataFetcher",
    "AShareMarketDataFetcher",
    "MarketDataService",
    "MarketDataFetcher",
]
