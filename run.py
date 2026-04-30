"""
BEYOND-HUMAN TRADING BOT v3.0
- Persistent state via SQLite database
- Multi-timeframe analysis
- Smart trailing stops
- Cooldown system (no repeat losses)
- Symbol performance tracking
- Adaptive learning
"""

import time
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging

from auth import FyersAuth
from data import FyersDataFetcher
from strategy import BeyondHumanStrategy
from orders import OrderManager
from risk_manager import RiskManager
from database import TradingDatabase

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    """Beyond-Human Automated Trading Bot"""
    
    def __init__(self, capital=100000, paper_trading=True, symbols=None):
        self.capital = capital
        self.paper_trading = paper_trading
        self.symbols = symbols or [
            'NSE:SBIN-EQ',
            'NSE:RELIANCE-EQ',
            'NSE:INFY-EQ',
            'NSE:HDFCBANK-EQ',
            'NSE:ICICIBANK-EQ'
        ]
        
        self.running = False
        self.auth = None
        self.data_fetcher = None
        self.strategy = None
        self.order_manager = None
        self.risk_manager = None
        self.db = None  # NEW: Database
        
        self.active_trades = {}
        
        logger.info("="*80)
        logger.info("🤖 BEYOND-HUMAN TRADING BOT v3.0")
        logger.info("="*80)
        logger.info(f"Mode: {'PAPER TRADING 📝' if paper_trading else 'LIVE TRADING 💰'}")
        logger.info(f"Capital: ₹{capital:,.0f}")
        logger.info(f"Symbols: {len(self.symbols)}")
        logger.info("="*80 + "\n")
    
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
            logger.info("3. Strategy (BeyondHuman v3.0)...")
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
            
            # 6. Restore active positions from DB
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
                    'trade_id': pos['trade_id'],
                    'entry_time': datetime.fromisoformat(pos['entry_time']),
                    'entry_price': pos['entry_price'],
                    'original_stop': pos['stop_loss'],
                    'current_stop': pos['current_stop'],
                    'target': pos['target'],
                    'breakeven_trigger': pos['breakeven_trigger'],
                    'trail_trigger': pos['trail_trigger'],
                    'highest_price': pos['highest_price'],
                    'lowest_price': pos['lowest_price'],
                    'partial_booked': bool(pos['partial_booked']),
                    'breakeven_set': bool(pos['breakeven_set']),
                    'max_profit': pos['max_profit']
                }
                self.risk_manager.position_opened()
                logger.info(f"  ✅ Restored: {symbol} {pos['side']} @ ₹{pos['entry_price']:.2f}")
    
    def is_market_open(self):
        return self.data_fetcher.is_market_open()
    
    def scan_for_signals(self):
        """Scan symbols for trading signals"""
        logger.info(f"\n{'='*80}")
        logger.info(f"🔍 SCANNING - {datetime.now().strftime('%H:%M:%S')}")
        logger.info(f"{'='*80}\n")
        
        signals = []
        
        for symbol in self.symbols:
            try:
                # Skip if already in position
                if symbol in self.active_trades:
                    logger.info(f"⏭️  {symbol}: Already in position")
                    continue
                
                # Check cooldown from DB (persists across restarts!)
                in_cooldown, reason = self.db.is_in_cooldown(symbol)
                if in_cooldown:
                    logger.info(f"❄️  {symbol}: {reason}")
                    continue
                
                # Fetch data
                df = self.data_fetcher.get_historical_data(symbol, interval='5', days_back=5)
                if df is None or len(df) < 50:
                    logger.warning(f"⚠️  {symbol}: Insufficient data")
                    continue
                
                # Add indicators
                df = self.strategy.add_indicators(df)
                if df is None:
                    continue
                
                # Generate signal
                signal = self.strategy.generate_signal(df, symbol=symbol)
                
                if signal and signal['signal'] in ['BUY', 'SELL']:
                    signal['symbol'] = symbol
                    signals.append(signal)
                    
                    # Save signal to DB
                    self.db.save_signal(
                        symbol=symbol,
                        signal_type=signal['signal'],
                        price=signal['close'],
                        strength=signal['strength'],
                        reasons=signal['reasons']
                    )
                    
                    logger.info(f"\n{'🟢' if signal['signal'] == 'BUY' else '🔴'} {signal['signal']}: {symbol}")
                    logger.info(f"  Price: ₹{signal['close']:.2f} | Strength: {signal['strength']*100:.0f}%")
                    logger.info(f"  Entry: ₹{signal['entry_price']:.2f}")
                    logger.info(f"  Stop Loss: ₹{signal['stop_loss']:.2f}")
                    logger.info(f"  Target: ₹{signal['target']:.2f}")
                else:
                    if signal and signal.get('reasons'):
                        logger.info(f"➖ {symbol}: {signal['reasons'][0] if signal['reasons'] else 'No signal'}")
                
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                continue
        
        logger.info(f"\n📊 Scan complete: {len(signals)} signals found\n")
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
                # Save to database
                trade_id = self.db.save_trade(
                    symbol=symbol, side=side, quantity=quantity,
                    entry_price=entry_price, stop_loss=stop_loss, target=target,
                    paper_trading=self.paper_trading
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
                    'order': order,
                    'signal': signal,
                    'trade_id': trade_id,
                    'entry_time': datetime.now(),
                    'entry_price': entry_price,
                    'side': side,
                    'quantity': quantity,
                    'original_stop': stop_loss,
                    'stop_loss': stop_loss,
                    'current_stop': stop_loss,
                    'target': target,
                    'breakeven_trigger': breakeven_trigger,
                    'trail_trigger': trail_trigger,
                    'highest_price': entry_price,
                    'lowest_price': entry_price,
                    'partial_booked': False,
                    'breakeven_set': False,
                    'max_profit': 0
                }
                
                self.active_trades[symbol] = position_data
                
                # Save to database for persistence!
                self.db.save_active_position(symbol, position_data)
                
                self.risk_manager.position_opened()
                
                logger.info(f"✅ Trade executed! Trade ID: {trade_id}")
                logger.info(f"   Breakeven: ₹{breakeven_trigger:.2f}")
                logger.info(f"   Trail trigger: ₹{trail_trigger:.2f}")
                logger.info(f"{'='*80}\n")
                return True
                
        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            return False
    
    def monitor_positions(self):
        """Smart monitoring with trailing stops + DB updates"""
        if not self.active_trades:
            return
        
        logger.info(f"\n📊 Monitoring {len(self.active_trades)} position(s)...")
        
        for symbol in list(self.active_trades.keys()):
            try:
                trade = self.active_trades[symbol]
                order = trade['order']
                
                quote = self.data_fetcher.get_live_quote([symbol])
                if not quote:
                    continue
                
                current_price = quote[0]['v']['lp']
                entry_price = trade['entry_price']
                side = order['side']
                quantity = order['quantity']
                
                # Update tracking
                if current_price > trade['highest_price']:
                    trade['highest_price'] = current_price
                if current_price < trade['lowest_price']:
                    trade['lowest_price'] = current_price
                
                # Calculate P&L
                if side == 'BUY':
                    pnl = (current_price - entry_price) * quantity
                else:
                    pnl = (entry_price - current_price) * quantity
                
                if pnl > trade['max_profit']:
                    trade['max_profit'] = pnl
                    self.db.update_position(symbol, max_profit=pnl, 
                                          highest_price=trade['highest_price'],
                                          lowest_price=trade['lowest_price'])
                
                pnl_pct = (pnl / (entry_price * quantity)) * 100
                logger.info(f"  {symbol}: ₹{current_price:.2f} | P&L: ₹{pnl:.2f} ({pnl_pct:+.2f}%) | Max: ₹{trade['max_profit']:.2f}")
                
                if not self.paper_trading:
                    continue
                
                # ===== SMART EXITS =====
                
                # 1. Stop Loss
                hit_stop = (side == 'BUY' and current_price <= trade['current_stop']) or \
                          (side == 'SELL' and current_price >= trade['current_stop'])
                
                if hit_stop:
                    if trade['breakeven_set']:
                        logger.info(f"  ✅ Trailing stop hit (PROFIT LOCKED!)")
                        self.close_position(symbol, current_price, 'TRAILING_STOP')
                    else:
                        logger.info(f"  📍 Stop loss hit!")
                        # Add to cooldown!
                        self.db.add_cooldown(symbol, minutes=45, reason="Stop loss hit")
                        self.close_position(symbol, current_price, 'STOP_LOSS')
                    continue
                
                # 2. Target
                hit_target = (side == 'BUY' and current_price >= trade['target']) or \
                            (side == 'SELL' and current_price <= trade['target'])
                
                if hit_target:
                    logger.info(f"  🎯 Target hit!")
                    self.close_position(symbol, current_price, 'TARGET')
                    continue
                
                # 3. Move SL to Breakeven at 50% target
                if not trade['breakeven_set']:
                    breakeven_hit = (side == 'BUY' and current_price >= trade['breakeven_trigger']) or \
                                   (side == 'SELL' and current_price <= trade['breakeven_trigger'])
                    
                    if breakeven_hit:
                        trade['current_stop'] = entry_price
                        trade['breakeven_set'] = True
                        self.db.update_position(symbol, current_stop=entry_price, breakeven_set=True)
                        logger.info(f"  🔒 BREAKEVEN: SL moved to ₹{entry_price:.2f} (RISK FREE!)")
                
                # 4. Trailing Stop after 1:1 RR
                if trade['breakeven_set']:
                    trail_hit = (side == 'BUY' and current_price >= trade['trail_trigger']) or \
                               (side == 'SELL' and current_price <= trade['trail_trigger'])
                    
                    if trail_hit:
                        if side == 'BUY':
                            profit_distance = trade['highest_price'] - entry_price
                            new_stop = entry_price + (profit_distance * 0.5)
                            if new_stop > trade['current_stop']:
                                trade['current_stop'] = new_stop
                                self.db.update_position(symbol, current_stop=new_stop)
                                logger.info(f"  📈 TRAILING UP: SL at ₹{new_stop:.2f}")
                        else:
                            profit_distance = entry_price - trade['lowest_price']
                            new_stop = entry_price - (profit_distance * 0.5)
                            if new_stop < trade['current_stop']:
                                trade['current_stop'] = new_stop
                                self.db.update_position(symbol, current_stop=new_stop)
                                logger.info(f"  📉 TRAILING DOWN: SL at ₹{new_stop:.2f}")
                
                # 5. Profit Giveback Protection
                if trade['max_profit'] > 200:
                    giveback = trade['max_profit'] - pnl
                    if giveback > (trade['max_profit'] * 0.5):
                        logger.info(f"  ⚠️  Giveback exit (₹{pnl:.2f} of max ₹{trade['max_profit']:.2f})")
                        self.close_position(symbol, current_price, 'PROFIT_GIVEBACK')
                        continue
                
                # 6. Time Exit (60 min if profitable)
                holding_time = (datetime.now() - trade['entry_time']).seconds / 60
                if holding_time > 60 and pnl > 0:
                    logger.info(f"  🕐 Time exit ({holding_time:.0f} min)")
                    self.close_position(symbol, current_price, 'TIME_EXIT')
                    continue
                
                # 7. EOD Exit
                if datetime.now().time() >= datetime.strptime("15:15", "%H:%M").time():
                    logger.info(f"  🕐 EOD exit")
                    self.close_position(symbol, current_price, 'EOD')
                    continue
                
            except Exception as e:
                logger.error(f"Error monitoring {symbol}: {e}")
    
    def close_position(self, symbol, exit_price, reason):
        """Close position and update database"""
        try:
            if symbol not in self.active_trades:
                return
            
            trade = self.active_trades[symbol]
            order = trade['order']
            entry_price = trade['entry_price']
            
            # Record in risk manager
            self.risk_manager.record_trade(
                entry_price=entry_price, exit_price=exit_price,
                quantity=order['quantity'], side=order['side']
            )
            
            # Close in database
            if 'trade_id' in trade:
                pnl = self.db.close_trade(trade['trade_id'], exit_price, reason)
                logger.info(f"💾 DB: Trade #{trade['trade_id']} closed, P&L: ₹{pnl:.2f}")
            
            # Save updated capital
            self.db.save_state('current_capital', self.risk_manager.total_capital)
            
            # Remove from active
            del self.active_trades[symbol]
            self.db.remove_active_position(symbol)
            
            logger.info(f"✅ Closed: {symbol} | Reason: {reason}")
            
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
        
        self.running = True
        scan_interval = 60
        last_scan = datetime.now() - timedelta(seconds=scan_interval)
        
        try:
            while self.running:
                try:
                    if not self.is_market_open():
                        logger.info("⏰ Market closed - waiting...")
                        time.sleep(300)
                        continue
                    
                    if (datetime.now() - last_scan).seconds >= scan_interval:
                        signals = self.scan_for_signals()
                        last_scan = datetime.now()
                        
                        for signal in signals:
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
        """Stop bot gracefully"""
        logger.info("\n" + "="*80)
        logger.info("🛑 STOPPING BOT")
        logger.info("="*80 + "\n")
        
        self.running = False
        
        # Close positions
        if self.active_trades:
            logger.info("Closing all positions...")
            for symbol in list(self.active_trades.keys()):
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
        
        # All-time stats
        if self.db:
            self.db.print_summary()
            
            # Show best symbols
            best = self.db.get_best_symbols(min_trades=2)
            if best:
                print("\n🏆 BEST PERFORMING SYMBOLS:")
                for s in best[:5]:
                    print(f"  {s['symbol']}: {s['win_rate']:.1f}% win | ₹{s['total_pnl']:.2f}")
            
            self.db.close()
        
        logger.info("✅ Bot stopped\n")


def main():
    print("\n" + "="*80)
    print("🤖 BEYOND-HUMAN TRADING BOT v3.0")
    print("="*80)
    print("\nFeatures:")
    print("  ✅ Persistent state (SQLite database)")
    print("  ✅ Multi-timeframe analysis")
    print("  ✅ Volatility-adjusted stops (no SL hunting)")
    print("  ✅ 45-min cooldown after losses")
    print("  ✅ Smart trailing stops")
    print("  ✅ Symbol performance tracking")
    print("  ✅ Adaptive learning")
    print("\nMode: PAPER TRADING 📝")
    print("Capital: ₹100,000")
    print("="*80 + "\n")
    
    input("Press ENTER to start...")
    
    bot = TradingBot(
        capital=100000,
        paper_trading=True,
        symbols=[
            'NSE:SBIN-EQ',
            'NSE:RELIANCE-EQ',
            'NSE:INFY-EQ',
            'NSE:HDFCBANK-EQ',
            'NSE:ICICIBANK-EQ'
        ]
    )
    
    bot.run()


if __name__ == "__main__":
    main()