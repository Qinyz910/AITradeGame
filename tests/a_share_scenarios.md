# A-share Trading Validation Scenarios

The following manual scenarios should be exercised (or automated) when validating the A-share trading engine updates:

- [ ] **T+1 Sell Restriction** – open a long position and attempt to close it within the same trading day; confirm the engine rejects the order and reports the stored `next_sellable_date`.
- [ ] **Holiday / Session Guardrails** – run a trading cycle during a known market holiday or outside trading hours and verify that A-share orders are skipped with the returned market status metadata.
- [ ] **Fee Model Accuracy** – execute both buy and sell trades and confirm the commission (0.03% with minimum 5 CNY), transfer fee (0.001%), and stamp duty on sells (0.1%) are recorded in `fee_details`, deducted from cash, and surfaced in portfolio and trade views.
