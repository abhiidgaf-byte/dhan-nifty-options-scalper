"""
9-15 EMA cross (blue/orange dot logic)
Relative calculation – no absolute prices used
"""
import pandas as pd

def ema_cross_signal(ohlc: pd.DataFrame, fast=9, slow=15) -> int:
    """
    Returns +1 (buy), -1 (sell), 0 (hold)
    """
    close = ohlc["close"]
    ema9  = close.ewm(span=fast, adjust=False).mean()
    ema15 = close.ewm(span=slow, adjust=False).mean()

    cross_up   = (ema9 > ema15) & (ema9.shift(1) <= ema15.shift(1))
    cross_down = (ema9 < ema15) & (ema9.shift(1) >= ema15.shift(1))

    if cross_up.iloc[-1]:
        return 1   # CE
    if cross_down.iloc[-1]:
        return -1  # PE
    return 0
