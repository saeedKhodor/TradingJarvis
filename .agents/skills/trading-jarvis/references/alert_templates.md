# J.A.R.V.I.S. Telegram Alert Templates

This reference contains the standard message templates used by J.A.R.V.I.S. when communicating trading events over Telegram.

---

## 1. Trade Signal Alert (`SIGNAL_ALERT`)

**Purpose**: Dispatched when a technical or quantitative strategy triggers an entry opportunity.

```html
📈 <b>J.A.R.V.I.S. TELEMETRY</b> | TRADE SIGNAL [XAUUSD]
<code>Timestamp: 2026-08-19 12:30:00 UTC</code>

<b>Signal Detected:</b> <code>BUY XAUUSD</code>
<b>Strategy:</b> Trend Pullback Engine (M15)
━━━━━━━━━━━━━━━━━━━━
🎯 <b>Entry Price:</b> <code>2350.25</code>
🛑 <b>Stop Loss:</b> <code>2342.00</code> (82.5 pips)
🎁 <b>Take Profit:</b> <code>2366.75</code> (165.0 pips)
⚖️ <b>Risk/Reward:</b> <code>1:2.00</code>
📊 <b>Estimated Risk:</b> <code>1.00% ($1,000.00)</code>

<i>Sir, all pre-flight confluence parameters have been satisfied. Awaiting order transmission.</i>
```

---

## 2. Order Execution Confirmation (`ORDER_EXECUTED`)

**Purpose**: Dispatched immediately when an order is filled on MetaTrader / broker.

```html
⚡ <b>J.A.R.V.I.S. TELEMETRY</b> | ORDER EXECUTED
<code>Timestamp: 2026-08-19 12:30:04 UTC</code>

<b>Order Type:</b> <code>BUY LIMIT FILLED</code>
<b>Ticket ID:</b> <code>#9482104</code>
<b>Instrument:</b> <code>EURUSD</code> | <b>Volume:</b> <code>2.50 Lots</code>
━━━━━━━━━━━━━━━━━━━━
🎯 <b>Fill Price:</b> <code>1.08542</code>
🛑 <b>SL:</b> <code>1.08200</code> | 🎁 <b>TP:</b> <code>1.09200</code>
⏱️ <b>Execution Latency:</b> <code>48ms</code>

<i>Sir, the position has been registered and active monitoring is engaged.</i>
```

---

## 3. Position Closed (`POSITION_CLOSED`)

**Purpose**: Dispatched when a trade hits TP, SL, or is manually liquidated.

```html
🎯 <b>J.A.R.V.I.S. TELEMETRY</b> | POSITION CLOSED [EURUSD]
<code>Timestamp: 2026-08-19 15:45:12 UTC</code>

<b>Outcome:</b> <code>TAKE PROFIT REACHED (WIN)</code>
<b>Ticket ID:</b> <code>#9482104</code>
━━━━━━━━━━━━━━━━━━━━
💵 <b>Net Profit:</b> <code>+$1,645.00 (+1.65%)</code>
📈 <b>Exit Price:</b> <code>1.09200</code>
⏳ <b>Trade Duration:</b> <code>3h 15m</code>
📊 <b>Updated Account Balance:</b> <code>$101,645.00</code>

<i>Sir, profit has been secured according to the trading plan.</i>
```

---

## 4. Risk / Drawdown Breach Advisory (`RISK_BREACH`)

**Purpose**: Dispatched when risk parameters or drawdown thresholds are challenged.

```html
🚨 <b>J.A.R.V.I.S. TELEMETRY</b> | RISK PROTOCOL [CRITICAL]
<code>Timestamp: 2026-08-19 16:10:00 UTC</code>

<b>Risk Advisory Level:</b> <code>CRITICAL (LEVEL 2)</code>
━━━━━━━━━━━━━━━━━━━━
📊 <b>Metric:</b> Daily Drawdown Threshold
📉 <b>Current Daily Loss:</b> <code>-$2,850.00 (-2.85%)</code>
🛑 <b>Hard Daily Limit:</b> <code>-$3,000.00 (-3.00%)</code>

💡 <b>Directive / Protocol:</b>
<i>Sir, daily loss limit is within 0.15% of hard stop. All automated new order entries have been suspended and trailing stops have been tightened to protect remaining capital.</i>
```

---

## 5. Daily / Session Briefing (`SESSION_BRIEFING`)

**Purpose**: Dispatched at the start or end of a major market session (London, New York, Tokyo).

```html
🌐 <b>J.A.R.V.I.S. TELEMETRY</b> | SESSION BRIEFING [New York Open]
<code>Timestamp: 2026-08-19 13:00:00 UTC</code>

<b>Trading Session:</b> <code>New York Opening Bell</code>
━━━━━━━━━━━━━━━━━━━━
💰 <b>Current Balance:</b> <code>$100,000.00</code>
📊 <b>Floating PnL:</b> <code>+$420.00</code>
📂 <b>Active Positions:</b> <code>1 (Long EURUSD)</code>

📋 <b>Diagnostics & Intelligence:</b>
• US CPI release scheduled in 30 minutes (High Volatility Expected).
• Algorithmic spreads are within normal tolerances (0.8 pips).
• All strategy daemons are online and synchronized.

<i>Sir, systems are prepared for the New York session.</i>
```
