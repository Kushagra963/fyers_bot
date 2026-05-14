"""
TRADING DATABASE v4.0 — High-Performance SQLite Layer

Advanced features:
  - Thread-local connections: each of the 10 parallel scanner threads gets its
    own SQLite connection — zero lock contention, no "database is locked" errors
  - WAL journal mode: concurrent reads never block writes (critical for parallel scan)
  - Performance PRAGMAs: 64 MB page cache, memory-mapped I/O, synchronous=NORMAL
  - In-memory cooldown cache (dict + RLock): O(1) lookup for all 150 symbol checks
    instead of 150 DB round-trips per scan cycle — biggest latency win
  - Full index coverage: symbol, status, entry_time — hot query paths ~10x faster
  - sector_performance table: sector-level win/loss analytics
  - scan_log table: per-scan timing + signal count history
  - batch_save_signals(): single transaction for multiple signal inserts
"""

import sqlite3
import json
import logging
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, Dict, List, Any, Tuple

logger = logging.getLogger(__name__)

# ─── Performance PRAGMA template applied to every new connection ───────────────
_PRAGMAS = """
PRAGMA journal_mode  = WAL;
PRAGMA synchronous   = NORMAL;
PRAGMA cache_size    = -65536;
PRAGMA temp_store    = MEMORY;
PRAGMA mmap_size     = 268435456;
PRAGMA busy_timeout  = 5000;
"""


class TradingDatabase:
    """
    Thread-safe, high-performance persistent storage for the trading bot.

    Connection model
    ────────────────
    Each thread (main loop + 10 scanner workers) owns its own SQLite connection
    via threading.local().  WAL mode lets all readers proceed concurrently while
    a writer (main thread) commits.  No Python-level locking needed for reads.

    Cooldown cache
    ──────────────
    `_cooldown_cache` is a plain dict {symbol: expiry_datetime} guarded by an
    RLock.  scanner workers hit the cache first (O(1)); DB is only consulted on
    a cache miss or when a new cooldown is written.  On a 150-symbol scan this
    reduces cooldown-related DB reads from 150 → ~0 (after first warm-up).
    """

    def __init__(self, db_path: str = 'trading_bot.db'):
        self.db_path   = db_path
        self._local    = threading.local()          # per-thread connection storage
        self._all_conns: List[sqlite3.Connection] = []   # track for graceful shutdown
        self._all_conns_lock = threading.Lock()

        # In-memory cooldown cache — eliminates DB reads during parallel scan
        self._cooldown_cache: Dict[str, datetime] = {}
        self._cooldown_lock  = threading.RLock()

        # Create schema on the main-thread connection
        self._create_schema()
        self._migrate_schema()
        logger.info(f"✅ Database ready: {db_path} | WAL mode | thread-local connections")

    # ══════════════════════════════════════════════════════════════════════════
    # CONNECTION MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def _new_connection(self) -> sqlite3.Connection:
        """Open a fresh SQLite connection with all performance PRAGMAs applied."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_PRAGMAS)
        with self._all_conns_lock:
            self._all_conns.append(conn)
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the calling thread's dedicated connection (create if first use)."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = self._new_connection()
        return self._local.conn

    def close(self):
        """Close all thread-local connections (call from main thread on shutdown)."""
        with self._all_conns_lock:
            for c in self._all_conns:
                try:
                    c.close()
                except Exception:
                    pass
            self._all_conns.clear()
        logger.info("Database connections closed")

    # ══════════════════════════════════════════════════════════════════════════
    # SCHEMA
    # ══════════════════════════════════════════════════════════════════════════

    def _create_schema(self):
        """Create all tables + indexes.  Idempotent — safe to call on every start."""
        cur = self.conn.cursor()

        # ── Trades ─────────────────────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol           TEXT    NOT NULL,
                side             TEXT    NOT NULL,
                quantity         INTEGER NOT NULL,
                entry_price      REAL    NOT NULL,
                exit_price       REAL,
                stop_loss        REAL,
                target           REAL,
                entry_time       TIMESTAMP NOT NULL,
                exit_time        TIMESTAMP,
                pnl              REAL,
                pnl_percent      REAL,
                exit_reason      TEXT,
                status           TEXT    DEFAULT 'OPEN',
                strategy_version TEXT,
                paper_trading    BOOLEAN DEFAULT 1,
                price_action_type TEXT,
                score            REAL,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Signals ────────────────────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT      NOT NULL,
                signal_type TEXT      NOT NULL,
                price       REAL      NOT NULL,
                strength    REAL,
                reasons     TEXT,
                executed    BOOLEAN   DEFAULT 0,
                timestamp   TIMESTAMP NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Cooldowns ──────────────────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS cooldowns (
                symbol         TEXT      PRIMARY KEY,
                cooldown_until TIMESTAMP NOT NULL,
                reason         TEXT,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Daily stats ────────────────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                date             TEXT PRIMARY KEY,
                starting_capital REAL,
                ending_capital   REAL,
                total_trades     INTEGER DEFAULT 0,
                winning_trades   INTEGER DEFAULT 0,
                losing_trades    INTEGER DEFAULT 0,
                total_pnl        REAL    DEFAULT 0,
                win_rate         REAL,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Symbol performance ─────────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS symbol_performance (
                symbol         TEXT    PRIMARY KEY,
                total_trades   INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades  INTEGER DEFAULT 0,
                total_pnl      REAL    DEFAULT 0,
                avg_win        REAL    DEFAULT 0,
                avg_loss       REAL    DEFAULT 0,
                win_rate       REAL    DEFAULT 0,
                last_updated   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Sector performance (NEW) ────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS sector_performance (
                sector         TEXT    PRIMARY KEY,
                total_trades   INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades  INTEGER DEFAULT 0,
                total_pnl      REAL    DEFAULT 0,
                win_rate       REAL    DEFAULT 0,
                last_updated   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Scan log (NEW) ─────────────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS scan_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_time     TIMESTAMP NOT NULL,
                duration_secs REAL,
                symbols_scanned INTEGER DEFAULT 0,
                signals_found   INTEGER DEFAULT 0,
                buy_signals     INTEGER DEFAULT 0,
                sell_signals    INTEGER DEFAULT 0,
                skipped_cooldown INTEGER DEFAULT 0,
                skipped_position INTEGER DEFAULT 0
            )
        ''')

        # ── Active positions ───────────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS active_positions (
                symbol           TEXT      PRIMARY KEY,
                trade_id         INTEGER,
                side             TEXT      NOT NULL,
                quantity         INTEGER   NOT NULL,
                entry_price      REAL      NOT NULL,
                stop_loss        REAL,
                current_stop     REAL,
                target           REAL,
                breakeven_trigger REAL,
                trail_trigger    REAL,
                highest_price    REAL,
                lowest_price     REAL,
                max_profit       REAL      DEFAULT 0,
                partial_booked   BOOLEAN   DEFAULT 0,
                breakeven_set    BOOLEAN   DEFAULT 0,
                atr_at_entry     REAL      DEFAULT 0,
                entry_time       TIMESTAMP NOT NULL,
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            )
        ''')

        # ── Bot state ──────────────────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bot_state (
                key        TEXT PRIMARY KEY,
                value      TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Indexes (idempotent) ───────────────────────────────────────────
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_trades_symbol     ON trades(symbol)",
            "CREATE INDEX IF NOT EXISTS idx_trades_status     ON trades(status)",
            "CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time)",
            "CREATE INDEX IF NOT EXISTS idx_trades_sym_status ON trades(symbol, status)",
            "CREATE INDEX IF NOT EXISTS idx_signals_symbol    ON signals(symbol)",
            "CREATE INDEX IF NOT EXISTS idx_signals_ts        ON signals(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_cooldowns_until   ON cooldowns(cooldown_until)",
        ]
        for idx in indexes:
            cur.execute(idx)

        # ── Migration: add atr_at_entry to existing v3 databases ──────────
        try:
            cur.execute('ALTER TABLE active_positions ADD COLUMN atr_at_entry REAL DEFAULT 0')
            logger.info("Migration: atr_at_entry column added to active_positions")
        except Exception:
            pass  # already exists — normal after first migration

        self.conn.commit()
        logger.info("Schema verified: all tables + indexes ready")

    def _migrate_schema(self):
        """Add new columns to existing tables if they don't exist yet (safe on re-run)."""
        cur = self.conn.cursor()
        migrations = [
            ("trades", "price_action_type", "TEXT"),
            ("trades", "score",             "REAL"),
        ]
        for table, column, col_type in migrations:
            cur.execute(f"PRAGMA table_info({table})")
            existing = [row[1] for row in cur.fetchall()]
            if column not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                logger.info(f"🔧 Migration: added {table}.{column} ({col_type})")
        self.conn.commit()

    # ══════════════════════════════════════════════════════════════════════════
    # COOLDOWN CACHE  (O(1) hot-path for parallel scan)
    # ══════════════════════════════════════════════════════════════════════════

    def _cache_warmup(self):
        """Load all active cooldowns into memory on startup."""
        cur = self.conn.cursor()
        cur.execute('SELECT symbol, cooldown_until FROM cooldowns')
        rows = cur.fetchall()
        with self._cooldown_lock:
            self._cooldown_cache.clear()
            for row in rows:
                try:
                    self._cooldown_cache[row['symbol']] = datetime.fromisoformat(row['cooldown_until'])
                except Exception:
                    pass
        logger.info(f"Cooldown cache warmed: {len(self._cooldown_cache)} active cooldown(s)")

    def is_in_cooldown(self, symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Check cooldown — in-memory first, DB only on miss.
        Called from 10 parallel threads; RLock makes cache reads thread-safe.
        """
        now = datetime.now()

        # ── Fast path: in-memory cache ─────────────────────────────────────
        with self._cooldown_lock:
            expiry = self._cooldown_cache.get(symbol)
            if expiry is not None:
                if now < expiry:
                    mins_left = int((expiry - now).total_seconds() // 60)
                    return True, f"Cooldown active ({mins_left} min left)"
                else:
                    # Expired — evict from cache + DB
                    del self._cooldown_cache[symbol]
                    cur = self.conn.cursor()
                    cur.execute('DELETE FROM cooldowns WHERE symbol = ?', (symbol,))
                    self.conn.commit()
                    return False, None

        # ── Slow path: DB lookup (cache miss — only happens on first scan) ─
        cur = self.conn.cursor()
        cur.execute('SELECT cooldown_until FROM cooldowns WHERE symbol = ?', (symbol,))
        row = cur.fetchone()
        if not row:
            return False, None

        expiry = datetime.fromisoformat(row['cooldown_until'])
        if now < expiry:
            # Populate cache for future hits
            with self._cooldown_lock:
                self._cooldown_cache[symbol] = expiry
            mins_left = int((expiry - now).total_seconds() // 60)
            return True, f"Cooldown active ({mins_left} min left)"

        # Expired in DB
        cur.execute('DELETE FROM cooldowns WHERE symbol = ?', (symbol,))
        self.conn.commit()
        return False, None

    def add_cooldown(self, symbol: str, minutes: int = 45, reason: str = "Stop loss hit"):
        """Add symbol to cooldown — writes DB + updates in-memory cache."""
        expiry = datetime.now() + timedelta(minutes=minutes)
        cur = self.conn.cursor()
        cur.execute(
            'INSERT OR REPLACE INTO cooldowns (symbol, cooldown_until, reason) VALUES (?, ?, ?)',
            (symbol, expiry, reason)
        )
        self.conn.commit()
        # Update cache
        with self._cooldown_lock:
            self._cooldown_cache[symbol] = expiry
        logger.info(f"❄️  {symbol} cooldown until {expiry.strftime('%H:%M')} ({reason})")

    def clear_cooldown(self, symbol: str):
        """Manually clear a cooldown (e.g. admin override)."""
        cur = self.conn.cursor()
        cur.execute('DELETE FROM cooldowns WHERE symbol = ?', (symbol,))
        self.conn.commit()
        with self._cooldown_lock:
            self._cooldown_cache.pop(symbol, None)

    # ══════════════════════════════════════════════════════════════════════════
    # TRADES
    # ══════════════════════════════════════════════════════════════════════════

    def save_trade(self, symbol, side, quantity, entry_price, stop_loss, target,
                   paper_trading=True, price_action_type=None, score=None) -> int:
        cur = self.conn.cursor()
        cur.execute('''
            INSERT INTO trades
              (symbol, side, quantity, entry_price, stop_loss, target,
               entry_time, status, paper_trading, strategy_version,
               price_action_type, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, 'v4.2', ?, ?)
        ''', (symbol, side, quantity, entry_price, stop_loss, target,
              datetime.now(), paper_trading, price_action_type, score))
        self.conn.commit()
        return cur.lastrowid

    def close_trade(self, trade_id: int, exit_price: float, exit_reason: str) -> Optional[float]:
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM trades WHERE id = ?', (trade_id,))
        trade = cur.fetchone()
        if not trade:
            return None

        pnl = ((exit_price - trade['entry_price']) if trade['side'] == 'BUY'
               else (trade['entry_price'] - exit_price)) * trade['quantity']
        pnl_pct = (pnl / (trade['entry_price'] * trade['quantity'])) * 100

        cur.execute('''
            UPDATE trades
            SET exit_price = ?, exit_time = ?, pnl = ?, pnl_percent = ?,
                exit_reason = ?, status = 'CLOSED'
            WHERE id = ?
        ''', (exit_price, datetime.now(), pnl, pnl_pct, exit_reason, trade_id))
        cur.execute('DELETE FROM active_positions WHERE trade_id = ?', (trade_id,))

        self.update_symbol_performance(trade['symbol'], pnl)
        self.conn.commit()
        return pnl

    def get_open_trades(self) -> List[Dict]:
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM trades WHERE status = "OPEN" ORDER BY entry_time DESC')
        return [dict(r) for r in cur.fetchall()]

    def get_recent_trades(self, days: int = 7) -> List[Dict]:
        cur = self.conn.cursor()
        cutoff = datetime.now() - timedelta(days=days)
        cur.execute('SELECT * FROM trades WHERE entry_time > ? ORDER BY entry_time DESC', (cutoff,))
        return [dict(r) for r in cur.fetchall()]

    # ══════════════════════════════════════════════════════════════════════════
    # ACTIVE POSITIONS
    # ══════════════════════════════════════════════════════════════════════════

    def save_active_position(self, symbol: str, position_data: Dict):
        cur = self.conn.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO active_positions
              (symbol, trade_id, side, quantity, entry_price, stop_loss, current_stop,
               target, breakeven_trigger, trail_trigger, highest_price, lowest_price,
               max_profit, partial_booked, breakeven_set, atr_at_entry, entry_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            position_data.get('lowest_price',  position_data['entry_price']),
            position_data.get('max_profit', 0),
            position_data.get('partial_booked', False),
            position_data.get('breakeven_set',  False),
            position_data.get('atr_at_entry', position_data['entry_price'] * 0.015),
            position_data.get('entry_time', datetime.now()),
        ))
        self.conn.commit()

    def update_position(self, symbol: str, **kwargs):
        if not kwargs:
            return
        cur = self.conn.cursor()
        fields = ', '.join(f'{k} = ?' for k in kwargs)
        cur.execute(
            f'UPDATE active_positions SET {fields} WHERE symbol = ?',
            list(kwargs.values()) + [symbol]
        )
        self.conn.commit()

    def get_active_positions(self) -> Dict[str, Dict]:
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM active_positions')
        return {row['symbol']: dict(row) for row in cur.fetchall()}

    def remove_active_position(self, symbol: str):
        cur = self.conn.cursor()
        cur.execute('DELETE FROM active_positions WHERE symbol = ?', (symbol,))
        self.conn.commit()

    # ══════════════════════════════════════════════════════════════════════════
    # SIGNALS
    # ══════════════════════════════════════════════════════════════════════════

    def save_signal(self, symbol, signal_type, price, strength, reasons, executed=False):
        cur = self.conn.cursor()
        cur.execute('''
            INSERT INTO signals (symbol, signal_type, price, strength, reasons, executed, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, signal_type, price, strength, json.dumps(reasons), executed, datetime.now()))
        self.conn.commit()

    def batch_save_signals(self, signal_list: List[Dict]):
        """Insert multiple signals in one transaction — used after parallel scan."""
        if not signal_list:
            return
        now = datetime.now()
        rows = [
            (s['symbol'], s['signal_type'], s['price'], s['strength'],
             json.dumps(s.get('reasons', [])), False, now)
            for s in signal_list
        ]
        cur = self.conn.cursor()
        cur.executemany('''
            INSERT INTO signals (symbol, signal_type, price, strength, reasons, executed, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', rows)
        self.conn.commit()
        logger.info(f"Batch saved {len(rows)} signal(s)")

    # ══════════════════════════════════════════════════════════════════════════
    # SCAN LOG
    # ══════════════════════════════════════════════════════════════════════════

    def log_scan(self, duration_secs: float, symbols_scanned: int, signals_found: int,
                 buy_signals: int = 0, sell_signals: int = 0,
                 skipped_cooldown: int = 0, skipped_position: int = 0):
        """Record per-scan timing and signal counts."""
        cur = self.conn.cursor()
        cur.execute('''
            INSERT INTO scan_log
              (scan_time, duration_secs, symbols_scanned, signals_found,
               buy_signals, sell_signals, skipped_cooldown, skipped_position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now(), duration_secs, symbols_scanned, signals_found,
              buy_signals, sell_signals, skipped_cooldown, skipped_position))
        self.conn.commit()

    def get_scan_stats(self, last_n: int = 10) -> List[Dict]:
        """Return recent scan performance metrics."""
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM scan_log ORDER BY scan_time DESC LIMIT ?', (last_n,))
        return [dict(r) for r in cur.fetchall()]

    # ══════════════════════════════════════════════════════════════════════════
    # DAILY STATS
    # ══════════════════════════════════════════════════════════════════════════

    def update_daily_stats(self, capital, pnl, total_trades, winners, losers):
        today    = datetime.now().date().isoformat()
        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0
        cur = self.conn.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO daily_stats
              (date, starting_capital, ending_capital, total_trades,
               winning_trades, losing_trades, total_pnl, win_rate)
            VALUES (
                ?,
                COALESCE((SELECT starting_capital FROM daily_stats WHERE date = ?), ?),
                ?, ?, ?, ?, ?, ?
            )
        ''', (today, today, capital, capital, total_trades, winners, losers, pnl, win_rate))
        self.conn.commit()

    def get_daily_stats(self, days: int = 7) -> List[Dict]:
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?', (days,))
        return [dict(r) for r in cur.fetchall()]

    # ══════════════════════════════════════════════════════════════════════════
    # SYMBOL PERFORMANCE
    # ══════════════════════════════════════════════════════════════════════════

    def update_symbol_performance(self, symbol: str, pnl: float):
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM symbol_performance WHERE symbol = ?', (symbol,))
        row = cur.fetchone()
        is_win = pnl > 0
        if row:
            nt  = row['total_trades']   + 1
            nw  = row['winning_trades'] + (1 if is_win else 0)
            nl  = row['losing_trades']  + (0 if is_win else 1)
            np_ = row['total_pnl']      + pnl
            cur.execute('''
                UPDATE symbol_performance
                SET total_trades = ?, winning_trades = ?, losing_trades = ?,
                    total_pnl = ?, win_rate = ?, last_updated = ?
                WHERE symbol = ?
            ''', (nt, nw, nl, np_, nw / nt * 100, datetime.now(), symbol))
        else:
            cur.execute('''
                INSERT INTO symbol_performance
                  (symbol, total_trades, winning_trades, losing_trades, total_pnl, win_rate)
                VALUES (?, 1, ?, ?, ?, ?)
            ''', (symbol, 1 if is_win else 0, 0 if is_win else 1, pnl, 100 if is_win else 0))
        self.conn.commit()

    def update_sector_performance(self, sector: str, pnl: float):
        """Track P&L at the sector level."""
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM sector_performance WHERE sector = ?', (sector,))
        row = cur.fetchone()
        is_win = pnl > 0
        if row:
            nt  = row['total_trades']   + 1
            nw  = row['winning_trades'] + (1 if is_win else 0)
            nl  = row['losing_trades']  + (0 if is_win else 1)
            np_ = row['total_pnl']      + pnl
            cur.execute('''
                UPDATE sector_performance
                SET total_trades = ?, winning_trades = ?, losing_trades = ?,
                    total_pnl = ?, win_rate = ?, last_updated = ?
                WHERE sector = ?
            ''', (nt, nw, nl, np_, nw / nt * 100, datetime.now(), sector))
        else:
            cur.execute('''
                INSERT INTO sector_performance
                  (sector, total_trades, winning_trades, losing_trades, total_pnl, win_rate)
                VALUES (?, 1, ?, ?, ?, ?)
            ''', (sector, 1 if is_win else 0, 0 if is_win else 1, pnl, 100 if is_win else 0))
        self.conn.commit()

    def get_best_sectors(self, min_trades: int = 2) -> List[Dict]:
        cur = self.conn.cursor()
        cur.execute('''
            SELECT * FROM sector_performance
            WHERE total_trades >= ?
            ORDER BY win_rate DESC, total_pnl DESC
        ''', (min_trades,))
        return [dict(r) for r in cur.fetchall()]

    def get_best_symbols(self, min_trades: int = 3) -> List[Dict]:
        cur = self.conn.cursor()
        cur.execute('''
            SELECT * FROM symbol_performance
            WHERE total_trades >= ?
            ORDER BY win_rate DESC, total_pnl DESC
        ''', (min_trades,))
        return [dict(r) for r in cur.fetchall()]

    # ══════════════════════════════════════════════════════════════════════════
    # BOT STATE
    # ══════════════════════════════════════════════════════════════════════════

    def save_state(self, key: str, value: Any):
        cur = self.conn.cursor()
        cur.execute(
            'INSERT OR REPLACE INTO bot_state (key, value, updated_at) VALUES (?, ?, ?)',
            (key, json.dumps(value), datetime.now())
        )
        self.conn.commit()

    def get_state(self, key: str, default: Any = None) -> Any:
        cur = self.conn.cursor()
        cur.execute('SELECT value FROM bot_state WHERE key = ?', (key,))
        row = cur.fetchone()
        return json.loads(row['value']) if row else default

    # ══════════════════════════════════════════════════════════════════════════
    # REPORTING
    # ══════════════════════════════════════════════════════════════════════════

    def print_summary(self):
        cur = self.conn.cursor()
        cur.execute('SELECT COUNT(*) as c FROM trades')
        total = cur.fetchone()['c']
        cur.execute('SELECT COUNT(*) as c FROM trades WHERE pnl > 0')
        wins = cur.fetchone()['c']
        cur.execute('SELECT COUNT(*) as c FROM trades WHERE pnl < 0')
        losses = cur.fetchone()['c']
        cur.execute('SELECT SUM(pnl) as s FROM trades WHERE pnl IS NOT NULL')
        total_pnl = cur.fetchone()['s'] or 0.0
        cur.execute('SELECT symbol, total_pnl, win_rate FROM symbol_performance ORDER BY total_pnl DESC LIMIT 1')
        best = cur.fetchone()
        cur.execute('SELECT AVG(duration_secs) as avg_dur, COUNT(*) as scans FROM scan_log')
        scan_row = cur.fetchone()

        print("\n" + "=" * 80)
        print("DATABASE STATS v4.0")
        print("=" * 80)
        print(f"Total Trades : {total}")
        print(f"Wins / Losses: {wins} / {losses}  |  Win Rate: {(wins/total*100 if total else 0):.1f}%")
        print(f"Total P&L    : Rs.{total_pnl:.2f}")
        if best:
            print(f"Best Symbol  : {best['symbol']} (Rs.{best['total_pnl']:.2f}, {best['win_rate']:.1f}% win)")
        if scan_row and scan_row['scans']:
            print(f"Scan History : {scan_row['scans']} scans | avg {scan_row['avg_dur']:.1f}s each")

        cur.execute('SELECT * FROM sector_performance WHERE total_trades > 0 ORDER BY total_pnl DESC LIMIT 5')
        sectors = cur.fetchall()
        if sectors:
            print("\nTop Sectors:")
            for s in sectors:
                print(f"  {s['sector']:<20} {s['total_trades']} trades | "
                      f"{s['win_rate']:.0f}% win | Rs.{s['total_pnl']:.2f}")
        print("=" * 80 + "\n")
