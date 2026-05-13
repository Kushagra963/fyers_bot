"""
DATABASE RESET SCRIPT
Wipes all trade history and resets capital to ₹1,00,000 for a clean start.
"""

import sqlite3
import json
from datetime import datetime

DB_PATH = "trading_bot.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=" * 60)
print("RESETTING DATABASE — clean slate with ₹1,00,000")
print("=" * 60)

# Clear all tables
tables = [
    "trades",
    "signals",
    "cooldowns",
    "daily_stats",
    "symbol_performance",
    "sector_performance",
    "scan_log",
    "active_positions",
    "bot_state",
]

for t in tables:
    cur.execute(f"DELETE FROM {t}")
    print(f"  ✅ Cleared: {t}")

# Reset capital to ₹1,00,000
cur.execute(
    "INSERT INTO bot_state (key, value, updated_at) VALUES (?, ?, ?)",
    ("current_capital", json.dumps(100000.0), datetime.now())
)
print(f"\n  💰 Capital reset to ₹1,00,000")

conn.commit()
conn.close()

print("\n✅ Database reset complete. Restart the bot now.\n")
