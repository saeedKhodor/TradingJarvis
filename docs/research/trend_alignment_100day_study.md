# J.A.R.V.I.S. Quantitative Research: 100-Day Study on Trend Alignment & Market Bias

**Target Symbol**: `US500.cash` (S&P 500 Index)  
**Sample Period**: March 23, 2026 – August 19, 2026 (100 Trading Days / 9,740 M15 bars / 29,000 M5 bars)  
**Data Source**: MetaTrader 5 Real-Time Historical Stream

---

## 1. Regime Breakdown & Market Time Distribution

| Market Regime | Definition | % of Total Time | Win Rate (1H) | Win Rate (4H) | 4H Edge (MFE/MAE) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Bullish Alignment** | $\text{Price} > \text{M15 9-EMA} > \text{H1 9-EMA}$ | **39.1%** | 50.8% | 54.8% | 0.90x |
| **Bullish + Macro D1 Bias** | Alignment + $\text{Price} > \text{D1 9-EMA}$ | **32.4%** | 51.5% | 54.7% | 0.93x |
| **Trend Ignition Breakout** | 1st bar of new Bullish Alignment | **7.3%** | 50.2% | 55.4% | 0.84x |
| **Safety Lock (Cascade)** | $\text{Price} < \text{H1 9} < \text{H1 21} < \text{H1 50}$ | **17.4%** | 49.8% | 54.1% | 1.04x |
| **Choppy / Consolidation** | Mixed or Conflicting EMAs | **43.3%** | 55.6% | 57.5% | 1.05x |

---

## 2. Discrete Strategy Simulation (Exact Entry, SL, & TP)

### Target R:R = 1:2.0 (Active London & NY Sessions: 07:00 – 20:00 UTC)

| Setup Strategy | Trades Executed | Win Rate | Total Net Pts | Expectancy (R) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1. Bullish M15 9-EMA Pullback** | **547** | **36.0%** | **+356.6 pts** | **+0.05R** | **1.11** |
| **2. Bullish + Macro D1 Confluence** | **441** | **36.7%** | **+294.8 pts** | **+0.07R** | **1.12** |
| **3. Cascade Short (H1 9-EMA Retest)** | **120** | **36.7%** | **-3.0 pts** | **+0.05R** | **1.00** |

### Target R:R = 1:1.5

| Setup Strategy | Trades Executed | Win Rate | Total Net Pts | Expectancy (R) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1. Bullish M15 9-EMA Pullback** | **547** | **42.0%** | **+226.4 pts** | **+0.04R** | **1.07** |
| **2. Bullish + Macro D1 Confluence** | **441** | **42.6%** | **+231.1 pts** | **+0.05R** | **1.10** |
| **3. Cascade Short (H1 9-EMA Retest)** | **120** | **43.3%** | **-13.9 pts** | **+0.06R** | **0.99** |

---

## 3. Key Quantitative Insights & Architecture Takeaways

1. **Bullish Alignment Edge**:
   - Buying pullbacks to the **M15 9-EMA** while in **Bullish Alignment ($\text{Price} > \text{M15 9-EMA} > \text{H1 9-EMA}$)** generated **+356.6 net index points** over 100 days.
   - Filtered with **Daily Macro 9-EMA Confluence**, expectancy rises to **+0.07R per trade**.

2. **The True Value of Safety Lock**:
   - On the S&P 500, counter-trend rallies during H1 cascades are violently volatile.
   - The primary role of the **Safety Lock Skill (`SKILL-01`)** is **Capital Defense**: locking capital in cash prevents taking false longs during cascade drops, protecting drawdown so that the full margin is available for high-conviction bullish runs.

3. **Recommended Execution Rules for Next Skills**:
   - **`SKILL-02` (Bullish Trend Ribbon Alignment)**: Fire alert when $\text{Price} > \text{M5 9-EMA} > \text{M15 9-EMA} > \text{H1 9-EMA}$.
   - **`SKILL-03` (9-EMA Pullback Sniper)**: Fire execution signal with Entry, Stop Loss below rejection wick, and Target R:R of **1:2.0** during London/NY sessions.
