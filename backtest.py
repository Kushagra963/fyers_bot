"""
BEYOND-HUMAN BACKTESTING ENGINE v1.0
=====================================
Runs the live strategy logic on historical 5-min OHLCV data for all 148 symbols.
Simulates full trade lifecycle: entry, SL, target, giveback, time exit.
Accounts for brokerage costs (Fyers flat ₹20/order + STT + exchange charges).

Usage:
    python backtest.py                     # full 90-day backtest, all symbols
    python backtest.py --days 60           # 60-day backtest
    python backtest.py --symbols 30        # top 30 symbols only (faster)
    python backtest.py --days 60 --symbols 30

Output:
    - Per-day P&L summary
    - Per-symbol win rate + expectancy
    - PA type breakdown (Breakout vs Breakdown vs PB-Bounce)
    - Overall stats with cost-adjusted expectancy
    - Saved to backtest_results.csv
"""

import argparse
import time
import sys
import os
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backtest.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# ── Cost model ────────────────────────────────────────────────────────────────
# Per round-trip (buy + sell):
#   Fyers brokerage: ₹20 × 2 = ₹40
#   STT (sell side): 0.025% of sell turnover
#   Exchange charges: 0.00345% each side → ~0.0069% round-trip
#   GST (18% on brokerage + exchange): ~₹8
#   Stamp duty (buy side): 0.015%
#   SEBI: negligible
BROKERAGE_PER_TRADE  = 40.0   # flat both sides
STT_RATE             = 0.00025  # 0.025% on sell
EXCHANGE_RATE        = 0.0000345 * 2  # both sides
GST_RATE             = 0.18
STAMP_RATE           = 0.00015  # buy side only


def calculate_cost(entry_price: float, exit_price: float, quantity: int) -> float:
    """Calculate realistic round-trip transaction cost."""
    buy_value  = entry_price * quantity
    sell_value = exit_price  * quantity
    brokerage  = BROKERAGE_PER_TRADE
    stt        = sell_value * STT_RATE
    exchange   = (buy_value + sell_value) * EXCHANGE_RATE / 2
    gst        = (brokerage + exchange) * GST_RATE
    stamp      = buy_value * STAMP_RATE
    return brokerage + stt + exchange + gst + stamp


def simulate_trade(entry_candle_idx: int, df: pd.DataFrame, signal: dict,
                   quantity: int) -> dict:
    """
    Simulate a trade from entry_candle_idx forward through df.
    Uses OHLC intra-candle logic: within each candle, assumes SL hits
    before target if both are in range (conservative).

    Returns a dict with pnl, exit_reason, exit_idx, max_profit, hold_minutes.
    """
    side         = signal['signal']
    entry_price  = signal['entry_price']
    stop_loss    = signal['stop_loss']
    target       = signal['target']
    atr          = signal.get('atr', entry_price * 0.015)

    current_stop = stop_loss
    max_profit   = 0.0
    partial_done = False
    breakeven_set= False
    highest      = entry_price
    lowest       = entry_price
    entry_time   = df.index[entry_candle_idx]

    for i in range(entry_candle_idx + 1, len(df)):
        candle      = df.iloc[i]
        candle_high = candle['high']
        candle_low  = candle['low']
        candle_time = df.index[i]
        hold_mins   = (candle_time - entry_time).total_seconds() / 60

        # Update extremes
        if candle_high > highest:
            highest = candle_high
        if candle_low < lowest:
            lowest = candle_low

        # Mid-candle P&L estimate (use close)
        mid_price = candle['close']
        pnl = ((mid_price - entry_price) if side == 'BUY'
               else (entry_price - mid_price)) * quantity
        if pnl > max_profit:
            max_profit = pnl

        # ── Check SL first (conservative) ──────────────────────────────
        if side == 'BUY':
            sl_hit = candle_low <= current_stop
        else:
            sl_hit = candle_high >= current_stop

        if sl_hit:
            exit_price = current_stop
            exit_pnl   = ((exit_price - entry_price) if side == 'BUY'
                          else (entry_price - exit_price)) * quantity
            label = 'TRAILING_STOP' if breakeven_set else 'STOP_LOSS'
            cost  = calculate_cost(entry_price, exit_price, quantity)
            return {
                'pnl': exit_pnl - cost, 'gross_pnl': exit_pnl, 'cost': cost,
                'exit_reason': label, 'hold_minutes': hold_mins,
                'max_profit': max_profit, 'exit_price': exit_price,
            }

        # ── Check target ────────────────────────────────────────────────
        if side == 'BUY':
            tgt_hit = candle_high >= target
        else:
            tgt_hit = candle_low <= target

        if tgt_hit:
            exit_price = target
            exit_pnl   = ((exit_price - entry_price) if side == 'BUY'
                          else (entry_price - exit_price)) * quantity
            cost = calculate_cost(entry_price, exit_price, quantity)
            return {
                'pnl': exit_pnl - cost, 'gross_pnl': exit_pnl, 'cost': cost,
                'exit_reason': 'TARGET', 'hold_minutes': hold_mins,
                'max_profit': max_profit, 'exit_price': exit_price,
            }

        # ── Sliding ATR stop ────────────────────────────────────────────
        if side == 'BUY':
            new_stop = max(current_stop, highest - atr * 1.5)
        else:
            new_stop = min(current_stop, lowest + atr * 1.5)
        current_stop = new_stop

        is_risk_free = ((side == 'BUY' and new_stop >= entry_price) or
                        (side == 'SELL' and new_stop <= entry_price))
        if is_risk_free:
            breakeven_set = True

        # ── Partial profit (1:1 RR → move to breakeven) ─────────────────
        if not partial_done:
            if side == 'BUY':
                risk_amount = (entry_price - stop_loss) * quantity
            else:
                risk_amount = (stop_loss - entry_price) * quantity
            if pnl >= risk_amount > 0:
                current_stop = entry_price
                partial_done = True
                breakeven_set = True

        # ── Giveback protection (tiered) ────────────────────────────────
        if max_profit > 150 and hold_mins >= 20:
            giveback_pct = (max_profit - pnl) / max_profit
            threshold    = 0.30 if hold_mins > 60 else 0.50
            if giveback_pct > threshold:
                exit_price = mid_price
                exit_pnl   = ((exit_price - entry_price) if side == 'BUY'
                              else (entry_price - exit_price)) * quantity
                cost = calculate_cost(entry_price, exit_price, quantity)
                return {
                    'pnl': exit_pnl - cost, 'gross_pnl': exit_pnl, 'cost': cost,
                    'exit_reason': 'PROFIT_GIVEBACK', 'hold_minutes': hold_mins,
                    'max_profit': max_profit, 'exit_price': exit_price,
                }

        # ── Time exit: 90 min ───────────────────────────────────────────
        if hold_mins >= 90:
            exit_price = candle['close']
            exit_pnl   = ((exit_price - entry_price) if side == 'BUY'
                          else (entry_price - exit_price)) * quantity
            cost = calculate_cost(entry_price, exit_price, quantity)
            return {
                'pnl': exit_pnl - cost, 'gross_pnl': exit_pnl, 'cost': cost,
                'exit_reason': 'TIME_EXIT', 'hold_minutes': hold_mins,
                'max_profit': max_profit, 'exit_price': exit_price,
            }

        # ── EOD exit (15:15) ────────────────────────────────────────────
        if hasattr(candle_time, 'time') and candle_time.time() >= pd.Timestamp('15:15').time():
            exit_price = candle['close']
            exit_pnl   = ((exit_price - entry_price) if side == 'BUY'
                          else (entry_price - exit_price)) * quantity
            cost = calculate_cost(entry_price, exit_price, quantity)
            return {
                'pnl': exit_pnl - cost, 'gross_pnl': exit_pnl, 'cost': cost,
                'exit_reason': 'EOD', 'hold_minutes': hold_mins,
                'max_profit': max_profit, 'exit_price': exit_price,
            }

    # End of data — close at last price
    exit_price = df.iloc[-1]['close']
    exit_pnl   = ((exit_price - entry_price) if side == 'BUY'
                  else (entry_price - exit_price)) * quantity
    cost = calculate_cost(entry_price, exit_price, quantity)
    return {
        'pnl': exit_pnl - cost, 'gross_pnl': exit_pnl, 'cost': cost,
        'exit_reason': 'DATA_END', 'hold_minutes': 0,
        'max_profit': max_profit, 'exit_price': exit_price,
    }


def backtest_symbol(symbol: str, df: pd.DataFrame, strategy) -> list:
    """
    Run backtest on a single symbol's historical data.
    Returns list of trade result dicts.
    """
    trades = []
    min_candles = 60   # need at least 60 candles for indicators to warm up
    cooldown_until = None   # timestamp after which next trade is allowed

    for i in range(min_candles, len(df) - 5):
        candle_time = df.index[i]

        # Skip if in cooldown
        if cooldown_until and candle_time < cooldown_until:
            continue

        # Time filter: only scan 9:45–14:45
        if hasattr(candle_time, 'time'):
            t = candle_time.time()
            from datetime import time as dtime
            if not (dtime(9, 45) <= t <= dtime(14, 45)):
                continue

        # Run strategy on data up to this candle
        window = df.iloc[:i + 1].copy()
        window = strategy.add_indicators(window)
        if window is None or len(window) < 50:
            continue

        signal = strategy.generate_signal(window, symbol=symbol, backtest_mode=True)
        if signal is None or signal['signal'] not in ['BUY', 'SELL']:
            continue

        # Position size: 2% capital risk (assume ₹1,00,000 capital)
        capital    = 100_000
        risk_amt   = capital * 0.02
        entry      = signal['entry_price']
        sl         = signal['stop_loss']
        risk_per_share = abs(entry - sl)
        if risk_per_share <= 0:
            continue
        quantity = max(1, int(risk_amt / risk_per_share))
        quantity = min(quantity, int(capital * 0.25 / entry))  # max 25% capital per trade

        result = simulate_trade(i, df, signal, quantity)
        result.update({
            'symbol':            symbol,
            'side':              signal['signal'],
            'entry_price':       entry,
            'stop_loss':         sl,
            'target':            signal['target'],
            'quantity':          quantity,
            'entry_time':        str(candle_time),
            'pa_type':           signal.get('price_action_type', 'Unknown'),
            'score':             signal.get('score', 0),
            'strength':          signal.get('strength', 0),
        })
        trades.append(result)

        # Apply 45-min cooldown after any trade (matches live bot)
        exit_mins   = result['hold_minutes']
        cooldown_until = candle_time + timedelta(minutes=exit_mins + 45)

    return trades


def fetch_symbol_data(symbol: str, data_fetcher, days_back: int) -> pd.DataFrame:
    """Fetch historical data with retry."""
    for attempt in range(3):
        try:
            df = data_fetcher.get_historical_data(symbol, interval='5', days_back=days_back)
            if df is not None and len(df) > 100:
                return df
        except Exception as e:
            logger.warning(f"  {symbol} fetch attempt {attempt+1} failed: {e}")
            time.sleep(2 ** attempt)
    return None


def print_results(all_trades: list, elapsed: float):
    """Print comprehensive backtest report."""
    if not all_trades:
        logger.info("No trades generated.")
        return

    df = pd.DataFrame(all_trades)

    total     = len(df)
    wins      = df[df['pnl'] > 0]
    losses    = df[df['pnl'] <= 0]
    win_rate  = len(wins) / total * 100
    total_pnl = df['pnl'].sum()
    avg_win   = wins['pnl'].mean() if len(wins) else 0
    avg_loss  = losses['pnl'].mean() if len(losses) else 0
    rr_ratio  = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    expectancy = df['pnl'].mean()
    total_cost = df['cost'].sum()
    gross_pnl  = df['gross_pnl'].sum()
    avg_hold   = df['hold_minutes'].mean()

    print("\n" + "="*70)
    print("  BEYOND-HUMAN BACKTEST RESULTS")
    print("="*70)
    print(f"  Period        : {df['entry_time'].min()[:10]} → {df['entry_time'].max()[:10]}")
    print(f"  Symbols       : {df['symbol'].nunique()}")
    print(f"  Total trades  : {total}")
    print(f"  Winners/Losers: {len(wins)}W / {len(losses)}L")
    print(f"  Win Rate      : {win_rate:.1f}%")
    print(f"  Avg Win       : ₹{avg_win:.0f}")
    print(f"  Avg Loss      : ₹{avg_loss:.0f}")
    print(f"  RR Ratio      : {rr_ratio:.2f}")
    print(f"  Expectancy    : ₹{expectancy:.2f}/trade (after costs)")
    print(f"  Total P&L     : ₹{total_pnl:,.0f} (after costs)")
    print(f"  Gross P&L     : ₹{gross_pnl:,.0f}")
    print(f"  Total Costs   : ₹{total_cost:,.0f}")
    print(f"  Avg hold time : {avg_hold:.0f} min")
    print(f"  Backtest time : {elapsed:.0f}s")

    # Exit reason breakdown
    print("\n--- Exit Reason Breakdown ---")
    for reason, grp in df.groupby('exit_reason'):
        w = (grp['pnl'] > 0).sum()
        print(f"  {reason:<20} {len(grp):>4} trades | {w}W/{len(grp)-w}L | "
              f"avg ₹{grp['pnl'].mean():.0f} | total ₹{grp['pnl'].sum():.0f}")

    # PA type breakdown
    print("\n--- Price Action Type Breakdown ---")
    for pa, grp in df.groupby('pa_type'):
        w = (grp['pnl'] > 0).sum()
        wr = w / len(grp) * 100
        print(f"  {pa:<15} {len(grp):>4} trades | {wr:.0f}% WR | "
              f"avg ₹{grp['pnl'].mean():.0f} | total ₹{grp['pnl'].sum():.0f}")

    # Daily P&L
    print("\n--- Daily P&L (last 20 days) ---")
    df['date'] = df['entry_time'].str[:10]
    daily = df.groupby('date')['pnl'].agg(['sum', 'count'])
    daily.columns = ['pnl', 'trades']
    for date, row in daily.tail(20).iterrows():
        bar = '▓' * int(abs(row['pnl']) / 50)
        sign = '+' if row['pnl'] >= 0 else '-'
        print(f"  {date}  {sign}₹{abs(row['pnl']):>6.0f}  {bar}  ({row['trades']:.0f} trades)")

    # Top / bottom symbols
    sym_stats = df.groupby('symbol')['pnl'].agg(['sum', 'count', 'mean'])
    sym_stats.columns = ['total', 'trades', 'avg']
    sym_stats = sym_stats[sym_stats['trades'] >= 3]
    print("\n--- Top 5 Symbols ---")
    for sym, row in sym_stats.nlargest(5, 'total').iterrows():
        print(f"  {sym:<25} {row['trades']:.0f} trades | avg ₹{row['avg']:.0f} | total ₹{row['total']:.0f}")
    print("--- Bottom 5 Symbols ---")
    for sym, row in sym_stats.nsmallest(5, 'total').iterrows():
        print(f"  {sym:<25} {row['trades']:.0f} trades | avg ₹{row['avg']:.0f} | total ₹{row['total']:.0f}")

    print("="*70 + "\n")

    # Save CSV
    df.to_csv('backtest_results.csv', index=False)
    logger.info("✅ Results saved to backtest_results.csv")


def run_backtest(days_back: int = 90, max_symbols: int = None):
    """Main backtest runner."""
    logger.info("="*70)
    logger.info(f"🔬 BEYOND-HUMAN BACKTEST ENGINE v1.0")
    logger.info(f"   Days back : {days_back}")
    logger.info(f"   Symbols   : {max_symbols or 'all'}")
    logger.info("="*70)

    # ── Init components ───────────────────────────────────────────────────
    from auth import FyersAuth
    from data import FyersDataFetcher
    from strategy import BeyondHumanStrategy
    from stocks_config import ALL_SYMBOLS

    auth = FyersAuth()
    if not auth.login():
        logger.error("Auth failed — cannot run backtest")
        return

    data_fetcher = FyersDataFetcher(auth.fyers)
    strategy     = BeyondHumanStrategy()

    symbols = ALL_SYMBOLS[:max_symbols] if max_symbols else ALL_SYMBOLS
    logger.info(f"Running on {len(symbols)} symbols over {days_back} days...\n")

    # ── Fetch all historical data ─────────────────────────────────────────
    logger.info("📥 Fetching historical data (this may take a few minutes)...")
    symbol_data = {}
    fetch_start = time.time()

    # Use 4 workers to fetch data in parallel (conservative to avoid 429s)
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix='fetcher') as executor:
        futures = {executor.submit(fetch_symbol_data, sym, data_fetcher, days_back): sym
                   for sym in symbols}
        done = 0
        for future in as_completed(futures):
            sym = futures[future]
            try:
                df = future.result()
                if df is not None:
                    symbol_data[sym] = df
                done += 1
                if done % 20 == 0:
                    logger.info(f"  Fetched {done}/{len(symbols)} symbols "
                                f"({len(symbol_data)} with valid data)...")
            except Exception as e:
                logger.warning(f"  {sym}: fetch failed ({e})")

    logger.info(f"✅ Data fetch complete: {len(symbol_data)}/{len(symbols)} symbols "
                f"in {time.time()-fetch_start:.0f}s\n")

    if not symbol_data:
        logger.error("No data fetched — aborting.")
        return

    # ── Run backtest per symbol ───────────────────────────────────────────
    logger.info("⚙️  Running strategy simulation...")
    all_trades = []
    bt_start   = time.time()

    for idx, (sym, df) in enumerate(symbol_data.items()):
        try:
            trades = backtest_symbol(sym, df, strategy)
            all_trades.extend(trades)
            wins = sum(1 for t in trades if t['pnl'] > 0)
            if trades:
                logger.info(f"  [{idx+1}/{len(symbol_data)}] {sym:<25} "
                            f"{len(trades)} trades | {wins}W/{len(trades)-wins}L | "
                            f"₹{sum(t['pnl'] for t in trades):.0f}")
            else:
                logger.info(f"  [{idx+1}/{len(symbol_data)}] {sym:<25} 0 trades")
        except Exception as e:
            logger.error(f"  {sym}: backtest error — {e}")

    elapsed = time.time() - bt_start
    logger.info(f"\n✅ Simulation complete: {len(all_trades)} total trades in {elapsed:.0f}s\n")

    # ── Print + save results ──────────────────────────────────────────────
    print_results(all_trades, elapsed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Beyond-Human Backtesting Engine')
    parser.add_argument('--days',    type=int, default=90,
                        help='Days of historical data to backtest (default: 90)')
    parser.add_argument('--symbols', type=int, default=None,
                        help='Max number of symbols to test (default: all 148)')
    args = parser.parse_args()

    run_backtest(days_back=args.days, max_symbols=args.symbols)
