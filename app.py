from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import time
import threading
import json
import re
from datetime import datetime, date
from trading_engine import TradingEngine
from market_data import MarketDataService
from ai_trader import AITrader
from database import Database
from version import __version__, __github_owner__, __repo__, GITHUB_REPO_URL, LATEST_RELEASE_URL
from market_calendar import MarketCalendar

app = Flask(__name__)
CORS(app)

db = Database('AITradeGame.db')
market_fetcher = MarketDataService()
market_calendar = MarketCalendar()
trading_engines = {}
auto_trading = True
TRADE_FEE_RATE = 0.001  # 默认交易费率

def _parse_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except Exception:
        try:
            return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except Exception:
            return None

def _enrich_positions(positions, quotes, market_type):
    if market_type != 'a_share':
        return positions
    status = market_calendar.get_market_status('a_share') if market_calendar else {}
    server_time = status.get('server_time')
    current_dt = _parse_timestamp(server_time) if server_time else datetime.now()
    current_date = current_dt.date() if current_dt else datetime.now().date()
    for pos in positions:
        instrument_code = pos.get('instrument_code') or pos.get('coin')
        pos['instrument_code'] = instrument_code
        quote = quotes.get(instrument_code) or quotes.get(pos.get('coin'), {}) or {}
        metadata = pos.get('metadata') or {}
        instrument_meta = pos.get('instrument_metadata') or {}
        pos['board'] = (
            pos.get('board')
            or metadata.get('board')
            or instrument_meta.get('board')
            or quote.get('board')
        )
        suspension_val = quote.get('suspension')
        if suspension_val is None:
            suspension_val = pos.get('suspension')
        if suspension_val is None:
            suspension_val = instrument_meta.get('suspension')
        pos['suspension'] = bool(suspension_val) if suspension_val is not None else False
        pos['limit_up_price'] = (
            pos.get('limit_up_price')
            or metadata.get('limit_up_price')
            or instrument_meta.get('limit_up_price')
            or quote.get('limit_up_price')
        )
        pos['limit_down_price'] = (
            pos.get('limit_down_price')
            or metadata.get('limit_down_price')
            or instrument_meta.get('limit_down_price')
            or quote.get('limit_down_price')
        )
        fundamentals = instrument_meta.get('fundamentals') or quote.get('fundamentals') or {}
        if metadata.get('fundamentals'):
            fundamentals = {**fundamentals, **metadata.get('fundamentals')}
        pos['fundamentals'] = fundamentals
        st_value = quote.get('is_st')
        if st_value is None:
            st_value = instrument_meta.get('is_st')
        if st_value is None:
            st_value = metadata.get('is_st')
        pos['is_st'] = bool(st_value) if st_value is not None else False
        status_flags = pos.get('status_flags') or instrument_meta.get('status_flags') or metadata.get('status_flags')
        if isinstance(status_flags, str):
            status_flags = [status_flags]
        pos['status_flags'] = status_flags or []
        pos['trading_status'] = (
            pos.get('trading_status')
            or instrument_meta.get('trading_status')
            or quote.get('trading_status')
        )
        lot_size_val = pos.get('lot_size')
        if lot_size_val is None:
            lot_size_val = instrument_meta.get('lot_size') or quote.get('lot_size')
        try:
            pos['lot_size'] = int(lot_size_val) if lot_size_val is not None else None
        except (TypeError, ValueError):
            pos['lot_size'] = None
        stored_next = pos.get('next_sellable_date') or metadata.get('next_sellable_date')
        if stored_next:
            pos['next_sellable_date'] = stored_next
        else:
            ts = _parse_timestamp(pos.get('updated_at'))
            pos['next_sellable_date'] = market_calendar.next_sellable_date('a_share', ts)
        next_sellable = pos.get('next_sellable_date')
        if next_sellable:
            try:
                ns_date = date.fromisoformat(next_sellable)
                pos['t1_locked'] = current_date < ns_date
            except ValueError:
                pos['t1_locked'] = False
        else:
            pos['t1_locked'] = False
        pos['entry_fee_total'] = metadata.get('entry_fee_total')
        pos['last_settlement_date'] = pos.get('last_settlement_date') or metadata.get('last_settlement_date')
    return positions

def _enrich_trades(trades, quotes, market_type):
    if market_type != 'a_share':
        return trades
    for trade in trades:
        instrument_code = trade.get('instrument_code') or trade.get('coin')
        trade['instrument_code'] = instrument_code
        quote = quotes.get(instrument_code) or quotes.get(trade.get('coin'), {}) or {}
        metadata = trade.get('metadata') or {}
        fee_details = trade.get('fee_details') or {}
        instrument_meta = trade.get('instrument_metadata') or {}
        trade['board'] = (
            trade.get('board')
            or metadata.get('board')
            or instrument_meta.get('board')
            or quote.get('board')
        )
        suspension_val = quote.get('suspension')
        if suspension_val is None:
            suspension_val = trade.get('suspension')
        if suspension_val is None:
            suspension_val = instrument_meta.get('suspension')
        trade['suspension'] = bool(suspension_val) if suspension_val is not None else False
        trade['limit_up_price'] = (
            trade.get('limit_up_price')
            or metadata.get('limit_up_price')
            or instrument_meta.get('limit_up_price')
            or quote.get('limit_up_price')
        )
        trade['limit_down_price'] = (
            trade.get('limit_down_price')
            or metadata.get('limit_down_price')
            or instrument_meta.get('limit_down_price')
            or quote.get('limit_down_price')
        )
        trade['fundamentals'] = instrument_meta.get('fundamentals') or quote.get('fundamentals') or {}
        next_sellable = metadata.get('next_sellable_date') or trade.get('next_sellable_date')
        if next_sellable:
            trade['next_sellable_date'] = next_sellable
        else:
            ts = _parse_timestamp(trade.get('timestamp'))
            trade['next_sellable_date'] = market_calendar.next_sellable_date('a_share', ts)
        trade['fee_details'] = fee_details
        trade['commission'] = fee_details.get('commission')
        trade['transfer_fee'] = fee_details.get('transfer_fee')
        trade['stamp_duty'] = fee_details.get('stamp_duty')
        trade['total_fee'] = fee_details.get('total', trade.get('fee'))
        trade['allocated_entry_fee'] = metadata.get('allocated_entry_fee')
        trade['net_pnl_before_entry_fee'] = metadata.get('net_pnl_before_entry_fee')
        status_flags = trade.get('status_flags') or instrument_meta.get('status_flags') or metadata.get('status_flags')
        if isinstance(status_flags, str):
            status_flags = [status_flags]
        trade['status_flags'] = status_flags or []
        trade['trading_status'] = trade.get('trading_status') or instrument_meta.get('trading_status') or quote.get('trading_status')
    return trades

@app.route('/')
def index():
    return render_template('index.html')

# ============ Provider API Endpoints ============

@app.route('/api/providers', methods=['GET'])
def get_providers():
    """Get all API providers"""
    providers = db.get_all_providers()
    return jsonify(providers)

@app.route('/api/providers', methods=['POST'])
def add_provider():
    """Add new API provider"""
    data = request.json
    try:
        provider_id = db.add_provider(
            name=data['name'],
            api_url=data['api_url'],
            api_key=data['api_key'],
            models=data.get('models', '')
        )
        return jsonify({'id': provider_id, 'message': 'Provider added successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/providers/<int:provider_id>', methods=['DELETE'])
def delete_provider(provider_id):
    """Delete API provider"""
    try:
        db.delete_provider(provider_id)
        return jsonify({'message': 'Provider deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/providers/models', methods=['POST'])
def fetch_provider_models():
    """Fetch available models from provider's API"""
    data = request.json
    api_url = data.get('api_url')
    api_key = data.get('api_key')

    if not api_url or not api_key:
        return jsonify({'error': 'API URL and key are required'}), 400

    try:
        # This is a placeholder - implement actual API call based on provider
        # For now, return empty list or common models
        models = []

        # Try to detect provider type and call appropriate API
        if 'openai.com' in api_url.lower():
            # OpenAI API call
            import requests
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            response = requests.get(f'{api_url}/models', headers=headers, timeout=10)
            if response.status_code == 200:
                result = response.json()
                models = [m['id'] for m in result.get('data', []) if 'gpt' in m['id'].lower()]
        elif 'deepseek' in api_url.lower():
            # DeepSeek API
            import requests
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            response = requests.get(f'{api_url}/models', headers=headers, timeout=10)
            if response.status_code == 200:
                result = response.json()
                models = [m['id'] for m in result.get('data', [])]
        else:
            # Default: return common model names
            models = ['gpt-3.5-turbo', 'gpt-4', 'gpt-4-turbo']

        return jsonify({'models': models})
    except Exception as e:
        print(f"[ERROR] Fetch models failed: {e}")
        return jsonify({'error': f'Failed to fetch models: {str(e)}'}), 500

# ============ Model API Endpoints ============

@app.route('/api/models', methods=['GET'])
def get_models():
    models = db.get_all_models()
    return jsonify(models)

@app.route('/api/models', methods=['POST'])
def add_model():
    data = request.json or {}
    try:
        provider_id = data.get('provider_id')
        if provider_id is None:
            return jsonify({'error': 'provider_id is required'}), 400
        provider = db.get_provider(provider_id)
        if not provider:
            return jsonify({'error': 'Provider not found'}), 404

        market_type = (data.get('market_type') or 'crypto').lower()
        if market_type not in ('crypto', 'a_share'):
            return jsonify({'error': 'Unsupported market_type'}), 400

        instruments = data.get('instruments') or data.get('trade_universe') or []
        if market_type == 'a_share':
            if not instruments or not isinstance(instruments, list):
                return jsonify({'error': 'A-share models require instruments list'}), 400
            instruments = [str(symbol).upper() for symbol in instruments]
        elif not instruments:
            instruments = market_fetcher.get_default_instruments('crypto')

        cash_currency = data.get('cash_currency') or ('CNY' if market_type == 'a_share' else 'USD')

        market_config = data.get('market_config') or {}
        if market_type == 'a_share':
            default_fees = {
                'commission_rate': 0.0003,
                'commission_min': 5,
                'transfer_rate': 0.00001,
                'stamp_duty_rate': 0.001
            }
            config_fees = market_config.get('fees') or {}
            merged_fees = {**default_fees, **config_fees}
            market_config = {
                'lot_size': int(market_config.get('lot_size', 100) or 100),
                'lot_step': int(market_config.get('lot_step', 100) or 100),
                'allow_partial_final_lot': bool(market_config.get('allow_partial_final_lot', True)),
                'price_limit_tolerance': float(market_config.get('price_limit_tolerance', 0) or 0),
                'fees': merged_fees
            }
        else:
            config_fees = market_config.get('fees') or {}
            config_fees.setdefault('trade_fee_rate', TRADE_FEE_RATE)
            market_config['fees'] = config_fees

        model_id = db.add_model(
            name=data['name'],
            provider_id=provider_id,
            model_name=data['model_name'],
            initial_capital=float(data.get('initial_capital', 100000)),
            market_type=market_type,
            instruments=instruments,
            cash_currency=cash_currency,
            market_config=market_config
        )

        model = db.get_model(model_id)
        trading_engines[model_id] = TradingEngine(
            model_id=model_id,
            db=db,
            market_fetcher=market_fetcher,
            market_calendar=market_calendar,
            market_type=model.get('market_type', 'crypto'),
            instruments=model.get('instruments') or market_fetcher.get_default_instruments(model.get('market_type')),
            cash_currency=model.get('cash_currency', cash_currency),
            market_config=model.get('market_config') or {},
            ai_trader=AITrader(
                api_key=model['api_key'],
                api_url=model['api_url'],
                model_name=model['model_name'],
                market_type=model.get('market_type', 'crypto'),
                instruments=model.get('instruments') or []
            ),
            trade_fee_rate=TRADE_FEE_RATE
        )
        print(f"[INFO] Model {model_id} ({data['name']}) initialized for {market_type}")

        return jsonify({'id': model_id, 'message': 'Model added successfully'})

    except Exception as e:
        print(f"[ERROR] Failed to add model: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>', methods=['DELETE'])
def delete_model(model_id):
    try:
        model = db.get_model(model_id)
        model_name = model['name'] if model else f"ID-{model_id}"
        
        db.delete_model(model_id)
        if model_id in trading_engines:
            del trading_engines[model_id]
        
        print(f"[INFO] Model {model_id} ({model_name}) deleted")
        return jsonify({'message': 'Model deleted successfully'})
    except Exception as e:
        print(f"[ERROR] Delete model {model_id} failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>/portfolio', methods=['GET'])
def get_portfolio(model_id):
    model = db.get_model(model_id)
    if not model:
        return jsonify({'error': 'Model not found'}), 404
    
    market_type = model.get('market_type', 'crypto')
    instruments = model.get('instruments') or market_fetcher.get_default_instruments(market_type)
    
    prices_data = market_fetcher.get_current_prices(instruments, market_type=market_type)
    current_prices = {key: prices_data[key].get('price', 0) for key in prices_data}
    
    portfolio = db.get_portfolio(model_id, current_prices)
    positions = _enrich_positions(portfolio.get('positions', []), prices_data, market_type)
    portfolio['positions'] = positions
    portfolio['market_type'] = market_type
    portfolio['cash_currency'] = model.get('cash_currency', 'USD')
    
    account_value = db.get_account_value_history(model_id, limit=100)
    
    return jsonify({
        'portfolio': portfolio,
        'account_value_history': account_value
    })

@app.route('/api/models/<int:model_id>/trades', methods=['GET'])
def get_trades(model_id):
    model = db.get_model(model_id)
    if not model:
        return jsonify({'error': 'Model not found'}), 404
    limit = request.args.get('limit', 50, type=int)
    trades = db.get_trades(model_id, limit=limit)
    market_type = model.get('market_type', 'crypto')
    if trades and market_type == 'a_share':
        unique_symbols = list({
            trade.get('instrument_code') or trade.get('coin')
            for trade in trades
            if trade.get('instrument_code') or trade.get('coin')
        })
        quotes = market_fetcher.get_current_prices(unique_symbols, market_type='a_share') if unique_symbols else {}
        trades = _enrich_trades(trades, quotes, 'a_share')
    return jsonify(trades)

@app.route('/api/models/<int:model_id>/conversations', methods=['GET'])
def get_conversations(model_id):
    limit = request.args.get('limit', 20, type=int)
    conversations = db.get_conversations(model_id, limit=limit)
    return jsonify(conversations)

@app.route('/api/aggregated/portfolio', methods=['GET'])
def get_aggregated_portfolio():
    """Get aggregated portfolio data across all models"""
    models = db.get_all_models()
    total_portfolio = {
        'total_value': 0,
        'cash': 0,
        'positions_value': 0,
        'realized_pnl': 0,
        'unrealized_pnl': 0,
        'initial_capital': 0,
        'positions': []
    }

    all_positions = {}

    for model in models:
        market_type = model.get('market_type', 'crypto')
        instruments = model.get('instruments') or market_fetcher.get_default_instruments(market_type)
        quotes = market_fetcher.get_current_prices(instruments, market_type=market_type)
        current_prices = {instrument: quotes[instrument].get('price', 0) for instrument in quotes}

        portfolio = db.get_portfolio(model['id'], current_prices)
        positions = _enrich_positions(portfolio.get('positions', []), quotes, market_type)
        portfolio['positions'] = positions

        total_portfolio['total_value'] += portfolio.get('total_value', 0)
        total_portfolio['cash'] += portfolio.get('cash', 0)
        total_portfolio['positions_value'] += portfolio.get('positions_value', 0)
        total_portfolio['realized_pnl'] += portfolio.get('realized_pnl', 0)
        total_portfolio['unrealized_pnl'] += portfolio.get('unrealized_pnl', 0)
        total_portfolio['initial_capital'] += portfolio.get('initial_capital', 0)

        for pos in positions:
            instrument_key = pos.get('instrument_code') or pos['coin']
            key = f"{market_type}_{instrument_key}_{pos['side']}"
            if key not in all_positions:
                all_positions[key] = {
                    'coin': pos['coin'],
                    'instrument_code': instrument_key,
                    'side': pos['side'],
                    'market_type': market_type,
                    'quantity': 0,
                    'avg_price': 0,
                    'total_cost': 0,
                    'leverage': pos['leverage'],
                    'current_price': pos.get('current_price'),
                    'pnl': 0,
                    'board': pos.get('board'),
                    'suspension': bool(pos.get('suspension')),
                    'limit_up_price': pos.get('limit_up_price'),
                    'limit_down_price': pos.get('limit_down_price'),
                    'status_flags': pos.get('status_flags') or [],
                    'trading_status': pos.get('trading_status'),
                    'lot_size': pos.get('lot_size'),
                }

            current_pos = all_positions[key]
            current_cost = current_pos['quantity'] * current_pos['avg_price']
            new_cost = pos['quantity'] * pos['avg_price']
            total_quantity = current_pos['quantity'] + pos['quantity']

            if total_quantity > 0:
                current_pos['avg_price'] = (current_cost + new_cost) / total_quantity
                current_pos['quantity'] = total_quantity
                current_pos['total_cost'] = current_cost + new_cost
                price = pos.get('current_price') or 0
                current_pos['current_price'] = price
                current_pos['pnl'] = (price - current_pos['avg_price']) * total_quantity
                if not current_pos.get('board') and pos.get('board'):
                    current_pos['board'] = pos.get('board')
                if pos.get('suspension'):
                    current_pos['suspension'] = pos.get('suspension')
                if pos.get('limit_up_price') and not current_pos.get('limit_up_price'):
                    current_pos['limit_up_price'] = pos.get('limit_up_price')
                if pos.get('limit_down_price') and not current_pos.get('limit_down_price'):
                    current_pos['limit_down_price'] = pos.get('limit_down_price')
                if pos.get('status_flags'):
                    existing_flags = current_pos.get('status_flags') or []
                    new_flags = [flag for flag in pos.get('status_flags') if flag not in existing_flags]
                    if new_flags:
                        current_pos['status_flags'] = existing_flags + new_flags
                if pos.get('trading_status') and not current_pos.get('trading_status'):
                    current_pos['trading_status'] = pos.get('trading_status')
                if pos.get('lot_size') and not current_pos.get('lot_size'):
                    current_pos['lot_size'] = pos.get('lot_size')

    total_portfolio['positions'] = list(all_positions.values())

    chart_data = db.get_multi_model_chart_data(limit=100)

    return jsonify({
        'portfolio': total_portfolio,
        'chart_data': chart_data,
        'model_count': len(models)
    })

@app.route('/api/models/chart-data', methods=['GET'])
def get_models_chart_data():
    """Get chart data for all models"""
    limit = request.args.get('limit', 100, type=int)
    chart_data = db.get_multi_model_chart_data(limit=limit)
    return jsonify(chart_data)

@app.route('/api/market/prices', methods=['GET'])
def get_market_prices():
    market_type = request.args.get('market_type', 'crypto').lower()
    instruments = request.args.getlist('instruments')
    
    if market_type == 'a_share':
        if not instruments:
            return jsonify({'error': 'instruments parameter required for A-share market'}), 400
        quotes = market_fetcher.get_current_prices(instruments, market_type='a_share')
        return jsonify(quotes)
    
    if not instruments:
        instruments = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE']
    prices = market_fetcher.get_current_prices(instruments, market_type='crypto')
    return jsonify(prices)


@app.route('/api/markets/a-share/symbols', methods=['GET'])
def get_a_share_symbols():
    """List supported A-share instruments with board info"""
    try:
        board = request.args.get('board')
        symbols = market_fetcher.a_share_fetcher.list_symbols(board=board)
        return jsonify(symbols)
    except Exception as e:
        print(f"[ERROR] Failed to fetch A-share symbols: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/markets/<market_type>/status', methods=['GET'])
def get_market_status(market_type: str):
    """Get current market trading status (open/closed, holidays, next session)"""
    try:
        status = market_calendar.get_market_status(market_type)
        return jsonify(status)
    except Exception as e:
        print(f"[ERROR] Failed to fetch market status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>/execute', methods=['POST'])
def execute_trading(model_id):
    model = db.get_model(model_id)
    if not model:
        return jsonify({'error': 'Model not found'}), 404
    
    market_type = model.get('market_type', 'crypto')
    if not market_calendar.is_market_open(market_type):
        status = market_calendar.get_market_status(market_type)
        return jsonify({
            'error': f'Market {market_type} is currently closed',
            'market_status': status
        }), 400
    
    if model_id not in trading_engines:
        provider = db.get_provider(model['provider_id'])
        if not provider:
            return jsonify({'error': 'Provider not found'}), 404
        
        instruments = model.get('instruments') or market_fetcher.get_default_instruments(market_type)
        cash_currency = model.get('cash_currency', 'USD')

        trading_engines[model_id] = TradingEngine(
            model_id=model_id,
            db=db,
            market_fetcher=market_fetcher,
            market_calendar=market_calendar,
            market_type=market_type,
            instruments=instruments,
            cash_currency=cash_currency,
            market_config=model.get('market_config') or {},
            ai_trader=AITrader(
                api_key=provider['api_key'],
                api_url=provider['api_url'],
                model_name=model['model_name'],
                market_type=market_type,
                instruments=instruments
            ),
            trade_fee_rate=TRADE_FEE_RATE
        )
    
    try:
        result = trading_engines[model_id].execute_trading_cycle()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def trading_loop():
    print("[INFO] Trading loop started")
    
    while auto_trading:
        try:
            if not trading_engines:
                time.sleep(30)
                continue
            
            print(f"\n{'='*60}")
            print(f"[CYCLE] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"[INFO] Active models: {len(trading_engines)}")
            print(f"{'='*60}")
            
            for model_id, engine in list(trading_engines.items()):
                try:
                    market_type = getattr(engine, 'market_type', 'crypto')
                    status = market_calendar.get_market_status(market_type)
                    if not status.get('market_open', True):
                        reason = status.get('reason') or 'Closed'
                        next_open = status.get('next_open')
                        print(f"[SKIP] Model {model_id} ({market_type}) market closed: {reason} (next: {next_open})")
                        continue

                    print(f"\n[EXEC] Model {model_id} [{market_type}]")
                    result = engine.execute_trading_cycle()

                    if result.get('success'):
                        print(f"[OK] Model {model_id} completed")
                        if result.get('executions'):
                            for exec_result in result['executions']:
                                signal = exec_result.get('signal', 'unknown')
                                coin = exec_result.get('coin', 'unknown')
                                msg = exec_result.get('message', '')
                                if signal != 'hold':
                                    print(f"  [TRADE] {coin}: {msg}")
                    else:
                        error = result.get('error', 'Unknown error')
                        print(f"[WARN] Model {model_id} failed: {error}")

                except Exception as e:
                    print(f"[ERROR] Model {model_id} exception: {e}")
                    import traceback
                    print(traceback.format_exc())
                    continue
            
            print(f"\n{'='*60}")
            print(f"[SLEEP] Waiting 3 minutes for next cycle")
            print(f"{'='*60}\n")
            
            time.sleep(180)
            
        except Exception as e:
            print(f"\n[CRITICAL] Trading loop error: {e}")
            import traceback
            print(traceback.format_exc())
            print("[RETRY] Retrying in 60 seconds\n")
            time.sleep(60)
    
    print("[INFO] Trading loop stopped")

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    models = db.get_all_models()
    leaderboard = []
    
    for model in models:
        market_type = model.get('market_type', 'crypto')
        instruments = model.get('instruments') or market_fetcher.get_default_instruments(market_type)
        quotes = market_fetcher.get_current_prices(instruments, market_type=market_type)
        current_prices = {instrument: quotes[instrument].get('price', 0) for instrument in quotes}
        
        portfolio = db.get_portfolio(model['id'], current_prices)
        account_value = portfolio.get('total_value', model['initial_capital'])
        initial_cap = model['initial_capital']
        returns = ((account_value - initial_cap) / initial_cap) * 100 if initial_cap else 0
        
        leaderboard.append({
            'model_id': model['id'],
            'model_name': model['name'],
            'market_type': market_type,
            'account_value': account_value,
            'returns': returns,
            'initial_capital': initial_cap
        })
    
    leaderboard.sort(key=lambda x: x['returns'], reverse=True)
    return jsonify(leaderboard)

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get system settings"""
    try:
        settings = db.get_settings()
        return jsonify(settings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['PUT'])
def update_settings():
    """Update system settings"""
    try:
        data = request.json
        trading_frequency_minutes = int(data.get('trading_frequency_minutes', 60))
        trading_fee_rate = float(data.get('trading_fee_rate', 0.001))

        success = db.update_settings(trading_frequency_minutes, trading_fee_rate)

        if success:
            return jsonify({'success': True, 'message': 'Settings updated successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to update settings'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/version', methods=['GET'])
def get_version():
    """Get current version information"""
    return jsonify({
        'current_version': __version__,
        'github_repo': GITHUB_REPO_URL,
        'latest_release_url': LATEST_RELEASE_URL
    })

@app.route('/api/check-update', methods=['GET'])
def check_update():
    """Check for GitHub updates"""
    try:
        import requests

        # Get latest release from GitHub
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'AITradeGame/1.0'
        }

        # Try to get latest release
        try:
            response = requests.get(
                f"https://api.github.com/repos/{__github_owner__}/{__repo__}/releases/latest",
                headers=headers,
                timeout=5
            )

            if response.status_code == 200:
                release_data = response.json()
                latest_version = release_data.get('tag_name', '').lstrip('v')
                release_url = release_data.get('html_url', '')
                release_notes = release_data.get('body', '')

                # Compare versions
                is_update_available = compare_versions(latest_version, __version__) > 0

                return jsonify({
                    'update_available': is_update_available,
                    'current_version': __version__,
                    'latest_version': latest_version,
                    'release_url': release_url,
                    'release_notes': release_notes,
                    'repo_url': GITHUB_REPO_URL
                })
            else:
                # If API fails, still return current version info
                return jsonify({
                    'update_available': False,
                    'current_version': __version__,
                    'error': 'Could not check for updates'
                })
        except Exception as e:
            print(f"[WARN] GitHub API error: {e}")
            return jsonify({
                'update_available': False,
                'current_version': __version__,
                'error': 'Network error checking updates'
            })

    except Exception as e:
        print(f"[ERROR] Check update failed: {e}")
        return jsonify({
            'update_available': False,
            'current_version': __version__,
            'error': str(e)
        }), 500

def compare_versions(version1, version2):
    """Compare two version strings.

    Returns:
        1 if version1 > version2
        0 if version1 == version2
        -1 if version1 < version2
    """
    def normalize(v):
        # Extract numeric parts from version string
        parts = re.findall(r'\d+', v)
        # Pad with zeros to make them comparable
        return [int(p) for p in parts]

    v1_parts = normalize(version1)
    v2_parts = normalize(version2)

    # Pad shorter version with zeros
    max_len = max(len(v1_parts), len(v2_parts))
    v1_parts.extend([0] * (max_len - len(v1_parts)))
    v2_parts.extend([0] * (max_len - len(v2_parts)))

    # Compare
    if v1_parts > v2_parts:
        return 1
    elif v1_parts < v2_parts:
        return -1
    else:
        return 0

def init_trading_engines():
    try:
        models = db.get_all_models()

        if not models:
            print("[WARN] No trading models found")
            return

        print(f"\n[INIT] Initializing trading engines...")
        for model in models:
            model_id = model['id']
            model_name = model['name']

            try:
                provider = db.get_provider(model['provider_id'])
                if not provider:
                    print(f"  [WARN] Model {model_id} ({model_name}): Provider not found")
                    continue

                market_type = model.get('market_type', 'crypto')
                instruments = model.get('instruments') or market_fetcher.get_default_instruments(market_type)
                cash_currency = model.get('cash_currency', 'USD')

                trading_engines[model_id] = TradingEngine(
                    model_id=model_id,
                    db=db,
                    market_fetcher=market_fetcher,
                    market_calendar=market_calendar,
                    market_type=market_type,
                    instruments=instruments,
                    cash_currency=cash_currency,
                    market_config=model.get('market_config') or {},
                    ai_trader=AITrader(
                        api_key=provider['api_key'],
                        api_url=provider['api_url'],
                        model_name=model['model_name'],
                        market_type=market_type,
                        instruments=instruments
                    ),
                    trade_fee_rate=TRADE_FEE_RATE
                )
                print(f"  [OK] Model {model_id} ({model_name}) [{market_type}]")
            except Exception as e:
                print(f"  [ERROR] Model {model_id} ({model_name}): {e}")
                continue

        print(f"[INFO] Initialized {len(trading_engines)} engine(s)\n")

    except Exception as e:
        print(f"[ERROR] Init engines failed: {e}\n")

if __name__ == '__main__':
    import webbrowser
    import os
    
    print("\n" + "=" * 60)
    print("AITradeGame - Starting...")
    print("=" * 60)
    print("[INFO] Initializing database...")
    
    db.init_db()
    
    print("[INFO] Database initialized")
    print("[INFO] Initializing trading engines...")
    
    init_trading_engines()
    
    if auto_trading:
        trading_thread = threading.Thread(target=trading_loop, daemon=True)
        trading_thread.start()
        print("[INFO] Auto-trading enabled")
    
    print("\n" + "=" * 60)
    print("AITradeGame is running!")
    print("Server: http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    # 自动打开浏览器
    def open_browser():
        time.sleep(1.5)  # 等待服务器启动
        url = "http://localhost:5000"
        try:
            webbrowser.open(url)
            print(f"[INFO] Browser opened: {url}")
        except Exception as e:
            print(f"[WARN] Could not open browser: {e}")
    
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
