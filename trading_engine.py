from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
import json

class TradingEngine:
    def __init__(
        self,
        model_id: int,
        db,
        market_fetcher,
        ai_trader,
        trade_fee_rate: float = 0.001,
        market_calendar=None,
        market_type: str = 'crypto',
        instruments: List[str] = None,
        cash_currency: str = 'USD',
        market_config: Optional[Dict] = None
    ):
        self.model_id = model_id
        self.db = db
        self.market_fetcher = market_fetcher
        self.ai_trader = ai_trader
        self.market_calendar = market_calendar
        self.market_type = (market_type or 'crypto').lower()
        self.instruments = instruments or ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE']
        self.instruments = [instrument.upper() for instrument in self.instruments]
        self.market_config = market_config or {}
        self.cash_currency = cash_currency or ('CNY' if self.market_type == 'a_share' else 'USD')
        self.fee_model = self._resolve_fee_model(trade_fee_rate)
        self.trade_fee_rate = self.fee_model.get('trade_fee_rate', trade_fee_rate)
        self.lot_size = int(self.market_config.get('lot_size', 100 if self.market_type == 'a_share' else 1) or 1)
        self.lot_step = int(self.market_config.get('lot_step', self.lot_size if self.market_type == 'a_share' else 1) or 1)
        self.allow_partial_final_lot = bool(self.market_config.get('allow_partial_final_lot', True))
        self.coins = self.instruments
    
    def execute_trading_cycle(self) -> Dict:
        try:
            market_state = self._get_market_state()
            if not market_state:
                raise ValueError('Market state unavailable')
            
            current_prices = {
                instrument: market_state.get(instrument, {}).get('price', 0)
                for instrument in self.instruments
            }
            
            portfolio = self.db.get_portfolio(self.model_id, current_prices)
            market_status = self._get_market_status()
            
            if self.market_type == 'a_share' and not market_status.get('market_open', False):
                return {
                    'success': True,
                    'decisions': {},
                    'executions': [],
                    'portfolio': portfolio,
                    'market_status': market_status,
                    'message': f"A-share market closed: {market_status.get('reason') or 'Closed'}"
                }
            
            account_info = self._build_account_info(portfolio)
            context = {
                'market_type': self.market_type,
                'cash_currency': self.cash_currency,
                'instruments': self.instruments,
                'market_config': self.market_config,
                'market_status': market_status
            }
            
            decisions = self.ai_trader.make_decision(
                market_state, portfolio, account_info, context
            )
            
            self.db.add_conversation(
                self.model_id,
                user_prompt=self._format_prompt(market_state, portfolio, account_info),
                ai_response=json.dumps(decisions, ensure_ascii=False),
                cot_trace=''
            )
            
            execution_results = self._execute_decisions(decisions, market_state, portfolio)
            
            updated_portfolio = self.db.get_portfolio(self.model_id, current_prices)
            self.db.record_account_value(
                self.model_id,
                updated_portfolio['total_value'],
                updated_portfolio['cash'],
                updated_portfolio['positions_value']
            )
            
            return {
                'success': True,
                'decisions': decisions,
                'executions': execution_results,
                'portfolio': updated_portfolio,
                'market_status': market_status
            }
            
        except Exception as e:
            print(f"[ERROR] Trading cycle failed (Model {self.model_id}): {e}")
            import traceback
            print(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_market_state(self) -> Dict:
        market_state: Dict = {}
        prices = self.market_fetcher.get_current_prices(self.instruments, market_type=self.market_type)
        
        for instrument in self.instruments:
            if instrument not in prices:
                continue
            payload = prices[instrument].copy()
            payload['price'] = payload.get('price', 0)
            market_state[instrument] = payload
            if self.market_type == 'crypto':
                indicators = self.market_fetcher.calculate_technical_indicators(instrument)
                market_state[instrument]['indicators'] = indicators
            else:
                if 'board' not in payload and 'board' in prices[instrument]:
                    payload['board'] = prices[instrument].get('board')
                if 'change_24h' not in payload and 'change_pct' in payload:
                    payload['change_24h'] = payload.get('change_pct')
        
        return market_state
    
    def _build_account_info(self, portfolio: Dict) -> Dict:
        model = self.db.get_model(self.model_id)
        initial_capital = model['initial_capital']
        total_value = portfolio['total_value']
        total_return = ((total_value - initial_capital) / initial_capital) * 100 if initial_capital else 0
        
        return {
            'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_return': total_return,
            'initial_capital': initial_capital,
            'cash_currency': self.cash_currency
        }
    
    def _format_prompt(self, market_state: Dict, portfolio: Dict, 
                      account_info: Dict) -> str:
        return (
            f"Market {self.market_type.upper()} State: {len(market_state)} instruments, "
            f"Portfolio: {len(portfolio['positions'])} positions"
        )
    
    def _execute_decisions(self, decisions: Dict, market_state: Dict, 
                          portfolio: Dict) -> list:
        results = []
        if not decisions:
            return results
        current_prices = {
            instrument: market_state.get(instrument, {}).get('price', 0)
            for instrument in self.instruments
        }
        portfolio_snapshot = portfolio
        
        for instrument, decision in decisions.items():
            instrument_key = instrument.upper()
            if instrument_key not in self.instruments:
                results.append({'coin': instrument_key, 'error': 'Instrument not allowed', 'market_type': self.market_type})
                continue
            if instrument_key not in market_state:
                results.append({'coin': instrument_key, 'error': 'No market data available', 'market_type': self.market_type})
                continue
            
            signal = (decision.get('signal') or '').lower()
            if self.market_type == 'a_share':
                leverage_value = decision.get('leverage', 1)
                if float(leverage_value) != 1:
                    results.append({
                        'coin': instrument_key,
                        'signal': signal,
                        'error': 'Leverage is not supported for A-share trades',
                        'market_type': self.market_type
                    })
                    continue
                if signal == 'sell_to_enter':
                    results.append({
                        'coin': instrument_key,
                        'signal': signal,
                        'error': 'Short selling not supported in A-share market',
                        'market_type': self.market_type
                    })
                    continue
            
            try:
                if signal == 'buy_to_enter':
                    result = self._execute_buy(instrument_key, decision, market_state, portfolio_snapshot, current_prices)
                elif signal == 'sell_to_enter':
                    result = self._execute_sell(instrument_key, decision, market_state, portfolio_snapshot, current_prices)
                elif signal == 'close_position':
                    result = self._execute_close(instrument_key, decision, market_state, portfolio_snapshot, current_prices)
                elif signal == 'hold':
                    result = {
                        'coin': instrument_key,
                        'signal': 'hold',
                        'message': 'Hold position',
                        'market_type': self.market_type
                    }
                else:
                    result = {
                        'coin': instrument_key,
                        'signal': signal,
                        'error': f'Unknown signal: {signal}',
                        'market_type': self.market_type
                    }
            except Exception as e:
                result = {
                    'coin': instrument_key,
                    'signal': signal,
                    'error': str(e),
                    'market_type': self.market_type
                }
            else:
                if 'market_type' not in result:
                    result['market_type'] = self.market_type
            
            results.append(result)
            if not result.get('error'):
                portfolio_snapshot = self.db.get_portfolio(self.model_id, current_prices)
        
        return results
    
    def _execute_buy(self, coin: str, decision: Dict, market_state: Dict, 
                    portfolio: Dict, current_prices: Dict) -> Dict:
        if self.market_type == 'a_share':
            return self._execute_a_share_buy(coin, decision, market_state, portfolio, current_prices)
        return self._execute_crypto_buy(coin, decision, market_state, portfolio)
    
    def _execute_sell(self, coin: str, decision: Dict, market_state: Dict, 
                 portfolio: Dict, current_prices: Dict) -> Dict:
        return self._execute_crypto_sell(coin, decision, market_state, portfolio)
    
    def _execute_close(self, coin: str, decision: Dict, market_state: Dict, 
                    portfolio: Dict, current_prices: Dict) -> Dict:
        if self.market_type == 'a_share':
            return self._execute_a_share_close(coin, decision, market_state, portfolio, current_prices)
        return self._execute_crypto_close(coin, decision, market_state, portfolio)
    
    # ------------------------------------------------------------------
    # Crypto execution helpers
    # ------------------------------------------------------------------
    def _execute_crypto_buy(self, coin: str, decision: Dict, market_state: Dict, portfolio: Dict) -> Dict:
        quantity = float(decision.get('quantity', 0))
        if quantity <= 0:
            return {'coin': coin, 'error': 'Invalid quantity', 'market_type': self.market_type}
        leverage = int(decision.get('leverage', 1) or 1)
        leverage = max(leverage, 1)
        quote = market_state.get(coin, {}) or {}
        target_price = decision.get('price')
        try:
            price = float(target_price) if target_price else float(quote.get('price'))
        except (TypeError, ValueError):
            price = float(quote.get('price', 0) or 0)
        if price <= 0:
            return {'coin': coin, 'error': 'Market price unavailable', 'market_type': self.market_type}
        trade_amount = quantity * price
        trade_fee = trade_amount * self.trade_fee_rate
        required_margin = (quantity * price) / leverage
        total_required = required_margin + trade_fee
        if total_required > portfolio['cash']:
            return {'coin': coin, 'error': 'Insufficient cash (including fees)', 'market_type': self.market_type}
        self.db.update_position(
            self.model_id,
            coin,
            quantity,
            price,
            leverage,
            'long',
            instrument_code=coin,
            market_type=self.market_type,
            board=quote.get('board'),
            status_flags=quote.get('status_flags'),
            lot_size=quote.get('lot_size'),
            suspension=quote.get('suspension'),
            trading_status=quote.get('trading_status')
        )
        cash_after = portfolio['cash'] - total_required
        execution_dt = datetime.utcnow()
        trade_metadata = {'execution': 'market'}
        if quote.get('board'):
            trade_metadata['board'] = quote.get('board')
        self.db.add_trade(
            self.model_id,
            coin,
            'buy_to_enter',
            quantity,
            price,
            leverage,
            'long',
            pnl=0,
            fee=trade_fee,
            market_type=self.market_type,
            board=quote.get('board'),
            fee_details={'total': trade_fee},
            metadata=trade_metadata,
            cash_balance=cash_after,
            instrument_code=coin,
            trade_date=execution_dt.date().isoformat()
        )
        return {
            'coin': coin,
            'signal': 'buy_to_enter',
            'quantity': quantity,
            'price': price,
            'leverage': leverage,
            'fee': trade_fee,
            'cash_after': cash_after,
            'market_type': self.market_type,
            'message': f"Long {quantity:.4f} {coin} @ {self.cash_currency} {price:.2f} (Fee: {self.cash_currency} {trade_fee:.2f})"
        }
    
    def _execute_crypto_sell(self, coin: str, decision: Dict, market_state: Dict, portfolio: Dict) -> Dict:
        quantity = float(decision.get('quantity', 0))
        if quantity <= 0:
            return {'coin': coin, 'error': 'Invalid quantity', 'market_type': self.market_type}
        leverage = int(decision.get('leverage', 1) or 1)
        leverage = max(leverage, 1)
        quote = market_state.get(coin, {}) or {}
        target_price = decision.get('price')
        try:
            price = float(target_price) if target_price else float(quote.get('price'))
        except (TypeError, ValueError):
            price = float(quote.get('price', 0) or 0)
        if price <= 0:
            return {'coin': coin, 'error': 'Market price unavailable', 'market_type': self.market_type}
        trade_amount = quantity * price
        trade_fee = trade_amount * self.trade_fee_rate
        required_margin = (quantity * price) / leverage
        total_required = required_margin + trade_fee
        if total_required > portfolio['cash']:
            return {'coin': coin, 'error': 'Insufficient cash (including fees)', 'market_type': self.market_type}
        self.db.update_position(
            self.model_id,
            coin,
            quantity,
            price,
            leverage,
            'short',
            instrument_code=coin,
            market_type=self.market_type,
            board=quote.get('board'),
            status_flags=quote.get('status_flags'),
            lot_size=quote.get('lot_size'),
            suspension=quote.get('suspension'),
            trading_status=quote.get('trading_status')
        )
        cash_after = portfolio['cash'] - total_required
        execution_dt = datetime.utcnow()
        trade_metadata = {'execution': 'market'}
        if quote.get('board'):
            trade_metadata['board'] = quote.get('board')
        self.db.add_trade(
            self.model_id,
            coin,
            'sell_to_enter',
            quantity,
            price,
            leverage,
            'short',
            pnl=0,
            fee=trade_fee,
            market_type=self.market_type,
            board=quote.get('board'),
            fee_details={'total': trade_fee},
            metadata=trade_metadata,
            cash_balance=cash_after,
            instrument_code=coin,
            trade_date=execution_dt.date().isoformat()
        )
        return {
            'coin': coin,
            'signal': 'sell_to_enter',
            'quantity': quantity,
            'price': price,
            'leverage': leverage,
            'fee': trade_fee,
            'cash_after': cash_after,
            'market_type': self.market_type,
            'message': f"Short {quantity:.4f} {coin} @ {self.cash_currency} {price:.2f} (Fee: {self.cash_currency} {trade_fee:.2f})"
        }
    
    def _execute_crypto_close(self, coin: str, decision: Dict, market_state: Dict, portfolio: Dict) -> Dict:
        preferred_side = (decision.get('side') or 'long')
        position = self._find_position(portfolio, coin, side=preferred_side)
        if not position:
            # Try the opposite side (e.g., short positions)
            opposite_side = 'short' if preferred_side == 'long' else 'long'
            position = self._find_position(portfolio, coin, side=opposite_side)
        if not position:
            return {'coin': coin, 'error': 'Position not found', 'market_type': self.market_type}
        target_price = decision.get('price')
        try:
            current_price = float(target_price) if target_price else float(market_state[coin]['price'])
        except (TypeError, ValueError):
            current_price = float(market_state[coin]['price'])
        if current_price <= 0:
            return {'coin': coin, 'error': 'Market price unavailable', 'market_type': self.market_type}
        quantity = position['quantity']
        entry_price = position['avg_price']
        side = position['side']
        leverage = position.get('leverage', 1) or 1
        if side == 'long':
            gross_pnl = (current_price - entry_price) * quantity
        else:
            gross_pnl = (entry_price - current_price) * quantity
        trade_amount = quantity * current_price
        trade_fee = trade_amount * self.trade_fee_rate
        net_pnl = gross_pnl - trade_fee
        quote = market_state.get(coin, {}) or {}
        self.db.close_position(
            self.model_id,
            coin,
            side,
            instrument_code=coin,
            market_type=self.market_type
        )
        execution_dt = datetime.utcnow()
        trade_metadata = {'execution': 'market'}
        if quote.get('board'):
            trade_metadata['board'] = quote.get('board')
        self.db.add_trade(
            self.model_id,
            coin,
            'close_position',
            quantity,
            current_price,
            leverage,
            side,
            pnl=net_pnl,
            fee=trade_fee,
            market_type=self.market_type,
            board=quote.get('board'),
            fee_details={'total': trade_fee},
            metadata=trade_metadata,
            cash_balance=portfolio['cash'] + (trade_amount - trade_fee),
            instrument_code=coin,
            trade_date=execution_dt.date().isoformat()
        )
        return {
            'coin': coin,
            'signal': 'close_position',
            'quantity': quantity,
            'price': current_price,
            'pnl': net_pnl,
            'fee': trade_fee,
            'market_type': self.market_type,
            'message': (
                f"Close {coin}, Gross P&L: {self.cash_currency} {gross_pnl:.2f}, "
                f"Fee: {self.cash_currency} {trade_fee:.2f}, Net P&L: {self.cash_currency} {net_pnl:.2f}"
            )
        }
    
    # ------------------------------------------------------------------
    # A-share execution helpers
    # ------------------------------------------------------------------
    def _execute_a_share_buy(self, coin: str, decision: Dict, market_state: Dict, portfolio: Dict, current_prices: Dict) -> Dict:
        market_open, status = self._ensure_market_session_open()
        if not market_open:
            reason = status.get('reason') or 'Market closed'
            next_open = status.get('next_open')
            message = f"A-share market closed: {reason}"
            if next_open:
                message += f" (next session {next_open})"
            return {'coin': coin, 'error': message, 'market_type': self.market_type, 'market_status': status}
        quantity_raw = decision.get('quantity', 0)
        normalized_quantity, error = self._normalize_a_share_quantity(quantity_raw)
        if error:
            return {'coin': coin, 'error': error, 'market_type': self.market_type}
        quote = market_state.get(coin, {})
        target_price = decision.get('price')
        try:
            execution_price = float(target_price) if target_price else float(quote.get('price', 0))
        except (TypeError, ValueError):
            execution_price = float(quote.get('price', 0))
        if execution_price <= 0:
            return {'coin': coin, 'error': 'Price unavailable for order execution', 'market_type': self.market_type}
        limit_error = self._check_price_limits(quote, execution_price)
        if limit_error:
            return {'coin': coin, 'error': limit_error, 'market_type': self.market_type,
                    'limit_up_price': quote.get('limit_up_price'), 'limit_down_price': quote.get('limit_down_price')}
        trade_amount = normalized_quantity * execution_price
        fees = self._compute_a_share_fees(trade_amount, side='buy', quote=quote)
        total_fee_raw = fees['raw']['total']
        total_required = trade_amount + total_fee_raw
        if total_required > portfolio['cash']:
            return {'coin': coin, 'error': 'Insufficient cash (including fees)', 'market_type': self.market_type}
        existing_position = self._find_position(portfolio, coin, side='long')
        prev_quantity = existing_position['quantity'] if existing_position else 0
        prev_avg_price = existing_position['avg_price'] if existing_position else execution_price
        new_quantity = prev_quantity + normalized_quantity
        if new_quantity <= 0:
            return {'coin': coin, 'error': 'Invalid resulting position quantity', 'market_type': self.market_type}
        new_avg_price = ((prev_quantity * prev_avg_price) + (normalized_quantity * execution_price)) / new_quantity
        trade_datetime = self._get_market_datetime()
        last_buy_date = trade_datetime.date().isoformat()
        next_sellable_date = self.market_calendar.next_sellable_date('a_share', trade_datetime) if self.market_calendar else None
        position_metadata = dict(existing_position.get('metadata', {})) if existing_position else {}
        entry_fee_total = float(position_metadata.get('entry_fee_total', 0)) + total_fee_raw
        status_flags = []
        if quote.get('is_st'):
            status_flags.append('ST')
        if quote.get('suspension'):
            status_flags.append('SUSPENDED')
        quote_flags = quote.get('status_flags')
        if isinstance(quote_flags, str):
            quote_flags = [quote_flags]
        if isinstance(quote_flags, (list, tuple, set)):
            for flag in quote_flags:
                if flag and flag not in status_flags:
                    status_flags.append(flag)
        position_metadata.update({
            'entry_fee_total': entry_fee_total,
            'board': quote.get('board'),
            'limit_up_price': quote.get('limit_up_price'),
            'limit_down_price': quote.get('limit_down_price'),
            'last_buy_date': last_buy_date,
            'next_sellable_date': next_sellable_date,
            'market_type': self.market_type,
            'status_flags': status_flags
        })
        self.db.update_position(
            self.model_id,
            coin,
            new_quantity,
            new_avg_price,
            1,
            'long',
            metadata=position_metadata,
            last_buy_date=last_buy_date,
            next_sellable_date=next_sellable_date,
            instrument_code=coin,
            market_type=self.market_type,
            board=quote.get('board'),
            status_flags=status_flags or None,
            lot_size=quote.get('lot_size', self.lot_size),
            suspension=quote.get('suspension'),
            trading_status=quote.get('trading_status'),
            last_settlement_date=trade_datetime.date().isoformat()
        )
        try:
            fundamentals = quote.get('fundamentals') or {}
            self.db.upsert_instrument_metadata(
                coin,
                self.market_type,
                name=quote.get('name'),
                board=quote.get('board'),
                status_flags=status_flags or fundamentals.get('status_flags'),
                trading_status=quote.get('trading_status'),
                is_st=quote.get('is_st'),
                suspension=quote.get('suspension'),
                limit_up_price=quote.get('limit_up_price'),
                limit_down_price=quote.get('limit_down_price'),
                lot_size=quote.get('lot_size', self.lot_size),
                market_cap=fundamentals.get('market_cap'),
                pe=fundamentals.get('pe_dynamic') or fundamentals.get('pe'),
                pb=fundamentals.get('pb'),
                fundamentals=fundamentals,
                metadata={'updated_from': 'trading_engine_buy'}
            )
        except Exception:
            pass
        cash_after = portfolio['cash'] - total_required
        trade_metadata = {
            'limit_up_price': quote.get('limit_up_price'),
            'limit_down_price': quote.get('limit_down_price'),
            'board': quote.get('board'),
            'market_status': status,
            'next_sellable_date': next_sellable_date,
            'executed_at': trade_datetime.isoformat(),
            'status_flags': status_flags,
        }
        fee_details_record = {
            'commission': fees['commission'],
            'transfer_fee': fees['transfer_fee'],
            'stamp_duty': fees['stamp_duty'],
            'total': fees['total']
        }
        self.db.add_trade(
            self.model_id,
            coin,
            'buy_to_enter',
            normalized_quantity,
            execution_price,
            1,
            'long',
            pnl=0,
            fee=total_fee_raw,
            market_type=self.market_type,
            board=quote.get('board'),
            fee_details=fee_details_record,
            metadata=trade_metadata,
            cash_balance=cash_after,
            instrument_code=coin,
            trade_date=trade_datetime.date().isoformat()
        )
        message = (
            f"Buy {normalized_quantity} {coin} @ {self.cash_currency} {execution_price:.2f} "
            f"(Fees: {self.cash_currency} {fees['total']:.2f}, next sellable {next_sellable_date})"
        )
        return {
            'coin': coin,
            'signal': 'buy_to_enter',
            'quantity': normalized_quantity,
            'price': execution_price,
            'fees': fee_details_record,
            'board': quote.get('board'),
            'limit_up_price': quote.get('limit_up_price'),
            'limit_down_price': quote.get('limit_down_price'),
            'next_sellable_date': next_sellable_date,
            'cash_after': cash_after,
            'market_type': self.market_type,
            'message': message
        }
    
    def _execute_a_share_close(self, coin: str, decision: Dict, market_state: Dict, portfolio: Dict, current_prices: Dict) -> Dict:
        market_open, status = self._ensure_market_session_open()
        if not market_open:
            reason = status.get('reason') or 'Market closed'
            next_open = status.get('next_open')
            message = f"A-share market closed: {reason}"
            if next_open:
                message += f" (next session {next_open})"
            return {'coin': coin, 'error': message, 'market_type': self.market_type, 'market_status': status}
        position = self._find_position(portfolio, coin, side='long')
        if not position:
            return {'coin': coin, 'error': 'Position not found', 'market_type': self.market_type}
        position_quantity = float(position['quantity'])
        if position_quantity <= 0:
            return {'coin': coin, 'error': 'Position quantity is zero', 'market_type': self.market_type}
        requested_quantity = decision.get('quantity')
        allow_remainder = False
        if requested_quantity is None:
            normalized_quantity = int(round(position_quantity))
            allow_remainder = True
        else:
            allow_remainder = True
            normalized_quantity, error = self._normalize_a_share_quantity(
                requested_quantity,
                allow_remainder=True,
                max_quantity=position_quantity
            )
            if error:
                return {'coin': coin, 'error': error, 'market_type': self.market_type}
        if normalized_quantity > position_quantity:
            normalized_quantity = int(round(position_quantity))
        if normalized_quantity <= 0:
            return {'coin': coin, 'error': 'Invalid sell quantity', 'market_type': self.market_type}
        quote = market_state.get(coin, {})
        status_flags = []
        if quote.get('is_st'):
            status_flags.append('ST')
        if quote.get('suspension'):
            status_flags.append('SUSPENDED')
        quote_flags = quote.get('status_flags')
        if isinstance(quote_flags, str):
            quote_flags = [quote_flags]
        if isinstance(quote_flags, (list, tuple, set)):
            for flag in quote_flags:
                if flag and flag not in status_flags:
                    status_flags.append(flag)
        target_price = decision.get('price')
        try:
            execution_price = float(target_price) if target_price else float(quote.get('price', 0))
        except (TypeError, ValueError):
            execution_price = float(quote.get('price', 0))
        if execution_price <= 0:
            return {'coin': coin, 'error': 'Price unavailable for order execution', 'market_type': self.market_type}
        limit_error = self._check_price_limits(quote, execution_price)
        if limit_error:
            return {
                'coin': coin,
                'error': limit_error,
                'market_type': self.market_type,
                'limit_up_price': quote.get('limit_up_price'),
                'limit_down_price': quote.get('limit_down_price')
            }
        trade_datetime = self._get_market_datetime()
        next_sellable = position.get('next_sellable_date') or position.get('metadata', {}).get('next_sellable_date')
        if next_sellable:
            try:
                next_sellable_date = date.fromisoformat(next_sellable)
            except ValueError:
                next_sellable_date = None
        else:
            next_sellable_date = None
        if next_sellable_date and trade_datetime.date() < next_sellable_date:
            return {
                'coin': coin,
                'error': f"T+1 rule: next sellable date is {next_sellable}",
                'market_type': self.market_type,
                'next_sellable_date': next_sellable
            }
        trade_amount = normalized_quantity * execution_price
        fees = self._compute_a_share_fees(trade_amount, side='sell', quote=quote)
        total_fee_raw = fees['raw']['total']
        entry_price = position['avg_price']
        gross_pnl = (execution_price - entry_price) * normalized_quantity
        metadata = dict(position.get('metadata', {}))
        entry_fee_total = float(metadata.get('entry_fee_total', 0.0))
        allocated_entry_fee = entry_fee_total * (normalized_quantity / position_quantity)
        net_pnl_before_entry = gross_pnl - total_fee_raw
        net_pnl_after_entry = net_pnl_before_entry - allocated_entry_fee
        remaining_quantity = max(position_quantity - normalized_quantity, 0)
        if remaining_quantity <= 0:
            self.db.close_position(
                self.model_id,
                coin,
                'long',
                instrument_code=coin,
                market_type=self.market_type
            )
        else:
            remaining_quantity = float(int(round(remaining_quantity)))
            remaining_entry_fee = max(entry_fee_total - allocated_entry_fee, 0)
            metadata['entry_fee_total'] = remaining_entry_fee
            metadata['status_flags'] = status_flags
            self.db.update_position(
                self.model_id,
                coin,
                remaining_quantity,
                entry_price,
                1,
                'long',
                metadata=metadata,
                last_buy_date=position.get('last_buy_date'),
                next_sellable_date=position.get('next_sellable_date'),
                instrument_code=coin,
                market_type=self.market_type,
                board=quote.get('board'),
                status_flags=status_flags or metadata.get('status_flags'),
                lot_size=quote.get('lot_size', self.lot_size),
                suspension=quote.get('suspension'),
                trading_status=quote.get('trading_status'),
                last_settlement_date=trade_datetime.date().isoformat()
            )
        try:
            fundamentals = quote.get('fundamentals') or {}
            self.db.upsert_instrument_metadata(
                coin,
                self.market_type,
                name=quote.get('name'),
                board=quote.get('board'),
                status_flags=status_flags or fundamentals.get('status_flags'),
                trading_status=quote.get('trading_status'),
                is_st=quote.get('is_st'),
                suspension=quote.get('suspension'),
                limit_up_price=quote.get('limit_up_price'),
                limit_down_price=quote.get('limit_down_price'),
                lot_size=quote.get('lot_size', self.lot_size),
                market_cap=fundamentals.get('market_cap'),
                pe=fundamentals.get('pe_dynamic') or fundamentals.get('pe'),
                pb=fundamentals.get('pb'),
                fundamentals=fundamentals,
                metadata={'updated_from': 'trading_engine_close'}
            )
        except Exception:
            pass
        cash_after = portfolio['cash'] + (trade_amount - total_fee_raw)
        trade_metadata = {
            'limit_up_price': quote.get('limit_up_price'),
            'limit_down_price': quote.get('limit_down_price'),
            'board': quote.get('board'),
            'market_status': status,
            'next_sellable_date_before': next_sellable,
            'executed_at': trade_datetime.isoformat(),
            'allocated_entry_fee': allocated_entry_fee,
            'net_pnl_before_entry_fee': net_pnl_before_entry,
            'status_flags': status_flags,
        }
        fee_details_record = {
            'commission': fees['commission'],
            'transfer_fee': fees['transfer_fee'],
            'stamp_duty': fees['stamp_duty'],
            'total': fees['total']
        }
        self.db.add_trade(
            self.model_id,
            coin,
            'close_position',
            normalized_quantity,
            execution_price,
            1,
            'long',
            pnl=net_pnl_after_entry,
            fee=total_fee_raw,
            market_type=self.market_type,
            board=quote.get('board'),
            fee_details=fee_details_record,
            metadata=trade_metadata,
            cash_balance=cash_after,
            instrument_code=coin,
            trade_date=trade_datetime.date().isoformat()
        )
        message = (
            f"Sell {normalized_quantity} {coin} @ {self.cash_currency} {execution_price:.2f} "
            f"(Gross P&L {self.cash_currency} {gross_pnl:.2f}, Fees {self.cash_currency} {fees['total']:.2f}, "
            f"Entry fees allocated {self.cash_currency} {allocated_entry_fee:.2f}, Net P&L {self.cash_currency} {net_pnl_after_entry:.2f})"
        )
        return {
            'coin': coin,
            'signal': 'close_position',
            'quantity': normalized_quantity,
            'price': execution_price,
            'pnl': net_pnl_after_entry,
            'fees': fee_details_record,
            'board': quote.get('board'),
            'limit_up_price': quote.get('limit_up_price'),
            'limit_down_price': quote.get('limit_down_price'),
            'next_sellable_date_before': next_sellable,
            'cash_after': cash_after,
            'market_type': self.market_type,
            'message': message
        }
    
    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def _resolve_fee_model(self, trade_fee_rate: float) -> Dict:
        if self.market_type == 'a_share':
            defaults = {
                'commission_rate': 0.0003,
                'commission_min': self.market_config.get('commission_min', 5),
                'transfer_rate': 0.00001,
                'stamp_duty_rate': 0.001
            }
            config_fees = self.market_config.get('fees') or {}
            merged = {**defaults, **config_fees}
            return merged
        config_fees = self.market_config.get('fees') or {}
        fee_rate = config_fees.get('trade_fee_rate', trade_fee_rate)
        return {'trade_fee_rate': fee_rate}
    
    def _get_market_status(self) -> Dict:
        if not self.market_calendar:
            return {'market_type': self.market_type, 'market_open': True}
        try:
            return self.market_calendar.get_market_status(self.market_type)
        except Exception:
            return {'market_type': self.market_type, 'market_open': True}
    
    def _ensure_market_session_open(self) -> Tuple[bool, Dict]:
        status = self._get_market_status()
        is_open = status.get('market_open', True)
        return is_open, status
    
    def _get_market_datetime(self) -> datetime:
        status = self._get_market_status()
        server_time = status.get('server_time')
        if server_time:
            try:
                return datetime.fromisoformat(server_time.replace('Z', '+00:00'))
            except Exception:
                pass
        return datetime.now()
    
    def _normalize_a_share_quantity(self, quantity, allow_remainder: bool = False, max_quantity: Optional[float] = None) -> Tuple[Optional[int], Optional[str]]:
        try:
            qty_float = float(quantity)
        except (TypeError, ValueError):
            return None, 'Invalid quantity'
        if qty_float <= 0:
            return None, 'Invalid quantity'
        normalized = int(round(qty_float))
        if abs(qty_float - normalized) > 1e-4:
            return None, 'Quantity must be an integer number of shares'
        if allow_remainder and max_quantity is not None:
            max_int = int(round(max_quantity))
            if normalized >= max_int:
                return max_int, None
        min_lot = max(1, self.lot_size)
        lot_step = max(1, self.lot_step)
        if normalized < min_lot and not allow_remainder:
            return None, f'Quantity must be at least {min_lot} shares'
        if normalized < min_lot and allow_remainder and max_quantity is not None:
            max_int = int(round(max_quantity))
            if normalized == max_int:
                return normalized, None
        if normalized % lot_step != 0 and not (allow_remainder and max_quantity is not None and normalized >= int(round(max_quantity))):
            return None, f'Quantity must be a multiple of {lot_step}'
        return normalized, None
    
    def _check_price_limits(self, quote: Dict, price: float) -> Optional[str]:
        limit_up = quote.get('limit_up_price')
        limit_down = quote.get('limit_down_price')
        tolerance = float(self.market_config.get('price_limit_tolerance', 0))
        if limit_up is not None:
            if price > float(limit_up) * (1 + tolerance):
                return f'Price {price:.2f} exceeds daily limit-up {float(limit_up):.2f}'
        if limit_down is not None:
            if price < float(limit_down) * (1 - tolerance):
                return f'Price {price:.2f} below daily limit-down {float(limit_down):.2f}'
        return None
    
    def _compute_a_share_fees(self, trade_amount: float, side: str, quote: Dict) -> Dict:
        commission_rate = float(self.fee_model.get('commission_rate', 0.0003))
        commission_min = float(self.fee_model.get('commission_min', 0))
        transfer_rate = float(self.fee_model.get('transfer_rate', 0.00001))
        stamp_duty_rate = float(self.fee_model.get('stamp_duty_rate', 0.001)) if side == 'sell' else 0.0
        commission = trade_amount * commission_rate
        if commission_min > 0:
            commission = max(commission, commission_min) if trade_amount > 0 else 0
        transfer_fee = trade_amount * transfer_rate
        stamp_duty = trade_amount * stamp_duty_rate
        total = commission + transfer_fee + stamp_duty
        return {
            'commission': round(commission, 2),
            'transfer_fee': round(transfer_fee, 2),
            'stamp_duty': round(stamp_duty, 2),
            'total': round(total, 2),
            'raw': {
                'commission': commission,
                'transfer_fee': transfer_fee,
                'stamp_duty': stamp_duty,
                'total': total
            }
        }
    
    def _find_position(self, portfolio: Dict, coin: str, side: str = 'long') -> Optional[Dict]:
        for pos in portfolio.get('positions', []):
            if pos['coin'] == coin and (pos.get('side') or 'long') == side:
                return pos
        return self.db.get_position(self.model_id, coin, side)
