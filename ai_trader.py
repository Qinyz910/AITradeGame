import json
from typing import Dict, Optional
from openai import OpenAI, APIConnectionError, APIError

class AITrader:
    def __init__(
        self,
        api_key: str,
        api_url: str,
        model_name: str,
        market_type: str = 'crypto',
        instruments: Optional[list] = None
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name
        self.market_type = (market_type or 'crypto').lower()
        self.instruments = instruments or []
    
    def make_decision(
        self,
        market_state: Dict,
        portfolio: Dict,
        account_info: Dict,
        context: Optional[Dict] = None
    ) -> Dict:
        ctx = context or {}
        prompt = self._build_prompt(market_state, portfolio, account_info, ctx)
        
        response = self._call_llm(prompt)
        
        decisions = self._parse_response(response)
        
        return decisions
    
    def _build_prompt(
        self,
        market_state: Dict,
        portfolio: Dict,
        account_info: Dict,
        context: Optional[Dict] = None
    ) -> str:
        ctx = context or {}
        market_type = ctx.get('market_type', self.market_type)
        
        if market_type == 'a_share':
            asset_type = 'A-share stocks'
            role = 'professional Chinese A-share stock trader'
        else:
            asset_type = 'cryptocurrencies'
            role = 'professional cryptocurrency trader'
        
        prompt = f"""You are a {role}. Analyze the market and make trading decisions for {asset_type}.

MARKET DATA:
"""
        for symbol, data in market_state.items():
            price = data.get('price', 0)
            change = data.get('change_24h', 0)
            prompt += f"{symbol}: {price:.2f} ({change:+.2f}%)\n"
            if market_type == 'a_share':
                prompt += f"  Board: {data.get('board', 'n/a')}, Limit Up: {data.get('limit_up_price', 'n/a')}, Limit Down: {data.get('limit_down_price', 'n/a')}\n"
                fundamentals = data.get('fundamentals', {})
                if fundamentals:
                    details = ", ".join(
                        f"{key}:{value}" for key, value in fundamentals.items() if value not in (None, 0)
                    )
                    if details:
                        prompt += f"  Fundamentals: {details}\n"
            elif 'indicators' in data and data['indicators']:
                indicators = data['indicators']
                prompt += f"  SMA7: {indicators.get('sma_7', 0):.2f}, SMA14: {indicators.get('sma_14', 0):.2f}, RSI: {indicators.get('rsi_14', 0):.1f}\n"
        
        prompt += f"""

ACCOUNT STATUS:
- Initial Capital: {account_info['initial_capital']:.2f}
- Total Value: {portfolio['total_value']:.2f}
- Cash: {portfolio['cash']:.2f} {account_info.get('cash_currency', '')}
- Total Return: {account_info['total_return']:.2f}%

CURRENT POSITIONS:
"""
        if portfolio['positions']:
            for pos in portfolio['positions']:
                prompt += f"- {pos['coin']} {pos['side']}: {pos['quantity']:.4f} @ {pos['avg_price']:.2f} ({pos['leverage']}x)\n"
        else:
            prompt += "None\n"
        
        if market_type == 'a_share':
            prompt += """
TRADING RULES:
1. Signals: buy_to_enter (long), close_position, hold
2. Short selling is not permitted.
3. Respect daily limit up/down bands.
4. Avoid suspended securities; ensure liquidity considerations.
"""
        else:
            prompt += """
TRADING RULES:
1. Signals: buy_to_enter (long), sell_to_enter (short), close_position, hold
2. Risk Management:
   - Max 3 positions
   - Risk 1-5% per trade
   - Use appropriate leverage (1-20x)
3. Position Sizing:
   - Conservative: 1-2% risk
   - Moderate: 2-4% risk
   - Aggressive: 4-5% risk
4. Exit Strategy:
   - Close losing positions quickly
   - Let winners run
   - Use technical indicators
"""
        
        prompt += """
OUTPUT FORMAT (JSON only):
```json
{
  "INSTRUMENT": {
    "signal": "buy_to_enter|sell_to_enter|hold|close_position",
    "quantity": 0.5,
    "leverage": 1,
    "profit_target": 0.0,
    "stop_loss": 0.0,
    "confidence": 0.75,
    "justification": "Brief reason"
  }
}
```

Analyze and output JSON only.
"""
        
        return prompt
    
    def _call_llm(self, prompt: str) -> str:
        try:
            base_url = self.api_url.rstrip('/')
            if not base_url.endswith('/v1'):
                if '/v1' in base_url:
                    base_url = base_url.split('/v1')[0] + '/v1'
                else:
                    base_url = base_url + '/v1'
            
            client = OpenAI(
                api_key=self.api_key,
                base_url=base_url
            )
            
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional trader. Output JSON format only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            return response.choices[0].message.content
            
        except APIConnectionError as e:
            error_msg = f"API connection failed: {str(e)}"
            print(f"[ERROR] {error_msg}")
            raise Exception(error_msg)
        except APIError as e:
            error_msg = f"API error ({e.status_code}): {e.message}"
            print(f"[ERROR] {error_msg}")
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"LLM call failed: {str(e)}"
            print(f"[ERROR] {error_msg}")
            import traceback
            print(traceback.format_exc())
            raise Exception(error_msg)
    
    def _parse_response(self, response: str) -> Dict:
        response = response.strip()
        
        if '```json' in response:
            response = response.split('```json')[1].split('```')[0]
        elif '```' in response:
            response = response.split('```')[1].split('```')[0]
        
        try:
            decisions = json.loads(response.strip())
            return decisions
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON parse failed: {e}")
            print(f"[DATA] Response:\n{response}")
            return {}
