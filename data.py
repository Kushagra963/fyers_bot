"""
Data Fetcher Module for Fyers Trading Bot
Handles historical data, live quotes, and market data
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from fyers_apiv3 import fyersModel
from dotenv import load_dotenv
import logging
import time

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FyersDataFetcher:
    """Fetch market data from Fyers API"""
    
    def __init__(self, fyers_model):
        """
        Initialize data fetcher
        
        Args:
            fyers_model: Authenticated FyersModel instance from auth.py
        """
        self.fyers = fyers_model
        logger.info("Data fetcher initialized")
    
    def get_historical_data(self, symbol, interval, days_back=30):
        """
        Fetch historical candlestick data
        
        Args:
            symbol (str): Trading symbol (e.g., 'NSE:SBIN-EQ')
            interval (str): Candle interval - '1', '5', '15', '60', 'D' (1min, 5min, 15min, 1hour, 1day)
            days_back (int): Number of days of historical data to fetch
            
        Returns:
            pandas.DataFrame: OHLCV data with datetime index
        """
        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            # Format dates for API (epoch timestamp)
            range_from = int(start_date.timestamp())
            range_to = int(end_date.timestamp())
            
            # Prepare data request
            data = {
                "symbol": symbol,
                "resolution": interval,
                "date_format": "0",  # 0 for epoch timestamps
                "range_from": str(range_from),
                "range_to": str(range_to),
                "cont_flag": "1"  # Continuous data
            }
            
            logger.info(f"Fetching historical data for {symbol} ({interval} interval, {days_back} days)")
            
            # Fetch data
            response = self.fyers.history(data=data)
            
            if response['code'] != 200:
                logger.error(f"Error fetching data: {response}")
                return None
            
            # Convert to DataFrame
            candles = response['candles']
            
            # Columns are: epoch, open, high, low, close, volume
            df = pd.DataFrame(candles, columns=['epoch', 'open', 'high', 'low', 'close', 'volume'])
            
            # Convert epoch to datetime
            df['datetime'] = pd.to_datetime(df['epoch'], unit='s')
            df.set_index('datetime', inplace=True)
            df.drop('epoch', axis=1, inplace=True)
            
            logger.info(f"Fetched {len(df)} candles for {symbol}")
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return None
    
    def get_live_quote(self, symbols):
        """
        Get live quotes for symbols
        
        Args:
            symbols (list): List of symbols (e.g., ['NSE:SBIN-EQ', 'NSE:RELIANCE-EQ'])
            
        Returns:
            dict: Live quote data for each symbol
        """
        try:
            if isinstance(symbols, str):
                symbols = [symbols]
            
            data = {"symbols": ",".join(symbols)}
            
            response = self.fyers.quotes(data=data)
            
            if response['code'] != 200:
                logger.error(f"Error fetching quotes: {response}")
                return None
            
            return response['d']
            
        except Exception as e:
            logger.error(f"Error fetching live quotes: {e}")
            return None
    
    def get_market_depth(self, symbol):
        """
        Get market depth (order book) for a symbol
        
        Args:
            symbol (str): Trading symbol
            
        Returns:
            dict: Market depth data
        """
        try:
            data = {"symbol": symbol, "ohlcv_flag": "1"}
            
            response = self.fyers.depth(data=data)
            
            if response['code'] != 200:
                logger.error(f"Error fetching market depth: {response}")
                return None
            
            return response['d'][symbol]
            
        except Exception as e:
            logger.error(f"Error fetching market depth: {e}")
            return None
    
    def calculate_vwap(self, df):
        """
        Calculate VWAP (Volume Weighted Average Price)
        
        Args:
            df (pandas.DataFrame): OHLCV data
            
        Returns:
            pandas.Series: VWAP values
        """
        try:
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
            return vwap
        except Exception as e:
            logger.error(f"Error calculating VWAP: {e}")
            return None
    
    def is_market_open(self):
        """
        Check if market is currently open
        
        Returns:
            bool: True if market is open
        """
        try:
            now = datetime.now()
            
            # Check if it's a weekday (Monday=0 to Friday=4)
            if now.weekday() > 4:
                return False
            
            # Market hours: 9:15 AM to 3:30 PM
            market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
            market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
            
            return market_open <= now <= market_close
            
        except Exception as e:
            logger.error(f"Error checking market status: {e}")
            return False
    
    def get_intraday_data(self, symbol, interval='5'):
        """
        Get today's intraday data for a symbol
        
        Args:
            symbol (str): Trading symbol
            interval (str): Candle interval ('1', '5', '15')
            
        Returns:
            pandas.DataFrame: Intraday OHLCV data
        """
        try:
            # Get data from market open today
            now = datetime.now()
            start_of_day = now.replace(hour=9, minute=15, second=0, microsecond=0)
            
            range_from = int(start_of_day.timestamp())
            range_to = int(now.timestamp())
            
            data = {
                "symbol": symbol,
                "resolution": interval,
                "date_format": "0",
                "range_from": str(range_from),
                "range_to": str(range_to),
                "cont_flag": "1"
            }
            
            logger.info(f"Fetching intraday data for {symbol} ({interval}min)")
            
            response = self.fyers.history(data=data)
            
            if response['code'] != 200:
                logger.error(f"Error fetching intraday data: {response}")
                return None
            
            candles = response['candles']
            df = pd.DataFrame(candles, columns=['epoch', 'open', 'high', 'low', 'close', 'volume'])
            
            df['datetime'] = pd.to_datetime(df['epoch'], unit='s')
            df.set_index('datetime', inplace=True)
            df.drop('epoch', axis=1, inplace=True)
            
            logger.info(f"Fetched {len(df)} intraday candles")
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching intraday data: {e}")
            return None
    
    def get_multiple_symbols_data(self, symbols, interval='5', days_back=5):
        """
        Fetch historical data for multiple symbols
        
        Args:
            symbols (list): List of symbols
            interval (str): Candle interval
            days_back (int): Days of historical data
            
        Returns:
            dict: Dictionary with symbol as key and DataFrame as value
        """
        try:
            data_dict = {}
            
            for symbol in symbols:
                df = self.get_historical_data(symbol, interval, days_back)
                if df is not None:
                    data_dict[symbol] = df
                time.sleep(0.5)  # Rate limiting
            
            logger.info(f"Fetched data for {len(data_dict)} symbols")
            
            return data_dict
            
        except Exception as e:
            logger.error(f"Error fetching multiple symbols data: {e}")
            return {}


def test_data_fetcher():
    """Test data fetcher functionality"""
    from auth import FyersAuth
    
    print("\n" + "="*80)
    print("TESTING DATA FETCHER")
    print("="*80 + "\n")
    
    # Authenticate
    print("Authenticating...")
    auth = FyersAuth()
    if not auth.login():
        print("Authentication failed!")
        return
    
    # Initialize data fetcher
    data_fetcher = FyersDataFetcher(auth.fyers)
    
    # Test 1: Check market status
    print("\n" + "-"*80)
    print("Test 1: Market Status")
    print("-"*80)
    is_open = data_fetcher.is_market_open()
    print(f"Market is currently: {'OPEN ✅' if is_open else 'CLOSED ❌'}")
    
    # Test 2: Get historical data
    print("\n" + "-"*80)
    print("Test 2: Historical Data (5min, last 5 days)")
    print("-"*80)
    symbol = 'NSE:SBIN-EQ'
    df = data_fetcher.get_historical_data(symbol, interval='5', days_back=5)
    if df is not None:
        print(f"\n✓ Fetched {len(df)} candles for {symbol}")
        print(f"\nFirst 5 rows:")
        print(df.head())
        print(f"\nLast 5 rows:")
        print(df.tail())
    
    # Test 3: Get live quote
    print("\n" + "-"*80)
    print("Test 3: Live Quote")
    print("-"*80)
    symbols = ['NSE:SBIN-EQ', 'NSE:RELIANCE-EQ']
    quotes = data_fetcher.get_live_quote(symbols)
    if quotes:
        for symbol_data in quotes:
            symbol = symbol_data['v']['short_name']
            ltp = symbol_data['v']['lp']
            change = symbol_data['v']['ch']
            change_pct = symbol_data['v']['chp']
            print(f"\n{symbol}:")
            print(f"  LTP: ₹{ltp}")
            print(f"  Change: ₹{change} ({change_pct}%)")
    
    # Test 4: Calculate VWAP
    if df is not None:
        print("\n" + "-"*80)
        print("Test 4: VWAP Calculation")
        print("-"*80)
        vwap = data_fetcher.calculate_vwap(df)
        print(f"\nVWAP calculated successfully")
        print(f"Current VWAP: ₹{vwap.iloc[-1]:.2f}")
        print(f"Current Price: ₹{df['close'].iloc[-1]:.2f}")
        
        if df['close'].iloc[-1] > vwap.iloc[-1]:
            print("Price is ABOVE VWAP (Bullish) 📈")
        else:
            print("Price is BELOW VWAP (Bearish) 📉")
    
    print("\n" + "="*80)
    print("DATA FETCHER TEST COMPLETE")
    print("="*80 + "\n")


if __name__ == "__main__":
    test_data_fetcher()