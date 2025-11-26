"""
Dhan 5-min data + Donchian + VPVR
All calls use sandbox=True
"""
import pandas as pd
from dhanhq import dhan

client = dhan(client_id=os.getenv("DHAN_SANDBOX_CLIENT_ID"),
              access_token=os.getenv("DHAN_SANDBOX_ACCESS_TOKEN"),
              sandbox=True)

SECURITY_ID = "13"  # NIFTY 50 index

def get_5min_bars(n=20):
    """Last n 5-min bars for NIFTY 50 index"""
    data = client.intraday_minute_data(
        security_id=SECURITY_ID,
        exchange_segment="IDX_I",
        instrument_type="INDEX"
    )
    df = pd.DataFrame(data["data"])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].tail(n)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["close"] = pd.to_numeric(df["close"])
    df["volume"] = pd.to_numeric(df["volume"])
    return df.reset_index(drop=True)

def donchian_channels(df, period=20):
    df["don_up"]  = df["high"].rolling(period).max()
    df["don_low"] = df["low"].rolling(period).min()
    return df

def vpvr_nodes(df, top_pct=0.20):
    """Volume-price nodes = prices with top 20 % accumulated volume"""
    vp = df.groupby("close")["volume"].sum()
    return vp[vp > vp.quantile(1 - top_pct)].index.tolist()
