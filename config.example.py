# Configuration Example

# Server
HOST = '0.0.0.0'
PORT = 5000
DEBUG = False

# Database
DATABASE_PATH = 'AITradeGame.db'

# Trading Loop
AUTO_TRADING = True
TRADING_INTERVAL = 180  # seconds between strategy evaluations

# A-share Instruments
A_SHARE_SYMBOLS = [
    '600519.SH',  # Kweichow Moutai
    '600036.SH',  # China Merchants Bank
    '000001.SZ',  # Ping An Bank
    '300750.SZ',  # CATL
]
CASH_CURRENCY = 'CNY'

# Market Data (AkShare)
MARKET_API_CACHE_SECONDS = 8
FUNDAMENTALS_CACHE_SECONDS = 300

# Refresh Rates (frontend)
MARKET_REFRESH = 5000  # ms
PORTFOLIO_REFRESH = 10000  # ms
TRADE_FEE_RATE = 0.001  # 0.1% commission per side
LOT_SIZE = 100  # minimum lot size in A-share trading
ALLOW_PARTIAL_FINAL_LOT = True
