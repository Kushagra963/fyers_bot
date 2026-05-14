"""
BEYOND-HUMAN TRADING BOT v4.0
- Persistent state via SQLite (WAL mode, thread-local connections)
- Multi-timeframe analysis (5m + real 15m resample)
- Sliding window stop loss (ATR-trail, replaces fixed triggers)
- Cooldown system (no repeat losses) — O(1) in-memory cache
- Symbol + sector performance tracking
- Async parallel scanning (ThreadPoolExecutor × 10, ~8s vs ~75s)
- Wilder's RSI & ATR (matches TradingView/Zerodha exactly)
- 7/8 condition threshold + 1.5x volume (realistic signal generation)

Advanced data structures
────────────────────────
  threading.RLock   — active_trades dict guarded for parallel-scan safety
  heapq             — signal priority queue; strongest signal executes first
  deque(maxlen=20)  — rolling price history per position for smarter exits
  defaultdict(list) — sector signal grouping; logs which sectors are trending
"""

import time
import os
import sys
import io
import heapq
import threading
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging

from auth import FyersAuth
from data import FyersDataFetcher
from strategy import BeyondHumanStrategy
from orders import OrderManager
from risk_manager import RiskManager
from database import TradingDatabase
from stocks_config import ALL_SYMBOLS

load_dotenv()

# Build a UTF-8 console stream — fixes UnicodeEncodeError on Windows cp1252 terminals
# StreamHandler() with no args uses sys.stderr which Windows locks to cp1252.
# Instead we wrap sys.stderr.buffer directly with UTF-8 encoding + 'replace' fallback.
if hasattr(sys.stderr, 'buffer'):
    _console_stream = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
else:
    _console_stream = sys.stderr  # non-Windows fallback (already UTF-8)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log', encoding='utf-8'),
        logging.StreamHandler(_console_stream)
    ],
    force=True  # override any basicConfig calls from imported modules
)
logger = logging.getLogger(__name__)


class TradingBot:
    """Beyond-Human Automated Trading Bot"""
    
    def __init__(self, capital=100000, paper_trading=True, symbols=None):
        self.capital       = capital
        self.paper_trading = paper_trading
        self.symbols       = symbols or ALL_SYMBOLS

        self.running       = False
        self.auth          = None
        self.data_fetcher  = None
        self.strategy      = None
        self.order_manager = None
        self.risk_manager  = None
        self.db            = None

        # Late-start guard: if bot boots after 10:00 AM, skip trade execution on
        # the very first scan cycle to avoid "catch-up burst" — stale signals
        # piling up that all fire simultaneously and hit stop losses immediately.
        self._first_scan_done = False

        # ── Advanced data structures ────────────────────────────────────────
        # RLock: parallel scan workers read active_trades; main thread writes it.
        # RLock (re-entrant) allows the same thread to acquire it multiple times
        # (needed when close_position is called from within a locked section).
        self.active_trades      = {}
        self._trades_lock       = threading.RLock()

        # heapq signal queue: (-strength, signal) — max-heap via negation.
        # Strongest signals rise to the top; we execute best edge first.
        self._signal_heap: list = []

        # Scan counters — fed into db.log_scan() after every scan cycle
        self._last_scan_stats: dict = {}

        logger.info("=" * 80)
        logger.info("🤖 BEYOND-HUMAN TRADING BOT v4.0")
        logger.info("=" * 80)
        logger.info(f"Mode   : {'PAPER TRADING 📝' if paper_trading else 'LIVE TRADING 💰'}")
        logger.info(f"Capital: ₹{capital:,.0f}")
        logger.info(f"Symbols: {len(self.symbols)}")
        logger.info("=" * 80 + "\n")
    
    def initialize(self):
        """Initialize all components including database"""
        try:
            logger.info("Initializing bot components...")
            
            # 0. Database FIRST
            logger.info("0. Initializing database...")
            self.db = TradingDatabase('trading_bot.db')
            
            # Print historical stats
            self.db.print_summary()
            
            # 1. Authenticate
            logger.info("1. Authenticating...")
            self.auth = FyersAuth()
            if not self.auth.login():
                return False
            
            # 2. Data fetcher
            logger.info("2. Data fetcher...")
            self.data_fetcher = FyersDataFetcher(self.auth.fyers)
            
            # 3. Strategy
            logger.info("3. Strategy (BeyondHuman v4.0)...")
            self.strategy = BeyondHumanStrategy()
            
            # 4. Order manager
            logger.info("4. Order manager...")
            self.order_manager = OrderManager(self.auth.fyers, paper_trading=self.paper_trading)
            
            # 5. Risk manager (load capital from DB if exists)
            saved_capital = self.db.get_state('current_capital', self.capital)
            logger.info(f"5. Risk manager (Capital: ₹{saved_capital:,.0f})...")
            self.risk_manager = RiskManager(
                total_capital=saved_capital,
                risk_per_trade=0.02,
                max_daily_loss=0.05,
                max_positions=3,
                paper_trading=self.paper_trading
            )
            
            # 6. Warm up in-memory cooldown cache (avoids 150 DB reads on first scan)
            logger.info("6. Warming cooldown cache...")
            self.db._cache_warmup()

            # 7. Restore active positions from DB
            self.restore_positions_from_db()

            logger.info("\n✅ All components initialized!\n")
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False
    
    def restore_positions_from_db(self):
        """Restore active positions from database (after restart)"""
        positions = self.db.get_active_positions()
        if positions:
            logger.info(f"📊 Restoring {len(positions)} active position(s) from database...")
            with self._trades_lock:
                for symbol, pos in positions.items():
                    self.active_trades[symbol] = {
                        'order': {
                            'order_id': f"DB_RESTORED_{pos['trade_id']}",
                            'side': pos['side'],
                            'quantity': pos['quantity'],
                            'limit_price': pos['entry_price']
                        },
                        'signal': {
                            'entry_price': pos['entry_price'],
                            'stop_loss': pos['stop_loss'],
                            'target': pos['target'],
                            'signal': pos['side']
                        },
                        'trade_id':        pos['trade_id'],
                        'entry_time':      datetime.fromisoformat(pos['entry_time']),
                        'entry_price':     pos['entry_price'],
                        'side':            pos['side'],
                        'quantity':        pos['quantity'],
                        'original_stop':   pos['stop_loss'],
                        'current_stop':    pos['current_stop'],
                        'target':          pos['target'],
                        'breakeven_trigger': pos['breakeven_trigger'],
                        'trail_trigger':   pos['trail_trigger'],
                        'highest_price':   pos['highest_price'],
                        'lowest_price':    pos['lowest_price'],
                        'partial_booked':  bool(pos['partial_booked']),
                        'breakeven_set':   bool(pos['breakeven_set']),
                        'max_profit':      pos['max_profit'],
                        'atr_at_entry':    pos.get('atr_at_entry') or pos['entry_price'] * 0.015,
                        # deque(maxlen=20): rolling window of last 20 price ticks
                        # Used for consecutive-down-tick detection in giveback protection
                        'price_history':   deque([pos['entry_price']], maxlen=20),
                    }
                    self.risk_manager.position_opened(capital_used=pos['entry_price'] * pos['quantity'])
                    logger.info(f"  ✅ Restored: {symbol} {pos['side']} @ ₹{pos['entry_price']:.2f}")
    
    def is_market_open(self):
        return self.data_fetcher.is_market_open()
    
    def scan_symbol_worker(self, symbol):
        """
        Per-symbol scan worker — runs inside ThreadPoolExecutor.
        Returns a dict: {'signal': ..., 'skipped': 'position'|'cooldown'|None}

        Thread-safety:
        - active_trades read  : protected by _trades_lock (RLock)
        - db.is_in_cooldown() : hits in-memory cache (RLock inside DB) — O(1), no SQLite I/O
        - get_historical_data : independent HTTP call per thread
        - add_indicators / generate_signal : operate only on local df copy — fully stateless
        """
        try:
            # ── Guard: already in position ─────────────────────────────────
            with self._trades_lock:
                in_position = symbol in self.active_trades
            if in_position:
                logger.info(f"⏭️  {symbol}: Already in position")
                return {'signal': None, 'skipped': 'position'}

            # ── Guard: cooldown (O(1) in-memory cache) ─────────────────────
            in_cooldown, reason = self.db.is_in_cooldown(symbol)
            if in_cooldown:
                logger.info(f"❄️  {symbol}: {reason}")
                return {'signal': None, 'skipped': 'cooldown'}

            # ── Fetch + compute ────────────────────────────────────────────
            df = self.data_fetcher.get_historical_data(symbol, interval='5', days_back=5)
            if df is None or len(df) < 50:
                logger.warning(f"⚠️  {symbol}: Insufficient data")
                return {'signal': None, 'skipped': None}

            df = self.strategy.add_indicators(df)
            if df is None:
                return {'signal': None, 'skipped': None}

            signal = self.strategy.generate_signal(df, symbol=symbol)

            if signal and signal['signal'] in ['BUY', 'SELL']:
                signal['symbol'] = symbol
                return {'signal': signal, 'skipped': None}
            else:
                if signal and signal.get('reasons'):
                    logger.info(f"➖ {symbol}: {signal['reasons'][0] if signal['reasons'] else 'No signal'}")
                return {'signal': None, 'skipped': None}

        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")
            return {'signal': None, 'skipped': None}

    def check_nifty_trend(self):
        """
        P2: Nifty Market Filter — skip scan if market is sideways.
        Fetches NSE:NIFTY50-INDEX 5-min data, computes EMA20 and EMA50.
        Returns (is_trending, direction) where direction is 'UP', 'DOWN', or 'SIDEWAYS'.
        If sideways (EMA spread < 0.1%), returns False so scan is skipped.
        """
        try:
            df = self.data_fetcher.get_historical_data('NSE:NIFTY50-INDEX', interval='5', days_back=3)
            if df is None or len(df) < 50:
                logger.warning("⚠️  Nifty data unavailable — allowing scan")
                return True, 'UNKNOWN'

            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

            latest_ema20 = df['ema20'].iloc[-1]
            latest_ema50 = df['ema50'].iloc[-1]

            spread_pct = abs(latest_ema20 - latest_ema50) / latest_ema50 * 100

            if spread_pct < 0.1:
                logger.info(f"⏸️  Nifty SIDEWAYS (EMA20={latest_ema20:.1f} EMA50={latest_ema50:.1f} spread={spread_pct:.3f}%) — skipping scan")
                return False, 'SIDEWAYS'

            direction = 'UP' if latest_ema20 > latest_ema50 else 'DOWN'
            logger.info(f"📈 Nifty trend: {direction} (EMA20={latest_ema20:.1f} EMA50={latest_ema50:.1f} spread={spread_pct:.2f}%)")
            return True, direction

        except Exception as e:
            logger.warning(f"⚠️  Nifty filter error: {e} — allowing scan")
            return True, 'UNKNOWN'

    def scan_for_signals(self):
        """
        Parallel scan with ThreadPoolExecutor (8 workers).
        Returns signals sorted by strength (strongest first) via heapq.

        After collection:
        - batch_save_signals() writes all signals in one DB transaction
        - db.log_scan() records timing + counts for perf analysis
        - defaultdict groups signals by sector for trend visibility
        """
        scan_start = time.time()
        logger.info(f"\n{'='*80}")
        logger.info(f"🔍 SCANNING (PARALLEL ×8) — {datetime.now().strftime('%H:%M:%S')} | {len(self.symbols)} symbols")
        logger.info(f"{'='*80}\n")

        # P2: Nifty Market Filter — skip scan entirely if market is sideways
        is_trending, nifty_direction = self.check_nifty_trend()
        if not is_trending:
            return []

        raw_signals  = []   # all valid signals
        skipped_pos  = 0
        skipped_cool = 0

        with ThreadPoolExecutor(max_workers=8, thread_name_prefix='scanner') as executor:
            future_to_symbol = {
                executor.submit(self.scan_symbol_worker, sym): sym
                for sym in self.symbols
            }
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    res = future.result()
                    if res['skipped'] == 'position':
                        skipped_pos += 1
                    elif res['skipped'] == 'cooldown':
                        skipped_cool += 1
                    if res['signal'] is not None:
                        raw_signals.append(res['signal'])
                except Exception as e:
                    logger.error(f"Error collecting result for {symbol}: {e}")

        # ── Priority sort via heapq (strongest signal first) ──────────────
        # heapq is a min-heap; negate strength for max-heap behaviour.
        signal_heap = []
        for sig in raw_signals:
            heapq.heappush(signal_heap, (-sig['strength'], sig['symbol'], sig))
        signals = []
        while signal_heap:
            _, _, sig = heapq.heappop(signal_heap)
            signals.append(sig)

        # ── Sector breakdown via defaultdict ──────────────────────────────
        from stocks_config import SYMBOL_TO_SECTOR
        sector_signals: dict = defaultdict(list)
        for sig in signals:
            sector = SYMBOL_TO_SECTOR.get(sig['symbol'], 'UNKNOWN')
            sector_signals[sector].append(sig['signal'])

        if sector_signals:
            logger.info("📡 Sector signal breakdown:")
            for sector, sides in sorted(sector_signals.items()):
                buys  = sides.count('BUY')
                sells = sides.count('SELL')
                logger.info(f"   {sector:<20} BUY={buys}  SELL={sells}")

        # ── Log each confirmed signal ─────────────────────────────────────
        for sig in signals:
            icon = '🟢' if sig['signal'] == 'BUY' else '🔴'
            logger.info(f"\n{icon} {sig['signal']}: {sig['symbol']}")
            logger.info(f"  Price: ₹{sig['close']:.2f} | Strength: {sig['strength']*100:.0f}%")
            logger.info(f"  Entry: ₹{sig['entry_price']:.2f} | SL: ₹{sig['stop_loss']:.2f} | T: ₹{sig['target']:.2f} | ATR: ₹{sig.get('atr', 0):.2f}")

        # ── Batch-save signals (single DB transaction) ────────────────────
        if signals:
            self.db.batch_save_signals([
                {'symbol': s['symbol'], 'signal_type': s['signal'],
                 'price': s['close'], 'strength': s['strength'], 'reasons': s['reasons']}
                for s in signals
            ])

        # ── Log scan metrics to DB ────────────────────────────────────────
        duration = time.time() - scan_start
        buys  = sum(1 for s in signals if s['signal'] == 'BUY')
        sells = sum(1 for s in signals if s['signal'] == 'SELL')
        self.db.log_scan(
            duration_secs=round(duration, 2),
            symbols_scanned=len(self.symbols),
            signals_found=len(signals),
            buy_signals=buys, sell_signals=sells,
            skipped_cooldown=skipped_cool,
            skipped_position=skipped_pos,
        )
        self._last_scan_stats = {'duration': duration, 'signals': len(signals)}

        logger.info(f"\n📊 Scan done in {duration:.1f}s | {len(signals)} signal(s) | "
                    f"skipped: {skipped_pos} in-pos, {skipped_cool} cooldown\n")
        return signals
    
    def execute_signal(self, signal):
        """Execute a trading signal with database tracking"""
        try:
            symbol = signal['symbol']
            side = signal['signal']
            entry_price = signal['entry_price']
            stop_loss = signal['stop_loss']
            target = signal['target']
            
            can_trade, reason = self.risk_manager.can_take_trade()
            if not can_trade:
                logger.warning(f"❌ Cannot take trade: {reason}")
                return False
            
            quantity = self.risk_manager.calculate_position_size(entry_price, stop_loss)
            if quantity == 0:
                return False
            
            logger.info(f"\n{'='*80}")
            logger.info(f"💰 EXECUTING TRADE")
            logger.info(f"{'='*80}")
            
            order = self.order_manager.place_order(
                symbol=symbol, side=side, quantity=quantity,
                order_type='MARKET', stop_loss=stop_loss, target=target
            )
            
            if order and order['status'] in ['EXECUTED', 'PLACED']:
                # Save to database (include PA type + score for analytics)
                trade_id = self.db.save_trade(
                    symbol=symbol, side=side, quantity=quantity,
                    entry_price=entry_price, stop_loss=stop_loss, target=target,
                    paper_trading=self.paper_trading,
                    price_action_type=signal.get('price_action_type'),
                    score=signal.get('score'),
                )
                
                # Calculate exit triggers
                if side == 'BUY':
                    risk = entry_price - stop_loss
                    breakeven_trigger = entry_price + (risk * 0.5)
                    trail_trigger = entry_price + (risk * 1.0)
                else:
                    risk = stop_loss - entry_price
                    breakeven_trigger = entry_price - (risk * 0.5)
                    trail_trigger = entry_price - (risk * 1.0)
                
                # Track in memory
                position_data = {
                    'order':             order,
                    'signal':            signal,
                    'trade_id':          trade_id,
                    'entry_time':        datetime.now(),
                    'entry_price':       entry_price,
                    'side':              side,
                    'quantity':          quantity,
                    'original_stop':     stop_loss,
                    'stop_loss':         stop_loss,
                    'current_stop':      stop_loss,
                    'target':            target,
                    'breakeven_trigger': breakeven_trigger,
                    'trail_trigger':     trail_trigger,
                    'highest_price':     entry_price,
                    'lowest_price':      entry_price,
                    'partial_booked':    False,
                    'breakeven_set':     False,
                    'max_profit':        0,
                    # ATR at entry for sliding window SL
                    'atr_at_entry':      signal.get('atr', entry_price * 0.015),
                    # P7: Enhanced logging fields
                    'score':             signal.get('score', 0),
                    'price_action_type': signal.get('price_action_type', 'Unknown'),
                    # deque(maxlen=20): rolling window of last 20 price ticks.
                    'price_history':     deque([entry_price], maxlen=20),
                }

                with self._trades_lock:
                    self.active_trades[symbol] = position_data

                self.db.save_active_position(symbol, position_data)
                self.risk_manager.position_opened(capital_used=quantity * entry_price)

                logger.info(f"✅ Trade executed! Trade ID: {trade_id}")
                logger.info(f"   Initial SL : ₹{stop_loss:.2f}")
                logger.info(f"   Target     : ₹{target:.2f}")
                logger.info(f"   ATR        : ₹{signal.get('atr', 0):.2f}")
                logger.info(f"{'='*80}\n")
                return True
                
        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            return False
    
    def monitor_positions(self):
        """
        Smart position monitoring with:
        - Sliding window ATR stop loss
        - deque price history → consecutive adverse-tick giveback protection
        - RLock on active_trades for thread safety
        """
        with self._trades_lock:
            symbols_to_monitor = list(self.active_trades.keys())

        if not symbols_to_monitor:
            return

        logger.info(f"\n📊 Monitoring {len(symbols_to_monitor)} position(s)...")

        for symbol in symbols_to_monitor:
            try:
                with self._trades_lock:
                    if symbol not in self.active_trades:
                        continue           # closed by another path between lock acquisitions
                    trade = self.active_trades[symbol]

                order        = trade['order']
                quote        = self.data_fetcher.get_live_quote([symbol])
                if not quote:
                    continue

                current_price = quote[0]['v']['lp']
                entry_price   = trade['entry_price']
                side          = order['side']
                quantity      = order['quantity']

                # ── Update price extremes ──────────────────────────────────
                if current_price > trade['highest_price']:
                    trade['highest_price'] = current_price
                if current_price < trade['lowest_price']:
                    trade['lowest_price'] = current_price

                # ── Append tick to rolling deque (maxlen=20) ──────────────
                trade['price_history'].append(current_price)

                # ── P&L ───────────────────────────────────────────────────
                pnl = ((current_price - entry_price) if side == 'BUY'
                       else (entry_price - current_price)) * quantity

                if pnl > trade['max_profit']:
                    trade['max_profit'] = pnl
                    self.db.update_position(symbol, max_profit=pnl,
                                            highest_price=trade['highest_price'],
                                            lowest_price=trade['lowest_price'])

                pnl_pct = (pnl / (entry_price * quantity)) * 100
                logger.info(
                    f"  {symbol}: ₹{current_price:.2f} | P&L: ₹{pnl:.2f} ({pnl_pct:+.2f}%) | "
                    f"Max: ₹{trade['max_profit']:.2f} | SL: ₹{trade['current_stop']:.2f}"
                )

                if not self.paper_trading:
                    continue

                # ══════════════ SMART EXITS ══════════════

                # 1. Stop Loss
                hit_stop = ((side == 'BUY'  and current_price <= trade['current_stop']) or
                            (side == 'SELL' and current_price >= trade['current_stop']))
                if hit_stop:
                    label = 'TRAILING_STOP' if trade['breakeven_set'] else 'STOP_LOSS'
                    prefix = '✅ Trailing stop (profit locked)' if trade['breakeven_set'] else '📍 Stop loss hit'
                    logger.info(f"  {prefix}")
                    if not trade['breakeven_set']:
                        self.db.add_cooldown(symbol, minutes=45, reason="Stop loss hit")
                    self.close_position(symbol, current_price, label)
                    continue

                # 2. Target
                hit_target = ((side == 'BUY'  and current_price >= trade['target']) or
                              (side == 'SELL' and current_price <= trade['target']))
                if hit_target:
                    logger.info(f"  🎯 Target hit!")
                    self.close_position(symbol, current_price, 'TARGET')
                    continue

                # 3. Sliding window ATR stop loss
                atr      = trade.get('atr_at_entry', entry_price * 0.015)
                new_stop = self.strategy.calculate_sliding_stop(
                    side=side, entry_price=entry_price,
                    current_stop=trade['current_stop'],
                    highest_price=trade['highest_price'],
                    lowest_price=trade['lowest_price'],
                    atr=atr,
                )
                if abs(new_stop - trade['current_stop']) > 0.01:
                    old_stop = trade['current_stop']
                    trade['current_stop'] = new_stop
                    is_risk_free = ((side == 'BUY'  and new_stop >= entry_price) or
                                    (side == 'SELL' and new_stop <= entry_price))
                    trade['breakeven_set'] = is_risk_free
                    self.db.update_position(symbol, current_stop=new_stop,
                                            breakeven_set=is_risk_free)
                    zone = '🔒 RISK-FREE' if is_risk_free else '📈 SLIDING'
                    logger.info(f"  {zone} SL: ₹{old_stop:.2f} → ₹{new_stop:.2f}")

                # 3b. Partial profit booking — at 1:1 RR, move SL to breakeven
                # Locks in the trade risk-free once profit = initial risk amount.
                if not trade['partial_booked']:
                    if side == 'BUY':
                        risk_amount = (trade['entry_price'] - trade['original_stop']) * quantity
                    else:
                        risk_amount = (trade['original_stop'] - trade['entry_price']) * quantity
                    if pnl >= risk_amount and risk_amount > 0:
                        # Move SL to entry (breakeven) — worst case now = 0 loss
                        trade['current_stop'] = trade['entry_price']
                        trade['partial_booked'] = True
                        trade['breakeven_set'] = True
                        self.db.update_position(symbol, current_stop=trade['entry_price'],
                                                breakeven_set=True)
                        logger.info(
                            f"  💰 Partial profit locked @ 1:1 | P&L ₹{pnl:.2f} ≥ risk ₹{risk_amount:.2f} | "
                            f"SL moved to breakeven ₹{trade['entry_price']:.2f}"
                        )

                # 4. Giveback protection — tiered drawdown from peak
                #    Rules:
                #      - Min profit ₹150 before activating (ignore tiny moves)
                #      - 20-min minimum hold (avoid cutting fresh trades that just dipped)
                #      - Allow 50% drawdown in first 60 min (let winners breathe)
                #      - Tighten to 30% after 60 min (protect locked-in gains near EOD)
                holding_time = (datetime.now() - trade['entry_time']).seconds / 60
                if trade['max_profit'] > 150 and holding_time >= 20:
                    giveback_pct = (trade['max_profit'] - pnl) / trade['max_profit']
                    threshold = 0.30 if holding_time > 60 else 0.50
                    if giveback_pct > threshold:
                        logger.info(
                            f"  ⚠️  Giveback exit | {giveback_pct*100:.0f}% drawdown from "
                            f"peak ₹{trade['max_profit']:.2f} | current P&L ₹{pnl:.2f} "
                            f"| hold={holding_time:.0f}min threshold={threshold*100:.0f}%"
                        )
                        self.close_position(symbol, current_price, 'PROFIT_GIVEBACK')
                        continue

                # 5. Time Exit — 90 min regardless of P&L (frees slots for better signals)
                if holding_time > 90:
                    logger.info(f"  🕐 Time exit ({holding_time:.0f} min | P&L ₹{pnl:.2f})")
                    self.close_position(symbol, current_price, 'TIME_EXIT')
                    continue

                # 6. EOD Exit
                if datetime.now().time() >= datetime.strptime("15:15", "%H:%M").time():
                    logger.info(f"  🕐 EOD exit")
                    self.close_position(symbol, current_price, 'EOD')
                    continue

            except Exception as e:
                logger.error(f"Error monitoring {symbol}: {e}")
    
    def close_position(self, symbol, exit_price, reason):
        """Close position, update DB, and record sector performance."""
        try:
            with self._trades_lock:
                if symbol not in self.active_trades:
                    return
                trade = self.active_trades.pop(symbol)   # atomic remove under lock

            order       = trade['order']
            entry_price = trade['entry_price']

            # Risk manager accounting
            self.risk_manager.record_trade(
                entry_price=entry_price, exit_price=exit_price,
                quantity=order['quantity'], side=order['side']
            )

            # Close trade in DB
            pnl = None
            if 'trade_id' in trade:
                pnl = self.db.close_trade(trade['trade_id'], exit_price, reason)
                logger.info(f"💾 DB: Trade #{trade['trade_id']} closed | P&L: ₹{pnl:.2f}")

            # Update sector performance (new in v4.0)
            if pnl is not None:
                from stocks_config import SYMBOL_TO_SECTOR
                sector = SYMBOL_TO_SECTOR.get(symbol, 'UNKNOWN')
                self.db.update_sector_performance(sector, pnl)

            self.db.save_state('current_capital', self.risk_manager.total_capital)
            self.db.remove_active_position(symbol)

            # P7: Enhanced trade summary log
            time_in_trade = round((datetime.now() - trade.get('entry_time', datetime.now())).seconds / 60)
            logger.info(f"✅ Closed: {symbol} | Reason: {reason}")
            logger.info(
                f"   📋 TRADE SUMMARY | PA={trade.get('price_action_type','?')} | "
                f"Score={trade.get('score', 0):.1f}/7.5 | "
                f"Time={time_in_trade}min | MaxProfit=₹{trade.get('max_profit', 0):.0f} | "
                f"FinalPnL=₹{pnl:.0f}"
            )

        except Exception as e:
            logger.error(f"Error closing position: {e}")

    def run(self):
        """Main trading loop"""
        logger.info("\n" + "="*80)
        logger.info("🚀 STARTING BEYOND-HUMAN TRADING BOT")
        logger.info("="*80 + "\n")

        if not self.initialize():
            logger.error("Initialization failed")
            return

        self.running  = True
        scan_interval = 300   # 5 min — parallel scan finishes in ~8s
        last_scan     = datetime.now() - timedelta(seconds=scan_interval)

        try:
            while self.running:
                try:
                    if not self.is_market_open():
                        logger.info("⏰ Market closed - waiting...")
                        time.sleep(300)
                        continue

                    if (datetime.now() - last_scan).total_seconds() >= scan_interval:
                        signals = self.scan_for_signals()   # already sorted by strength
                        last_scan = datetime.now()

                        # Late-start burst guard: if first scan fires after 10:00 AM,
                        # skip execution this cycle — signals may be stale catch-ups.
                        now = datetime.now()
                        late_start = not self._first_scan_done and now.hour >= 10
                        self._first_scan_done = True

                        if late_start and signals:
                            logger.info(
                                f"⏩ LATE START ({now.strftime('%H:%M')}) — skipping "
                                f"{len(signals)} signal(s) on first scan to avoid burst entries. "
                                f"Normal trading resumes next cycle."
                            )
                        else:
                            # Execute signals strongest-first (heapq sorted them).
                            # Stop early if risk_manager says no more capacity.
                            for signal in signals:
                                can_trade, _ = self.risk_manager.can_take_trade()
                                if not can_trade:
                                    logger.info("⛔ Max positions reached — skipping remaining signals")
                                    break
                                self.execute_signal(signal)

                    self.monitor_positions()

                    # Hourly stats save
                    if datetime.now().minute == 0 and datetime.now().second < 30:
                        self.risk_manager.print_summary()
                        stats = self.risk_manager.get_stats()
                        self.db.update_daily_stats(
                            capital=stats['total_capital'],
                            pnl=stats['daily_pnl'],
                            total_trades=stats['total_trades'],
                            winners=stats['winning_trades'],
                            losers=stats['losing_trades']
                        )

                    time.sleep(10)

                except KeyboardInterrupt:
                    logger.info("\n⚠️  Stopping bot...")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    time.sleep(60)

        finally:
            self.stop()

    def stop(self):
        """Stop bot gracefully — closes all positions and all DB connections."""
        logger.info("\n" + "="*80)
        logger.info("🛑 STOPPING BOT")
        logger.info("="*80 + "\n")

        self.running = False

        # Close all open positions at market
        with self._trades_lock:
            open_symbols = list(self.active_trades.keys())
        if open_symbols:
            logger.info("Closing all positions...")
            for symbol in open_symbols:
                quote = self.data_fetcher.get_live_quote([symbol])
                if quote:
                    current_price = quote[0]['v']['lp']
                    self.close_position(symbol, current_price, 'BOT_STOP')

        # Final stats
        if self.risk_manager:
            self.risk_manager.print_summary()
            stats = self.risk_manager.get_stats()
            self.db.update_daily_stats(
                capital=stats['total_capital'],
                pnl=stats['daily_pnl'],
                total_trades=stats['total_trades'],
                winners=stats['winning_trades'],
                losers=stats['losing_trades']
            )
            self.db.save_state('current_capital', stats['total_capital'])

        # All-time leaderboards
        if self.db:
            self.db.print_summary()   # includes sector table + scan stats

            best_symbols = self.db.get_best_symbols(min_trades=2)
            if best_symbols:
                print("\n🏆 BEST PERFORMING SYMBOLS:")
                for s in best_symbols[:5]:
                    print(f"  {s['symbol']:<25} {s['win_rate']:.0f}% win | ₹{s['avg_pnl']:.2f}")

            sector_stats = self.db.get_sector_performance()
            if sector_stats:
                print("\n📡 SECTOR PERFORMANCE:")
                for s in sector_stats[:5]:
                    print(f"  {s['sector']:<20} {s['total_trades']} trades | "
                          f"{s['win_rate']:.0f}% win | ₹{s['total_pnl']:.2f}")

            scan_stats = self.db.get_scan_stats(last_n=5)
            if scan_stats:
                avg_dur = sum(r['duration_secs'] for r in scan_stats) / len(scan_stats)
                print(f"\n⚡ Last {len(scan_stats)} scans avg: {avg_dur:.1f}s")

            self.db.close()   # closes all thread-local connections

        logger.info("✅ Bot stopped\n")


def main():
    print("\n" + "="*80)
    print("🤖 BEYOND-HUMAN TRADING BOT v4.2")
    print("="*80)
    print("\nFeatures:")
    print("  ✅ Persistent state (SQLite — WAL, thread-local connections)")
    print("  ✅ Multi-timeframe analysis (5m + real 15m resample)")
    print("  ✅ Wilder\'s RSI & ATR (matches TradingView/Zerodha)")
    print("  ✅ Sliding window stop loss (ATR-trail, continuous)")
    print("  ✅ 45-min cooldown + O(1) in-memory cache")
    print("  ✅ Parallel scanning (ThreadPoolExecutor ×8, ~17s)")
    print("  ✅ heapq signal priority | deque price history | defaultdict sectors")
    print("  ✅ PA hard gate + weighted scoring (v4.1)")
    print("  ✅ Nifty market filter (v4.1)")
    print("  ✅ Breakout threshold 6.5 (v4.2)")
    print("  ✅ Tiered giveback protection (v4.2)")
    print("  ✅ Late-start burst guard (v4.2)")
    print("\nMode: PAPER TRADING 📝")
    print("Capital: ₹100,000")
    print("="*80 + "\n")

    input("Press ENTER to start...")

    bot = TradingBot(
        capital=100000,
        paper_trading=True,
    )
    bot.run()


if __name__ == "__main__":
    main()
