import os
import time
import requests
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from pybit.unified_trading import HTTP
from flask import Flask
from threading import Thread

# --- SECTION 1: SECURITY & CONFIGURATION ---
# We use 'os.getenv' to fetch keys from the secure server environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_SECRET = os.getenv("BYBIT_SECRET")

# Trading Settings
USE_TESTNET = True  # Set True for Demo, False for Real Money
QUANTITY_USDT = 50  # Investment amount per trade
WATCHLIST = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]

# Initialize Bybit Connection
session = HTTP(
    testnet=USE_TESTNET,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_SECRET
)

# --- SECTION 2: THE KEEP-ALIVE SERVER (For Render) ---
app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot is Running 24/7!"

def run_http():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_http)
    t.start()

# --- SECTION 3: HELPER FUNCTIONS ---
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

# --- REPLACE THE OLD get_crypto_data FUNCTION WITH THIS ---

def get_crypto_data(symbol):
    """Downloads data from Yahoo Finance with Anti-Blocking Headers"""
    y_symbol = symbol.replace("USDT", "-USD")
    
    try:
        # 1. Create a "Session" to trick Yahoo
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })
        
        # 2. Download with the session (and a tiny delay)
        # We verify ssl=False to avoid strict handshake errors on cloud
        df = yf.download(y_symbol, period="1y", interval="1d", progress=False, session=session)
        
        # 3. Validation: Did we actually get data?
        if df.empty:
            print(f"⚠️ Yahoo gave empty data for {symbol}")
            return pd.DataFrame()
            
        return df

    except Exception as e:
        print(f"❌ Data Download Error for {symbol}: {e}")
        return pd.DataFrame()

def place_order(symbol, side):
    try:
        # 1. Get Current Price
        ticker_data = session.get_tickers(category="linear", symbol=symbol)
        price = float(ticker_data['result']['list'][0]['lastPrice'])
        
        # 2. Calculate Quantity (USDT / Price)
        qty = round(QUANTITY_USDT / price, 3)
        
        # 3. Calculate Stop Loss (5% below price)
        sl_price = round(price * 0.95, 2)

        # 4. Execute Order
        print(f"🚀 Executing {side} on {symbol}...")
        order = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=qty,
            timeInForce="GTC",
            stopLoss=str(sl_price)
        )
        
        msg = f"✅ TRADE EXECUTED!\nSymbol: {symbol}\nSide: {side}\nPrice: ${price}\nQty: {qty}\nSL: ${sl_price}"
        send_telegram(msg)
        print(msg)
        return True

    except Exception as e:
        err = f"❌ Order Failed for {symbol}: {e}"
        print(err)
        send_telegram(err)
        return False

# --- SECTION 4: THE STRATEGY LOGIC ---
def check_market(symbol):
    df = get_crypto_data(symbol)
    
    # Need at least 125 days of data
    if len(df) < 125: return None
    
    # INDICATORS
    # 1. RSI (14)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    
    # 2. 125-Day High (Price Ceiling)
    df['Max_High_125'] = df['High'].rolling(125).max().shift(1)
    
    # 3. 125-Day Volume Average (For Volume Explosion)
    df['Vol_SMA_125'] = df['Volume'].rolling(125).mean().shift(1)

    today = df.iloc[-1]
    
    # LOGIC RULES
    # Rule A: Price Breakout (Close > 125 Day High)
    cond_price = today['Close'] > today['Max_High_125']
    
    # Rule B: RSI is healthy (< 70) - Not overbought
    cond_rsi = today['RSI'] < 70
    
    # Rule C: Volume is 2x Normal (Explosion)
    cond_vol = today['Volume'] > (today['Vol_SMA_125'] * 2)

    if cond_price and cond_rsi and cond_vol:
        return "Buy"
        
    return None

# --- SECTION 5: THE MAIN LOOP ---
if __name__ == "__main__":
    print("🚀 Starting Bot Server...")
    keep_alive() # Start the fake web server
    
    send_telegram("🤖 Cloud Bot is Online and Scanning...")
    
    while True:
        print("🔍 Scanning Market...")
        for coin in WATCHLIST:
            try:
                signal = check_market(coin)
                if signal == "Buy":
                    send_telegram(f"💎 SIGNAL FOUND: {coin}. Analyzing...")
                    place_order(coin, "Buy")
                    time.sleep(300) # Wait 5 mins after a trade
            except Exception as e:
                print(f"Error scanning {coin}: {e}")
                
        time.sleep(900) # Scan every 15 minutes
