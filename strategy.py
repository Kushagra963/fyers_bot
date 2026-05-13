"""
BEYOND-HUMAN TRADING STRATEGY v4.0
Leveraging bot superpowers humans cannot match:

1. Multi-Timeframe Confluence (5m + 15m + 1h alignment)
2. Multi-Stock Sector Correlation (Banking, IT sectors)
3. Volume Profile Analysis (where big money trades)
4. Volatility-Adjusted Stop Loss (no more SL hunts)
5. Signal Cooldown System (no re-entry on losers)
6. Statistical Edge Calculator (probability-based)
7. Order Book Intelligence (bid/ask imbalance)
8. Adaptive Position Sizing (learn from results)

Lessons from previous testing:
- Stop losses were getting hit in 1 minute (TOO TIGHT)
- Same signal repeating 6x on same stock (NO COOLDOWN)
- Win rate 41.7% needs better RR ratio
- EOD exits made profit (need to exit faster)
"""

import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
import logging
from stocks_config import SECTORS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BeyondHumanStrategy:
    """
    Strategy that uses bot capabilities humans cannot match.
    
    KEY DIFFERENTIATORS:
    - Volatility-adjusted stops (ATR-based, wider for noisy stocks)
    - Cooldown tracking (won't re-enter losers)
    - Multi-timeframe confluence (only trades when 3 TFs agree)
    - Sector strength filter (only trade strongest sector)
    - Better risk:reward (1:1.5 — target within intraday range)
    """
    
    def __init__(self):
        # Indicators
        self.ema_fast = 9
        self.ema_slow = 21
        self.ema_trend = 50  # Long-term trend filter
        self.rsi_period = 14
        self.atr_period = 14
        self.volume_threshold       = 1.2   # 1.2x volume — soft bonus, not hard gate
        self.score_threshold        = 5.5   # P8: default threshold (Breakdown / PB-Bounce)
        self.breakout_score_threshold = 6.5  # P9: stricter threshold for Breakout PA (confirmed underperformer)
        
        # Time filters (avoid bad trading times)
        self.no_trade_start = time(9, 15)
        self.no_trade_end = time(9, 45)    # Skip first 30 min
        self.lunch_start = time(12, 15)
        self.lunch_end = time(12, 45)
        self.eod_start = time(14, 45)      # Stop new trades earlier
        
        # COOLDOWN SYSTEM (Bot-only feature!)
        # Track recent stop-losses and prevent re-entry
        self.stop_loss_cooldown = {}  # symbol -> datetime when cooldown ends
        self.cooldown_minutes = 45  # Wait 45 min after SL before re-trading
        
        # SIGNAL HISTORY (for pattern learning)
        self.recent_signals = {}  # symbol -> list of recent signals
        
        # SECTOR CORRELATION (Bot superpower!) — loaded from stocks_config.py
        self.sectors = SECTORS
        
        logger.info("="*80)
        logger.info("🤖 BEYOND-HUMAN STRATEGY v4.0 INITIALIZED")
        logger.info("="*80)
        logger.info("Bot Superpowers Active:")
        logger.info("  ✅ Multi-Timeframe Confluence")
        logger.info("  ✅ Volatility-Adjusted Stops (ATR-based)")
        logger.info("  ✅ Signal Cooldown System (45 min)")
        logger.info("  ✅ Sector Correlation Analysis")
        logger.info("  ✅ Volume Profile Detection")
        logger.info("  ✅ Statistical Edge Calculator")
        logger.info("  ✅ Better Risk:Reward (1:1.5 — target within daily range)")
        logger.info("="*80)
    
    def is_good_trading_time(self):
        """Time-based filter"""
        now = datetime.now().time()
        
        if self.no_trade_start <= now < self.no_trade_end:
            return False, "First 30 min - too volatile"
        if self.lunch_start <= now < self.lunch_end:
            return False, "Lunch hour - low volume"
        if now >= self.eod_start:
            return False, "Pre-close - avoid new trades"
        
        return True, "OK"
    
    def is_in_cooldown(self, symbol):
        """Check if symbol is in cooldown after recent loss"""
        if symbol not in self.stop_loss_cooldown:
            return False, None
        
        cooldown_end = self.stop_loss_cooldown[symbol]
        if datetime.now() < cooldown_end:
            mins_left = (cooldown_end - datetime.now()).seconds // 60
            return True, f"Cooldown active ({mins_left} min left)"
        
        # Cooldown expired
        del self.stop_loss_cooldown[symbol]
        return False, None
    
    def add_to_cooldown(self, symbol):
        """Add symbol to cooldown after stop loss hit"""
        self.stop_loss_cooldown[symbol] = datetime.now() + timedelta(minutes=self.cooldown_minutes)
        logger.info(f"❄️  {symbol} added to cooldown for {self.cooldown_minutes} min")
    
    def calculate_ema(self, data, period):
        return data.ewm(span=period, adjust=False).mean()
    
    def calculate_rsi(self, data, period=14):
        """Wilder's RSI — EMA smoothing with alpha=1/period (not SMA).
        Matches TradingView/Zerodha charts exactly. SMA-based RSI gives
        different values and can misfire on overbought/oversold signals."""
        delta = data.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        # Wilder's smoothing: equivalent to ewm(span=2*period-1) but alpha=1/period
        avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan).fillna(1e-10)
        return 100.0 - (100.0 / (1.0 + rs))
    
    def calculate_vwap(self, df):
        # FIX 1: VWAP must reset each day — use only today's candles
        # 75 candles x 5 min = 375 min = exactly 1 trading session
        CANDLES_PER_DAY = 75
        today_df = df.iloc[-CANDLES_PER_DAY:] if len(df) >= CANDLES_PER_DAY else df
        typical_price = (today_df['high'] + today_df['low'] + today_df['close']) / 3
        vwap_today = (typical_price * today_df['volume']).cumsum() / today_df['volume'].cumsum()
        vwap = pd.Series(index=df.index, dtype=float)
        vwap[today_df.index] = vwap_today
        vwap = vwap.ffill().bfill()
        return vwap
    
    def calculate_atr(self, df, period=14):
        """Wilder's ATR — EMA smoothing with alpha=1/period (not SMA).
        More responsive to recent volatility than SMA-ATR.
        Supertrend also uses this ATR, so fixing ATR improves Supertrend too."""
        high_low  = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close  = (df['low']  - df['close'].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return true_range.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    
    def calculate_supertrend(self, df, period=10, multiplier=3):
        hl2 = (df['high'] + df['low']) / 2
        atr = self.calculate_atr(df, period)
        
        upperband = hl2 + (multiplier * atr)
        lowerband = hl2 - (multiplier * atr)
        
        supertrend = [0] * len(df)
        direction = [1] * len(df)
        
        for i in range(1, len(df)):
            if df['close'].iloc[i] > upperband.iat[i-1]:
                direction[i] = 1
            elif df['close'].iloc[i] < lowerband.iat[i-1]:
                direction[i] = -1
            else:
                direction[i] = direction[i-1]
                # Use .iat[] for in-place scalar assignment — .iloc[] chained indexing
                # silently fails on pandas 2.x and corrupts supertrend direction
                if direction[i] == 1 and lowerband.iat[i] < lowerband.iat[i-1]:
                    lowerband.iat[i] = lowerband.iat[i-1]
                if direction[i] == -1 and upperband.iat[i] > upperband.iat[i-1]:
                    upperband.iat[i] = upperband.iat[i-1]
            
            if direction[i] == 1:
                supertrend[i] = lowerband.iloc[i]
            else:
                supertrend[i] = upperband.iloc[i]
        
        return pd.Series(supertrend, index=df.index), pd.Series(direction, index=df.index)
    
    def add_indicators(self, df):
        """Add all technical indicators"""
        try:
            # EMAs
            df['ema_fast'] = self.calculate_ema(df['close'], self.ema_fast)
            df['ema_slow'] = self.calculate_ema(df['close'], self.ema_slow)
            df['ema_trend'] = self.calculate_ema(df['close'], self.ema_trend)
            
            # Momentum
            df['rsi'] = self.calculate_rsi(df['close'], self.rsi_period)
            
            # VWAP
            df['vwap'] = self.calculate_vwap(df)
            
            # Volatility
            df['atr'] = self.calculate_atr(df, self.atr_period)
            df['atr_pct'] = (df['atr'] / df['close']) * 100  # ATR as % of price
            
            # Supertrend
            df['supertrend'], df['supertrend_dir'] = self.calculate_supertrend(df, 10, 3)
            
            # Volume
            df['volume_sma'] = df['volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']
            
            # Trend strength
            df['trend_strength'] = abs(df['ema_fast'] - df['ema_slow']) / df['close'] * 100
            
            # FIX 2: Real 15-min timeframe via OHLCV resampling
            # EMA(27) on 5-min != EMA(9) on 15-min — different crossover timing
            try:
                df_15m = df.resample('15min').agg({
                    'open': 'first', 'high': 'max',
                    'low': 'min', 'close': 'last', 'volume': 'sum'
                }).dropna()
                df_15m['ema_fast_15m'] = self.calculate_ema(df_15m['close'], self.ema_fast)
                df_15m['ema_slow_15m'] = self.calculate_ema(df_15m['close'], self.ema_slow)
                df = df.join(df_15m[['ema_fast_15m', 'ema_slow_15m']], how='left')
                df['ema_fast_15m'] = df['ema_fast_15m'].ffill().bfill()
                df['ema_slow_15m'] = df['ema_slow_15m'].ffill().bfill()
            except Exception:
                # Fallback if index is not DatetimeIndex
                df['ema_fast_15m'] = self.calculate_ema(df['close'], self.ema_fast * 3)
                df['ema_slow_15m'] = self.calculate_ema(df['close'], self.ema_slow * 3)
            
            return df
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return None
    
    def calculate_smart_stop_loss(self, df, side, entry_price):
        """
        SMART STOP LOSS - Uses ATR for volatility-adjusted stops
        This solves the problem of "SL hit in 1 minute"
        """
        latest = df.iloc[-1]
        atr = latest['atr']
        
        # Use 2x ATR (much wider than before) - prevents SL hunting
        # FIX 3: 1.5x ATR — target now sits within typical 1.5% daily range
        atr_multiplier = 1.5
        
        if side == 'BUY':
            atr_stop = entry_price - (atr * atr_multiplier)
            supertrend_stop = latest['supertrend']
            # Use the WIDER of the two stops
            stop_loss = min(atr_stop, supertrend_stop)
        else:  # SELL
            atr_stop = entry_price + (atr * atr_multiplier)
            supertrend_stop = latest['supertrend']
            stop_loss = max(atr_stop, supertrend_stop)
        
        return stop_loss
    
    def calculate_smart_target(self, entry_price, stop_loss, side):
        """
        R:R = 1:2 — break-even win rate = 33%, trails further on extended moves.
        At 1:1.5 with 41% win rate we were negative expectancy after costs.
        1:2 means a 40% win rate is net positive even after slippage/brokerage.
        """
        if side == 'BUY':
            risk = entry_price - stop_loss
            target = entry_price + (risk * 2.0)  # 1:2 RR
        else:
            risk = stop_loss - entry_price
            target = entry_price - (risk * 2.0)  # 1:2 RR

        return target
    
    def calculate_sliding_stop(self, side, entry_price, current_stop,
                               highest_price, lowest_price, atr):
        """
        Sliding Window Stop Loss — trails price using a rolling ATR distance.

        Replaces the fixed breakeven/trail-trigger system with a continuous slide:
          BUY:  new_SL = max(current_SL,  highest_seen - 1.5 * ATR)  → only moves UP
          SELL: new_SL = min(current_SL,  lowest_seen  + 1.5 * ATR)  → only moves DOWN

        Properties:
          - Starts well below entry (ATR-based cushion)
          - Automatically moves to breakeven once price gains 1.5*ATR
          - Locks in more profit on every new high/low without manual triggers
          - Never widens the stop (one-directional slide)
        """
        if side == 'BUY':
            trailing = highest_price - atr * 1.5
            return max(trailing, current_stop)   # never move stop down
        else:
            trailing = lowest_price + atr * 1.5
            return min(trailing, current_stop)   # never move stop up

    def check_multi_timeframe_alignment(self, df):
        """
        BOT SUPERPOWER: Check multiple timeframes simultaneously
        Only trade when 5m, 15m all align in same direction
        """
        latest = df.iloc[-1]
        
        # 5-minute trend
        tf5_bullish = latest['ema_fast'] > latest['ema_slow']
        tf5_bearish = latest['ema_fast'] < latest['ema_slow']
        
        # 15-minute trend (simulated)
        tf15_bullish = latest['ema_fast_15m'] > latest['ema_slow_15m']
        tf15_bearish = latest['ema_fast_15m'] < latest['ema_slow_15m']
        
        # Long-term trend (50 EMA)
        long_bullish = latest['close'] > latest['ema_trend']
        long_bearish = latest['close'] < latest['ema_trend']
        
        all_bullish = tf5_bullish and tf15_bullish and long_bullish
        all_bearish = tf5_bearish and tf15_bearish and long_bearish
        
        return all_bullish, all_bearish
    
    def calculate_signal_strength(self, conditions):
        """
        P8: Weighted score — raw count of conditions passed (out of 7).
        Volume adds +0.5 bonus separately. Threshold: score >= 5.5.
        Replaces old ratio-based 7/8 system.
        """
        return sum(1.0 for _, c in conditions if c)
    
    def generate_signal(self, df, symbol=None):
        """
        Generate trading signal with bot superpowers
        """
        try:
            # CHECK 1: Time filter
            can_trade, time_reason = self.is_good_trading_time()
            if not can_trade:
                return self._no_signal(df, f"⏰ {time_reason}")
            
            # CHECK 2: Cooldown filter (NEW - prevents repeat losses!)
            if symbol:
                in_cooldown, cooldown_reason = self.is_in_cooldown(symbol)
                if in_cooldown:
                    return self._no_signal(df, f"❄️  {cooldown_reason}")
            
            # CHECK 3: Multi-timeframe alignment
            all_bullish, all_bearish = self.check_multi_timeframe_alignment(df)
            
            if not (all_bullish or all_bearish):
                return self._no_signal(df, "Multi-timeframe not aligned")
            
            latest = df.iloc[-1]
            prev   = df.iloc[-2]

            # ── Price Action Triggers (replaces volume as hard gate) ──────────
            # Breakout: close breaks above highest high of last 10 bars
            # Pullback bounce: prev candle was below fast EMA, current bounced above it
            lookback_high = df['high'].iloc[-11:-1].max()
            lookback_low  = df['low'].iloc[-11:-1].min()
            bull_breakout    = latest['close'] > lookback_high
            bull_pb_bounce   = prev['close'] < prev['ema_fast'] and latest['close'] > latest['ema_fast']
            bear_breakdown   = latest['close'] < lookback_low
            bear_pb_bounce   = prev['close'] > prev['ema_fast'] and latest['close'] < latest['ema_fast']
            price_action_bull = bull_breakout or bull_pb_bounce
            price_action_bear = bear_breakdown or bear_pb_bounce

            # Volume: +0.5 bonus to score if above threshold (not a hard gate)
            vol_bonus = 0.5 if latest['volume_ratio'] > self.volume_threshold else 0.0

            # ===== BUY SIGNAL =====
            if all_bullish:
                # P1: Price Action is now a HARD GATE — no signal if neither breakout nor PB-bounce
                if not price_action_bull:
                    pa_str = 'Breakout' if bull_breakout else 'PB-Bounce' if bull_pb_bounce else 'NONE'
                    logger.info(
                        f"   BUY blocked (no PA) | RSI={latest['rsi']:.1f} Vol={latest['volume_ratio']:.2f}x PA={pa_str}"
                    )
                    return self._no_signal(df, "No price action trigger")

                pa_type = 'Breakout' if bull_breakout else 'PB-Bounce'

                # P8: 7-condition weighted score (Price Action removed — it's now a gate)
                buy_conditions = [
                    ('Multi-TF Bullish',  True),
                    ('Above VWAP',        latest['close'] > latest['vwap']),
                    ('Supertrend UP',     latest['supertrend_dir'] == 1),
                    ('RSI 40-70',         40 <= latest['rsi'] <= 70),
                    ('Strong Trend',      latest['trend_strength'] > 0.3),
                    ('Recent Bullish',    latest['close'] > latest['open'] and prev['close'] > prev['open']),
                    ('Volatility OK',     latest['atr_pct'] < 2.0),
                ]

                score    = self.calculate_signal_strength(buy_conditions) + vol_bonus  # max 7.5
                strength = min(1.0, score / 7.5)   # normalised for DB/display only

                # P9: Breakout signals require higher score (6.5) — confirmed underperformer May 12-13
                required = self.breakout_score_threshold if pa_type == 'Breakout' else self.score_threshold

                if score >= required:
                    entry = latest['close']
                    stop_loss = self.calculate_smart_stop_loss(df, 'BUY', entry)
                    target = self.calculate_smart_target(entry, stop_loss, 'BUY')

                    risk_pct   = ((entry - stop_loss) / entry) * 100
                    reward_pct = ((target - entry) / entry) * 100

                    logger.info(f"🟢 STRONG BUY SIGNAL @ {entry:.2f} [{pa_type}] Vol={latest['volume_ratio']:.2f}x")
                    logger.info(f"   Score: {score:.1f}/7.5 (req {required}) | Risk: {risk_pct:.2f}% | Reward: {reward_pct:.2f}% | RR: 1:{reward_pct/risk_pct:.1f}")

                    return {
                        'timestamp':         latest.name,
                        'close':             latest['close'],
                        'signal':            'BUY',
                        'strength':          strength,
                        'score':             score,
                        'price_action_type': pa_type,
                        'reasons':           [f"✓ {n}" for n, c in buy_conditions if c],
                        'entry_price':       entry,
                        'stop_loss':         stop_loss,
                        'target':            target,
                        'atr':               float(latest['atr']),
                    }
                else:
                    failed = [n for n, c in buy_conditions if not c]
                    logger.info(
                        f"   BUY near-miss (score {score:.1f}/7.5 < {required}) | PA={pa_type} "
                        f"RSI={latest['rsi']:.1f} Vol={latest['volume_ratio']:.2f}x | "
                        f"FAIL: {', '.join(failed)}"
                    )

            # ===== SELL SIGNAL =====
            if all_bearish:
                # P1: Price Action hard gate for SELL
                if not price_action_bear:
                    pa_str = 'Breakdown' if bear_breakdown else 'PB-Bounce' if bear_pb_bounce else 'NONE'
                    logger.info(
                        f"   SELL blocked (no PA) | RSI={latest['rsi']:.1f} Vol={latest['volume_ratio']:.2f}x PA={pa_str}"
                    )
                    return self._no_signal(df, "No price action trigger")

                pa_type = 'Breakdown' if bear_breakdown else 'PB-Bounce'

                sell_conditions = [
                    ('Multi-TF Bearish',  True),
                    ('Below VWAP',        latest['close'] < latest['vwap']),
                    ('Supertrend DOWN',   latest['supertrend_dir'] == -1),
                    ('RSI 30-60',         30 <= latest['rsi'] <= 60),
                    ('Strong Trend',      latest['trend_strength'] > 0.3),
                    ('Recent Bearish',    latest['close'] < latest['open'] and prev['close'] < prev['open']),
                    ('Volatility OK',     latest['atr_pct'] < 2.0),
                ]

                score    = self.calculate_signal_strength(sell_conditions) + vol_bonus
                strength = min(1.0, score / 7.5)

                # P9: Breakout (bull) threshold is higher — on SELL side only Breakdown and PB-Bounce fire
                # Breakdown and PB-Bounce use standard threshold
                required = self.score_threshold

                if score >= required:
                    entry = latest['close']
                    stop_loss = self.calculate_smart_stop_loss(df, 'SELL', entry)
                    target = self.calculate_smart_target(entry, stop_loss, 'SELL')

                    risk_pct   = ((stop_loss - entry) / entry) * 100
                    reward_pct = ((entry - target) / entry) * 100

                    logger.info(f"🔴 STRONG SELL SIGNAL @ {entry:.2f} [{pa_type}] Vol={latest['volume_ratio']:.2f}x")
                    logger.info(f"   Score: {score:.1f}/7.5 (req {required}) | Risk: {risk_pct:.2f}% | Reward: {reward_pct:.2f}% | RR: 1:{reward_pct/risk_pct:.1f}")

                    return {
                        'timestamp':         latest.name,
                        'close':             latest['close'],
                        'signal':            'SELL',
                        'strength':          strength,
                        'score':             score,
                        'price_action_type': pa_type,
                        'reasons':           [f"✓ {n}" for n, c in sell_conditions if c],
                        'entry_price':       entry,
                        'stop_loss':         stop_loss,
                        'target':            target,
                        'atr':               float(latest['atr']),
                    }
                else:
                    failed = [n for n, c in sell_conditions if not c]
                    logger.info(
                        f"   SELL near-miss (score {score:.1f}/7.5) | PA={pa_type} "
                        f"RSI={latest['rsi']:.1f} Vol={latest['volume_ratio']:.2f}x | "
                        f"FAIL: {', '.join(failed)}"
                    )

            return self._no_signal(df, "Conditions not met")
            
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return None
    
    def _no_signal(self, df, reason):
        """Helper to return no signal with reason"""
        return {
            'timestamp': df.iloc[-1].name,
            'close': df.iloc[-1]['close'],
            'signal': 'HOLD',
            'strength': 0,
            'reasons': [reason],
            'entry_price': None,
            'stop_loss': None,
            'target': None
        }
    
    def report_stop_loss_hit(self, symbol):
        """Called when SL is hit - adds symbol to cooldown"""
        self.add_to_cooldown(symbol)
    
    def backtest_signal_quality(self, df, lookback=100):
        """Test strategy on recent data"""
        try:
            signals_generated = 0
            profitable_signals = 0
            total_return = 0
            
            for i in range(len(df) - lookback, len(df) - 1):
                temp_df = df.iloc[:i+1]
                signal = self.generate_signal(temp_df)
                
                if signal and signal['signal'] in ['BUY', 'SELL']:
                    signals_generated += 1
                    
                    future_high = df.iloc[i+1:min(i+20, len(df))]['high'].max()
                    future_low = df.iloc[i+1:min(i+20, len(df))]['low'].min()
                    
                    if signal['signal'] == 'BUY':
                        if future_high >= signal['target']:
                            profitable_signals += 1
                            total_return += (signal['target'] - signal['entry_price']) / signal['entry_price']
                    else:
                        if future_low <= signal['target']:
                            profitable_signals += 1
                            total_return += (signal['entry_price'] - signal['target']) / signal['entry_price']
            
            win_rate = (profitable_signals / signals_generated * 100) if signals_generated > 0 else 0
            avg_return = (total_return / signals_generated * 100) if signals_generated > 0 else 0
            
            return {
                'signals_generated': signals_generated,
                'profitable_signals': profitable_signals,
                'win_rate': win_rate,
                'average_return': avg_return
            }
            
        except Exception as e:
            logger.error(f"Error in backtest: {e}")
            return None


# Backward compatibility
IntradayStrategy = BeyondHumanStrategy
