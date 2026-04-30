# 🤖 AUTOMATED TRADING BOT - MASTER DOCUMENT
**Last Updated:** April 30, 2026  
**Version:** 3.1 - "Beyond Human"  
**Owner:** Kushagra Upadhyay

---

## 📋 QUICK CONTEXT FOR NEW CHATS

> I'm building an automated intraday trading bot for Indian stock market (NSE) using Fyers API. The bot uses Python and trades 5-minute candles with multi-indicator strategy. Currently testing with paper trading (₹100,000 virtual). Goal is to make ₹1,000+/month with ₹10,000 real capital after 2 weeks testing. Bot monitors **150 stocks** across 18 sectors with database persistence, smart exits, trailing stops, cooldown system, and a live Streamlit dashboard.

---

## 🎯 PROJECT GOALS

### Primary Goal:
- **Make ₹1,000/month** to cover half of Claude subscription

### Secondary Goals:
- Build experience with algorithmic trading
- Eventually scale to US markets (IBKR) and crypto
- Leverage bot superpowers humans can't match

### Capital Plan:
- **Week 1-2:** Paper trading (₹100,000 virtual)
- **Week 3+:** Real trading with ₹10,000
- **Month 2+:** Scale to ₹20,000-₹50,000

---

## 📊 CURRENT STATUS

### Strategy Version:
**v3.1 - "Beyond Human"** (Latest)

### Key Features:
✅ Multi-timeframe confluence (5m, 15m, 50 EMA)  
✅ Volatility-adjusted stop loss (2x ATR)  
✅ 45-minute cooldown after stop loss  
✅ Trailing stops + breakeven protection  
✅ 1:2.5 Risk:Reward ratio  
✅ SQLite database for persistent learning  
✅ Smart exit management (6 layers)  
✅ **150 stocks across 18 sectors** (v3.1)  
✅ **Streamlit live dashboard** (v3.1)  
✅ **5-minute scan cycle** aligned to candle timeframe (v3.1)  

### Testing Results:
- **April 29, 2026:**
  - Strategy v2: 12 trades, 41.7% win rate, -₹631 loss
  - Issues: Tight SL (hit in 1 min), repeat signals (6x on same stock)
  - Improvements made → v3.0 created
- **April 30, 2026:**
  - Watchlist expanded 5 → 150 stocks
  - Dashboard added for real-time monitoring

### Expected Performance (v3.1):
- Win Rate: 55-65%
- Trades/Day: 2-5 (more opportunities with 150 stocks)
- Daily Profit: ₹150-₹250 (with ₹10k capital)
- Monthly: ₹3,000-₹5,000

---

## 🏦 BROKER DETAILS

**Broker:** Fyers  
**Account Type:** Individual  
**Trading Type:** Intraday (MIS)  
**Authentication:** External TOTP using pyotp library  

> ⚠️ **Credentials are stored in `.env` file only — never commit `.env` to Git.**  
> See `.env.example` for the required format.

---

## 📁 PROJECT STRUCTURE

```
C:\Users\kushagra\Trading Bot\fyers_bot\
│
├── venv\                      # Virtual environment (gitignored)
├── .env                       # Credentials — DO NOT COMMIT (gitignored)
│
├── auth.py                    # TOTP-based Fyers authentication
├── data.py                    # Historical/live data fetcher
├── strategy.py                # Trading strategy (v3.1 - Beyond Human)
├── orders.py                  # Order placement (paper/live)
├── risk_manager.py            # Position sizing & risk limits
├── run.py                     # Main bot loop with smart exits
├── database.py                # SQLite persistence
├── stocks_config.py           # ★ 150 stocks across 18 sectors (single source of truth)
├── dashboard.py               # ★ Streamlit live monitoring dashboard
│
├── trading_bot.db             # SQLite database (auto-created, gitignored)
├── trading_bot.log            # Log file (gitignored)
└── Readme.md                  # This file
```

---

## 📦 INSTALLED PACKAGES

```
fyers-apiv3==3.3.2
pyotp==2.9.0
python-dotenv==1.0.0
pandas==2.1.4
numpy==1.26.2
ta-lib==0.4.28
streamlit
plotly
```

**Install command:**
```bash
pip install fyers-apiv3 pyotp python-dotenv pandas numpy TA-Lib streamlit plotly --user
```

---

## 🎯 TRADING STRATEGY v3.1 - "BEYOND HUMAN"

### Philosophy:
Leverage bot capabilities humans cannot match:
- 150 stocks scanned in parallel every 5 minutes
- Microsecond calculations across 18 sectors
- Perfect discipline (no emotions)
- Persistent memory across days
- Multi-timeframe simultaneous analysis
- Sector strength correlation (trade the strongest sector)

### Entry Criteria (ALL must be TRUE):

**Time Filters:**
- ❌ NOT 9:15-9:45 AM (too volatile)
- ❌ NOT 11:30 AM-1:00 PM (lunch hour)
- ❌ NOT after 2:45 PM (pre-close)

**Cooldown Filter:**
- ❌ NOT in 45-min cooldown (after recent SL hit)

**Multi-Timeframe Confluence:**
- ✅ 5-min: EMA(9) crossover EMA(21)
- ✅ 15-min: EMA trend aligned
- ✅ 50 EMA: Long-term trend aligned

**Technical Conditions (for BUY):**
1. ✅ Multi-timeframe bullish
2. ✅ Price > VWAP
3. ✅ Supertrend = UPTREND
4. ✅ RSI 45-65 (healthy momentum)
5. ✅ Volume > 2.0x average (strong confirmation)
6. ✅ Trend strength > 0.3%
7. ✅ Last 2 candles bullish
8. ✅ Volatility < 2% (not too choppy)

**For SELL:** Opposite conditions

### Stop Loss Calculation:
**Volatility-Adjusted (2x ATR)**
- Prevents SL hunting
- Adapts to stock's volatility
- Typical: 0.5-1.0% from entry

### Target Calculation:
**1:2.5 Risk:Reward**
- Only needs 40% win rate to break even
- Better than old 1:2 ratio

### Position Sizing:
- **Risk per trade:** 2% of capital
- **Max positions:** 3 concurrent
- **Max daily loss:** 5% of capital

---

## 📈 STOCKS MONITORED (150 Total)

All stocks defined in `stocks_config.py` — edit that file to add/remove stocks.

| Sector | Count | Key Stocks |
|--------|-------|------------|
| Banking | 14 | SBIN, HDFCBANK, ICICIBANK, KOTAKBANK, AXISBANK |
| IT | 12 | INFY, TCS, WIPRO, HCLTECH, TECHM, LTIM |
| Infra/CapGoods | 14 | LT, NTPC, POWERGRID, HAL, BEL, ADANIPORTS |
| Auto | 12 | TATAMOTORS, MARUTI, M&M, BAJAJ-AUTO, EICHERMOT |
| Pharma | 12 | SUNPHARMA, DRREDDY, CIPLA, LUPIN, DIVISLAB |
| Finance/NBFC | 11 | BAJFINANCE, BAJAJFINSV, CHOLAFIN, PFC, RECLTD |
| FMCG | 10 | ITC, HINDUNILVR, BRITANNIA, DABUR, TATACONSUM |
| Metals/Mining | 9 | TATASTEEL, JSWSTEEL, HINDALCO, SAIL, VEDL |
| Oil & Gas | 7 | RELIANCE, ONGC, IOC, BPCL, GAIL |
| Consumer Durables | 7 | TITAN, HAVELLS, DIXON, POLYCAB, TATAELXSI |
| Retail/Consumer | 8 | DMART, TRENT, ZOMATO, IRCTC, JUBLFOOD |
| Cement | 6 | ULTRACEMCO, GRASIM, AMBUJACEM, ACC |
| Chemicals | 6 | PIDILITIND, SRF, DEEPAKNTR, NAVINFLUOR |
| Insurance | 5 | HDFCLIFE, SBILIFE, ICICIPRULI, STARHEALTH |
| Realty | 4 | DLF, GODREJPROP, OBEROIRLTY, PRESTIGE |
| Paints | 4 | ASIANPAINT, BERGEPAINT, INDIGOPNTS, KANSAINER |
| Telecom | 2 | BHARTIARTL, TATACOMM |
| Misc | 7 | ADANIGREEN, IEX, SUPREMEIND, SCHAEFFLER |

> To add/remove stocks, edit `stocks_config.py`. Changes apply automatically on next bot restart.

---

## 📊 LIVE DASHBOARD

A Streamlit dashboard is available for real-time monitoring — no more copy-pasting logs!

### Run the dashboard:
```bash
# In a separate terminal (keep it running alongside run.py)
python -m streamlit run dashboard.py
```
Opens at **http://localhost:8501**

### Dashboard Pages:
| Page | What it shows |
|------|--------------|
| Overview | Capital, P&L, win rate, active positions, cooldowns, growth chart |
| Trade History | Full trade log with filters by symbol/side/exit reason |
| Symbol Performance | Best/worst stocks, P&L by sector chart |
| Active Positions | Live positions with SL, target, breakeven & trailing stop status |
| Signals | Every signal generated — executed or filtered |
| Log Viewer | Live tail of trading_bot.log with keyword search & error counts |

Auto-refreshes every 30 seconds while the bot runs.

---

## 🚪 EXIT MANAGEMENT (6 Layers)

**Layer 1: Stop Loss Hit** — Exit immediately, add 45-min cooldown  
**Layer 2: Breakeven Protection** — At 50% to target → move SL to entry (risk-free)  
**Layer 3: Trailing Stop** — After 1:1 reward → trail SL at 50% of profit  
**Layer 4: Profit Giveback** — If lose 50% of max profit → exit  
**Layer 5: Time Exit** — After 60 minutes → take any profit  
**Layer 6: EOD Exit** — 3:15 PM → close all positions (no overnight risk)  

---

## 🗄️ DATABASE SCHEMA

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `trades` | Full trade history | symbol, side, entry/exit price, pnl, exit_reason |
| `active_positions` | Live open trades | entry_price, stop_loss, target, trailing state |
| `signals` | Every signal generated | symbol, signal_type, strength, executed |
| `cooldowns` | 45-min blocks after SL | symbol, cooldown_until, reason |
| `daily_stats` | Daily P&L summary | date, capital, total_pnl, win_rate |
| `symbol_performance` | Per-stock stats | total_trades, win_rate, avg_win, avg_loss |
| `bot_state` | Bot config/state | key-value pairs (capital, paper_trading mode) |

---

## 🐛 KNOWN ISSUES & FIXES

| # | Issue | Status | Solution |
|---|-------|--------|----------|
| 1 | SL too tight — hit in 1 minute | ✅ Fixed | 2x ATR volatility-adjusted stop |
| 2 | Repeat signals — same stock 6x | ✅ Fixed | 45-min cooldown after SL hit |
| 3 | Poor R:R — needed 50% win rate | ✅ Fixed | 1:2.5 RR needs only 40% |
| 4 | Holding too long | ✅ Fixed | 60-min time exit + trailing stops |
| 5 | Only 5 stocks — few signals | ✅ Fixed | 150 stocks across 18 sectors |
| 6 | Manual log copy-paste to Claude | ✅ Fixed | Streamlit dashboard + folder access |
| 7 | Data fetch error -99 (SBIN) | ⚠️ Pending | Need graceful retry logic |

---

## 🚀 HOW TO RUN

### Daily Startup (9:10 AM):
```bash
cd "C:\Users\kushagra\Trading Bot\fyers_bot"

# Terminal 1 — Trading bot
python run.py

# Terminal 2 — Dashboard (optional but recommended)
python -m streamlit run dashboard.py
```

### What Happens:
1. Loads credentials from `.env`
2. Authenticates with Fyers (TOTP)
3. Paste the redirect URL when prompted
4. Bot starts scanning 150 stocks at 9:15 AM
5. Scans every 5 minutes, trades automatically
6. Dashboard updates every 30 seconds
7. All positions closed by 3:15 PM

### To Stop:
Press **Ctrl+C** — bot saves all state to database and can resume cleanly.

---

## 📊 PERFORMANCE TRACKING

### Key Metrics:
1. **Win Rate** — target 55-65%
2. **Daily P&L** — target ₹150-₹250 with ₹10k
3. **Max Drawdown** — should stay < 5%
4. **Trades/Day** — target 2-5 (higher with 150 stocks)
5. **Best Sector** — rotate focus toward strongest
6. **Worst Stock** — candidates for removal from watchlist

### Go-Live Checklist (after 2 weeks paper):
- [ ] Win rate consistently > 55%
- [ ] No single stock causing repeated losses
- [ ] Cooldown system firing correctly
- [ ] Trailing stops activating on winners
- [ ] Dashboard showing healthy metrics
- [ ] Decide: continue paper or switch to real ₹10k

---

## 💰 CAPITAL PROJECTIONS

### With ₹10,000 Real Capital:

| Timeframe | Target | ROI |
|-----------|--------|-----|
| Daily | ₹150-₹250 | 1.5-2.5% |
| Weekly | ₹750-₹1,250 | 7.5-12.5% |
| Monthly | ₹3,000-₹5,000 | 30-50% |

### Growth Plan:
- Month 1: ₹10k → ₹13.5k
- Month 2: ₹13.5k → ₹18k
- Month 3: ₹18k → ₹24k
- Month 6: ₹10k → ₹50k+ (compounding)

---

## 🌍 FUTURE EXPANSION

| Phase | Market | Broker | Capital | Expected Monthly |
|-------|--------|--------|---------|-----------------|
| 1 (Now) | NSE India | Fyers | ₹10k | ₹3k-₹5k |
| 2 (Month 3-4) | US Stocks | IBKR | $500 | ₹40k-₹1.5L |
| 3 (Month 3-4) | Crypto | CoinDCX/Binance | ₹5k-₹10k | ₹15k-₹80k |
| 4 (Month 5+) | MCX Commodities | Fyers | ₹50k+ | ₹10k-₹50k |

**Ultimate Goal:** 4 bots running = ₹72,000+/month

---

## 🔧 TROUBLESHOOTING

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | `pip install [module] --user` |
| `Authentication failed` | Check `.env` credentials; paste redirect URL within 30 sec |
| `No signals generated` | Market choppy, or all in cooldown — check dashboard |
| `streamlit not recognized` | Use `python -m streamlit run dashboard.py` |
| `pip permission error` | Add `--user` flag to pip install |
| Bot keeps losing | Check win rate on dashboard; reduce position size; back to paper |
| Database errors | Delete `trading_bot.db` to recreate fresh |

---

## 📞 QUICK REFERENCE

```bash
# Run bot
python run.py

# Run dashboard
python -m streamlit run dashboard.py

# Check stock count
python stocks_config.py

# Test individual modules
python auth.py
python strategy.py
python database.py
```

**Trading Hours:**
- Market Open: 9:15 AM IST
- Bot Trades: 9:45 AM – 2:45 PM
- EOD Exit: 3:15 PM (auto)
- Market Close: 3:30 PM IST

---

## 📝 LESSONS LEARNED

1. **Paper trade first** — always test before risking real money
2. **Wide stops** — 2x ATR works better than tight Supertrend stops
3. **Cooldown system** — don't re-enter a losing stock for 45 minutes
4. **Multi-timeframe** — single timeframe = noise; 3 TFs = real trend
5. **Bot superpowers** — scan 150 stocks simultaneously, no human can do this
6. **R:R math** — 1:2.5 only needs 40% win rate vs 50% for 1:2
7. **Realistic expectations** — ₹10k capital = ₹150-250/day, not ₹1,000/day

---

## 📊 VERSION HISTORY

### v3.1 (April 30, 2026) — CURRENT
- Added: `stocks_config.py` — 150 stocks across 18 sectors (single source of truth)
- Added: `dashboard.py` — Streamlit live monitoring dashboard
- Changed: Scan interval 60s → 300s (matches 5-min candle timeframe)
- Changed: Sector list in strategy.py now imported from stocks_config
- Removed: Hardcoded 5-stock list from run.py
- Security: Removed credentials from Readme (use .env only)

### v3.0 (April 30, 2026)
- Added: 2x ATR stop loss, 45-min cooldown, multi-timeframe confluence
- Added: Database persistence, 6-layer smart exits
- Changed: Risk:Reward 1:2 → 1:2.5

### v2.0 (April 29, 2026)
- Added: Time filters, EMA 50 trend filter
- Changed: EMA (5,20) → (9,21), volume threshold 1.5x → 2.0x
- Result: 41.7% win rate, -₹631 loss

### v1.0 (April 28, 2026)
- Initial version: EMA, RSI, VWAP, Supertrend
- Result: 0% win rate (too many signals, tight SL)

---

## ⚠️ RISK DISCLAIMER

- Past performance does not guarantee future results
- Trading involves risk of loss — only use money you can afford to lose
- This is NOT financial advice
- Always monitor the bot — it can malfunction
- Internet/API failures can occur at any time
- Never risk more than 2% per trade
- Keep daily loss limit at 5%

---

## 🎯 CORE PHILOSOPHY

**"We're not building what humans can do. We're building what ONLY bots can do."**

✅ Scan 150 stocks simultaneously across 18 sectors  
✅ Multi-timeframe analysis in parallel  
✅ Zero emotions, perfect discipline  
✅ Remember every trade forever  
✅ React in milliseconds  
✅ Sector rotation intelligence  
✅ Never gets tired  

---

**Happy Trading! 🚀💰**  
*Version 3.1 | Last Updated: April 30, 2026 | Status: Active Development*
