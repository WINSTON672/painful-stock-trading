import yfinance as yf

def fetch_data(symbol):
    data = yf.download(symbol, period="3mo", interval="1h", auto_adjust=True, progress=False)
    return data
