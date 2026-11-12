"""Connors RSI-2 sur indices CFD – backtest 4 ans (D1, frais inclus, entrée/sortie à la clôture).
pip install yfinance pandas numpy   puis   python backtest_rsi2_indices.py"""
import numpy as np, pandas as pd, yfinance as yf

INDICES = {"US500": "ES=F", "NAS100": "NQ=F", "US30": "YM=F", "GER40": "^GDAXI"}
START, END = "2022-11-12", "2026-11-12"
FEE, SL_ATR, RISK = 0.02, 2.0, 0.005           # frais aller-retour %, stop en ATR, risque/trade

def rma(x, n): return x.ewm(alpha=1 / n, adjust=False).mean()
def rsi(c, n=2):
    d = c.diff(); return 100 - 100 / (1 + rma(d.clip(lower=0), n) / rma((-d).clip(lower=0), n).replace(0, np.nan))
def atr(d, n=14):
    pc = d.close.shift()
    return rma(pd.concat([d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1).max(axis=1), n)

def backtest(d):
    c = d.close; r2 = rsi(c); s200 = c.rolling(200).mean(); s5 = c.rolling(5).mean(); a = atr(d)
    buy = ((c > s200) & (r2 < 10)).values; out = (c > s5).values
    o, l, cc, a = d.open.values, d.low.values, c.values, a.values; res, i = [], 0
    while i < len(d) - 1:
        if not buy[i] or d.index[i] < pd.Timestamp(START): i += 1; continue
        entry, risk = cc[i], SL_ATR * a[i]; sl = entry - risk; j = i + 1; px = None
        while j < len(d):
            if l[j] <= sl: px = min(o[j], sl); break                 # stop touché (gap = prix d'ouverture)
            if out[j] or j - i >= 10: px = cc[j]; break              # clôture > SMA5 ou 10 jours
            j += 1
        if px is None: px, j = cc[-1], len(d) - 1
        res.append((d.index[i], (px - entry - entry * FEE / 100) / risk)); i = j
    return res

trades = []
for name, tk in INDICES.items():
    d = yf.download(tk, start="2021-09-01", end=END, progress=False, auto_adjust=False)
    d.columns = [x[0].lower() for x in d.columns]; d = d[["open", "high", "low", "close"]].dropna()
    trades += [(name, t, R) for t, R in backtest(d)]
T = pd.DataFrame(trades, columns=["indice", "date", "R"]).sort_values("date")
R = T.R; eq = R.cumsum()
print(f"{len(R)} trades | gagnants {100 * (R > 0).mean():.1f} % | PF {R[R > 0].sum() / -R[R <= 0].sum():.2f} "
      f"| {R.mean():+.3f} R/trade | total {R.sum():+.1f} R | pire creux {(eq - eq.cummax()).min():.1f} R")
print(f"Compte 6000 $ à {RISK:.1%}/trade -> {6000 * (1 + RISK * R.sum()):.0f} $")
print(T.groupby("indice").R.agg(["count", "mean", "sum"]).round(2))
