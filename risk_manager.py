"""
Risk Management Module
Handles position sizing, daily loss limits, and capital protection
"""

import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RiskManager:
    """Manage trading risk and position sizing"""
    
    def __init__(self, total_capital, risk_per_trade=0.02, max_daily_loss=0.05, 
                 max_positions=3, paper_trading=True):
        """
        Initialize risk manager
        
        Args:
            total_capital (float): Total trading capital
            risk_per_trade (float): Risk per trade as % of capital (0.02 = 2%)
            max_daily_loss (float): Maximum daily loss as % of capital (0.05 = 5%)
            max_positions (int): Maximum concurrent positions
            paper_trading (bool): Paper trading mode
        """
        self.total_capital = total_capital
        self.starting_capital = total_capital
        self.risk_per_trade = risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_positions = max_positions
        self.paper_trading = paper_trading
        
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.trades_today = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.current_positions = 0
        self.locked_capital = 0.0   # FIX: capital currently in open positions
        
        self.today = datetime.now().date()
        
        logger.info(f"Risk Manager initialized:")
        logger.info(f"  Capital: ₹{total_capital:,.0f}")
        logger.info(f"  Risk per trade: {risk_per_trade*100}%")
        logger.info(f"  Max daily loss: {max_daily_loss*100}%")
        logger.info(f"  Max positions: {max_positions}")
        logger.info(f"  Mode: {'PAPER TRADING' if paper_trading else 'LIVE TRADING'}")
    
    def calculate_position_size(self, entry_price, stop_loss):
        """
        Calculate position size based on risk
        
        Args:
            entry_price (float): Entry price
            stop_loss (float): Stop loss price
            
        Returns:
            int: Number of shares to buy
        """
        try:
            # FIX: available capital = total minus what's locked in open positions
            available_capital = self.total_capital - self.locked_capital

            # FIX: each position slot gets an equal share of available capital
            # This ensures 3 concurrent positions don't exceed total capital
            capital_per_slot = available_capital / max(self.max_positions - self.current_positions, 1)

            # Risk amount in rupees (2% of total, not just available)
            risk_amount = self.total_capital * self.risk_per_trade

            # Risk per share
            risk_per_share = abs(entry_price - stop_loss)

            if risk_per_share == 0:
                logger.error("Stop loss equals entry price!")
                return 0

            # Position size from risk formula
            position_size = int(risk_amount / risk_per_share)

            # FIX: cap to what's actually affordable in this slot
            max_affordable = int(capital_per_slot / entry_price)
            position_size = min(position_size, max_affordable)

            actual_risk = position_size * risk_per_share
            capital_used = position_size * entry_price

            logger.info(f"Position Size Calculation:")
            logger.info(f"  Available Capital: ₹{available_capital:.0f} | Slot: ₹{capital_per_slot:.0f}")
            logger.info(f"  Risk Amount: ₹{risk_amount:.2f} ({self.risk_per_trade*100}%)")
            logger.info(f"  Risk/Share: ₹{risk_per_share:.2f}")
            logger.info(f"  Quantity: {position_size} shares")
            logger.info(f"  Capital Used: ₹{capital_used:.2f} ({capital_used/self.total_capital*100:.1f}%)")
            logger.info(f"  Actual Risk: ₹{actual_risk:.2f} ({actual_risk/self.total_capital*100:.2f}%)")

            return position_size
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0
    
    def can_take_trade(self):
        """
        Check if we can take a new trade
        
        Returns:
            tuple: (bool, str) - (can_trade, reason)
        """
        # Reset daily stats if new day
        current_date = datetime.now().date()
        if current_date != self.today:
            self.reset_daily_stats()
            self.today = current_date
        
        # Check daily loss limit
        daily_loss_pct = (self.daily_pnl / self.starting_capital) * 100
        max_loss_pct = self.max_daily_loss * 100
        
        if self.daily_pnl < 0 and abs(daily_loss_pct) >= max_loss_pct:
            return False, f"Daily loss limit reached: {daily_loss_pct:.2f}%"
        
        # Check max positions
        if self.current_positions >= self.max_positions:
            return False, f"Max positions reached: {self.current_positions}/{self.max_positions}"
        
        # Check if we have capital
        if self.total_capital <= 0:
            return False, "No capital remaining"
        
        return True, "OK"
    
    def record_trade(self, entry_price, exit_price, quantity, side):
        """
        Record trade result and update stats
        
        Args:
            entry_price (float): Entry price
            exit_price (float): Exit price
            quantity (int): Number of shares
            side (str): 'BUY' or 'SELL'
        """
        try:
            # Calculate P&L
            if side == 'BUY':
                pnl = (exit_price - entry_price) * quantity
            else:  # SELL
                pnl = (entry_price - exit_price) * quantity
            
            # Update stats
            self.daily_pnl += pnl
            self.total_pnl += pnl
            self.total_capital += pnl
            self.trades_today += 1
            
            if pnl > 0:
                self.winning_trades += 1
                logger.info(f"✅ PROFIT: ₹{pnl:.2f}")
            else:
                self.losing_trades += 1
                logger.info(f"❌ LOSS: ₹{pnl:.2f}")
            
            # Update position count and release locked capital
            self.current_positions -= 1
            capital_released = entry_price * quantity
            self.locked_capital = max(0.0, self.locked_capital - capital_released)
            
            logger.info(f"Updated Stats:")
            logger.info(f"  Today's P&L: ₹{self.daily_pnl:.2f}")
            logger.info(f"  Total P&L: ₹{self.total_pnl:.2f}")
            logger.info(f"  Current Capital: ₹{self.total_capital:.2f}")
            logger.info(f"  Win Rate: {self.get_win_rate():.1f}%")
            
        except Exception as e:
            logger.error(f"Error recording trade: {e}")
    
    def position_opened(self, capital_used=0):
        """Increment position counter and lock capital"""
        self.current_positions += 1
        self.locked_capital += capital_used
        logger.info(f"Position opened. Current: {self.current_positions}/{self.max_positions} | Locked: ₹{self.locked_capital:.0f}")
    
    def position_closed(self, capital_released=0):
        """Decrement position counter and release capital"""
        if self.current_positions > 0:
            self.current_positions -= 1
        self.locked_capital = max(0, self.locked_capital - capital_released)
        logger.info(f"Position closed. Current: {self.current_positions}/{self.max_positions} | Locked: ₹{self.locked_capital:.0f}")
    
    def get_stats(self):
        """Get current statistics"""
        total_trades = self.winning_trades + self.losing_trades
        win_rate = (self.winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        return {
            'total_capital': self.total_capital,
            'starting_capital': self.starting_capital,
            'total_pnl': self.total_pnl,
            'daily_pnl': self.daily_pnl,
            'total_trades': total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'current_positions': self.current_positions,
            'trades_today': self.trades_today
        }
    
    def get_win_rate(self):
        """Calculate win rate"""
        total_trades = self.winning_trades + self.losing_trades
        return (self.winning_trades / total_trades * 100) if total_trades > 0 else 0
    
    def reset_daily_stats(self):
        """Reset daily statistics"""
        logger.info(f"\n{'='*80}")
        logger.info(f"DAY END SUMMARY - {self.today}")
        logger.info(f"{'='*80}")
        logger.info(f"Trades Today: {self.trades_today}")
        logger.info(f"Daily P&L: ₹{self.daily_pnl:.2f}")
        logger.info(f"Total Capital: ₹{self.total_capital:.2f}")
        logger.info(f"Overall Win Rate: {self.get_win_rate():.1f}%")
        logger.info(f"{'='*80}\n")
        
        self.daily_pnl = 0.0
        self.trades_today = 0
    
    def print_summary(self):
        """Print trading summary"""
        stats = self.get_stats()
        
        print("\n" + "="*80)
        print("TRADING SUMMARY")
        print("="*80)
        print(f"\n💰 Capital:")
        print(f"  Starting: ₹{stats['starting_capital']:,.2f}")
        print(f"  Current:  ₹{stats['total_capital']:,.2f}")
        print(f"  P&L:      ₹{stats['total_pnl']:,.2f} ({(stats['total_pnl']/stats['starting_capital']*100):.2f}%)")
        
        print(f"\n📊 Performance:")
        print(f"  Total Trades: {stats['total_trades']}")
        print(f"  Winners: {stats['winning_trades']}")
        print(f"  Losers: {stats['losing_trades']}")
        print(f"  Win Rate: {stats['win_rate']:.1f}%")
        
        print(f"\n📈 Today:")
        print(f"  Trades: {stats['trades_today']}")
        print(f"  P&L: ₹{stats['daily_pnl']:,.2f}")
        print(f"  Open Positions: {stats['current_positions']}/{self.max_positions}")
        
        print("="*80 + "\n")


def test_risk_manager():
    """Test risk manager"""
    print("\n" + "="*80)
    print("TESTING RISK MANAGER")
    print("="*80 + "\n")
    
    # Initialize with 100k capital
    risk_mgr = RiskManager(
        total_capital=100000,
        risk_per_trade=0.02,  # 2% risk
        max_daily_loss=0.05,  # 5% max loss
        max_positions=3,
        paper_trading=True
    )
    
    # Test position sizing
    print("\n" + "-"*80)
    print("Test 1: Position Size Calculation")
    print("-"*80 + "\n")
    
    entry = 1100
    stop_loss = 1095
    quantity = risk_mgr.calculate_position_size(entry, stop_loss)
    
    # Test if can trade
    print("\n" + "-"*80)
    print("Test 2: Can Take Trade?")
    print("-"*80 + "\n")
    
    can_trade, reason = risk_mgr.can_take_trade()
    print(f"Can trade: {can_trade}")
    print(f"Reason: {reason}")
    
    # Simulate winning trade
    print("\n" + "-"*80)
    print("Test 3: Record Winning Trade")
    print("-"*80 + "\n")
    
    risk_mgr.position_opened()
    risk_mgr.record_trade(1100, 1110, quantity, 'BUY')
    
    # Simulate losing trade
    print("\n" + "-"*80)
    print("Test 4: Record Losing Trade")
    print("-"*80 + "\n")
    
    risk_mgr.position_opened()
    risk_mgr.record_trade(1100, 1095, quantity, 'BUY')
    
    # Print summary
    risk_mgr.print_summary()
    
    print("="*80)
    print("RISK MANAGER TEST COMPLETE")
    print("="*80 + "\n")


if __name__ == "__main__":
    test_risk_manager()