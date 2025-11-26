#!/usr/bin/env python3
"""
Dhan Nifty 50 Options Scalper
- Entry: 5-min EMA cross (blue/orange dot)
- Filter: 15-min AI trend + Donchian S/R
- Exit: RL chooses 1R/3R/6R/trail
- Risk: ₹500 max per trade
"""
import os
import sys
import time
import signal
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
from dotenv import load_dotenv

from dhanhq import dhan
from src.data.dhan_vpn import get_5min_bars, donchian_channels, vpvr_nodes
from src.indicators.ema_cross import ema_cross_signal
from src.ai.infer import ai_direction, ai_confidence
from src.risk.kelly_sizer import allowed_lots
from src.ai.rl_exit import choose_action, load_q
from src.utils.telegram import send_telegram
from src.utils.logger import setup_logger

load_dotenv()

# ---------- config ----------
CLIENT_ID     = os.getenv("DHAN_SANDBOX_CLIENT_ID")
ACCESS_TOKEN  = os.getenv("DHAN_SANDBOX_ACCESS_TOKEN")
SYMBOL        = "NIFTY 50"
EXCHANGE      = "NSE_INDEX"
SECURITY_ID   = "13"
LOT_QTY       = 75
MAX_RISK_RS   = 500
# ------------------------------

client = dhan(client_id=CLIENT_ID, access_token=ACCESS_TOKEN, sandbox=True)
setup_logger()
log = logging.getLogger(__name__)

class Trader:
    def __init__(self):
        self.q_table = load_q()
        self.position = None   # {'side': 'CE'/'PE', 'qty': int, 'entry': float, 'sl': float, 'target': float}
        self.entry_time = None
        self.trades_csv = Path("trades.csv")
        self.init_csv()

    def init_csv(self):
        if not self.trades_csv.exists():
            pd.DataFrame(columns=["timestamp","symbol","side","qty","entry","exit","pnl","commission"]).to_csv(self.trades_csv, index=False)

    def log_trade(self, **kwargs):
        kwargs["timestamp"] = datetime.now().isoformat()
        pd.DataFrame([kwargs]).to_csv(self.trades_csv, mode="a", header=False, index=False)

    def pre_market(self):
        """09:16 scan – AI + S/R"""
        bars = get_5min_bars(48)  # last 4 h
        df   = donchian_channels(bars)
        vpn  = vpvr_nodes(df)
        trend = ai_direction(df)
        conf  = ai_confidence(df)
        send_telegram(f"🌅 15-min scan – trend: {trend}, conf: {conf:.2f}, VPN: {vpn}")
        return trend, conf, vpn

    def entry_signal(self, trend, vpn):
        """5-min close – blue/orange dot"""
        df = get_5min_bars(5)
        signal = ema_cross_signal(df)
        if signal == 0:
            return None
        # direction filter
        if (signal == 1 and trend != "BULL") or (signal == -1 and trend != "BEAR"):
            return None
        # breakout filter
        latest = df.iloc[-1]
        if signal == 1 and latest.close < latest.don_up:
            return None
        if signal == -1 and latest.close > latest.don_low:
            return None
        return "CE" if signal == 1 else "PE"

    def strike_selection(self, direction):
        """ATM ±1, premium ₹30-80, 150 qty"""
        chain = client.get_option_chain(security_id=SECURITY_ID, exchange_segment="IDX_I", instrument_type="OPTIDX")
        df = pd.DataFrame(chain["data"])
        spot = float(client.intraday_minute_data(security_id=SECURITY_ID, exchange_segment="IDX_I", instrument_type="INDEX")["data"][-1]["close"])
        if direction == "CE":
            strikes = df[df["strike_price"] >= spot].head(3)
        else:
            strikes = df[df["strike_price"] <= spot].tail(3)
        for _, row in strikes.iterrows():
            ltp = row["last_price"]
            if 30 <= ltp <= 80:
                return int(row["strike_price"]), ltp
        return None, None

    def compute_size(self, sl_pts):
        lots = allowed_lots(ai_conf=0.75, sl_pts=sl_pts)  # force 2-3 lots
        return lots * LOT_QTY

    def enter_trade(self, direction):
        strike, premium = self.strike_selection(direction)
        if strike is None:
            send_telegram("⚠️ No valid strike")
            return
        sl_pts = 3.33
        qty = self.compute_size(sl_pts)
        target_pts = 10.0  # RL will override
        order = client.place_order(
            security_id=str(strike),
            exchange_segment="NSE_FNO",
            transaction_type="BUY",
            quantity=qty,
            order_type="MARKET",
            product_type="INTRADAY",
            price=0,
            validity="DAY"
        )
        if order["status"] == "success":
            self.position = {
                "side": direction,
                "qty": qty,
                "entry": premium,
                "sl": premium - sl_pts,
                "target": premium + target_pts,
                "strike": strike
            }
            self.entry_time = datetime.now()
            send_telegram(f"🟢 ENTRY {direction} {strike} ₹{premium} qty={qty}")
            self.log_trade(symbol=f"NIFTY{strike}{direction}", side="BUY", qty=qty, entry=premium, commission=0)

    def manage_exit(self):
        if not self.position:
            return
        # current premium
        chain = client.get_option_chain(security_id=SECURITY_ID, exchange_segment="IDX_I", instrument_type="OPTIDX")
        df = pd.DataFrame(chain["data"])
        row = df[df["strike_price"] == self.position["strike"]].iloc[0]
        ltp = row["last_price"]
        pnl_pct = (ltp - self.position["entry"]) / abs(self.position["entry"] - self.position["sl"])
        secs_in = (datetime.now() - self.entry_time).seconds
        iv_delta = 0  # TODO: fetch IV change
        state = f"{int(pnl_pct*100)}:{int(secs_in//300)}:{int(iv_delta*10)}"
        action = choose_action(state, self.q_table)

        exit_price = None
        if action == "take_1r" and pnl_pct >= 1:
            exit_price = self.position["entry"] + 3.33
        elif action == "take_3r" and pnl_pct >= 3:
            exit_price = self.position["entry"] + 10.0
        elif action == "take_6r" and pnl_pct >= 6:
            exit_price = self.position["entry"] + 20.0
        elif ltp <= self.position["sl"]:
            exit_price = ltp
        elif datetime.now().time() >= datetime.strptime("15:20", "%H:%M").time():
            exit_price = ltp

        if exit_price:
            order = client.place_order(
                security_id=str(self.position["strike"]),
                exchange_segment="NSE_FNO",
                transaction_type="SELL",
                quantity=self.position["qty"],
                order_type="MARKET",
                product_type="INTRADAY",
                price=0,
                validity="DAY"
            )
            if order["status"] == "success":
                pnl = (exit_price - self.position["entry"]) * self.position["qty"]
                send_telegram(f"🔴 EXIT {self.position['side']} ₹{exit_price} P&L ₹{pnl:.0f}")
                self.log_trade(symbol=f"NIFTY{self.position['strike']}{self.position['side']}", side="SELL", qty=self.position["qty"], exit=exit_price, pnl=pnl, commission=0)
                self.position = None

    def run(self):
        send_telegram("🤖 Bot started (paper)")
        while True:
            now = datetime.now().time()
            if now < datetime.strptime("09:15", "%H:%M").time():
                time.sleep(60)
                continue
            if now < datetime.strptime("09:16", "%H:%M").time():
                trend, conf, vpn = self.pre_market()
            if datetime.strptime("09:30", "%H:%M").time() <= now <= datetime.strptime("15:20", "%H:%M").time():
                if not self.position:
                    signal = self.entry_signal(trend, vpn)
                    if signal:
                        self.enter_trade(signal)
                else:
                    self.manage_exit()
            if now >= datetime.strptime("15:25", "%H:%M").time():
                if self.position:
                    self.manage_exit()  # force square-off
                send_telegram("🏁 Day finished – CSV saved")
                break
            time.sleep(300)  # 5-min

if __name__ == "__main__":
    trader = Trader()
    try:
        trader.run()
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
