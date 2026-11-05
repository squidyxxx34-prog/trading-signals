"""Exemples réels de FVG (gagnant + iFVG) sur XAUUSD/EURUSD H4 et stats sur toutes les paires."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, ".")
from fx_common import load_fx, SYMS
from shootout import atr
def scale(s): return 100 if s == "XAUUSD" else 1000 if s.endswith("JPY") else 100000
def dec(s): return 2 if s == "XAUUSD" else 3 if s.endswith("JPY") else 5
def scan(sym):
    df = load_fx(sym, "4h"); o, h, l, c = (df[k].values for k in ["open", "high", "low", "close"]); a = atr(df).values; n = len(c); ev = []
    for g in range(30, n - 60):
        if np.isnan(a[g]): continue
        top, bot = l[g], h[g - 2]
        if top - bot < 0.5 * a[g] or not (c[g - 1] > o[g - 1]): continue
        sl = l[g - 2]; risk = top - sl
        if risk <= 0 or risk > 3 * a[g]: continue
        tp = top + 2 * risk; res = None; k = None; m = None; inv = None
        for k in range(g + 1, min(g + 30, n - 1)):
            if l[k] <= top: break
            if h[k] >= tp: k = None; break
        else: k = None
        if k is None: continue
        if l[k] <= sl: res, m = "SL", k
        else:
            for m in range(k + 1, min(k + 60, n)):
                if l[m] <= sl: res = "SL"; break
                if h[m] >= tp: res = "TP"; break
        if res is None: continue
        # iFVG : une clôture sous le bas du FVG pendant le trade
        if res == "SL":
            inv = next((q for q in range(k, m + 1) if c[q] < bot), None)
        ev.append(dict(sym=sym, g=g, k=k, m=m, res=res, top=top, bot=bot, sl=sl, tp=tp, inv=inv, ce=(top + bot) / 2, df=df,
                       deep=bool(l[k] <= (top + bot) / 2)))
    return ev
allev = [e for s in SYMS for e in scan(s)]
r = np.array([e["res"] == "TP" for e in allev])
stats = dict(n=len(r), win=round(100 * r.mean(), 1),
             ce_n=int(sum(e["deep"] for e in allev)), ce_win=round(100 * np.mean([e["res"] == "TP" for e in allev if e["deep"]]), 1),
             top_n=int(sum(not e["deep"] for e in allev)), top_win=round(100 * np.mean([e["res"] == "TP" for e in allev if not e["deep"]]), 1))
print(stats)
def pack(e, extra=6):
    df = e["df"]; s = scale(e["sym"]); lo = e["g"] - 14; hi = min(len(df), e["m"] + extra)
    if hi - lo > 60: hi = lo + 60
    w = df.iloc[lo:hi]; d = dec(e["sym"]); X = lambda i: int(i - lo)
    return dict(sym=e["sym"], date=str(df.index[e["g"]])[:16], dec=d, g=X(e["g"]), k=X(e["k"]), m=X(e["m"]), res=e["res"],
                inv=X(e["inv"]) if e["inv"] is not None else None,
                top=round(e["top"] / s, d), bot=round(e["bot"] / s, d), ce=round(e["ce"] / s, d), sl=round(e["sl"] / s, d), tp=round(e["tp"] / s, d),
                ohlc=[[round(v / s, d) for v in rr] for rr in w[["open", "high", "low", "close"]].values.tolist()], t=[str(t)[:16] for t in w.index])
def ok(e, res):
    return (e["res"] == res and e["sym"] in ("XAUUSD", "EURUSD") and e["df"].index[e["g"]].year >= 2019
            and 3 <= e["k"] - e["g"] <= 12 and e["m"] - e["g"] <= 40)
wins = [e for e in allev if ok(e, "TP") and e["deep"]]
fails = [e for e in allev if ok(e, "SL") and e["inv"] is not None and e["m"] > e["k"] + 1]
rng = np.random.default_rng(5)
win = wins[int(rng.integers(len(wins)))]; fail = fails[int(rng.integers(len(fails)))]
fp = pack(fail, extra=14)
json.dump(dict(stats=stats, win=pack(win), fail=fp), open("fvg_anim.json", "w"))
print(win["sym"], win["df"].index[win["g"]], fail["sym"], fail["df"].index[fail["g"]])
