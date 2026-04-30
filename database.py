"""
Database Module for Trading Bot
Maintains persistent state across restarts using SQLite
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TradingDatabase:
    """Persistent storage for trading bot using SQLite"""
    
    def __init__(self, db_path='trading_bot.db'):
        self.db_path = db_path
        self.conn = None
        self.connect()
        self.create_tables()
        logger.info(f"Database initialized: {db_path}")
    
    def connect(self):
        """Connect to SQLite database"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
    
    def create_tables(self):
        """Create all required tables"""
        cursor = self.conn.cursor()
        
        # Trades table - all executed trades
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                stop_loss REAL,
                target REAL,
                entry_time TIMESTAMP NOT NULL,
                exit_time TIMESTAMP,
                pnl REAL,
                pnl_percent REAL,
                exit_reason TEXT,
                status TEXT DEFAULT 'OPEN',
                strategy_version TEXT,
                paper_trading BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Signals table - all signals generated
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                price REAL NOT NULL,
                strength REAL,
                reasons TEXT,
                executed BOOLEAN DEFAULT 0,
                timestamp TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Cooldowns table - track stop loss cooldowns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cooldowns (
                symbol TEXT PRIMARY KEY,
                cooldown_until TIMESTAMP NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Daily stats table - track daily performance
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                starting_capital REAL,
                ending_capital REAL,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                win_rate REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Symbol performance table - which stocks work best
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS symbol_performance (
                symbol TEXT PRIMARY KEY,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                avg_win REAL DEFAULT 0,
                avg_loss REAL DEFAULT 0,
                win_rate REAL DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Active positions table - current open trades
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_positions (
                symbol TEXT PRIMARY KEY,
                trade_id INTEGER,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                current_stop REAL,
                target REAL,
                breakeven_trigger REAL,
                trail_trigger REAL,
                highest_price REAL,
                lowest_price REAL,
                max_profit REAL DEFAULT 0,
                partial_booked BOOLEAN DEFAULT 0,
                breakeven_set BOOLEAN DEFAULT 0,
                entry_time TIMESTAMP NOT NULL,
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            )
        ''')
        
        # Bot state table - persistent bot configuration
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
        logger.info("All tables created/verified")
    
    # ============ TRADES ============
    
    def save_trade(self, symbol, side, quantity, entry_price, stop_loss, target, paper_trading=True):
        """Save new trade to database"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO trades (symbol, side, quantity, entry_price, stop_loss, target, 
                               entry_time, status, paper_trading, strategy_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, 'v3.0')
        ''', (symbol, side, quantity, entry_price, stop_loss, target, 
              datetime.now(), paper_trading))
        self.conn.commit()
        return cursor.lastrowid
    
    def close_trade(self, trade_id, exit_price, exit_reason):
        """Close a trade in database"""
        cursor = self.conn.cursor()
        
        # Get trade details
        cursor.execute('SELECT * FROM trades WHERE id = ?', (trade_id,))
        trade = cursor.fetchone()
        if not trade:
            return None
        
        # Calculate P&L
        if trade['side'] == 'BUY':
            pnl = (exit_price - trade['entry_price']) * trade['quantity']
        else:
            pnl = (trade['entry_price'] - exit_price) * trade['quantity']
        
        pnl_percent = (pnl / (trade['entry_price'] * trade['quantity'])) * 100
        
        cursor.execute('''
            UPDATE trades 
            SET exit_price = ?, exit_time = ?, pnl = ?, pnl_percent = ?, 
                exit_reason = ?, status = 'CLOSED'
            WHERE id = ?
        ''', (exit_price, datetime.now(), pnl, pnl_percent, exit_reason, trade_id))
        
        # Remove from active positions
        cursor.execute('DELETE FROM active_positions WHERE trade_id = ?', (trade_id,))
        
        # Update symbol performance
        self.update_symbol_performance(trade['symbol'], pnl)
        
        self.conn.commit()
        return pnl
    
    def get_open_trades(self):
        """Get all open trades"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM trades WHERE status = "OPEN"')
        return [dict(row) for row in cursor.fetchall()]
    
    def get_recent_trades(self, days=7):
        """Get trades from last N days"""
        cursor = self.conn.cursor()
        cutoff = datetime.now() - timedelta(days=days)
        cursor.execute('SELECT * FROM trades WHERE entry_time > ? ORDER BY entry_time DESC', (cutoff,))
        return [dict(row) for row in cursor.fetchall()]
    
    # ============ ACTIVE POSITIONS ============
    
    def save_active_position(self, symbol, position_data):
        """Save active position with all tracking data"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO active_positions 
            (symbol, trade_id, side, quantity, entry_price, stop_loss, current_stop, 
             target, breakeven_trigger, trail_trigger, highest_price, lowest_price,
             max_profit, partial_booked, breakeven_set, entry_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            symbol,
            position_data.get('trade_id'),
            position_data['side'],
            position_data['quantity'],
            position_data['entry_price'],
            position_data['stop_loss'],
            position_data.get('current_stop', position_data['stop_loss']),
            position_data['target'],
            position_data.get('breakeven_trigger'),
            position_data.get('trail_trigger'),
            position_data.get('highest_price', position_data['entry_price']),
            position_data.get('lowest_price', position_data['entry_price']),
            position_data.get('max_profit', 0),
            position_data.get('partial_booked', False),
            position_data.get('breakeven_set', False),
            position_data.get('entry_time', datetime.now())
        ))
        self.conn.commit()
    
    def update_position(self, symbol, **kwargs):
        """Update position fields"""
        if not kwargs:
            return
        cursor = self.conn.cursor()
        fields = ', '.join([f'{k} = ?' for k in kwargs.keys()])
        values = list(kwargs.values()) + [symbol]
        cursor.execute(f'UPDATE active_positions SET {fields} WHERE symbol = ?', values)
        self.conn.commit()
    
    def get_active_positions(self):
        """Get all active positions"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM active_positions')
        return {row['symbol']: dict(row) for row in cursor.fetchall()}
    
    def remove_active_position(self, symbol):
        """Remove an active position"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM active_positions WHERE symbol = ?', (symbol,))
        self.conn.commit()
    
    # ============ COOLDOWNS ============
    
    def add_cooldown(self, symbol, minutes=45, reason="Stop loss hit"):
        """Add symbol to cooldown"""
        cursor = self.conn.cursor()
        cooldown_until = datetime.now() + timedelta(minutes=minutes)
        cursor.execute('''
            INSERT OR REPLACE INTO cooldowns (symbol, cooldown_until, reason)
            VALUES (?, ?, ?)
        ''', (symbol, cooldown_until, reason))
        self.conn.commit()
        logger.info(f"❄️  {symbol} cooldown until {cooldown_until.strftime('%H:%M')}")
    
    def is_in_cooldown(self, symbol):
        """Check if symbol is in cooldown"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM cooldowns WHERE symbol = ?', (symbol,))
        row = cursor.fetchone()
        
        if not row:
            return False, None
        
        cooldown_until = datetime.fromisoformat(row['cooldown_until'])
        if datetime.now() < cooldown_until:
            mins_left = (cooldown_until - datetime.now()).seconds // 60
            return True, f"Cooldown active ({mins_left} min left)"
        
        # Expired - remove
        cursor.execute('DELETE FROM cooldowns WHERE symbol = ?', (symbol,))
        self.conn.commit()
        return False, None
    
    # ============ SIGNALS ============
    
    def save_signal(self, symbol, signal_type, price, strength, reasons, executed=False):
        """Save signal to database"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO signals (symbol, signal_type, price, strength, reasons, executed, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, signal_type, price, strength, json.dumps(reasons), executed, datetime.now()))
        self.conn.commit()
    
    # ============ DAILY STATS ============
    
    def update_daily_stats(self, capital, pnl, total_trades, winners, losers):
        """Update today's stats"""
        today = datetime.now().date().isoformat()
        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO daily_stats 
            (date, starting_capital, ending_capital, total_trades, winning_trades, 
             losing_trades, total_pnl, win_rate)
            VALUES (?, COALESCE((SELECT starting_capital FROM daily_stats WHERE date = ?), ?), 
                    ?, ?, ?, ?, ?, ?)
        ''', (today, today, capital, capital, total_trades, winners, losers, pnl, win_rate))
        self.conn.commit()
    
    def get_daily_stats(self, days=7):
        """Get last N days of stats"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?', (days,))
        return [dict(row) for row in cursor.fetchall()]
    
    # ============ SYMBOL PERFORMANCE ============
    
    def update_symbol_performance(self, symbol, pnl):
        """Track which symbols work best"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM symbol_performance WHERE symbol = ?', (symbol,))
        row = cursor.fetchone()
        
        is_win = pnl > 0
        
        if row:
            new_total = row['total_trades'] + 1
            new_wins = row['winning_trades'] + (1 if is_win else 0)
            new_losses = row['losing_trades'] + (0 if is_win else 1)
            new_pnl = row['total_pnl'] + pnl
            
            cursor.execute('''
                UPDATE symbol_performance 
                SET total_trades = ?, winning_trades = ?, losing_trades = ?, 
                    total_pnl = ?, win_rate = ?, last_updated = ?
                WHERE symbol = ?
            ''', (new_total, new_wins, new_losses, new_pnl, 
                  (new_wins/new_total*100), datetime.now(), symbol))
        else:
            cursor.execute('''
                INSERT INTO symbol_performance 
                (symbol, total_trades, winning_trades, losing_trades, total_pnl, win_rate)
                VALUES (?, 1, ?, ?, ?, ?)
            ''', (symbol, 1 if is_win else 0, 0 if is_win else 1, pnl, 100 if is_win else 0))
        
        self.conn.commit()
    
    def get_best_symbols(self, min_trades=3):
        """Get best performing symbols"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM symbol_performance 
            WHERE total_trades >= ? 
            ORDER BY win_rate DESC, total_pnl DESC
        ''', (min_trades,))
        return [dict(row) for row in cursor.fetchall()]
    
    # ============ BOT STATE ============
    
    def save_state(self, key, value):
        """Save bot state value"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO bot_state (key, value, updated_at)
            VALUES (?, ?, ?)
        ''', (key, json.dumps(value), datetime.now()))
        self.conn.commit()
    
    def get_state(self, key, default=None):
        """Get bot state value"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT value FROM bot_state WHERE key = ?', (key,))
        row = cursor.fetchone()
        if row:
            return json.loads(row['value'])
        return default
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database closed")
    
    def print_summary(self):
        """Print database summary"""
        cursor = self.conn.cursor()
        
        # Total trades
        cursor.execute('SELECT COUNT(*) as count FROM trades')
        total_trades = cursor.fetchone()['count']
        
        # Win/loss
        cursor.execute('SELECT COUNT(*) as count FROM trades WHERE pnl > 0')
        wins = cursor.fetchone()['count']
        cursor.execute('SELECT COUNT(*) as count FROM trades WHERE pnl < 0')
        losses = cursor.fetchone()['count']
        
        # Total P&L
        cursor.execute('SELECT SUM(pnl) as total FROM trades WHERE pnl IS NOT NULL')
        total_pnl = cursor.fetchone()['total'] or 0
        
        # Best symbol
        cursor.execute('''
            SELECT symbol, total_pnl, win_rate FROM symbol_performance 
            ORDER BY total_pnl DESC LIMIT 1
        ''')
        best = cursor.fetchone()
        
        print("\n" + "="*80)
        print("📊 ALL-TIME DATABASE STATS")
        print("="*80)
        print(f"Total Trades: {total_trades}")
        print(f"Wins: {wins} | Losses: {losses}")
        print(f"Win Rate: {(wins/total_trades*100 if total_trades > 0 else 0):.1f}%")
        print(f"Total P&L: ₹{total_pnl:.2f}")
        if best:
            print(f"Best Symbol: {best['symbol']} (₹{best['total_pnl']:.2f}, {best['win_rate']:.1f}% win)")
        print("="*80 + "\n")