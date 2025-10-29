"""
Database management module
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional

class Database:
    def __init__(self, db_path: str = 'AITradeGame.db'):
        self.db_path = db_path
        
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
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
                models TEXT,  -- JSON string or comma-separated list of models
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
                instruments TEXT,
                cash_currency TEXT DEFAULT 'USD',
                market_config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (provider_id) REFERENCES providers(id)
            )
        ''')
        
        # Add new columns to existing models table if they don't exist
        try:
            cursor.execute('ALTER TABLE models ADD COLUMN market_type TEXT DEFAULT "crypto"')
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute('ALTER TABLE models ADD COLUMN instruments TEXT')
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute('ALTER TABLE models ADD COLUMN cash_currency TEXT DEFAULT "USD"')
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute('ALTER TABLE models ADD COLUMN market_config TEXT')
        except sqlite3.OperationalError:
            pass
        
        # Portfolios table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                coin TEXT NOT NULL,
                quantity REAL NOT NULL,
                avg_price REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                side TEXT DEFAULT 'long',
                metadata TEXT,
                last_buy_date TEXT,
                next_sellable_date TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id),
                UNIQUE(model_id, coin, side)
            )
        ''')
        
        try:
            cursor.execute('ALTER TABLE portfolios ADD COLUMN metadata TEXT')
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute('ALTER TABLE portfolios ADD COLUMN last_buy_date TEXT')
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute('ALTER TABLE portfolios ADD COLUMN next_sellable_date TEXT')
        except sqlite3.OperationalError:
            pass
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                coin TEXT NOT NULL,
                signal TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                side TEXT DEFAULT 'long',
                pnl REAL DEFAULT 0,
                fee REAL DEFAULT 0,
                market_type TEXT,
                board TEXT,
                fee_details TEXT,
                metadata TEXT,
                cash_balance REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')
        
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN market_type TEXT')
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN board TEXT')
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN fee_details TEXT')
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN metadata TEXT')
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN cash_balance REAL')
        except sqlite3.OperationalError:
            pass
        
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
        next_sellable_date: Optional[str] = None
    ):
        """Update position"""
        conn = self.get_connection()
        cursor = conn.cursor()
        metadata_json = json.dumps(metadata) if metadata is not None else None
        cursor.execute('''
            INSERT INTO portfolios (model_id, coin, quantity, avg_price, leverage, side, metadata, last_buy_date, next_sellable_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(model_id, coin, side) DO UPDATE SET
                quantity = excluded.quantity,
                avg_price = excluded.avg_price,
                leverage = excluded.leverage,
                metadata = CASE WHEN excluded.metadata IS NOT NULL THEN excluded.metadata ELSE metadata END,
                last_buy_date = CASE WHEN excluded.last_buy_date IS NOT NULL THEN excluded.last_buy_date ELSE last_buy_date END,
                next_sellable_date = CASE WHEN excluded.next_sellable_date IS NOT NULL THEN excluded.next_sellable_date ELSE next_sellable_date END,
                updated_at = CURRENT_TIMESTAMP
        ''', (model_id, coin, quantity, avg_price, leverage, side, metadata_json, last_buy_date, next_sellable_date))
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
    
    def get_position(self, model_id: int, coin: str, side: str = 'long') -> Optional[Dict]:
        """Fetch a single position"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM portfolios WHERE model_id = ? AND coin = ? AND side = ? LIMIT 1
        ''', (model_id, coin, side))
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
        return position
    
    def close_position(self, model_id: int, coin: str, side: str = 'long'):
        """Close position"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM portfolios WHERE model_id = ? AND coin = ? AND side = ?
        ''', (model_id, coin, side))
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
        cash_balance: Optional[float] = None
    ):
        """Add trade record with detailed metadata"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (model_id, coin, signal, quantity, price, leverage, side, pnl, fee, market_type, board, fee_details, metadata, cash_balance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            model_id,
            coin,
            signal,
            quantity,
            price,
            leverage,
            side,
            pnl,
            fee,
            market_type,
            board,
            json.dumps(fee_details) if fee_details is not None else None,
            json.dumps(metadata) if metadata is not None else None,
            cash_balance
        ))
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
            trades.append(trade)
        return trades
    
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

