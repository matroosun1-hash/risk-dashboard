"""Diagnose nan issue - quick version"""
import yfinance as yf
import pandas as pd

tickers = ["SPY", "^TNX", "RSP"]
data = yf.download(tickers, period="1mo", group_by="ticker", auto_adjust=True, progress=False)

print(f"Columns nlevels: {data.columns.nlevels}")
print(f"First 10 columns: {data.columns.tolist()[:10]}")

# Check if level 0 is ticker or price
if data.columns.nlevels == 2:
    l0 = data.columns.get_level_values(0).unique().tolist()
    l1 = data.columns.get_level_values(1).unique().tolist()
    print(f"Level 0 values: {l0}")
    print(f"Level 1 values: {l1}")

    # Try both orderings
    try:
        v1 = data["SPY"]["Close"].iloc[-1]
        print(f"\ndata['SPY']['Close'] = {v1}")
    except:
        print("\ndata['SPY']['Close'] FAILED")

    try:
        v2 = data["Close"]["SPY"].iloc[-1]
        print(f"data['Close']['SPY'] = {v2}")
    except:
        print("data['Close']['SPY'] FAILED")

    # Check for potential ticker in level 0 vs level 1
    price_cols = ["Close", "Open", "High", "Low", "Volume"]
    if l0[0] in price_cols:
        print("\n>>> Level 0 = Price type, Level 1 = Ticker")
        print(">>> Need to access as data['Close']['SPY']")
    else:
        print("\n>>> Level 0 = Ticker, Level 1 = Price type")
        print(">>> Access as data['SPY']['Close']")
