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
import threading

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global rate-limiter: at most MAX_CONCURRENT_API_CALLS simultaneous Fyers
# history requests.  The semaphore is shared across all FyersDataFetcher
# instances (there is only one in normal usage, but this is thread-safe).
# ---------------------------------------------------------------------------
MAX_CONCURRENT_API_CALLS = 3          # safe concurrency for Fyers API
_api_semaphore = threading.Semaphore(MAX_CONCURRENT_API_CALLS)

# Retry settings for HTTP 429 / transient errors
_MAX_RETRIES   = 4                    # total attempts (1 original + 3 retries)
_RETRY_BASE_S  = 1.0                  # base sleep seconds; doubles each retry


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
            interval (str): Candle interval - '1', '5', '15', '60', 'D'
            days_back (int): Number of days of historical data to fetch

        Returns:
            pandas.DataFrame: OHLCV data with datetime index
        """
        # Build request payload once (dates don't change between retries)
        end_date   = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        request_data = {
            "symbol":      symbol,
            "resolution":  interval,
            "date_format": "0",          # epoch timestamps
            "range_from":  str(int(start_date.timestamp())),
            "range_to":    str(int(end_date.timestamp())),
            "cont_flag":   "1",          # continuous data
        }

        for attempt in range(_MAX_RETRIES):
            try:
                # Semaphore: cap concurrent in-flight requests globally
                with _api_semaphore:
                    response = self.fyers.history(data=request_data)

                code = response.get('code', -1)

                # ── success ──────────────────────────────────────────────
                if code == 200:
                    candles = response['candles']
                    df = pd.DataFrame(
                        candles,
                        columns=['epoch', 'open', 'high', 'low', 'close', 'volume']
                    )
                    df['datetime'] = pd.to_datetime(df['epoch'], unit='s')
                    df.set_index('datetime', inplace=True)
                    df.drop('epoch', axis=1, inplace=True)
                    logger.info(f"Fetched {len(df)} candles for {symbol}")
                    return df

                # ── rate-limited (429) -> exponential back-off then retry
                elif code == 429:
                    sleep_s = _RETRY_BASE_S * (2 ** attempt)   # 1s, 2s, 4s, 8s
                    logger.warning(
                        f"Rate-limited (429) for {symbol} "
                        f"(attempt {attempt + 1}/{_MAX_RETRIES}). "
                        f"Retrying in {sleep_s:.1f}s ..."
                    )
                    time.sleep(sleep_s)
                    continue   # retry

                # ── any other non-200 error -> no point retrying ──────────
                else:
                    logger.error(f"Error fetching data for {symbol}: {response}")
                    return None

            except Exception as e:
                sleep_s = _RETRY_BASE_S * (2 ** attempt)
                logger.warning(
                    f"Exception fetching {symbol} "
                    f"(attempt {attempt + 1}/{_MAX_RETRIES}): {e}. "
                    f"Retrying in {sleep_s:.1f}s ..."
                )
                time.sleep(sleep_s)

        # All retries exhausted
        logger.error(f"All {_MAX_RETRIES} attempts failed for {symbol}. Giving up.")
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
    
    # NSE holidays 2025-2026 (add new year's list each January)
    NSE_HOLIDAYS = {
        # 2025
        "2025-01-26", "2025-02-19", "2025-03-14", "2025-03-31",
        "2025-04-10", "2025-04-14", "2025-04-18", "2025-05-01",
        "2025-08-15", "2025-08-27", "2025-10-02", "2025-10-02",
        "2025-10-24", "2025-11-05", "2025-12-25",
        # 2026
        "2026-01-26", "2026-03-19", "2026-04-02", "2026-04-03",
        "2026-04-14", "2026-05-01", "2026-08-15", "2026-10-02",
        "2026-11-14", "2026-12-25",
    }

    def is_market_open(self):
        """
        Check if market is currently open (weekday + hours + NSE holiday check)

        Returns:
            bool: True if market is open
        """
        try:
            now = datetime.now()

            # Check if it's a weekday (Monday=0 to Friday=4)
            if now.weekday() > 4:
                return False

            # Check NSE holiday list
            today_str = now.strftime("%Y-%m-%d")
            if today_str in self.NSE_HOLIDAYS:
                logger.info(f"NSE Holiday today ({today_str}) -- market closed")
                return False

            # Market hours: 9:15 AM to 3:30 PM
            market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
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
        now          = datetime.now()
        start_of_day = now.replace(hour=9, minute=15, second=0, microsecond=0)

        request_data = {
            "symbol":      symbol,
            "resolution":  interval,
            "date_format": "0",
            "range_from":  str(int(start_of_day.timestamp())),
            "range_to":    str(int(now.timestamp())),
            "cont_flag":   "1",
        }

        for attempt in range(_MAX_RETRIES):
            try:
                with _api_semaphore:
                    response = self.fyers.history(data=request_data)

                code = response.get('code', -1)

                if code == 200:
                    candles = response['candles']
                    df = pd.DataFrame(
                        candles,
                        columns=['epoch', 'open', 'high', 'low', 'close', 'volume']
                    )
                    df['datetime'] = pd.to_datetime(df['epoch'], unit='s')
                    df.set_index('datetime', inplace=True)
                    df.drop('epoch', axis=1, inplace=True)
                    logger.info(f"Fetched {len(df)} intraday candles for {symbol}")
                    return df

                elif code == 429:
                    sleep_s = _RETRY_BASE_S * (2 ** attempt)
                    logger.warning(
                        f"Rate-limited (429) for intraday {symbol} "
                        f"(attempt {attempt + 1}/{_MAX_RETRIES}). "
                        f"Retrying in {sleep_s:.1f}s ..."
                    )
                    time.sleep(sleep_s)
                    continue

                else:
                    logger.error(f"Error fetching intraday data for {symbol}: {response}")
                    return None

            except Exception as e:
                sleep_s = _RETRY_BASE_S * (2 ** attempt)
                logger.warning(
                    f"Exception fetching intraday {symbol} "
                    f"(attempt {attempt + 1}/{_MAX_RETRIES}): {e}. "
                    f"Retrying in {sleep_s:.1f}s ..."
                )
                time.sleep(sleep_s)

        logger.error(f"All {_MAX_RETRIES} intraday attempts failed for {symbol}.")
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
    print(f"Market is currently: {'OPEN' if is_open else 'CLOSED'}")
    
    # Test 2: Get historical data
    print("\n" + "-"*80)
    print("Test 2: Historical Data (5min, last 5 days)")
    print("-"*80)
    symbol = 'NSE:SBIN-EQ'
    df = data_fetcher.get_historical_data(symbol, interval='5', days_back=5)
    if df is not None:
        print(f"\nFetched {len(df)} candles for {symbol}")
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
            sym   = symbol_data['v']['short_name']
            ltp   = symbol_data['v']['lp']
            change     = symbol_data['v']['ch']
            change_pct = symbol_data['v']['chp']
            print(f"\n{sym}:")
            print(f"  LTP: Rs.{ltp}")
            print(f"  Change: Rs.{change} ({change_pct}%)")
    
    # Test 4: Calculate VWAP
    if df is not None:
        print("\n" + "-"*80)
        print("Test 4: VWAP Calculation")
        print("-"*80)
        vwap = data_fetcher.calculate_vwap(df)
        print(f"\nVWAP calculated successfully")
        print(f"Current VWAP: Rs.{vwap.iloc[-1]:.2f}")
        print(f"Current Price: Rs.{df['close'].iloc[-1]:.2f}")
        
        if df['close'].iloc[-1] > vwap.iloc[-1]:
            print("Price is ABOVE VWAP (Bullish)")
        else:
            print("Price is BELOW VWAP (Bearish)")
    
    print("\n" + "="*80)
    print("DATA FETCHER TEST COMPLETE")
    print("="*80 + "\n")


if __name__ == "__main__":
    test_data_fetcher()
