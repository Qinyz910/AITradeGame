from datetime import datetime
from typing import Dict, List
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
        cash_currency: str = 'USD'
    ):
        self.model_id = model_id
        self.db = db
        self.market_fetcher = market_fetcher
        self.ai_trader = ai_trader
        self.trade_fee_rate = trade_fee_rate
        self.market_calendar = market_calendar
        self.market_type = (market_type or 'crypto').lower()
        self.instruments = instruments or ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE']
        self.cash_currency = cash_currency or 'USD'
        self.coins = self.instruments
    
    def execute_trading_cycle(self) -> Dict:
        try:
            market_state = self._get_market_state()
            if not market_state:
                raise ValueError('Market state unavailable')
            
            current_prices = {instrument: market_state[instrument]['price'] for instrument in market_state}
            
            portfolio = self.db.get_portfolio(self.model_id, current_prices)
            
            account_info = self._build_account_info(portfolio)
            context = {
                'market_type': self.market_type,
                'cash_currency': self.cash_currency,
                'instruments': self.instruments
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
                'portfolio': updated_portfolio
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
        
        for instrument, decision in decisions.items():
            if instrument not in self.instruments:
                continue
            if instrument not in market_state:
                results.append({'coin': instrument, 'error': 'No market data available'})
                continue
            
            signal = decision.get('signal', '').lower()
            
            if self.market_type == 'a_share' and signal == 'sell_to_enter':
                results.append({'coin': instrument, 'error': 'Short selling not supported in A-share market'})
                continue
            
            try:
                if signal == 'buy_to_enter':
                    result = self._execute_buy(instrument, decision, market_state, portfolio)
                elif signal == 'sell_to_enter':
                    result = self._execute_sell(instrument, decision, market_state, portfolio)
                elif signal == 'close_position':
                    result = self._execute_close(instrument, decision, market_state, portfolio)
                elif signal == 'hold':
                    result = {'coin': instrument, 'signal': 'hold', 'message': 'Hold position'}
                else:
                    result = {'coin': instrument, 'error': f'Unknown signal: {signal}'}
                
                results.append(result)
                
            except Exception as e:
                results.append({'coin': instrument, 'error': str(e)})
        
        return results
    
    def _execute_buy(self, coin: str, decision: Dict, market_state: Dict, 
                    portfolio: Dict) -> Dict:
        quantity = float(decision.get('quantity', 0))
        leverage = int(decision.get('leverage', 1))
        if self.market_type == 'a_share':
            leverage = 1
        price = market_state[coin]['price']
        
        if quantity <= 0:
            return {'coin': coin, 'error': 'Invalid quantity'}
        
        trade_amount = quantity * price
        trade_fee = trade_amount * self.trade_fee_rate
        required_margin = (quantity * price) / leverage
        
        total_required = required_margin + trade_fee
        if total_required > portfolio['cash']:
            return {'coin': coin, 'error': 'Insufficient cash (including fees)'}
        
        # 更新持仓
        self.db.update_position(
            self.model_id, coin, quantity, price, leverage, 'long'
        )
        
        # 记录交易（包含交易费）
        self.db.add_trade(
            self.model_id, coin, 'buy_to_enter', quantity, 
            price, leverage, 'long', pnl=0, fee=trade_fee  # 新增fee参数
        )
        
        return {
            'coin': coin,
            'signal': 'buy_to_enter',
            'quantity': quantity,
            'price': price,
            'leverage': leverage,
            'fee': trade_fee,  # 返回费用信息
            'message': f'Long {quantity:.4f} {coin} @ ${price:.2f} (Fee: ${trade_fee:.2f})'
        }
    
    def _execute_sell(self, coin: str, decision: Dict, market_state: Dict, 
                 portfolio: Dict) -> Dict:
        quantity = float(decision.get('quantity', 0))
        leverage = int(decision.get('leverage', 1))
        price = market_state[coin]['price']
        
        if quantity <= 0:
            return {'coin': coin, 'error': 'Invalid quantity'}
        
        # 计算交易额和交易费
        trade_amount = quantity * price
        trade_fee = trade_amount * self.trade_fee_rate
        required_margin = (quantity * price) / leverage
        
        # 总需资金 = 保证金 + 交易费
        total_required = required_margin + trade_fee
        if total_required > portfolio['cash']:
            return {'coin': coin, 'error': 'Insufficient cash (including fees)'}
        
        # 更新持仓
        self.db.update_position(
            self.model_id, coin, quantity, price, leverage, 'short'
        )
        
        # 记录交易（包含交易费）
        self.db.add_trade(
            self.model_id, coin, 'sell_to_enter', quantity, 
            price, leverage, 'short', pnl=0, fee=trade_fee  # 新增fee参数
        )
        
        return {
            'coin': coin,
            'signal': 'sell_to_enter',
            'quantity': quantity,
            'price': price,
            'leverage': leverage,
            'fee': trade_fee,
            'message': f'Short {quantity:.4f} {coin} @ ${price:.2f} (Fee: ${trade_fee:.2f})'
        }
    
    def _execute_close(self, coin: str, decision: Dict, market_state: Dict, 
                    portfolio: Dict) -> Dict:
        position = None
        for pos in portfolio['positions']:
            if pos['coin'] == coin:
                position = pos
                break
        
        if not position:
            return {'coin': coin, 'error': 'Position not found'}
        
        current_price = market_state[coin]['price']
        entry_price = position['avg_price']
        quantity = position['quantity']
        side = position['side']
        
        # 计算平仓利润（未扣费）
        if side == 'long':
            gross_pnl = (current_price - entry_price) * quantity
        else:  # short
            gross_pnl = (entry_price - current_price) * quantity
        
        # 计算平仓交易费（按平仓时的交易额）
        trade_amount = quantity * current_price
        trade_fee = trade_amount * self.trade_fee_rate
        net_pnl = gross_pnl - trade_fee  # 净利润 = 毛利润 - 交易费
        
        # 关闭持仓
        self.db.close_position(self.model_id, coin, side)
        
        # 记录平仓交易（包含费用和净利润）
        self.db.add_trade(
            self.model_id, coin, 'close_position', quantity,
            current_price, position['leverage'], side, pnl=net_pnl, fee=trade_fee  # 新增fee参数
        )
        
        return {
            'coin': coin,
            'signal': 'close_position',
            'quantity': quantity,
            'price': current_price,
            'pnl': net_pnl,
            'fee': trade_fee,
            'message': f'Close {coin}, Gross P&L: ${gross_pnl:.2f}, Fee: ${trade_fee:.2f}, Net P&L: ${net_pnl:.2f}'
        }
