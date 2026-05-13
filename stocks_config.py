"""
STOCKS CONFIGURATION
Organized by sector for sector-strength analysis.
All 150+ NSE liquid stocks eligible for intraday trading.
Format: NSE:SYMBOL-EQ (Fyers API format)
"""

SECTORS = {

    'BANKING': [
        'NSE:SBIN-EQ',
        'NSE:HDFCBANK-EQ',
        'NSE:ICICIBANK-EQ',
        'NSE:KOTAKBANK-EQ',
        'NSE:AXISBANK-EQ',
        'NSE:BANKBARODA-EQ',
        'NSE:PNB-EQ',
        'NSE:CANBK-EQ',
        'NSE:INDUSINDBK-EQ',
        'NSE:FEDERALBNK-EQ',
        'NSE:IDFCFIRSTB-EQ',
        'NSE:BANDHANBNK-EQ',
        'NSE:AUBANK-EQ',
        'NSE:UNIONBANK-EQ',
    ],

    'IT': [
        'NSE:INFY-EQ',
        'NSE:TCS-EQ',
        'NSE:WIPRO-EQ',
        'NSE:HCLTECH-EQ',
        'NSE:TECHM-EQ',
        # 'NSE:LTIMINDTREE-EQ',  # TODO: verify correct Fyers symbol — returns -300
        'NSE:MPHASIS-EQ',
        'NSE:PERSISTENT-EQ',
        'NSE:COFORGE-EQ',
        'NSE:KPITTECH-EQ',
        'NSE:LTTS-EQ',
        'NSE:OFSS-EQ',
    ],

    'OIL_GAS': [
        'NSE:RELIANCE-EQ',
        'NSE:ONGC-EQ',
        'NSE:IOC-EQ',
        'NSE:BPCL-EQ',
        'NSE:GAIL-EQ',
        'NSE:PETRONET-EQ',
        'NSE:MGL-EQ',
    ],

    'AUTO': [
        # 'NSE:TATAMOTORS-EQ',  # TODO: verify correct Fyers symbol — returns -300
        'NSE:MARUTI-EQ',
        'NSE:M&M-EQ',
        'NSE:BAJAJ-AUTO-EQ',
        'NSE:EICHERMOT-EQ',
        'NSE:HEROMOTOCO-EQ',
        'NSE:TVSMOTOR-EQ',
        'NSE:ASHOKLEY-EQ',
        'NSE:MOTHERSON-EQ',
        'NSE:ESCORTS-EQ',
        'NSE:BALKRISIND-EQ',
        'NSE:BOSCHLTD-EQ',
    ],

    'PHARMA': [
        'NSE:SUNPHARMA-EQ',
        'NSE:DRREDDY-EQ',
        'NSE:CIPLA-EQ',
        'NSE:LUPIN-EQ',
        'NSE:DIVISLAB-EQ',
        'NSE:AUROPHARMA-EQ',
        'NSE:ALKEM-EQ',
        'NSE:LALPATHLAB-EQ',
        'NSE:GRANULES-EQ',
        'NSE:ZYDUSLIFE-EQ',
        'NSE:APOLLOHOSP-EQ',
        'NSE:BIOCON-EQ',
    ],

    'FINANCE_NBFC': [
        'NSE:BAJFINANCE-EQ',
        'NSE:BAJAJFINSV-EQ',
        'NSE:CHOLAFIN-EQ',
        'NSE:MUTHOOTFIN-EQ',
        'NSE:MANAPPURAM-EQ',
        'NSE:LICHSGFIN-EQ',
        'NSE:PFC-EQ',
        'NSE:RECLTD-EQ',
        'NSE:SBICARD-EQ',
        'NSE:ANGELONE-EQ',
        'NSE:IRFC-EQ',
    ],

    'INSURANCE': [
        'NSE:HDFCLIFE-EQ',
        'NSE:SBILIFE-EQ',
        'NSE:ICICIPRULI-EQ',
        'NSE:STARHEALTH-EQ',
        'NSE:MFSL-EQ',
    ],

    'FMCG': [
        'NSE:ITC-EQ',
        'NSE:HINDUNILVR-EQ',
        'NSE:BRITANNIA-EQ',
        'NSE:DABUR-EQ',
        'NSE:MARICO-EQ',
        'NSE:COLPAL-EQ',
        'NSE:TATACONSUM-EQ',
        'NSE:NESTLEIND-EQ',
        'NSE:GODREJCP-EQ',
        'NSE:UBL-EQ',
    ],

    'METALS_MINING': [
        'NSE:TATASTEEL-EQ',
        'NSE:JSWSTEEL-EQ',
        'NSE:HINDALCO-EQ',
        'NSE:SAIL-EQ',
        'NSE:VEDL-EQ',
        'NSE:NATIONALUM-EQ',
        'NSE:NMDC-EQ',
        'NSE:JINDALSTEL-EQ',
        'NSE:COALINDIA-EQ',
    ],

    'INFRA_CAPGOODS': [
        'NSE:LT-EQ',
        'NSE:POWERGRID-EQ',
        'NSE:NTPC-EQ',
        'NSE:BHEL-EQ',
        'NSE:BEL-EQ',
        'NSE:HAL-EQ',
        'NSE:ABB-EQ',
        'NSE:SIEMENS-EQ',
        'NSE:CUMMINSIND-EQ',
        'NSE:CONCOR-EQ',
        'NSE:RVNL-EQ',
        'NSE:TATAPOWER-EQ',
        'NSE:ADANIPORTS-EQ',
        'NSE:ADANIENT-EQ',
    ],

    'CEMENT': [
        'NSE:ULTRACEMCO-EQ',
        'NSE:GRASIM-EQ',
        'NSE:AMBUJACEM-EQ',
        'NSE:ACC-EQ',
        'NSE:JKCEMENT-EQ',
        'NSE:RAMCOCEM-EQ',
    ],

    'CONSUMER_DURABLES': [
        'NSE:TITAN-EQ',
        'NSE:HAVELLS-EQ',
        'NSE:CROMPTON-EQ',
        'NSE:VOLTAS-EQ',
        'NSE:DIXON-EQ',
        'NSE:POLYCAB-EQ',
        'NSE:TATAELXSI-EQ',
    ],

    'TELECOM': [
        'NSE:BHARTIARTL-EQ',
        'NSE:TATACOMM-EQ',
    ],

    'REALTY': [
        'NSE:DLF-EQ',
        'NSE:GODREJPROP-EQ',
        'NSE:OBEROIRLTY-EQ',
        'NSE:PRESTIGE-EQ',
    ],

    'CHEMICALS': [
        'NSE:PIDILITIND-EQ',
        'NSE:SRF-EQ',
        'NSE:DEEPAKNTR-EQ',
        'NSE:NAVINFLUOR-EQ',
        'NSE:ATUL-EQ',
        'NSE:FINEORG-EQ',
    ],

    'PAINTS': [
        'NSE:ASIANPAINT-EQ',
        'NSE:BERGEPAINT-EQ',
        'NSE:INDIGOPNTS-EQ',
        'NSE:KANSAINER-EQ',
    ],

    'RETAIL_CONSUMER': [
        'NSE:DMART-EQ',
        'NSE:TRENT-EQ',
        'NSE:NAUKRI-EQ',
        'NSE:PAGEIND-EQ',
        'NSE:ETERNAL-EQ',    # Zomato rebranded to Eternal Limited in 2025
        'NSE:IRCTC-EQ',
        'NSE:INDHOTEL-EQ',
        'NSE:JUBLFOOD-EQ',
    ],

    'MISC': [
        'NSE:ADANIGREEN-EQ',
        'NSE:IEX-EQ',
        'NSE:SUPREMEIND-EQ',
        'NSE:UPL-EQ',
        'NSE:ASTRAL-EQ',
        'NSE:HFCL-EQ',
        'NSE:SCHAEFFLER-EQ',
    ],
}

# Flat list of all symbols — used as the main watchlist
ALL_SYMBOLS = []
for sector_symbols in SECTORS.values():
    for sym in sector_symbols:
        if sym not in ALL_SYMBOLS:
            ALL_SYMBOLS.append(sym)

# Quick lookup: symbol -> sector
SYMBOL_TO_SECTOR = {}
for sector, syms in SECTORS.items():
    for sym in syms:
        SYMBOL_TO_SECTOR[sym] = sector

if __name__ == '__main__':
    print(f"Total symbols: {len(ALL_SYMBOLS)}")
    for sector, syms in SECTORS.items():
        print(f"  {sector}: {len(syms)} stocks")
