"""
Database management module
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Union

class Database:
    def __init__(self, db_path: str = 'AITradeGame.db'):
        self.db_path = db_path
        
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_table_columns(self, cursor, table_name: str) -> set:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {row['name'] for row in cursor.fetchall()}
    
    def _ensure_column(self, cursor, table_name: str, column_name: str, column_definition: str) -> bool:
        columns = self._get_table_columns(cursor, table_name)
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")
            return True
        return False
    
    def _get_table_indexes(self, cursor, table_name: str) -> set:
        cursor.execute(f"PRAGMA index_list({table_name})")
        return {row['name'] for row in cursor.fetchall()}
    
    def _ensure_unique_index(
        self,
        cursor,
        table_name: str,
        index_name: str,
        columns_sql: str,
        where_clause: Optional[str] = None
    ) -> bool:
        indexes = self._get_table_indexes(cursor, table_name)
        if index_name not in indexes:
            sql = f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table_name}{columns_sql}"
            if where_clause:
                sql += f" WHERE {where_clause}"
            cursor.execute(sql)
            return True
        return False
    
    def _parse_instrument_list(self, value: Optional[Union[str, List[str]]]) -> List[str]:
        if not value:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item and item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []
    
    def _dedupe_preserve(self, items: List[str]) -> List[str]:
        seen = set()
        deduped: List[str] = []
        for item in items:
            key = item.strip().upper()
            if key not in seen:
                seen.add(key)
                deduped.append(key)
        return deduped
    
    def init_db(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Providers table (API提供方)
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

        # Models table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                provider_id INTEGER,
                model_name TEXT NOT NULL,
                initial_capital REAL DEFAULT 10000,
                market_type TEXT DEFAULT 'crypto',
                instrument_list TEXT,
                instruments TEXT,
                cash_currency TEXT DEFAULT 'USD',
                market_config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (provider_id) REFERENCES providers(id)
            )
        ''')
        self._ensure_column(cursor, 'models', 'market_type', "market_type TEXT DEFAULT 'crypto'")
        self._ensure_column(cursor, 'models', 'instrument_list', "instrument_list TEXT")
        self._ensure_column(cursor, 'models', 'instruments', "instruments TEXT")
        self._ensure_column(cursor, 'models', 'cash_currency', "cash_currency TEXT DEFAULT 'USD'")
        self._ensure_column(cursor, 'models', 'market_config', "market_config TEXT")
        cursor.execute('''
            UPDATE models
            SET market_type = 'crypto'
            WHERE market_type IS NULL OR TRIM(market_type) = ''
        ''')
        cursor.execute('SELECT id, instruments, instrument_list FROM models')
        model_rows = cursor.fetchall()
        for row in model_rows:
            current_list = row['instrument_list']
            if current_list and str(current_list).strip():
                continue
            instruments_raw = row['instruments']
            instrument_list_value = ''
            if instruments_raw:
                parsed = None
                try:
                    parsed = json.loads(instruments_raw)
                except (json.JSONDecodeError, TypeError):
                    parsed = None
                if isinstance(parsed, list):
                    cleaned = [
                        str(item).strip().upper()
                        for item in parsed
                        if str(item).strip()
                    ]
                    cleaned = self._dedupe_preserve(cleaned)
                    if cleaned:
                        instrument_list_value = ','.join(cleaned)
                else:
                    cleaned = [
                        part.strip().upper()
                        for part in str(instruments_raw).split(',')
                        if part.strip()
                    ]
                    cleaned = self._dedupe_preserve(cleaned)
                    if cleaned:
                        instrument_list_value = ','.join(cleaned)
            if instrument_list_value:
                cursor.execute(
                    'UPDATE models SET instrument_list = ? WHERE id = ?',
                    (instrument_list_value, row['id'])
                )
        cursor.execute('''
            UPDATE models
            SET instrument_list = ''
            WHERE instrument_list IS NULL
        ''')

        # Portfolios table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                coin TEXT NOT NULL,
                instrument_code TEXT,
                quantity REAL NOT NULL,
                avg_price REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                side TEXT DEFAULT 'long',
                metadata TEXT,
                last_buy_date TEXT,
                next_sellable_date TEXT,
                market_type TEXT DEFAULT 'crypto',
                board TEXT,
                is_suspended INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')
        self._ensure_column(cursor, 'portfolios', 'metadata', 'metadata TEXT')
        self._ensure_column(cursor, 'portfolios', 'last_buy_date', 'last_buy_date TEXT')
        self._ensure_column(cursor, 'portfolios', 'next_sellable_date', 'next_sellable_date TEXT')
        self._ensure_column(cursor, 'portfolios', 'instrument_code', 'instrument_code TEXT')
        self._ensure_column(cursor, 'portfolios', 'market_type', "market_type TEXT DEFAULT 'crypto'")
        self._ensure_column(cursor, 'portfolios', 'board', 'board TEXT')
        self._ensure_column(cursor, 'portfolios', 'is_suspended', 'is_suspended INTEGER DEFAULT 0')
        cursor.execute('''
            UPDATE portfolios
            SET market_type = 'crypto'
            WHERE market_type IS NULL OR TRIM(market_type) = ''
        ''')
        cursor.execute('''
            UPDATE portfolios
            SET is_suspended = 0
            WHERE is_suspended IS NULL
        ''')
        cursor.execute('''
            UPDATE portfolios
            SET instrument_code = UPPER(coin)
            WHERE instrument_code IS NULL OR TRIM(instrument_code) = ''
        ''')
        self._ensure_unique_index(
            cursor,
            'portfolios',
            'idx_portfolios_model_coin_side_market',
            '(model_id, coin, side, market_type)'
        )
        self._ensure_unique_index(
            cursor,
            'portfolios',
            'idx_portfolios_model_instrument_side_market',
            '(model_id, instrument_code, side, market_type)',
            where_clause='instrument_code IS NOT NULL'
        )

        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                coin TEXT NOT NULL,
                instrument_code TEXT,
                signal TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                side TEXT DEFAULT 'long',
                pnl REAL DEFAULT 0,
                fee REAL DEFAULT 0,
                market_type TEXT DEFAULT 'crypto',
                board TEXT,
                trade_date TEXT,
                commission REAL DEFAULT 0,
                stamp_duty REAL DEFAULT 0,
                transfer_fee REAL DEFAULT 0,
                fee_details TEXT,
                metadata TEXT,
                cash_balance REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')
        self._ensure_column(cursor, 'trades', 'instrument_code', 'instrument_code TEXT')
        self._ensure_column(cursor, 'trades', 'market_type', "market_type TEXT DEFAULT 'crypto'")
        self._ensure_column(cursor, 'trades', 'board', 'board TEXT')
        self._ensure_column(cursor, 'trades', 'trade_date', 'trade_date TEXT')
        self._ensure_column(cursor, 'trades', 'commission', 'commission REAL DEFAULT 0')
        self._ensure_column(cursor, 'trades', 'stamp_duty', 'stamp_duty REAL DEFAULT 0')
        self._ensure_column(cursor, 'trades', 'transfer_fee', 'transfer_fee REAL DEFAULT 0')
        self._ensure_column(cursor, 'trades', 'fee_details', 'fee_details TEXT')
        self._ensure_column(cursor, 'trades', 'metadata', 'metadata TEXT')
        self._ensure_column(cursor, 'trades', 'cash_balance', 'cash_balance REAL')
        cursor.execute('''
            UPDATE trades
            SET market_type = 'crypto'
            WHERE market_type IS NULL OR TRIM(market_type) = ''
        ''')
        cursor.execute('''
            UPDATE trades
            SET commission = 0
            WHERE commission IS NULL
        ''')
        cursor.execute('''
            UPDATE trades
            SET stamp_duty = 0
            WHERE stamp_duty IS NULL
        ''')
        cursor.execute('''
            UPDATE trades
            SET transfer_fee = 0
            WHERE transfer_fee IS NULL
        ''')
        cursor.execute('''
            UPDATE trades
            SET trade_date = DATE(timestamp)
            WHERE trade_date IS NULL AND timestamp IS NOT NULL
        ''')
        cursor.execute('''
            UPDATE trades
            SET instrument_code = UPPER(coin)
            WHERE instrument_code IS NULL OR TRIM(instrument_code) = ''
        ''')

        # Instruments table (A-share metadata cache)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS instruments (
                instrument_code TEXT NOT NULL,
                market_type TEXT NOT NULL,
                board TEXT,
                is_st INTEGER DEFAULT 0,
                is_suspended INTEGER DEFAULT 0,
                limit_up_price REAL,
                limit_down_price REAL,
                market_cap REAL,
                pe_ratio REAL,
                pb_ratio REAL,
                lot_size INTEGER DEFAULT 100,
                updated_at TEXT,
                PRIMARY KEY (instrument_code, market_type)
            )
        ''')

        # Conversations table
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

        # Account values history table
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

        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trading_frequency_minutes INTEGER DEFAULT 60,
                trading_fee_rate REAL DEFAULT 0.001,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Insert default settings if no settings exist
        cursor.execute('SELECT COUNT(*) FROM settings')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO settings (trading_frequency_minutes, trading_fee_rate)
                VALUES (60, 0.001)
            ''')

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
        market_type: str = 'crypto',
        board: Optional[str] = None,
        is_suspended: Optional[bool] = None
    ):
        """Update position"""
        conn = self.get_connection()
        cursor = conn.cursor()
        metadata_json = json.dumps(metadata) if metadata is not None else None
        instrument_code_value_raw = instrument_code or coin
        instrument_code_value = None
        if instrument_code_value_raw is not None:
            instrument_code_value = str(instrument_code_value_raw).strip().upper()
        market_type_value = (market_type or 'crypto').lower()
        board_value = board.strip() if isinstance(board, str) else board
        is_suspended_provided = is_suspended is not None
        is_suspended_value = int(bool(is_suspended)) if is_suspended_provided else 0
        cursor.execute(
            '''
            INSERT INTO portfolios (
                model_id,
                coin,
                instrument_code,
                quantity,
                avg_price,
                leverage,
                side,
                metadata,
                last_buy_date,
                next_sellable_date,
                market_type,
                board,
                is_suspended,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(model_id, coin, side, market_type) DO UPDATE SET
                quantity = excluded.quantity,
                avg_price = excluded.avg_price,
                leverage = excluded.leverage,
                metadata = CASE WHEN excluded.metadata IS NOT NULL THEN excluded.metadata ELSE metadata END,
                last_buy_date = CASE WHEN excluded.last_buy_date IS NOT NULL THEN excluded.last_buy_date ELSE last_buy_date END,
                next_sellable_date = CASE WHEN excluded.next_sellable_date IS NOT NULL THEN excluded.next_sellable_date ELSE next_sellable_date END,
                board = CASE WHEN excluded.board IS NOT NULL THEN excluded.board ELSE board END,
                instrument_code = CASE WHEN excluded.instrument_code IS NOT NULL THEN excluded.instrument_code ELSE instrument_code END,
                is_suspended = CASE WHEN ? THEN excluded.is_suspended ELSE is_suspended END,
                market_type = excluded.market_type,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (
                model_id,
                coin,
                instrument_code_value,
                quantity,
                avg_price,
                leverage,
                side,
                metadata_json,
                last_buy_date,
                next_sellable_date,
                market_type_value,
                board_value,
                is_suspended_value,
                1 if is_suspended_provided else 0
            )
        )
        conn.commit()
        conn.close()
    
    def get_portfolio(self, model_id: int, current_prices: Dict = None) -> Dict:
        """Get portfolio with positions and P&L
        
        Args:
            model_id: Model ID
            current_prices: Current market prices {coin: price} for unrealized P&L calculation
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM portfolios WHERE model_id = ? AND quantity > 0
        ''', (model_id,))
        raw_positions = cursor.fetchall()
        positions: List[Dict] = []
        for row in raw_positions:
            pos = dict(row)
            metadata_raw = pos.get('metadata')
            if metadata_raw:
                try:
                    pos['metadata'] = json.loads(metadata_raw)
                except (json.JSONDecodeError, TypeError):
                    pos['metadata'] = {}
            else:
                pos['metadata'] = {}
            instrument_code_value = pos.get('instrument_code') or pos.get('coin')
            pos['instrument_code'] = str(instrument_code_value).strip().upper() if instrument_code_value else None
            pos['market_type'] = (pos.get('market_type') or 'crypto').lower()
            pos['is_suspended'] = bool(pos.get('is_suspended')) if pos.get('is_suspended') is not None else False
            positions.append(pos)
        
        cursor.execute('SELECT initial_capital FROM models WHERE id = ?', (model_id,))
        capital_row = cursor.fetchone()
        initial_capital = capital_row['initial_capital'] if capital_row else 0
        
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
        
        margin_used = 0
        for pos in positions:
            leverage = pos.get('leverage') or 1
            if leverage == 0:
                leverage = 1
            margin_used += (pos['quantity'] * pos['avg_price']) / leverage
        
        unrealized_pnl = 0.0
        positions_value = 0.0
        if current_prices:
            for pos in positions:
                coin = pos['coin']
                entry_price = pos['avg_price']
                quantity = pos['quantity']
                side = pos.get('side', 'long')
                current_price = current_prices.get(coin)
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
        coin: Optional[str] = None,
        side: str = 'long',
        market_type: Optional[str] = None,
        instrument_code: Optional[str] = None
    ) -> Optional[Dict]:
        """Fetch a single position"""
        conn = self.get_connection()
        cursor = conn.cursor()
        conditions = ['model_id = ?', 'side = ?']
        params = [model_id, side]
        if coin is not None:
            conditions.append('coin = ?')
            params.append(coin)
        if instrument_code is not None:
            instrument_code_clean = str(instrument_code).strip().upper()
            conditions.append('instrument_code = ?')
            params.append(instrument_code_clean)
        if market_type is not None:
            conditions.append('market_type = ?')
            params.append((market_type or 'crypto').lower())
        cursor.execute(
            f"SELECT * FROM portfolios WHERE {' AND '.join(conditions)} LIMIT 1",
            tuple(params)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        position = dict(row)
        metadata_raw = position.get('metadata')
        if metadata_raw:
            try:
                position['metadata'] = json.loads(metadata_raw)
            except (json.JSONDecodeError, TypeError):
                position['metadata'] = {}
        else:
            position['metadata'] = {}
        instrument_code_value = position.get('instrument_code') or position.get('coin')
        position['instrument_code'] = str(instrument_code_value).strip().upper() if instrument_code_value else None
        position['market_type'] = (position.get('market_type') or 'crypto').lower()
        position['is_suspended'] = bool(position.get('is_suspended')) if position.get('is_suspended') is not None else False
        return position
    
    def close_position(
        self,
        model_id: int,
        coin: Optional[str] = None,
        side: str = 'long',
        instrument_code: Optional[str] = None,
        market_type: Optional[str] = None
    ):
        """Close position"""
        conn = self.get_connection()
        cursor = conn.cursor()
        conditions = ['model_id = ?', 'side = ?']
        params = [model_id, side]
        if coin is not None:
            conditions.append('coin = ?')
            params.append(coin)
        if instrument_code is not None:
            instrument_code_clean = str(instrument_code).strip().upper()
            conditions.append('instrument_code = ?')
            params.append(instrument_code_clean)
        if market_type is not None:
            conditions.append('market_type = ?')
            params.append((market_type or 'crypto').lower())
        cursor.execute(
            f"DELETE FROM portfolios WHERE {' AND '.join(conditions)}",
            tuple(params)
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
        instrument_code: Optional[str] = None,
        trade_date: Optional[str] = None,
        commission: Optional[float] = None,
        stamp_duty: Optional[float] = None,
        transfer_fee: Optional[float] = None,
        fee_details: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        cash_balance: Optional[float] = None
    ):
        """Add trade record with detailed metadata"""
        conn = self.get_connection()
        cursor = conn.cursor()
        market_type_value = (market_type or 'crypto').lower()
        instrument_code_value_raw = instrument_code or coin
        instrument_code_value = None
        if instrument_code_value_raw is not None:
            instrument_code_value = str(instrument_code_value_raw).strip().upper()
        trade_date_value = trade_date or datetime.utcnow().date().isoformat()
        commission_value = float(commission) if commission is not None else 0.0
        stamp_duty_value = float(stamp_duty) if stamp_duty is not None else 0.0
        transfer_fee_value = float(transfer_fee) if transfer_fee is not None else 0.0
        fee_details_json = json.dumps(fee_details) if fee_details is not None else None
        metadata_json = json.dumps(metadata) if metadata is not None else None
        board_value = board.strip() if isinstance(board, str) else board
        cursor.execute(
            '''
            INSERT INTO trades (
                model_id,
                coin,
                instrument_code,
                signal,
                quantity,
                price,
                leverage,
                side,
                pnl,
                fee,
                market_type,
                board,
                trade_date,
                commission,
                stamp_duty,
                transfer_fee,
                fee_details,
                metadata,
                cash_balance
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                model_id,
                coin,
                instrument_code_value,
                signal,
                quantity,
                price,
                leverage,
                side,
                pnl,
                fee,
                market_type_value,
                board_value,
                trade_date_value,
                commission_value,
                stamp_duty_value,
                transfer_fee_value,
                fee_details_json,
                metadata_json,
                cash_balance
            )
        )
        conn.commit()
        conn.close()
    
    def get_trades(self, model_id: int, limit: int = 50) -> List[Dict]:
        """Get trade history"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM trades WHERE model_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (model_id, limit))
        rows = cursor.fetchall()
        conn.close()
        trades: List[Dict] = []
        for row in rows:
            trade = dict(row)
            fee_details = trade.get('fee_details')
            if fee_details:
                try:
                    trade['fee_details'] = json.loads(fee_details)
                except (json.JSONDecodeError, TypeError):
                    trade['fee_details'] = {}
            else:
                trade['fee_details'] = {}
            metadata_raw = trade.get('metadata')
            if metadata_raw:
                try:
                    trade['metadata'] = json.loads(metadata_raw)
                except (json.JSONDecodeError, TypeError):
                    trade['metadata'] = {}
            else:
                trade['metadata'] = {}
            instrument_code_value = trade.get('instrument_code') or trade.get('coin')
            trade['instrument_code'] = str(instrument_code_value).strip().upper() if instrument_code_value else None
            trade['market_type'] = (trade.get('market_type') or 'crypto').lower()
            trade['commission'] = float(trade.get('commission') or 0)
            trade['stamp_duty'] = float(trade.get('stamp_duty') or 0)
            trade['transfer_fee'] = float(trade.get('transfer_fee') or 0)
            if not trade.get('trade_date') and trade.get('timestamp'):
                trade['trade_date'] = str(trade['timestamp']).split(' ')[0]
            trades.append(trade)
        return trades
    
    # ============ Instrument Metadata Cache ============
    
    def upsert_instrument_metadata(
        self,
        instrument_code: str,
        market_type: str,
        metadata: Optional[Dict] = None,
        **extra_fields
    ):
        """Insert or update cached instrument metadata"""
        payload = {}
        if metadata:
            payload.update(metadata)
        payload.update({k: v for k, v in extra_fields.items() if v is not None})
        instrument_code_clean = str(instrument_code).strip().upper()
        market_type_clean = (market_type or 'crypto').lower()

        def _to_float(value):
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _to_int(value, default=0):
            if value is None:
                return default
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        board = payload.get('board')
        if isinstance(board, str):
            board = board.strip()
        is_st = 1 if payload.get('is_st') else 0
        is_suspended = 1 if payload.get('is_suspended') else 0
        limit_up_price = _to_float(payload.get('limit_up_price'))
        limit_down_price = _to_float(payload.get('limit_down_price'))
        market_cap = _to_float(payload.get('market_cap'))
        pe_ratio = _to_float(payload.get('pe_ratio'))
        pb_ratio = _to_float(payload.get('pb_ratio'))
        lot_size = _to_int(payload.get('lot_size'), default=100)
        updated_at = payload.get('updated_at') or datetime.utcnow().isoformat()

        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO instruments (
                instrument_code,
                market_type,
                board,
                is_st,
                is_suspended,
                limit_up_price,
                limit_down_price,
                market_cap,
                pe_ratio,
                pb_ratio,
                lot_size,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(instrument_code, market_type) DO UPDATE SET
                board = excluded.board,
                is_st = excluded.is_st,
                is_suspended = excluded.is_suspended,
                limit_up_price = excluded.limit_up_price,
                limit_down_price = excluded.limit_down_price,
                market_cap = excluded.market_cap,
                pe_ratio = excluded.pe_ratio,
                pb_ratio = excluded.pb_ratio,
                lot_size = excluded.lot_size,
                updated_at = excluded.updated_at
            ''',
            (
                instrument_code_clean,
                market_type_clean,
                board,
                is_st,
                is_suspended,
                limit_up_price,
                limit_down_price,
                market_cap,
                pe_ratio,
                pb_ratio,
                lot_size,
                updated_at
            )
        )
        conn.commit()
        conn.close()

    def get_instrument_metadata(self, instrument_code: str, market_type: str) -> Optional[Dict]:
        """Fetch cached instrument metadata"""
        conn = self.get_connection()
        cursor = conn.cursor()
        instrument_code_clean = str(instrument_code).strip().upper()
        market_type_clean = (market_type or 'crypto').lower()
        cursor.execute(
            '''
            SELECT * FROM instruments
            WHERE instrument_code = ? AND market_type = ?
            LIMIT 1
            ''',
            (instrument_code_clean, market_type_clean)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        result = dict(row)
        if result.get('instrument_code'):
            result['instrument_code'] = str(result['instrument_code']).strip().upper()
        if isinstance(result.get('board'), str):
            result['board'] = result['board'].strip()
        result['is_st'] = bool(result.get('is_st'))
        result['is_suspended'] = bool(result.get('is_suspended'))
        return result

    def get_instruments_by_market(self, market_type: str) -> List[Dict]:
        """List cached instruments for a market"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM instruments
            WHERE market_type = ?
            ORDER BY instrument_code
            ''',
            ((market_type or 'crypto').lower(),)
        )
        rows = cursor.fetchall()
        conn.close()
        results: List[Dict] = []
        for row in rows:
            item = dict(row)
            instrument_code_value = item.get('instrument_code')
            if instrument_code_value:
                item['instrument_code'] = str(instrument_code_value).strip().upper()
            if isinstance(item.get('board'), str):
                item['board'] = item['board'].strip()
            item['is_st'] = bool(item.get('is_st'))
            item['is_suspended'] = bool(item.get('is_suspended'))
            results.append(item)
        return results
    
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
        instrument_list: Optional[Union[str, List[str]]] = None,
        cash_currency: str = 'USD',
        market_config: Optional[Dict] = None
    ) -> int:
        """Add new trading model"""
        conn = self.get_connection()
        cursor = conn.cursor()
        market_type_value = (market_type or 'crypto').lower()
        instrument_items_from_param = [
            str(item).strip().upper()
            for item in (instruments or [])
            if str(item).strip()
        ]
        instrument_items_from_param = self._dedupe_preserve(instrument_items_from_param)
        instrument_list_items = [item.upper() for item in self._parse_instrument_list(instrument_list)]
        instrument_list_items = self._dedupe_preserve(instrument_list_items)
        if not instrument_items_from_param and instrument_list_items:
            instrument_items_from_param = instrument_list_items.copy()
        elif instrument_items_from_param and not instrument_list_items:
            instrument_list_items = instrument_items_from_param.copy()
        else:
            combined = self._dedupe_preserve(instrument_list_items + instrument_items_from_param)
            instrument_items_from_param = combined.copy()
            instrument_list_items = combined.copy()
        instrument_list_value = ','.join(instrument_list_items) if instrument_list_items else ''
        instruments_json = json.dumps(instrument_items_from_param)
        market_config_json = json.dumps(market_config or {})
        cursor.execute(
            '''
            INSERT INTO models (
                name,
                provider_id,
                model_name,
                initial_capital,
                market_type,
                instrument_list,
                instruments,
                cash_currency,
                market_config
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                name,
                provider_id,
                model_name,
                initial_capital,
                market_type_value,
                instrument_list_value,
                instruments_json,
                cash_currency,
                market_config_json
            )
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
            result['market_type'] = (result.get('market_type') or 'crypto').lower()
            instruments_raw = result.get('instruments')
            parsed_instruments: List[str] = []
            if instruments_raw:
                try:
                    loaded = json.loads(instruments_raw)
                    if isinstance(loaded, list):
                        parsed_instruments = [
                            str(item).strip().upper()
                            for item in loaded
                            if str(item).strip()
                        ]
                except (json.JSONDecodeError, TypeError):
                    parsed_instruments = []
            parsed_instruments = self._dedupe_preserve(parsed_instruments)
            instrument_list_items = [item.upper() for item in self._parse_instrument_list(result.get('instrument_list'))]
            instrument_list_items = self._dedupe_preserve(instrument_list_items)
            if not parsed_instruments and instrument_list_items:
                parsed_instruments = instrument_list_items.copy()
            elif parsed_instruments and not instrument_list_items:
                instrument_list_items = parsed_instruments.copy()
            else:
                combined = self._dedupe_preserve(instrument_list_items + parsed_instruments)
                parsed_instruments = combined.copy()
                instrument_list_items = combined.copy()
            result['instruments'] = parsed_instruments
            result['instrument_list_items'] = instrument_list_items
            result['instrument_list'] = ','.join(instrument_list_items)
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
            item['market_type'] = (item.get('market_type') or 'crypto').lower()
            instruments_raw = item.get('instruments')
            parsed_instruments: List[str] = []
            if instruments_raw:
                try:
                    loaded = json.loads(instruments_raw)
                    if isinstance(loaded, list):
                        parsed_instruments = [
                            str(value).strip().upper()
                            for value in loaded
                            if str(value).strip()
                        ]
                except (json.JSONDecodeError, TypeError):
                    parsed_instruments = []
            parsed_instruments = self._dedupe_preserve(parsed_instruments)
            instrument_list_items = [item_str.upper() for item_str in self._parse_instrument_list(item.get('instrument_list'))]
            instrument_list_items = self._dedupe_preserve(instrument_list_items)
            if not parsed_instruments and instrument_list_items:
                parsed_instruments = instrument_list_items.copy()
            elif parsed_instruments and not instrument_list_items:
                instrument_list_items = parsed_instruments.copy()
            else:
                combined = self._dedupe_preserve(instrument_list_items + parsed_instruments)
                parsed_instruments = combined.copy()
                instrument_list_items = combined.copy()
            item['instruments'] = parsed_instruments
            item['instrument_list_items'] = instrument_list_items
            item['instrument_list'] = ','.join(instrument_list_items)

            if item.get('market_config'):
                try:
                    item['market_config'] = json.loads(item['market_config'])
                except (json.JSONDecodeError, TypeError):
                    item['market_config'] = {}
            else:
                item['market_config'] = {}
            results.append(item)
        return results

