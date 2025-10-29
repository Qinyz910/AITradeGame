"""
Database management module
"""
import sqlite3
import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

class Database:
    def __init__(self, db_path: str = 'AITradeGame.db'):
        self.db_path = db_path
        
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    @staticmethod
    def _safe_loads(value, fallback=None):
        """Safely deserialize JSON values."""
        if value is None:
            return fallback
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, (bytes, bytearray)):
            try:
                value = value.decode('utf-8')
            except Exception:
                value = value.decode('utf-8', errors='ignore')
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return fallback
    
    @staticmethod
    def _serialize_optional_json(value):
        """Serialize complex structures to JSON while preserving plain strings."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return json.dumps(str(value))
    
    @staticmethod
    def _to_bool(value):
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        try:
            return bool(int(value))
        except (TypeError, ValueError):
            return bool(value)
    
    @staticmethod
    def _to_int(value):
        if value is None or value == '':
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None
    
    @staticmethod
    def _to_float(value):
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    
    def _get_model_market_type(self, cursor: sqlite3.Cursor, model_id: int) -> str:
        cursor.execute('SELECT market_type FROM models WHERE id = ?', (model_id,))
        row = cursor.fetchone()
        if not row:
            return 'crypto'
        market_type = row['market_type']
        if not market_type:
            return 'crypto'
        return str(market_type).lower()
    
    def _prepare_instrument_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        prepared = dict(row)
        prepared['fundamentals'] = self._safe_loads(prepared.get('fundamentals'), {})
        prepared['metadata'] = self._safe_loads(prepared.get('metadata'), {})
        status_raw = prepared.get('status_flags')
        status_parsed = self._safe_loads(status_raw, None)
        if status_parsed is None and status_raw not in (None, '', b''):
            if isinstance(status_raw, (bytes, bytearray)):
                prepared['status_flags'] = status_raw.decode('utf-8', errors='ignore')
            else:
                prepared['status_flags'] = status_raw
        else:
            prepared['status_flags'] = status_parsed
        for bool_field in ('is_st', 'suspension'):
            if bool_field in prepared and prepared[bool_field] is not None:
                prepared[bool_field] = bool(prepared[bool_field])
        for int_field in ('lot_size',):
            if int_field in prepared and prepared[int_field] is not None:
                prepared[int_field] = self._to_int(prepared[int_field])
        for float_field in ('limit_up_price', 'limit_down_price', 'market_cap', 'pe', 'pb'):
            if float_field in prepared and prepared[float_field] is not None:
                prepared[float_field] = self._to_float(prepared[float_field])
        return prepared
    
    def _fetch_instrument_metadata_bulk(
        self,
        cursor: sqlite3.Cursor,
        instrument_pairs: Iterable[Tuple[str, str]]
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        results: Dict[Tuple[str, str], Dict[str, Any]] = {}
        seen = set()
        for code, market in instrument_pairs:
            if not code:
                continue
            normalized_market = (market or 'crypto').lower()
            key = (code, normalized_market)
            if key in seen:
                continue
            seen.add(key)
            cursor.execute(
                '''
                SELECT *
                FROM instruments
                WHERE instrument_code = ? AND market_type = ?
                ''',
                (code, normalized_market)
            )
            row = cursor.fetchone()
            if row:
                results[key] = self._prepare_instrument_row(dict(row))
        return results
    
    def init_db(self):
        """Initialize database tables with schema migrations."""
        conn = self.get_connection()
        cursor = conn.cursor()

        def table_exists(name: str) -> bool:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (name,)
            )
            return cursor.fetchone() is not None

        def table_columns(name: str) -> set:
            cursor.execute(f'PRAGMA table_info({name})')
            return {row[1] for row in cursor.fetchall()}

        def add_column_if_missing(table: str, column: str, ddl: str):
            if not table_exists(table):
                return
            columns = table_columns(table)
            if column not in columns:
                try:
                    cursor.execute(ddl)
                except sqlite3.OperationalError:
                    pass

        def ensure_providers_table():
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS providers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    api_url TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    models TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

        def ensure_models_table():
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    provider_id INTEGER,
                    model_name TEXT NOT NULL,
                    initial_capital REAL DEFAULT 10000,
                    market_type TEXT DEFAULT 'crypto',
                    instruments TEXT,
                    cash_currency TEXT DEFAULT 'USD',
                    market_config TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (provider_id) REFERENCES providers(id)
                )
            ''')
            add_column_if_missing('models', 'market_type', 'ALTER TABLE models ADD COLUMN market_type TEXT DEFAULT "crypto"')
            add_column_if_missing('models', 'instruments', 'ALTER TABLE models ADD COLUMN instruments TEXT')
            add_column_if_missing('models', 'cash_currency', 'ALTER TABLE models ADD COLUMN cash_currency TEXT DEFAULT "USD"')
            add_column_if_missing('models', 'market_config', 'ALTER TABLE models ADD COLUMN market_config TEXT')

        def ensure_portfolios_table():
            create_sql = '''
                CREATE TABLE IF NOT EXISTS portfolios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER NOT NULL,
                    coin TEXT NOT NULL,
                    instrument_code TEXT NOT NULL,
                    market_type TEXT NOT NULL DEFAULT 'crypto',
                    quantity REAL NOT NULL,
                    avg_price REAL NOT NULL,
                    leverage INTEGER DEFAULT 1,
                    side TEXT DEFAULT 'long',
                    board TEXT,
                    status_flags TEXT,
                    trading_status TEXT,
                    lot_size INTEGER,
                    suspension INTEGER DEFAULT 0,
                    metadata TEXT,
                    last_buy_date TEXT,
                    next_sellable_date TEXT,
                    last_settlement_date TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (model_id) REFERENCES models(id)
                )
            '''
            if not table_exists('portfolios'):
                cursor.execute(create_sql)
                cursor.execute('''
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolios_model_instrument_market_side
                    ON portfolios (model_id, instrument_code, market_type, side)
                ''')
                return

            legacy_columns = table_columns('portfolios')
            if 'instrument_code' not in legacy_columns or 'market_type' not in legacy_columns:
                cursor.execute('ALTER TABLE portfolios RENAME TO portfolios__legacy')
                cursor.execute(create_sql)
                metadata_expr = 'p.metadata' if 'metadata' in legacy_columns else 'NULL'
                last_buy_expr = 'p.last_buy_date' if 'last_buy_date' in legacy_columns else 'NULL'
                next_sell_expr = 'p.next_sellable_date' if 'next_sellable_date' in legacy_columns else 'NULL'
                updated_expr = 'p.updated_at' if 'updated_at' in legacy_columns else 'CURRENT_TIMESTAMP'
                cursor.execute(f'''
                    INSERT INTO portfolios (
                        id, model_id, coin, instrument_code, market_type, quantity, avg_price,
                        leverage, side, board, status_flags, trading_status, lot_size, suspension,
                        metadata, last_buy_date, next_sellable_date, last_settlement_date, updated_at
                    )
                    SELECT
                        p.id,
                        p.model_id,
                        p.coin,
                        COALESCE(p.coin, ''),
                        LOWER(COALESCE(m.market_type, 'crypto')),
                        p.quantity,
                        p.avg_price,
                        p.leverage,
                        p.side,
                        NULL,
                        NULL,
                        NULL,
                        NULL,
                        0,
                        {metadata_expr},
                        {last_buy_expr},
                        {next_sell_expr},
                        NULL,
                        {updated_expr}
                    FROM portfolios__legacy p
                    LEFT JOIN models m ON m.id = p.model_id
                ''')
                cursor.execute('DROP TABLE portfolios__legacy')
                legacy_columns = table_columns('portfolios')

            column_defs = [
                ('board', 'ALTER TABLE portfolios ADD COLUMN board TEXT'),
                ('status_flags', 'ALTER TABLE portfolios ADD COLUMN status_flags TEXT'),
                ('trading_status', 'ALTER TABLE portfolios ADD COLUMN trading_status TEXT'),
                ('lot_size', 'ALTER TABLE portfolios ADD COLUMN lot_size INTEGER'),
                ('suspension', 'ALTER TABLE portfolios ADD COLUMN suspension INTEGER DEFAULT 0'),
                ('metadata', 'ALTER TABLE portfolios ADD COLUMN metadata TEXT'),
                ('last_buy_date', 'ALTER TABLE portfolios ADD COLUMN last_buy_date TEXT'),
                ('next_sellable_date', 'ALTER TABLE portfolios ADD COLUMN next_sellable_date TEXT'),
                ('last_settlement_date', 'ALTER TABLE portfolios ADD COLUMN last_settlement_date TEXT'),
                ('updated_at', 'ALTER TABLE portfolios ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            ]
            for column, ddl in column_defs:
                if column not in legacy_columns:
                    try:
                        cursor.execute(ddl)
                    except sqlite3.OperationalError:
                        pass
                    legacy_columns.add(column)

            cursor.execute('''
                UPDATE portfolios
                SET instrument_code = coin
                WHERE instrument_code IS NULL OR instrument_code = ''
            ''')
            cursor.execute('''
                UPDATE portfolios
                SET market_type = COALESCE(
                    (SELECT LOWER(COALESCE(m.market_type, 'crypto')) FROM models m WHERE m.id = portfolios.model_id),
                    'crypto'
                )
                WHERE market_type IS NULL OR market_type = ''
            ''')
            cursor.execute('''
                UPDATE portfolios
                SET suspension = 0
                WHERE suspension IS NULL
            ''')
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolios_model_instrument_market_side
                ON portfolios (model_id, instrument_code, market_type, side)
            ''')

        def ensure_trades_table():
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER NOT NULL,
                    coin TEXT NOT NULL,
                    instrument_code TEXT,
                    market_type TEXT DEFAULT 'crypto',
                    signal TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    trade_date TEXT,
                    leverage INTEGER DEFAULT 1,
                    side TEXT DEFAULT 'long',
                    board TEXT,
                    pnl REAL DEFAULT 0,
                    fee REAL DEFAULT 0,
                    fee_details TEXT,
                    metadata TEXT,
                    cash_balance REAL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (model_id) REFERENCES models(id)
                )
            ''')
            add_column_if_missing('trades', 'market_type', 'ALTER TABLE trades ADD COLUMN market_type TEXT')
            add_column_if_missing('trades', 'instrument_code', 'ALTER TABLE trades ADD COLUMN instrument_code TEXT')
            add_column_if_missing('trades', 'trade_date', 'ALTER TABLE trades ADD COLUMN trade_date TEXT')
            add_column_if_missing('trades', 'board', 'ALTER TABLE trades ADD COLUMN board TEXT')
            add_column_if_missing('trades', 'fee_details', 'ALTER TABLE trades ADD COLUMN fee_details TEXT')
            add_column_if_missing('trades', 'metadata', 'ALTER TABLE trades ADD COLUMN metadata TEXT')
            add_column_if_missing('trades', 'cash_balance', 'ALTER TABLE trades ADD COLUMN cash_balance REAL')
            cursor.execute('''
                UPDATE trades
                SET instrument_code = coin
                WHERE instrument_code IS NULL OR instrument_code = ''
            ''')
            cursor.execute('''
                UPDATE trades
                SET market_type = COALESCE(
                    (SELECT LOWER(COALESCE(m.market_type, 'crypto')) FROM models m WHERE m.id = trades.model_id),
                    'crypto'
                )
                WHERE market_type IS NULL OR market_type = ''
            ''')
            cursor.execute('''
                UPDATE trades
                SET trade_date = COALESCE(trade_date, DATE(timestamp))
            ''')

        def ensure_instruments_table():
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS instruments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    instrument_code TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    name TEXT,
                    board TEXT,
                    status_flags TEXT,
                    trading_status TEXT,
                    is_st INTEGER DEFAULT 0,
                    suspension INTEGER DEFAULT 0,
                    limit_up_price REAL,
                    limit_down_price REAL,
                    lot_size INTEGER,
                    market_cap REAL,
                    pe REAL,
                    pb REAL,
                    fundamentals TEXT,
                    metadata TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(instrument_code, market_type)
                )
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_instruments_market
                ON instruments (market_type)
            ''')

        def ensure_conversations_table():
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER NOT NULL,
                    user_prompt TEXT NOT NULL,
                    ai_response TEXT NOT NULL,
                    cot_trace TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (model_id) REFERENCES models(id)
                )
            ''')

        def ensure_account_values_table():
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS account_values (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER NOT NULL,
                    total_value REAL NOT NULL,
                    cash REAL NOT NULL,
                    positions_value REAL NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (model_id) REFERENCES models(id)
                )
            ''')

        def ensure_settings_table():
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trading_frequency_minutes INTEGER DEFAULT 60,
                    trading_fee_rate REAL DEFAULT 0.001,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('SELECT COUNT(*) FROM settings')
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO settings (trading_frequency_minutes, trading_fee_rate)
                    VALUES (60, 0.001)
                ''')

        ensure_providers_table()
        ensure_models_table()
        ensure_portfolios_table()
        ensure_trades_table()
        ensure_instruments_table()
        ensure_conversations_table()
        ensure_account_values_table()
        ensure_settings_table()

        conn.commit()
        conn.close()
    
    # ============ Model Management (Moved) ============
    
    def delete_model(self, model_id: int):
        """Delete model and related data"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM models WHERE id = ?', (model_id,))
        cursor.execute('DELETE FROM portfolios WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM trades WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM conversations WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM account_values WHERE model_id = ?', (model_id,))
        conn.commit()
        conn.close()
    
    # ============ Portfolio Management ============
    
    def update_position(
        self,
        model_id: int,
        coin: str,
        quantity: float,
        avg_price: float,
        leverage: int = 1,
        side: str = 'long',
        metadata: Optional[Dict] = None,
        last_buy_date: Optional[str] = None,
        next_sellable_date: Optional[str] = None,
        instrument_code: Optional[str] = None,
        market_type: Optional[str] = None,
        board: Optional[str] = None,
        status_flags: Optional[Any] = None,
        lot_size: Optional[int] = None,
        suspension: Optional[bool] = None,
        trading_status: Optional[str] = None,
        last_settlement_date: Optional[str] = None
    ):
        """Update or create a position with instrument metadata."""
        conn = self.get_connection()
        cursor = conn.cursor()
        determined_market = (market_type or self._get_model_market_type(cursor, model_id)).lower()
        instrument_code_value = instrument_code or coin
        metadata_json = json.dumps(metadata) if metadata is not None else None
        status_flags_value = self._serialize_optional_json(status_flags)
        lot_size_value = self._to_int(lot_size)
        suspension_value = None if suspension is None else int(bool(suspension))
        cursor.execute('''
            INSERT INTO portfolios (
                model_id,
                coin,
                instrument_code,
                market_type,
                quantity,
                avg_price,
                leverage,
                side,
                board,
                status_flags,
                trading_status,
                lot_size,
                suspension,
                metadata,
                last_buy_date,
                next_sellable_date,
                last_settlement_date,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(model_id, instrument_code, market_type, side) DO UPDATE SET
                quantity = excluded.quantity,
                avg_price = excluded.avg_price,
                leverage = excluded.leverage,
                board = COALESCE(excluded.board, board),
                status_flags = CASE WHEN excluded.status_flags IS NOT NULL THEN excluded.status_flags ELSE status_flags END,
                trading_status = CASE WHEN excluded.trading_status IS NOT NULL THEN excluded.trading_status ELSE trading_status END,
                lot_size = CASE WHEN excluded.lot_size IS NOT NULL THEN excluded.lot_size ELSE lot_size END,
                suspension = CASE WHEN excluded.suspension IS NOT NULL THEN excluded.suspension ELSE suspension END,
                metadata = CASE WHEN excluded.metadata IS NOT NULL THEN excluded.metadata ELSE metadata END,
                last_buy_date = CASE WHEN excluded.last_buy_date IS NOT NULL THEN excluded.last_buy_date ELSE last_buy_date END,
                next_sellable_date = CASE WHEN excluded.next_sellable_date IS NOT NULL THEN excluded.next_sellable_date ELSE next_sellable_date END,
                last_settlement_date = CASE WHEN excluded.last_settlement_date IS NOT NULL THEN excluded.last_settlement_date ELSE last_settlement_date END,
                updated_at = CURRENT_TIMESTAMP
        ''', (
            model_id,
            coin,
            instrument_code_value,
            determined_market,
            quantity,
            avg_price,
            leverage,
            side,
            board,
            status_flags_value,
            trading_status,
            lot_size_value,
            suspension_value,
            metadata_json,
            last_buy_date,
            next_sellable_date,
            last_settlement_date
        ))
        conn.commit()
        conn.close()
    
    def get_portfolio(self, model_id: int, current_prices: Dict = None) -> Dict:
        """Get portfolio with positions, valuations, and instrument metadata."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT initial_capital, market_type FROM models WHERE id = ?', (model_id,))
        model_row = cursor.fetchone()
        initial_capital = model_row['initial_capital'] if model_row else 0
        model_market = (model_row['market_type'] if model_row and model_row['market_type'] else 'crypto').lower()

        cursor.execute('''
            SELECT * FROM portfolios WHERE model_id = ? AND quantity > 0
        ''', (model_id,))
        raw_positions = cursor.fetchall()
        positions: List[Dict] = []
        instrument_pairs: List[Tuple[str, str]] = []

        for row in raw_positions:
            pos = dict(row)
            pos['instrument_code'] = pos.get('instrument_code') or pos['coin']
            pos['market_type'] = (pos.get('market_type') or model_market).lower()
            pos['metadata'] = self._safe_loads(pos.get('metadata'), {}) or {}
            status_raw = pos.get('status_flags')
            status_parsed = self._safe_loads(status_raw, None)
            if status_parsed is None and status_raw not in (None, '', b''):
                if isinstance(status_raw, (bytes, bytearray)):
                    pos['status_flags'] = status_raw.decode('utf-8', errors='ignore')
                else:
                    pos['status_flags'] = status_raw
            else:
                pos['status_flags'] = status_parsed
            if isinstance(pos['status_flags'], str):
                pos['status_flags'] = [pos['status_flags']]
            elif pos['status_flags'] is None:
                pos['status_flags'] = []
            trading_status_raw = pos.get('trading_status')
            if isinstance(trading_status_raw, (bytes, bytearray)):
                pos['trading_status'] = trading_status_raw.decode('utf-8', errors='ignore')
            pos['lot_size'] = self._to_int(pos.get('lot_size'))
            suspension_raw = pos.get('suspension')
            if suspension_raw is not None:
                converted = self._to_int(suspension_raw)
                if converted is None:
                    pos['suspension'] = bool(suspension_raw)
                else:
                    pos['suspension'] = bool(converted)
            else:
                pos['suspension'] = None
            positions.append(pos)
            instrument_pairs.append((pos['instrument_code'], pos['market_type']))

        instrument_map = self._fetch_instrument_metadata_bulk(cursor, instrument_pairs)
        for pos in positions:
            key = (pos['instrument_code'], pos['market_type'])
            instrument_info = instrument_map.get(key)
            if instrument_info:
                pos['instrument_metadata'] = instrument_info
                if not pos.get('board') and instrument_info.get('board'):
                    pos['board'] = instrument_info.get('board')
                if pos.get('status_flags') in (None, '') and instrument_info.get('status_flags') is not None:
                    pos['status_flags'] = instrument_info.get('status_flags')
                if not pos.get('trading_status') and instrument_info.get('trading_status'):
                    pos['trading_status'] = instrument_info.get('trading_status')
                if pos.get('lot_size') is None and instrument_info.get('lot_size') is not None:
                    pos['lot_size'] = self._to_int(instrument_info.get('lot_size'))
                if pos.get('suspension') is None and instrument_info.get('suspension') is not None:
                    pos['suspension'] = bool(instrument_info.get('suspension'))
                if instrument_info.get('fundamentals'):
                    pos['fundamentals'] = instrument_info.get('fundamentals')
            else:
                pos['instrument_metadata'] = None

        cursor.execute('''
            SELECT COALESCE(SUM(pnl), 0) as total_pnl
            FROM trades
            WHERE model_id = ?
        ''', (model_id,))
        realized_row = cursor.fetchone()
        realized_pnl_raw = realized_row['total_pnl'] if realized_row else 0

        cursor.execute('''
            SELECT 
                COALESCE(SUM(CASE WHEN signal IN ('buy_to_enter', 'sell_to_enter') THEN fee ELSE 0 END), 0) AS entry_fees,
                COALESCE(SUM(fee), 0) AS total_fees
            FROM trades
            WHERE model_id = ?
        ''', (model_id,))
        fees_row = cursor.fetchone()
        entry_fees_trades = fees_row['entry_fees'] if fees_row else 0
        total_fees = fees_row['total_fees'] if fees_row else 0

        cursor.execute('''
            SELECT metadata FROM trades
            WHERE model_id = ? AND signal = 'close_position' AND metadata IS NOT NULL
        ''', (model_id,))
        close_rows = cursor.fetchall()
        allocated_entry_fees = 0.0
        for row in close_rows:
            metadata_raw = row['metadata']
            if metadata_raw:
                try:
                    metadata_obj = json.loads(metadata_raw)
                    allocated_entry_fees += float(metadata_obj.get('allocated_entry_fee', 0) or 0)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue

        entry_fees_open_metadata = sum(float((pos.get('metadata') or {}).get('entry_fee_total', 0) or 0) for pos in positions)
        entry_fees_open = max(entry_fees_trades - allocated_entry_fees, entry_fees_open_metadata, 0)
        realized_pnl = realized_pnl_raw - entry_fees_open

        margin_used = 0.0
        for pos in positions:
            leverage = pos.get('leverage') or 1
            if leverage == 0:
                leverage = 1
            margin_used += (pos['quantity'] * pos['avg_price']) / leverage

        unrealized_pnl = 0.0
        positions_value = 0.0
        if current_prices:
            for pos in positions:
                price_key = pos['coin']
                entry_price = pos['avg_price']
                quantity = pos['quantity']
                side = pos.get('side', 'long')
                current_price = current_prices.get(price_key)
                if current_price is None:
                    pos['current_price'] = None
                    pos['pnl'] = 0
                    positions_value += quantity * entry_price
                    continue
                pos['current_price'] = current_price
                if side == 'long':
                    market_value = quantity * current_price
                    pos_pnl = (current_price - entry_price) * quantity
                else:
                    market_value = quantity * entry_price
                    pos_pnl = (entry_price - current_price) * quantity
                pos['market_value'] = market_value
                pos['pnl'] = pos_pnl
                positions_value += market_value
                unrealized_pnl += pos_pnl
        else:
            for pos in positions:
                pos['current_price'] = None
                pos['pnl'] = 0
                positions_value += pos['quantity'] * pos['avg_price']

        cash = initial_capital + realized_pnl - margin_used
        total_value = initial_capital + realized_pnl + unrealized_pnl

        conn.close()

        return {
            'model_id': model_id,
            'market_type': model_market,
            'cash': cash,
            'positions': positions,
            'positions_value': positions_value,
            'margin_used': margin_used,
            'total_value': total_value,
            'realized_pnl': realized_pnl,
            'realized_pnl_before_entry_fees': realized_pnl_raw,
            'entry_fees': entry_fees_open,
            'fees_paid': total_fees,
            'unrealized_pnl': unrealized_pnl,
            'initial_capital': initial_capital
        }
    
    def get_position(
        self,
        model_id: int,
        coin: str,
        side: str = 'long',
        instrument_code: Optional[str] = None,
        market_type: Optional[str] = None
    ) -> Optional[Dict]:
        """Fetch a single position with instrument metadata."""
        conn = self.get_connection()
        cursor = conn.cursor()

        if instrument_code:
            query = 'SELECT * FROM portfolios WHERE model_id = ? AND instrument_code = ? AND side = ?'
            params = [model_id, instrument_code, side]
            if market_type:
                query += ' AND market_type = ?'
                params.append(market_type.lower())
            query += ' LIMIT 1'
            cursor.execute(query, params)
        else:
            cursor.execute('''
                SELECT * FROM portfolios
                WHERE model_id = ? AND coin = ? AND side = ?
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (model_id, coin, side))

        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        position = dict(row)
        position['instrument_code'] = position.get('instrument_code') or position['coin']
        effective_market = (position.get('market_type') or market_type or self._get_model_market_type(cursor, model_id)).lower()
        position['market_type'] = effective_market
        position['metadata'] = self._safe_loads(position.get('metadata'), {}) or {}
        status_raw = position.get('status_flags')
        status_parsed = self._safe_loads(status_raw, None)
        if status_parsed is None and status_raw not in (None, '', b''):
            if isinstance(status_raw, (bytes, bytearray)):
                position['status_flags'] = status_raw.decode('utf-8', errors='ignore')
            else:
                position['status_flags'] = status_raw
        else:
            position['status_flags'] = status_parsed
        trading_status_raw = position.get('trading_status')
        if isinstance(trading_status_raw, (bytes, bytearray)):
            position['trading_status'] = trading_status_raw.decode('utf-8', errors='ignore')
        position['lot_size'] = self._to_int(position.get('lot_size'))
        suspension_raw = position.get('suspension')
        if suspension_raw is not None:
            converted = self._to_int(suspension_raw)
            if converted is None:
                position['suspension'] = bool(suspension_raw)
            else:
                position['suspension'] = bool(converted)
        else:
            position['suspension'] = None

        instrument_map = self._fetch_instrument_metadata_bulk(
            cursor,
            [(position['instrument_code'], position['market_type'])]
        )
        instrument_info = instrument_map.get((position['instrument_code'], position['market_type']))
        if instrument_info:
            position['instrument_metadata'] = instrument_info
            if not position.get('board') and instrument_info.get('board'):
                position['board'] = instrument_info.get('board')
            if position.get('status_flags') in (None, '') and instrument_info.get('status_flags') is not None:
                position['status_flags'] = instrument_info.get('status_flags')
            if not position.get('trading_status') and instrument_info.get('trading_status'):
                position['trading_status'] = instrument_info.get('trading_status')
            if position.get('lot_size') is None and instrument_info.get('lot_size') is not None:
                position['lot_size'] = self._to_int(instrument_info.get('lot_size'))
            if position.get('suspension') is None and instrument_info.get('suspension') is not None:
                position['suspension'] = bool(instrument_info.get('suspension'))
            if instrument_info.get('fundamentals'):
                position['fundamentals'] = instrument_info.get('fundamentals')
        else:
            position['instrument_metadata'] = None

        conn.close()
        return position
    
    def close_position(
        self,
        model_id: int,
        coin: str,
        side: str = 'long',
        instrument_code: Optional[str] = None,
        market_type: Optional[str] = None
    ):
        """Close position by coin/instrument."""
        conn = self.get_connection()
        cursor = conn.cursor()
        effective_market = (market_type or self._get_model_market_type(cursor, model_id)).lower()

        if instrument_code:
            cursor.execute(
                '''
                DELETE FROM portfolios
                WHERE model_id = ? AND instrument_code = ? AND side = ? AND market_type = ?
                ''',
                (model_id, instrument_code, side, effective_market)
            )
            if cursor.rowcount == 0 and market_type is None:
                cursor.execute(
                    '''
                    DELETE FROM portfolios
                    WHERE model_id = ? AND instrument_code = ? AND side = ?
                    ''',
                    (model_id, instrument_code, side)
                )
        else:
            cursor.execute(
                '''
                DELETE FROM portfolios
                WHERE model_id = ? AND coin = ? AND side = ? AND market_type = ?
                ''',
                (model_id, coin, side, effective_market)
            )
            if cursor.rowcount == 0 and market_type is None:
                cursor.execute(
                    '''
                    DELETE FROM portfolios
                    WHERE model_id = ? AND coin = ? AND side = ?
                    ''',
                    (model_id, coin, side)
                )

        conn.commit()
        conn.close()
    
    # ============ Trade Records ============
    
    def add_trade(
        self,
        model_id: int,
        coin: str,
        signal: str,
        quantity: float,
        price: float,
        leverage: int = 1,
        side: str = 'long',
        pnl: float = 0,
        fee: float = 0,
        market_type: Optional[str] = None,
        board: Optional[str] = None,
        fee_details: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        cash_balance: Optional[float] = None,
        instrument_code: Optional[str] = None,
        trade_date: Optional[str] = None
    ):
        """Add trade record with detailed metadata."""
        conn = self.get_connection()
        cursor = conn.cursor()
        determined_market = (market_type or self._get_model_market_type(cursor, model_id)).lower()
        instrument_code_value = instrument_code or coin
        trade_date_value = trade_date or datetime.utcnow().date().isoformat()
        fee_details_json = json.dumps(fee_details) if fee_details is not None else None
        metadata_json = json.dumps(metadata) if metadata is not None else None
        cursor.execute('''
            INSERT INTO trades (
                model_id,
                coin,
                instrument_code,
                market_type,
                signal,
                quantity,
                price,
                trade_date,
                leverage,
                side,
                board,
                pnl,
                fee,
                fee_details,
                metadata,
                cash_balance
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            model_id,
            coin,
            instrument_code_value,
            determined_market,
            signal,
            quantity,
            price,
            trade_date_value,
            leverage,
            side,
            board,
            pnl,
            fee,
            fee_details_json,
            metadata_json,
            cash_balance
        ))
        conn.commit()
        conn.close()
    
    def get_trades(self, model_id: int, limit: int = 50) -> List[Dict]:
        """Get trade history including instrument metadata."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM trades WHERE model_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (model_id, limit))
        rows = cursor.fetchall()
        default_market = self._get_model_market_type(cursor, model_id)

        trades: List[Dict] = []
        instrument_pairs: List[Tuple[str, str]] = []
        for row in rows:
            trade = dict(row)
            trade['instrument_code'] = trade.get('instrument_code') or trade['coin']
            trade['market_type'] = (trade.get('market_type') or default_market).lower()
            trade['fee_details'] = self._safe_loads(trade.get('fee_details'), {}) or {}
            trade['metadata'] = self._safe_loads(trade.get('metadata'), {}) or {}
            if trade.get('trade_date'):
                trade['trade_date'] = str(trade['trade_date'])
            elif trade.get('timestamp'):
                trade['trade_date'] = str(trade['timestamp']).split(' ')[0]
            instrument_pairs.append((trade['instrument_code'], trade['market_type']))
            trades.append(trade)

        instrument_map = self._fetch_instrument_metadata_bulk(cursor, instrument_pairs)
        for trade in trades:
            key = (trade['instrument_code'], trade['market_type'])
            instrument_info = instrument_map.get(key)
            if instrument_info:
                trade['instrument_metadata'] = instrument_info
                if not trade.get('board') and instrument_info.get('board'):
                    trade['board'] = instrument_info.get('board')
                if instrument_info.get('status_flags') and not trade.get('status_flags'):
                    trade['status_flags'] = instrument_info.get('status_flags')
                if instrument_info.get('fundamentals'):
                    trade['fundamentals'] = instrument_info.get('fundamentals')
            else:
                trade['instrument_metadata'] = None
            if isinstance(trade.get('status_flags'), str):
                trade['status_flags'] = [trade['status_flags']]
            elif trade.get('status_flags') is None:
                trade['status_flags'] = []

        conn.close()
        return trades
    
    # ============ Instrument Metadata Management ============
    def upsert_instrument_metadata(
        self,
        instrument_code: str,
        market_type: str,
        name: Optional[str] = None,
        board: Optional[str] = None,
        status_flags: Optional[Any] = None,
        trading_status: Optional[str] = None,
        is_st: Optional[bool] = None,
        suspension: Optional[bool] = None,
        limit_up_price: Optional[float] = None,
        limit_down_price: Optional[float] = None,
        lot_size: Optional[int] = None,
        market_cap: Optional[float] = None,
        pe: Optional[float] = None,
        pb: Optional[float] = None,
        fundamentals: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ):
        conn = self.get_connection()
        cursor = conn.cursor()
        status_flags_value = self._serialize_optional_json(status_flags)
        is_st_value = None if is_st is None else int(bool(is_st))
        suspension_value = None if suspension is None else int(bool(suspension))
        limit_up_value = self._to_float(limit_up_price)
        limit_down_value = self._to_float(limit_down_price)
        lot_size_value = self._to_int(lot_size)
        market_cap_value = self._to_float(market_cap)
        pe_value = self._to_float(pe)
        pb_value = self._to_float(pb)
        fundamentals_json = json.dumps(fundamentals) if fundamentals else None
        metadata_json = json.dumps(metadata) if metadata else None
        cursor.execute('''
            INSERT INTO instruments (
                instrument_code,
                market_type,
                name,
                board,
                status_flags,
                trading_status,
                is_st,
                suspension,
                limit_up_price,
                limit_down_price,
                lot_size,
                market_cap,
                pe,
                pb,
                fundamentals,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(instrument_code, market_type) DO UPDATE SET
                name = COALESCE(excluded.name, name),
                board = COALESCE(excluded.board, board),
                status_flags = CASE WHEN excluded.status_flags IS NOT NULL THEN excluded.status_flags ELSE status_flags END,
                trading_status = COALESCE(excluded.trading_status, trading_status),
                is_st = CASE WHEN excluded.is_st IS NOT NULL THEN excluded.is_st ELSE is_st END,
                suspension = CASE WHEN excluded.suspension IS NOT NULL THEN excluded.suspension ELSE suspension END,
                limit_up_price = CASE WHEN excluded.limit_up_price IS NOT NULL THEN excluded.limit_up_price ELSE limit_up_price END,
                limit_down_price = CASE WHEN excluded.limit_down_price IS NOT NULL THEN excluded.limit_down_price ELSE limit_down_price END,
                lot_size = CASE WHEN excluded.lot_size IS NOT NULL THEN excluded.lot_size ELSE lot_size END,
                market_cap = CASE WHEN excluded.market_cap IS NOT NULL THEN excluded.market_cap ELSE market_cap END,
                pe = CASE WHEN excluded.pe IS NOT NULL THEN excluded.pe ELSE pe END,
                pb = CASE WHEN excluded.pb IS NOT NULL THEN excluded.pb ELSE pb END,
                fundamentals = CASE WHEN excluded.fundamentals IS NOT NULL THEN excluded.fundamentals ELSE fundamentals END,
                metadata = CASE WHEN excluded.metadata IS NOT NULL THEN excluded.metadata ELSE metadata END,
                updated_at = CURRENT_TIMESTAMP
        ''', (
            instrument_code,
            market_type.lower(),
            name,
            board,
            status_flags_value,
            trading_status,
            is_st_value,
            suspension_value,
            limit_up_value,
            limit_down_value,
            lot_size_value,
            market_cap_value,
            pe_value,
            pb_value,
            fundamentals_json,
            metadata_json
        ))
        conn.commit()
        conn.close()

    def get_instrument_metadata(self, instrument_code: str, market_type: str) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM instruments WHERE instrument_code = ? AND market_type = ?
        ''', (instrument_code, market_type.lower()))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return self._prepare_instrument_row(dict(row))

    def delete_instrument_metadata(self, instrument_code: str, market_type: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM instruments WHERE instrument_code = ? AND market_type = ?
        ''', (instrument_code, market_type.lower()))
        conn.commit()
        conn.close()
    
    # ============ Conversation History ============
    
    def add_conversation(self, model_id: int, user_prompt: str, 
                        ai_response: str, cot_trace: str = ''):
        """Add conversation record"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversations (model_id, user_prompt, ai_response, cot_trace)
            VALUES (?, ?, ?, ?)
        ''', (model_id, user_prompt, ai_response, cot_trace))
        conn.commit()
        conn.close()
    
    def get_conversations(self, model_id: int, limit: int = 20) -> List[Dict]:
        """Get conversation history"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM conversations WHERE model_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (model_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    # ============ Account Value History ============
    
    def record_account_value(self, model_id: int, total_value: float, 
                            cash: float, positions_value: float):
        """Record account value snapshot"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO account_values (model_id, total_value, cash, positions_value)
            VALUES (?, ?, ?, ?)
        ''', (model_id, total_value, cash, positions_value))
        conn.commit()
        conn.close()
    
    def get_account_value_history(self, model_id: int, limit: int = 100) -> List[Dict]:
        """Get account value history"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM account_values WHERE model_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (model_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_aggregated_account_value_history(self, limit: int = 100) -> List[Dict]:
        """Get aggregated account value history across all models"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get the most recent timestamp for each time point across all models
        cursor.execute('''
            SELECT timestamp,
                   SUM(total_value) as total_value,
                   SUM(cash) as cash,
                   SUM(positions_value) as positions_value,
                   COUNT(DISTINCT model_id) as model_count
            FROM (
                SELECT timestamp,
                       total_value,
                       cash,
                       positions_value,
                       model_id,
                       ROW_NUMBER() OVER (PARTITION BY model_id, DATE(timestamp) ORDER BY timestamp DESC) as rn
                FROM account_values
            ) grouped
            WHERE rn <= 10  -- Keep up to 10 records per model per day for aggregation
            GROUP BY DATE(timestamp), HOUR(timestamp)
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        result = []
        for row in rows:
            result.append({
                'timestamp': row['timestamp'],
                'total_value': row['total_value'],
                'cash': row['cash'],
                'positions_value': row['positions_value'],
                'model_count': row['model_count']
            })

        return result

    def get_multi_model_chart_data(self, limit: int = 100) -> List[Dict]:
        """Get chart data for all models to display in multi-line chart"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get all models
        cursor.execute('SELECT id, name FROM models')
        models = cursor.fetchall()

        chart_data = []

        for model in models:
            model_id = model['id']
            model_name = model['name']

            # Get account value history for this model
            cursor.execute('''
                SELECT timestamp, total_value FROM account_values
                WHERE model_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (model_id, limit))

            history = cursor.fetchall()

            if history:
                # Convert to list of dicts with model info
                model_data = {
                    'model_id': model_id,
                    'model_name': model_name,
                    'data': [
                        {
                            'timestamp': row['timestamp'],
                            'value': row['total_value']
                        } for row in history
                    ]
                }
                chart_data.append(model_data)

        conn.close()
        return chart_data

    # ============ Settings Management ============

    def get_settings(self) -> Dict:
        """Get system settings"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT trading_frequency_minutes, trading_fee_rate
            FROM settings
            ORDER BY id DESC
            LIMIT 1
        ''')

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'trading_frequency_minutes': row['trading_frequency_minutes'],
                'trading_fee_rate': row['trading_fee_rate']
            }
        else:
            # Return default settings if none exist
            return {
                'trading_frequency_minutes': 60,
                'trading_fee_rate': 0.001
            }

    def update_settings(self, trading_frequency_minutes: int, trading_fee_rate: float) -> bool:
        """Update system settings"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE settings
                SET trading_frequency_minutes = ?,
                    trading_fee_rate = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM settings ORDER BY id DESC LIMIT 1
                )
            ''', (trading_frequency_minutes, trading_fee_rate))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating settings: {e}")
            conn.close()
            return False

    # ============ Provider Management ============

    def add_provider(self, name: str, api_url: str, api_key: str, models: str = '') -> int:
        """Add new API provider"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO providers (name, api_url, api_key, models)
            VALUES (?, ?, ?, ?)
        ''', (name, api_url, api_key, models))
        provider_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return provider_id

    def get_provider(self, provider_id: int) -> Optional[Dict]:
        """Get provider information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM providers WHERE id = ?', (provider_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_providers(self) -> List[Dict]:
        """Get all API providers"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM providers ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def delete_provider(self, provider_id: int):
        """Delete provider"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM providers WHERE id = ?', (provider_id,))
        conn.commit()
        conn.close()

    def update_provider(self, provider_id: int, name: str, api_url: str, api_key: str, models: str):
        """Update provider information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE providers
            SET name = ?, api_url = ?, api_key = ?, models = ?
            WHERE id = ?
        ''', (name, api_url, api_key, models, provider_id))
        conn.commit()
        conn.close()

    # ============ Model Management (Updated) ============

    def add_model(
        self,
        name: str,
        provider_id: int,
        model_name: str,
        initial_capital: float = 10000,
        market_type: str = 'crypto',
        instruments: Optional[List[str]] = None,
        cash_currency: str = 'USD',
        market_config: Optional[Dict] = None
    ) -> int:
        """Add new trading model"""
        conn = self.get_connection()
        cursor = conn.cursor()
        instruments_json = json.dumps(instruments or [])
        market_config_json = json.dumps(market_config or {})
        cursor.execute(
            '''
            INSERT INTO models (name, provider_id, model_name, initial_capital, market_type, instruments, cash_currency, market_config)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (name, provider_id, model_name, initial_capital, market_type, instruments_json, cash_currency, market_config_json)
        )
        model_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return model_id

    def get_model(self, model_id: int) -> Optional[Dict]:
        """Get model information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.*, p.api_key, p.api_url
            FROM models m
            LEFT JOIN providers p ON m.provider_id = p.id
            WHERE m.id = ?
        ''', (model_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            result = dict(row)
            if 'instruments' in result and result['instruments']:
                try:
                    result['instruments'] = json.loads(result['instruments'])
                except (json.JSONDecodeError, TypeError):
                    result['instruments'] = []
            else:
                result['instruments'] = []

            if result.get('market_config'):
                try:
                    result['market_config'] = json.loads(result['market_config'])
                except (json.JSONDecodeError, TypeError):
                    result['market_config'] = {}
            else:
                result['market_config'] = {}
            return result
        return None

    def get_all_models(self) -> List[Dict]:
        """Get all trading models"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.*, p.name as provider_name
            FROM models m
            LEFT JOIN providers p ON m.provider_id = p.id
            ORDER BY m.created_at DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        results = []
        for row in rows:
            item = dict(row)
            if 'instruments' in item and item['instruments']:
                try:
                    item['instruments'] = json.loads(item['instruments'])
                except (json.JSONDecodeError, TypeError):
                    item['instruments'] = []
            else:
                item['instruments'] = []

            if item.get('market_config'):
                try:
                    item['market_config'] = json.loads(item['market_config'])
                except (json.JSONDecodeError, TypeError):
                    item['market_config'] = {}
            else:
                item['market_config'] = {}
            results.append(item)
        return results

