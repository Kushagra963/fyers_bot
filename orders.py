"""
Order Management Module
Handles order placement, tracking, and execution
"""

import logging
from datetime import datetime
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OrderManager:
    """Manage order placement and tracking"""
    
    def __init__(self, fyers_model, paper_trading=True):
        """
        Initialize order manager
        
        Args:
            fyers_model: Authenticated FyersModel instance
            paper_trading (bool): If True, simulate orders without real execution
        """
        self.fyers = fyers_model
        self.paper_trading = paper_trading
        self.open_orders = []
        self.executed_orders = []
        
        mode = "PAPER TRADING" if paper_trading else "LIVE TRADING"
        logger.info(f"Order Manager initialized - Mode: {mode}")
        
        if not paper_trading:
            logger.warning("⚠️  LIVE TRADING MODE - Real money will be used!")
    
    def place_order(self, symbol, side, quantity, order_type='MARKET', 
                   limit_price=None, stop_loss=None, target=None):
        """
        Place an order
        
        Args:
            symbol (str): Trading symbol (e.g., 'NSE:SBIN-EQ')
            side (str): 'BUY' or 'SELL'
            quantity (int): Number of shares
            order_type (str): 'MARKET' or 'LIMIT'
            limit_price (float): Limit price for limit orders
            stop_loss (float): Stop loss price
            target (float): Target price
            
        Returns:
            dict: Order details
        """
        try:
            order = {
                'symbol': symbol,
                'side': side,
                'quantity': quantity,
                'order_type': order_type,
                'limit_price': limit_price,
                'stop_loss': stop_loss,
                'target': target,
                'timestamp': datetime.now(),
                'status': 'PENDING',
                'order_id': None
            }
            
            if self.paper_trading:
                # Simulate order
                order['status'] = 'EXECUTED'
                order['order_id'] = f"PAPER_{int(time.time())}"
                self.executed_orders.append(order)
                
                logger.info(f"📝 PAPER ORDER: {side} {quantity} {symbol} @ {order_type}")
                if limit_price:
                    logger.info(f"   Entry: ₹{limit_price:.2f}")
                else:
                    logger.info(f"   Entry: MARKET")
                if stop_loss:
                    logger.info(f"   Stop Loss: ₹{stop_loss:.2f}")
                if target:
                    logger.info(f"   Target: ₹{target:.2f}")
                
                return order
            
            # Real order placement
            data = {
                "symbol": symbol,
                "qty": quantity,
                "type": 2 if order_type == 'MARKET' else 1,  # 1=LIMIT, 2=MARKET
                "side": 1 if side == 'BUY' else -1,  # 1=BUY, -1=SELL
                "productType": "INTRADAY",
                "validity": "DAY",
                "disclosedQty": 0,
                "offlineOrder": False
            }
            
            if order_type == 'LIMIT' and limit_price:
                data['limitPrice'] = limit_price
            
            response = self.fyers.place_order(data=data)
            
            if response['code'] == 200:
                order['status'] = 'PLACED'
                order['order_id'] = response['id']
                self.open_orders.append(order)
                
                logger.info(f"✅ ORDER PLACED: {side} {quantity} {symbol}")
                logger.info(f"   Order ID: {order['order_id']}")
                
                # Place stop loss and target orders
                if stop_loss:
                    self._place_stop_loss(symbol, side, quantity, stop_loss)
                if target:
                    self._place_target(symbol, side, quantity, target)
                
                return order
            else:
                logger.error(f"❌ Order placement failed: {response}")
                order['status'] = 'FAILED'
                order['error'] = response.get('message', 'Unknown error')
                return order
                
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    def _place_stop_loss(self, symbol, entry_side, quantity, stop_price):
        """Place stop loss order"""
        try:
            if self.paper_trading:
                logger.info(f"   📍 Stop Loss set at ₹{stop_price:.2f}")
                return
            
            # Reverse side for exit
            side = -1 if entry_side == 'BUY' else 1
            
            data = {
                "symbol": symbol,
                "qty": quantity,
                "type": 3,  # Stop loss order
                "side": side,
                "productType": "INTRADAY",
                "validity": "DAY",
                "stopPrice": stop_price,
                "limitPrice": 0,
                "disclosedQty": 0,
                "offlineOrder": False
            }
            
            response = self.fyers.place_order(data=data)
            
            if response['code'] == 200:
                logger.info(f"   📍 Stop Loss placed at ₹{stop_price:.2f}")
            else:
                logger.error(f"   ❌ Stop Loss placement failed: {response}")
                
        except Exception as e:
            logger.error(f"Error placing stop loss: {e}")
    
    def _place_target(self, symbol, entry_side, quantity, target_price):
        """Place target order"""
        try:
            if self.paper_trading:
                logger.info(f"   🎯 Target set at ₹{target_price:.2f}")
                return
            
            # Reverse side for exit
            side = -1 if entry_side == 'BUY' else 1
            
            data = {
                "symbol": symbol,
                "qty": quantity,
                "type": 1,  # Limit order
                "side": side,
                "productType": "INTRADAY",
                "validity": "DAY",
                "limitPrice": target_price,
                "disclosedQty": 0,
                "offlineOrder": False
            }
            
            response = self.fyers.place_order(data=data)
            
            if response['code'] == 200:
                logger.info(f"   🎯 Target placed at ₹{target_price:.2f}")
            else:
                logger.error(f"   ❌ Target placement failed: {response}")
                
        except Exception as e:
            logger.error(f"Error placing target: {e}")
    
    def get_order_status(self, order_id):
        """Get status of an order"""
        try:
            if self.paper_trading:
                return {'status': 'EXECUTED'}
            
            response = self.fyers.orderbook()
            
            if response['code'] == 200:
                for order in response.get('orderBook', []):
                    if order['id'] == order_id:
                        return order
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting order status: {e}")
            return None
    
    def get_positions(self):
        """Get current open positions"""
        try:
            if self.paper_trading:
                return self.executed_orders
            
            response = self.fyers.positions()
            
            if response['code'] == 200:
                return response.get('netPositions', [])
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def cancel_order(self, order_id):
        """Cancel an open order"""
        try:
            if self.paper_trading:
                logger.info(f"📝 PAPER: Order {order_id} cancelled")
                return True
            
            data = {"id": order_id}
            response = self.fyers.cancel_order(data=data)
            
            if response['code'] == 200:
                logger.info(f"✅ Order {order_id} cancelled")
                return True
            else:
                logger.error(f"❌ Cancel failed: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False
    
    def close_all_positions(self):
        """Close all open positions"""
        try:
            positions = self.get_positions()
            
            for position in positions:
                if self.paper_trading:
                    logger.info(f"📝 PAPER: Closing position {position['symbol']}")
                else:
                    symbol = position['symbol']
                    qty = abs(position['netQty'])
                    side = 'SELL' if position['netQty'] > 0 else 'BUY'
                    
                    self.place_order(symbol, side, qty, 'MARKET')
            
            logger.info("✅ All positions closed")
            return True
            
        except Exception as e:
            logger.error(f"Error closing positions: {e}")
            return False


def test_order_manager():
    """Test order manager"""
    from auth import FyersAuth
    
    print("\n" + "="*80)
    print("TESTING ORDER MANAGER (PAPER TRADING)")
    print("="*80 + "\n")
    
    # Authenticate
    print("Authenticating...")
    auth = FyersAuth()
    if not auth.login():
        print("Authentication failed!")
        return
    
    # Initialize order manager in paper trading mode
    order_mgr = OrderManager(auth.fyers, paper_trading=True)
    
    # Test order placement
    print("\n" + "-"*80)
    print("Test: Place Paper Order")
    print("-"*80 + "\n")
    
    order = order_mgr.place_order(
        symbol='NSE:SBIN-EQ',
        side='BUY',
        quantity=10,
        order_type='MARKET',
        stop_loss=1090.00,
        target=1100.00
    )
    
    if order:
        print(f"\n✅ Order placed successfully!")
        print(f"Order ID: {order['order_id']}")
        print(f"Status: {order['status']}")
    
    # Test positions
    print("\n" + "-"*80)
    print("Test: Get Positions")
    print("-"*80 + "\n")
    
    positions = order_mgr.get_positions()
    print(f"Open positions: {len(positions)}")
    
    print("\n" + "="*80)
    print("ORDER MANAGER TEST COMPLETE")
    print("="*80 + "\n")


if __name__ == "__main__":
    test_order_manager()