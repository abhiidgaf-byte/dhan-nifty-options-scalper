"""
Q-table RL exit – chooses 1R/3R/6R/trail
Updates nightly
"""
import json
import os
import numpy as np

Q_FILE   = "ai/q_table.json"
ACTIONS  = ["hold", "take_1r", "take_3r", "take_6r", "trail_05r"]

def load_q():
    if os.path.exists(Q_FILE):
        with open(Q_FILE) as f:
            return json.load(f)
    return {}

def save_q(q):
    os.makedirs(os.path.dirname(Q_FILE), exist_ok=True)
    with open(Q_FILE, "w") as f:
        json.dump(q, f, indent=2)

def state_bucket(pnl_pct, secs, iv_delta):
    p = int(np.clip(pnl_pct * 100, -5, 15))      # -5..15 %
    t = int(np.clip(secs // 300, 0, 24))         # 0..24 * 5-min
    v = int(np.clip(iv_delta * 10, -5, 5))
    return f"{p}:{t}:{v}"

def choose_action(state, q, eps=0.1):
    if np.random.rand() < eps:
        return np.random.choice(ACTIONS)
    return max(ACTIONS, key=lambda a: q.get(state, {}).get(a, 0))
