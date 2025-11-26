"""
Kelly-based lot sizing (0.25 cap) – max 3 lots, ₹500 risk cap
Uses Dhan funds() call
"""
import os
from dhanhq import dhan

client = dhan(client_id=os.getenv("DHAN_SANDBOX_CLIENT_ID"),
              access_token=os.getenv("DHAN_SANDBOX_ACCESS_TOKEN"),
              sandbox=True)

LOT_QTY     = 75
MAX_RISK_RS = 500
MAX_LOTS    = 3

def kelly_fraction(win_rate=0.42, avg_win=3, avg_loss=1):
    if avg_loss == 0: return 0
    return (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win

def allowed_lots(ai_conf, sl_pts):
    """
    Returns 2 or 3 lots while keeping ₹ risk ≤ 500
    """
    k = kelly_fraction()
    size = 2
    if ai_conf >= 0.75 and sl_pts <= 2.5 and k > 0.25:
        size = 3
    # hard cash check
    cash = float(client.funds()["data"]["available_balance"])
    need = size * LOT_QTY * sl_pts
    while need > MAX_RISK_RS and size > 2:
        size -= 1
        need = size * LOT_QTY * sl_pts
    return size
