import json
from typing import Any, Dict, Optional
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
        market_type = (ctx.get('market_type') or self.market_type).lower()
        cash_currency = ctx.get('cash_currency') or account_info.get('cash_currency') or 'USD'

        # NOTE: Crypto prompts retain legacy guidance while A-share prompts add mainland-specific rules and data.
        if market_type == 'a_share':
            return self._build_a_share_prompt(market_state, portfolio, account_info, cash_currency)

        return self._build_crypto_prompt(market_state, portfolio, account_info)

    def _build_a_share_prompt(
        self,
        market_state: Dict,
        portfolio: Dict,
        account_info: Dict,
        cash_currency: str
    ) -> str:
        def fmt_number(value: Any, decimals: int = 2) -> str:
            if value is None or value == '':
                return 'n/a'
            if isinstance(value, bool):
                return 'yes' if value else 'no'
            try:
                number = float(value)
            except (TypeError, ValueError):
                return str(value)
            if decimals == 0:
                return f"{number:,.0f}"
            return f"{number:,.{decimals}f}"

        def fmt_money(value: Any, decimals: int = 2) -> str:
            formatted = fmt_number(value, decimals)
            if formatted == 'n/a':
                return formatted
            return f"{formatted} {cash_currency}"

        def fmt_signed_percent(value: Any, decimals: int = 2) -> str:
            if value is None or value == '':
                return 'n/a'
            try:
                number = float(value)
            except (TypeError, ValueError):
                return str(value)
            return f"{number:+.{decimals}f}%"

        def fmt_percent(value: Any, decimals: int = 2) -> str:
            if value is None or value == '':
                return 'n/a'
            try:
                number = float(value)
            except (TypeError, ValueError):
                return str(value)
            return f"{number:.{decimals}f}%"

        lines = [
            "You are a professional Chinese A-share stock trader. Analyze the market and make trading decisions for A-share stocks.",
            "",
            "MARKET DATA:",
        ]

        for symbol, data in market_state.items():
            name = data.get('name')
            display_symbol = f"{symbol}{f' ({name})' if name else ''}"

            price = data.get('price')
            change_pct = data.get('change_pct', data.get('change_24h'))
            lines.append(
                f"{display_symbol}: {fmt_money(price, 2)} ({fmt_signed_percent(change_pct)})"
            )

            volume = data.get('volume') or data.get('turnover_volume')
            turnover = data.get('amount') or data.get('turnover')
            limit_up = data.get('limit_up_price')
            limit_down = data.get('limit_down_price')
            lines.append(
                "  "
                f"Volume: {fmt_number(volume, 0)}, "
                f"Turnover: {fmt_money(turnover, 0)}, "
                f"Limit Up: {fmt_money(limit_up, 2)}, "
                f"Limit Down: {fmt_money(limit_down, 2)}"
            )

            suspension_raw = data.get('suspension_status', data.get('suspension'))
            if isinstance(suspension_raw, str):
                suspension_text = suspension_raw
            elif suspension_raw is True:
                suspension_text = 'Suspended'
            elif suspension_raw is False:
                suspension_text = 'Active'
            else:
                suspension_text = 'Unknown'

            st_flag = data.get('is_st')
            if isinstance(st_flag, bool):
                st_text = 'ST/*ST' if st_flag else 'Normal'
            else:
                st_text = str(st_flag) if st_flag not in (None, '') else 'Normal'

            status_line = (
                f"  Status: {suspension_text}; Board: {data.get('board', 'n/a')}; "
                f"ST Flag: {st_text}"
            )
            next_sellable = data.get('next_sellable_date')
            if next_sellable:
                status_line += f"; Next sellable date: {next_sellable}"
            lines.append(status_line)

            fundamentals = data.get('fundamentals') or {}
            fundamental_bits = []
            fundamentals_map = [
                ('Market Cap', 'market_cap', 0, 'money'),
                ('Float Cap', 'float_market_cap', 0, 'money'),
                ('PE (dynamic)', 'pe_dynamic', 2, 'number'),
                ('PE (static)', 'pe_static', 2, 'number'),
                ('PB', 'pb', 2, 'number'),
                ('Turnover Rate', 'turnover_rate', 2, 'percent'),
                ('Amplitude', 'amplitude', 2, 'percent'),
            ]
            for label, key, decimals, fmt_type in fundamentals_map:
                value = fundamentals.get(key)
                if value in (None, '', 0):
                    continue
                if fmt_type == 'money':
                    fundamental_bits.append(f"{label}: {fmt_money(value, decimals)}")
                elif fmt_type == 'percent':
                    fundamental_bits.append(f"{label}: {fmt_percent(value, decimals)}")
                else:
                    fundamental_bits.append(f"{label}: {fmt_number(value, decimals)}")
            if fundamental_bits:
                lines.append(f"  Fundamentals: {', '.join(fundamental_bits)}")

        lines.extend(
            [
                "",
                "ACCOUNT STATUS:",
                f"- Initial Capital: {account_info['initial_capital']:.2f}",
                f"- Total Value: {portfolio['total_value']:.2f}",
                f"- Cash: {portfolio['cash']:.2f} {account_info.get('cash_currency', cash_currency)}",
                f"- Total Return: {account_info['total_return']:.2f}%",
                "",
                "CURRENT POSITIONS:",
            ]
        )

        if portfolio['positions']:
            for pos in portfolio['positions']:
                qty = pos.get('quantity', 0)
                avg_price = pos.get('avg_price', 0)
                annotations = []
                if pos.get('board'):
                    annotations.append(f"Board: {pos['board']}")
                if pos.get('suspension'):
                    annotations.append('Suspended')
                if pos.get('next_sellable_date'):
                    annotations.append(f"Next sellable: {pos['next_sellable_date']}")
                annotation_text = f" ({', '.join(annotations)})" if annotations else ''
                lines.append(
                    f"- {pos['coin']} {pos['side']}: {qty:.0f} shares @ {avg_price:.2f}{annotation_text}"
                )
        else:
            lines.append('None')

        lines.append(
            """
TRADING RULES:
1. Signals: buy_to_enter (long), close_position, hold
2. Short selling, margin trading, and leverage are ignored for A-shares.
3. Respect daily price limits (±10% regular, ±5% for ST) and avoid suspended securities.
4. Orders must be submitted in board lots of 100 shares; size decisions must reflect this.
5. T+1 rules apply: positions sold today can only be repurchased on the next trading day.
6. Use liquidity, board classification, and fundamentals when justifying trades.
""".strip()
        )

        lines.append(
            """
OUTPUT FORMAT (JSON only):
```json
{
  "600519.SH": {
    "signal": "buy_to_enter|close_position|hold",
    "quantity": 100,
    "leverage": 1,
    "market": "a_share",
    "profit_target": 0.0,
    "stop_loss": 0.0,
    "confidence": 0.75,
    "justification": "Brief reason"
  }
}
```
- Quantity must be a multiple of 100 shares (board lot).
- Ignore leverage adjustments; keep leverage as 1 for A-share trades.
- Include a "market" field when it aids instrument clarity.
Return JSON only.
""".strip()
        )

        return "\n".join(lines)

    def _build_crypto_prompt(
        self,
        market_state: Dict,
        portfolio: Dict,
        account_info: Dict
    ) -> str:
        prompt = """You are a professional cryptocurrency trader. Analyze the market and make trading decisions for cryptocurrencies.

MARKET DATA:
"""
        for symbol, data in market_state.items():
            price = data.get('price', 0)
            change = data.get('change_24h', 0)
            prompt += f"{symbol}: {price:.2f} ({change:+.2f}%)\n"
            if 'indicators' in data and data['indicators']:
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
        response = (response or '').strip()
        if not response:
            return {}

        cleaned = response
        if '```json' in cleaned:
            cleaned = cleaned.split('```json', 1)[1]
            cleaned = cleaned.split('```', 1)[0]
        elif '```' in cleaned:
            cleaned = cleaned.split('```', 1)[1]
            cleaned = cleaned.split('```', 1)[0]
        cleaned = cleaned.strip()

        candidates = []
        if cleaned:
            candidates.append(cleaned)
        start = cleaned.find('{') if cleaned else -1
        end = cleaned.rfind('}') if cleaned else -1
        if start != -1 and end != -1 and end > start:
            candidate = cleaned[start:end + 1]
            if candidate not in candidates:
                candidates.append(candidate)
        if response and response not in candidates:
            candidates.append(response)

        for candidate in candidates:
            try:
                parsed = json.loads(candidate.strip())
                decisions = self._normalize_decisions_payload(parsed)
                if decisions:
                    return decisions
                if isinstance(parsed, dict) and parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        print(f"[ERROR] JSON parse failed: Unable to decode response")
        print(f"[DATA] Response:\n{response}")
        return {}

    def _normalize_decisions_payload(self, payload: Any) -> Dict:
        if isinstance(payload, dict):
            decisions = payload.get('decisions')
            if isinstance(decisions, dict):
                return decisions
            return payload
        if isinstance(payload, list):
            normalized: Dict[str, Dict] = {}
            for item in payload:
                if not isinstance(item, dict):
                    continue
                symbol = item.get('instrument') or item.get('symbol') or item.get('ticker')
                if not symbol:
                    continue
                entry = item.copy()
                entry.pop('instrument', None)
                entry.pop('symbol', None)
                entry.pop('ticker', None)
                normalized[str(symbol)] = entry
            if normalized:
                return normalized
        return {}
