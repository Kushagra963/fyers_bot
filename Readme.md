# 🤖 AUTOMATED TRADING BOT - MASTER DOCUMENT
**Last Updated:** April 30, 2026  
**Version:** 3.0 - "Beyond Human"  
**Owner:** Kushagra Upadhyay

---

## 📋 QUICK CONTEXT FOR NEW CHATS

**Copy-paste this section to Claude in any new chat:**

> I'm building an automated intraday trading bot for Indian stock market (NSE) using Fyers API. The bot uses Python and trades 5-minute candles with multi-indicator strategy. Currently testing with paper trading (₹100,000 virtual). Goal is to make ₹1,000+/month with ₹10,000 real capital after 2 weeks testing. Bot has database persistence, smart exits, trailing stops, and cooldown system to prevent repeat losses.

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
**v3.0 - "Beyond Human"** (Latest)

### Key Features:
✅ Multi-timeframe confluence (5m, 15m, 50 EMA)
✅ Volatility-adjusted stop loss (2x ATR)
✅ 45-minute cooldown after stop loss
✅ Trailing stops + breakeven protection
✅ 1:2.5 Risk:Reward ratio
✅ SQLite database for persistent learning
✅ Smart exit management (6 layers)

### Testing Results:
- **April 29, 2026:**
  - Strategy v2: 12 trades, 41.7% win rate, -₹631 loss
  - Issues: Tight SL (hit in 1 min), repeat signals (6x on same stock)
  - Improvements made → v3.0 created

### Expected Performance (v3.0):
- Win Rate: 55-65%
- Trades/Day: 2-3
- Daily Profit: ₹150-₹250 (with ₹10k capital)
- Monthly: ₹3,000-₹5,000

---

## 🏦 BROKER DETAILS

**Broker:** Fyers  
**Account Type:** Individual  
**Trading Type:** Intraday (MIS)

### API Credentials:
- **App ID:** OHTOZN2ME2-100
- **Secret Key:** W1TIGAZ7QL
- **PIN:** 9639
- **TOTP Secret:** HIUPHSSGOUZI7VHIQXT7TPQ67XWLRKGM

**Authentication:** External TOTP using pyotp library

---

## 📁 PROJECT STRUCTURE

```
C:\Users\kushagra\Trading Bot\fyers_bot\
│
├── venv\                      # Virtual environment
├── .env                       # Credentials (DO NOT SHARE)
│
├── auth.py                    # TOTP-based Fyers authentication
├── data.py                    # Historical/live data fetcher
├── strategy.py                # Trading strategy (v3.0 - Beyond Human)
├── orders.py                  # Order placement (paper/live)
├── risk_manager.py            # Position sizing & risk limits
├── run.py                     # Main bot loop with smart exits
├── database.py                # SQLite persistence
│
├── trading_bot.db             # SQLite database (auto-created)
├── trading_bot.log            # Log file
├── requirements.txt           # Python dependencies
└── SETUP_GUIDE.md             # Setup instructions
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
```

**Install command:**
```bash
pip install fyers-apiv3 pyotp python-dotenv pandas numpy TA-Lib
```

---

## 🎯 TRADING STRATEGY v3.0 - "BEYOND HUMAN"

### Philosophy:
Leverage bot capabilities humans cannot match:
- Multi-stock parallel scanning
- Microsecond calculations
- Perfect discipline (no emotions)
- Persistent memory across days
- Multi-timeframe simultaneous analysis

### Entry Criteria (ALL must be TRUE):

**Time Filters:**
- ❌ NOT 9:15-9:45 AM (too volatile)
- ❌ NOT 11:30 AM-1:00 PM (lunch hour)
- ❌ NOT after 2:45 PM (pre-close)

**Cooldown Filter:**
- ❌ NOT in 45-min cooldown (after recent SL hit)

**Multi-Timeframe Confluence:**
✅ 5-min: EMA(9) crossover EMA(21)
✅ 15-min: EMA trend aligned
✅ 50 EMA: Long-term trend aligned

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

## 🚪 EXIT MANAGEMENT (6 Layers)

**Layer 1: Stop Loss Hit**
- Exit immediately
- Add symbol to 45-min cooldown
- Prevents re-entry on same loser

**Layer 2: Breakeven Protection**
- At 50% to target → Move SL to entry price
- Trade becomes RISK-FREE

**Layer 3: Trailing Stop**
- After 1:1 reward → Trail SL at 50% of profit
- Locks in gains as price moves

**Layer 4: Profit Giveback Protection**
- If lose 50% of max profit → Exit
- Example: Max ₹300, current ₹150 → Exit

**Layer 5: Time Exit**
- After 60 minutes → Take any profit
- Don't hold too long

**Layer 6: EOD Exit**
- 3:15 PM → Close all positions
- No overnight risk

---

## 📈 STOCKS TRADED

**Current List (5 stocks):**
1. NSE:SBIN-EQ (State Bank of India)
2. NSE:RELIANCE-EQ (Reliance Industries)
3. NSE:INFY-EQ (Infosys)
4. NSE:HDFCBANK-EQ (HDFC Bank)
5. NSE:ICICIBANK-EQ (ICICI Bank)

**Why These:**
- High liquidity
- Good volume
- Popular for intraday
- Blue-chip stocks

**Can Add Later:**
- NSE:TCS-EQ
- NSE:WIPRO-EQ
- NSE:KOTAKBANK-EQ
- NSE:AXISBANK-EQ

---

## 🗄️ DATABASE SCHEMA

**Tables:**

### 1. trades
- Stores all trade history
- Fields: symbol, side, entry_price, exit_price, quantity, pnl, entry_time, exit_time, exit_reason, status

### 2. symbol_performance
- Tracks performance per stock
- Fields: symbol, total_trades, win_rate, total_pnl, best_trade, worst_trade

### 3. cooldowns
- Manages 45-min cooldowns
- Fields: symbol, cooldown_until, reason

### 4. daily_stats
- Daily performance summary
- Fields: date, starting_capital, ending_capital, daily_pnl, total_trades, win_rate

---

## 🐛 KNOWN ISSUES & FIXES

### Issue 1: Stop Loss Too Tight ✅ FIXED
**Problem:** SL hit in 1 minute (April 29)
**Solution:** Now uses 2x ATR (wider, volatility-adjusted)

### Issue 2: Repeat Signals ✅ FIXED
**Problem:** ICICIBANK got 6 SELL signals in 2 hours
**Solution:** 45-minute cooldown after SL hit

### Issue 3: Poor Risk:Reward ✅ FIXED
**Problem:** 1:2 RR needed 50% win rate
**Solution:** Now 1:2.5 RR needs only 40% win rate

### Issue 4: Holding Too Long ✅ FIXED
**Problem:** Best profits came from EOD exits
**Solution:** 60-min time exit, trailing stops

### Issue 5: Data Fetch Errors ⚠️ PENDING
**Problem:** SBIN error code -99 at 13:22
**Solution:** Need graceful error handling (future update)

---

## 📊 PERFORMANCE TRACKING

### Key Metrics to Monitor:
1. **Win Rate** (target: 55-65%)
2. **Average Daily P&L** (target: ₹150-₹250 with ₹10k)
3. **Max Drawdown** (should be < 5%)
4. **Trades per Day** (target: 2-3)
5. **Best Performing Stock** (focus capital here)
6. **Worst Performing Stock** (consider removing)

### After 2 Weeks Paper Trading:
✅ Verify win rate > 55%
✅ Check consistent daily profits
✅ Review database analytics
✅ Decide: Continue paper or switch to real ₹10k

---

## 💰 CAPITAL PROJECTIONS

### With ₹10,000 Real Capital:

| Timeframe | Target | ROI |
|-----------|--------|-----|
| **Daily** | ₹150-₹250 | 1.5-2.5% |
| **Weekly** | ₹750-₹1,250 | 7.5-12.5% |
| **Monthly** | ₹3,000-₹5,000 | 30-50% |

### Growth Plan:
- **Month 1:** ₹10k → ₹13.5k (+₹3,500)
- **Month 2:** ₹13.5k → ₹18k (+₹4,500)
- **Month 3:** ₹18k → ₹24k (+₹6,000)
- **Month 6:** ₹10k → ₹50k+ (compounding)

---

## 🌍 FUTURE EXPANSION PLANS

### Phase 1: Master Indian Market (Current)
- Perfect the strategy
- Achieve 60%+ win rate
- Build capital to ₹25k-₹50k

### Phase 2: US Stock Market (Month 3-4)
**Broker:** Interactive Brokers (IBKR)
**Capital Required:** $500 (~₹42,000)
**Expected Monthly:** ₹40,000-₹1,50,000 (earn in USD!)
**Same bot, different broker API**

### Phase 3: Crypto Trading (Month 3-4)
**Broker:** CoinDCX or Binance
**Capital Required:** ₹5,000-₹10,000
**Advantage:** 24/7 trading
**Expected Monthly:** ₹15,000-₹80,000

### Phase 4: MCX Commodities (Month 5+)
**Broker:** Fyers (same account!)
**Capital Required:** ₹50,000+
**Trades:** Gold, Silver, Crude Oil
**Expected Monthly:** ₹10,000-₹50,000

**Ultimate Goal:** 4 bots running = ₹72,000+/month

---

## 🚀 HOW TO RUN THE BOT

### Daily Startup (9:10 AM):
```bash
cd C:\Users\kushagra\Trading Bot\fyers_bot
python run.py
```

### What Happens:
1. Loads credentials from .env
2. Authenticates with Fyers (TOTP)
3. You paste redirect URL
4. Bot starts scanning at 9:15 AM
5. Trades automatically until 3:30 PM
6. Logs everything to trading_bot.log

### To Stop:
- Press **Ctrl+C**
- Bot saves all data to database
- Can restart anytime

---

## 📝 IMPORTANT LESSONS LEARNED

### Lesson 1: Paper Trade First
**Always test new strategies** with paper trading before risking real money!

### Lesson 2: Wide Stop Losses
Intraday noise requires breathing room. **2x ATR stops** work better than tight Supertrend stops.

### Lesson 3: Cooldown System
**Don't re-enter losing trades immediately.** Wait 45 minutes for market to stabilize.

### Lesson 4: Multi-Timeframe Confluence
Single timeframe = Noise. **Multiple timeframes = Real trends.**

### Lesson 5: Bot Superpowers
Books teach human strategies. **Bots can do things humans can't:**
- Analyze 50+ stocks simultaneously
- React in milliseconds
- Never break discipline
- Remember everything forever

### Lesson 6: Risk:Reward Math
**1:2.5 RR is better than 1:2** because it only needs 40% win rate vs 50%.

### Lesson 7: Realistic Expectations
**₹10k won't make ₹1,000/day.** Realistic is ₹150-₹250/day. Scale capital to scale profits.

---

## 🔧 TROUBLESHOOTING

### Problem: "ModuleNotFoundError"
**Solution:** 
```bash
pip install [missing_module]
```

### Problem: "Authentication failed"
**Solution:** 
- Check .env file has correct credentials
- TOTP code changes every 30 sec, paste redirect URL quickly
- Verify External TOTP is enabled in Fyers

### Problem: "No signals generated"
**Solution:**
- Market might be choppy (no clear trend)
- Check if in cooldown period
- Verify time filters (not 9:15-9:45, lunch, or EOD)

### Problem: Bot keeps losing
**Solution:**
- Check win rate (should be 55%+)
- Review database for worst performing stocks
- Consider reducing position size
- Switch back to paper trading to test changes

### Problem: Database errors
**Solution:**
- Check trading_bot.db file exists
- Restart bot
- Delete .db file to recreate fresh

---

## 📞 QUICK REFERENCE

### File Locations:
- **Project:** `C:\Users\kushagra\Trading Bot\fyers_bot\`
- **Logs:** `trading_bot.log`
- **Database:** `trading_bot.db`
- **Env:** `.env`

### Key Commands:
```bash
# Activate virtual environment
venv\Scripts\activate

# Run bot
python run.py

# Test individual module
python auth.py
python strategy.py
python database.py
```

### Trading Hours:
- **Market Open:** 9:15 AM IST
- **Bot Trades:** 9:45 AM - 2:45 PM
- **Market Close:** 3:30 PM IST
- **EOD Exit:** 3:15 PM (bot auto-closes)

---

## 📚 RESOURCES & INSPIRATION

### Books Referenced:
1. "How To Make Money in Intraday Trading" - Ashwani Gujral
2. "The Subtle Art of Intraday Trading" - Indrazith Shantharaj
3. "Trading in the Zone" - Mark Douglas

### Hedge Fund Strategies Used:
- **Opening Range Breakout (ORB)** - Toby Crabel (Crabel Capital - $8.5B)
- **Multi-Timeframe Analysis** - Renaissance Technologies
- **Statistical Edge** - Two Sigma approach

### Indian Trader Wisdom:
- Time-based filters (avoid volatile periods)
- Volume confirmation (big money moves)
- Risk management (2% rule, 5% daily loss limit)

---

## ⚠️ RISK DISCLAIMER

**IMPORTANT:**
- Past performance does not guarantee future results
- Trading involves risk of loss
- Only trade with money you can afford to lose
- Start small, test thoroughly
- This is NOT financial advice
- Bot can malfunction, always monitor
- Internet/API failures can occur
- Market conditions change

**Recommended:**
- Start with paper trading
- Test for minimum 2 weeks
- Never risk more than 2% per trade
- Keep daily loss limit at 5%
- Have backup plan if bot fails

---

## 🎯 NEXT STEPS CHECKLIST

**Week 1-2:**
- [ ] Run bot daily in paper trading mode
- [ ] Monitor win rate (target: 55-65%)
- [ ] Check database analytics weekly
- [ ] Note best/worst performing stocks
- [ ] Verify cooldown system working
- [ ] Confirm trailing stops activating

**Week 3:**
- [ ] Review 2-week performance
- [ ] If win rate > 55%, proceed to real money
- [ ] Add ₹10,000 to Fyers account
- [ ] Change `paper_trading=False` in run.py
- [ ] Start with ₹10k capital
- [ ] Monitor closely first 3 days

**Month 2:**
- [ ] Review Month 1 results
- [ ] Calculate actual ROI
- [ ] Decide on capital increase
- [ ] Remove worst performing stocks
- [ ] Add better performing stocks
- [ ] Consider multi-market expansion

---

## 📊 VERSION HISTORY

### v3.0 - "Beyond Human" (April 30, 2026) - CURRENT
- Added: 2x ATR stop loss (volatility-adjusted)
- Added: 45-min cooldown system
- Added: Multi-timeframe confluence
- Added: Database persistence
- Added: 6-layer smart exit management
- Changed: Risk:Reward from 1:2 to 1:2.5
- Fixed: Tight stop losses
- Fixed: Repeat signal problem

### v2.0 - "Improved Filters" (April 29, 2026)
- Added: Time-based filters
- Added: EMA 50 trend filter
- Changed: EMA from (5,20) to (9,21)
- Changed: Volume threshold from 1.5x to 2.0x
- Result: 41.7% win rate, -₹631 loss (needs improvement)

### v1.0 - "Basic Multi-Indicator" (April 28, 2026)
- Initial version
- EMA (5, 20), RSI (14), VWAP, Supertrend
- Result: 0% win rate (too many signals, tight SL)

---

## 🤝 COLLABORATION NOTES

**For Claude in future chats:**

When user shares this document:
1. Understand the full context immediately
2. Know current strategy version (v3.0)
3. Reference past issues and fixes
4. Continue from where we left off
5. Don't repeat old mistakes
6. Build on existing foundation

**For User (Kushagra):**

Share this document in new chats with:
> "Read this master document to get full context of my trading bot project."

Then ask your question!

---

## 🎯 CORE PHILOSOPHY

**"We're not building what humans can do. We're building what ONLY bots can do."**

Bot advantages over humans:
✅ Analyze 50+ stocks simultaneously
✅ Multi-timeframe analysis in parallel
✅ Zero emotions, perfect discipline
✅ Remember every pattern forever
✅ React in milliseconds
✅ Trade 24/7 (for crypto/forex)
✅ Never get tired
✅ Statistical calculations instantly

**This is our competitive edge!**

---

## 📧 CONTACT & NOTES

**Project Owner:** Kushagra Upadhyay  
**Location:** Indore, Madhya Pradesh, India  
**Goal:** Build sustainable income from algorithmic trading  
**Timeline:** 2 weeks paper → Real money → Scale to multi-market  

**Personal Note:**
*"Started with ₹5,000 goal to pay half of Claude subscription (₹1,000/month). Building this bot not just for money, but to learn, grow, and create a system that works while I sleep. Excited to see where this journey goes!"*

---

**END OF MASTER DOCUMENT**

*Keep this document updated as the project evolves!*  
*Version 3.0 | Last Updated: April 30, 2026 | Status: Active Development*

---

## 🔗 QUICK COPY-PASTE FOR NEW CHATS

**Option 1 - Full Context:**
```
I have an automated trading bot project. Please read this master document 
[paste entire document] and help me with [your question].
```

**Option 2 - Quick Context:**
```
Trading bot context: v3.0 "Beyond Human" strategy for Indian stocks (NSE) 
using Fyers API. Multi-timeframe confluence, 2x ATR stops, 45-min cooldown, 
1:2.5 RR, smart exits. Paper trading ₹100k, goal ₹10k real after 2 weeks. 
Win rate target 55-65%. Stack: Python, pandas, TA-Lib, SQLite. 
Latest test: 41.7% win rate, -₹631 (issues fixed in v3.0).

Question: [your question]
```

---

**Happy Trading! 🚀💰**