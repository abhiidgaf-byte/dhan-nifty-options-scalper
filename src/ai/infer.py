"""
Lightweight AI inference – XGBoost on 15-min features
Returns trend direction & confidence
"""
import os
import joblib
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier   # fallback if no xgb

MODEL_PATH = "ai/model.joblib"

def load_model():
    if os.path.exists(MODEL_PATH):
        return joblib.load(MODEL_PATH)
    # dummy model (random) until first train
    return GradientBoostingClassifier()

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """15-min features for AI"""
    df["ema9"]   = df["close"].ewm(span=9).mean()
    df["ema15"]  = df["close"].ewm(span=15).mean()
    df["rsi"]    = 100 - (100 / (1 + (df["close"].diff().clip(lower=0).rolling(14).mean() /
                                     df["close"].diff().clip(upper=0).rolling(14).mean().abs())))
    df["atr"]    = (df["high"] - df["low"]).rolling(14).mean()
    df["atr_pct"]= df["atr"] / df["close"]
    df["vix"]    = 20.0  # placeholder
    # last row only
    feat = df[["ema9","ema15","rsi","atr_pct","vix"]].iloc[-1:]
    return feat

def ai_direction(df: pd.DataFrame) -> str:
    feat = build_features(df)
    model = load_model()
    pred = model.predict(feat)[0]   # 1=BULL, -1=BEAR, 0=CHOP
    return {1: "BULL", -1: "BEAR", 0: "CHOP"}.get(pred, "CHOP")

def ai_confidence(df: pd.DataFrame) -> float:
    feat = build_features(df)
    model = load_model()
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(feat)[0]
        return max(proba)          # 0-1
    return 0.5
