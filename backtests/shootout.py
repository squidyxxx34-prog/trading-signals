"""Comparatif de stratégies « proclamées meilleures » — mêmes données, mêmes frais, même moteur.
Entrée au OPEN de la bougie suivant le signal (pas de look-ahead), SL intrabar avec gaps, frais déduits.
"""
import sys, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, ".")
from common import load, FEE
from smc_engine import run as smc_run

SPLIT = pd.Timestamp("2024-01-01", tz="UTC")
SETS = [(a, tf) for a in ["PAXG", "BTC", "ETH"] for tf in ["1h", "4h", "1D"]]

# ---------- indicateurs ----------
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def sma(s, n): return s.rolling(n).mean()
def rma(s, n): return s.ewm(alpha=1 / n, adjust=False).mean()
def atr(df, n=14):
    pc = df.close.shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return rma(tr, n)
def rsi(c, n):
    d = c.diff(); up = rma(d.clip(lower=0), n); dn = rma((-d).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))
def cross_up(a, b): return (a > b) & (a.shift() <= b.shift())
def cross_dn(a, b): return (a < b) & (a.shift() >= b.shift())

def supertrend(df, n=10, m=3.0):
    a = atr(df, n).values; hl2 = ((df.high + df.low) / 2).values; c = df.close.values
    up = hl2 - m * a; dn = hl2 + m * a; d = np.ones(len(c)); fu, fd = up.copy(), dn.copy()
    for i in range(1, len(c)):
        fu[i] = max(up[i], fu[i - 1]) if c[i - 1] > fu[i - 1] else up[i]
        fd[i] = min(dn[i], fd[i - 1]) if c[i - 1] < fd[i - 1] else dn[i]
        d[i] = 1 if c[i] > fd[i - 1] else -1 if c[i] < fu[i - 1] else d[i - 1]
    return pd.Series(d, index=df.index)

def psar(df, step=0.02, mx=0.2):
    h, l = df.high.values, df.low.values; n = len(h); d = np.ones(n); sar = l[0]; ep = h[0]; af = step; up = True
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < sar: up, sar, ep, af = False, ep, l[i], step
            elif h[i] > ep: ep, af = h[i], min(af + step, mx)
        else:
            sar = max(sar, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > sar: up, sar, ep, af = True, ep, h[i], step
            elif l[i] < ep: ep, af = l[i], min(af + step, mx)
        d[i] = 1 if up else -1
    return pd.Series(d, index=df.index)

# ---------- stratégies : renvoient (long_in, short_in, long_out, short_out, sl_atr, tp_atr, max_hold) ----------
def S(df):
    c = df.close; F = lambda x: x.fillna(False).values
    out = {}
    s50, s200 = sma(c, 50), sma(c, 200)
    out["Croix d'Or (SMA 50/200)"] = (cross_up(s50, s200), cross_dn(s50, s200), cross_dn(s50, s200), cross_up(s50, s200), None, None, None)
    e9, e21 = ema(c, 9), ema(c, 21)
    out["Scalpeur EMA 9/21"] = (cross_up(e9, e21), cross_dn(e9, e21), cross_dn(e9, e21), cross_up(e9, e21), None, None, None)
    r14 = rsi(c, 14)
    out["Rebond RSI 30/70"] = (cross_up(r14, pd.Series(30, index=c.index)), cross_dn(r14, pd.Series(70, index=c.index)),
                              r14 > 50, r14 < 50, 2.0, None, 100)
    r2 = rsi(c, 2); s5 = sma(c, 5)
    out["Connors RSI-2"] = ((c > s200) & (r2 < 10), (c < s200) & (r2 > 90), c > s5, c < s5, None, None, 20)
    m = ema(c, 12) - ema(c, 26); sg = ema(m, 9)
    out["MACD Classique"] = (cross_up(m, sg), cross_dn(m, sg), cross_dn(m, sg), cross_up(m, sg), None, None, None)
    mid = sma(c, 20); sd = c.rolling(20).std(); bu, bl = mid + 2 * sd, mid - 2 * sd
    out["Élastique Bollinger"] = (cross_up(c, bl), cross_dn(c, bu), c >= mid, c <= mid, 2.0, None, 50)
    bw = (bu - bl) / mid; sq = bw < bw.rolling(120).quantile(0.2)
    out["Squeeze Bollinger"] = (sq.shift().fillna(False) & cross_up(c, bu), sq.shift().fillna(False) & cross_dn(c, bl), c < mid, c > mid, 2.0, None, None)
    hh, ll = df.high.rolling(20).max().shift(), df.low.rolling(20).min().shift()
    hx, lx = df.high.rolling(10).max().shift(), df.low.rolling(10).min().shift()
    out["La Tortue (Donchian 20/10)"] = (c > hh, c < ll, c < lx, c > hx, 2.0, None, None)
    st = supertrend(df)
    out["Supertrend 10/3"] = (st.diff() > 0, st.diff() < 0, st < 0, st > 0, None, None, None)
    t = (df.high.rolling(9).max() + df.low.rolling(9).min()) / 2; k = (df.high.rolling(26).max() + df.low.rolling(26).min()) / 2
    sa = ((t + k) / 2).shift(26); sb = ((df.high.rolling(52).max() + df.low.rolling(52).min()) / 2).shift(26)
    top, bot = np.maximum(sa, sb), np.minimum(sa, sb)
    out["Nuage Ichimoku"] = (cross_up(t, k) & (c > top), cross_dn(t, k) & (c < bot), c < k, c > k, None, None, None)
    ha_c = (df.open + df.high + df.low + c) / 4; ha_o = ha_c.copy()
    hv = ha_o.to_numpy().copy(); hcv = ha_c.to_numpy(); ov = df.open.to_numpy()
    hv[0] = (ov[0] + c.values[0]) / 2
    for i in range(1, len(hv)): hv[i] = (hv[i - 1] + hcv[i - 1]) / 2
    ha_o = pd.Series(hv, index=c.index); g = ha_c > ha_o
    e50 = ema(c, 50)
    out["Heikin Ashi Trend"] = (g & ~g.shift().fillna(False) & (c > e50), ~g & g.shift().fillna(False) & (c < e50), ~g, g, None, None, None)
    ps = psar(df)
    out["Parabolic SAR"] = (ps.diff() > 0, ps.diff() < 0, ps < 0, ps > 0, None, None, None)
    lo14, hi14 = df.low.rolling(14).min(), df.high.rolling(14).max(); kk = 100 * (c - lo14) / (hi14 - lo14); dd = sma(kk, 3)
    out["Stochastique 20/80"] = (cross_up(kk, dd) & (kk < 20), cross_dn(kk, dd) & (kk > 80), kk > 80, kk < 20, 2.0, None, 50)
    up = df.high.diff(); dn = -df.low.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=c.index); mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=c.index)
    tr = atr(df, 14); pdi = 100 * rma(pdm, 14) / tr; mdi = 100 * rma(mdm, 14) / tr
    adx = rma(100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan), 14)
    out["ADX Trend (>25)"] = (cross_up(pdi, mdi) & (adx > 25), cross_dn(pdi, mdi) & (adx > 25), cross_dn(pdi, mdi), cross_up(pdi, mdi), 2.0, None, None)
    ib = (df.high.shift() < df.high.shift(2)) & (df.low.shift() > df.low.shift(2))
    out["Inside Bar Breakout"] = (ib & (c > df.high.shift(2)), ib & (c < df.low.shift(2)), pd.Series(False, index=c.index), pd.Series(False, index=c.index), 1.0, 2.0, 30)
    out["Pullback Tendance (EMA200+RSI)"] = ((c > ema(c, 200)) & cross_up(r14, pd.Series(40, index=c.index)), (c < ema(c, 200)) & cross_dn(r14, pd.Series(60, index=c.index)),
                                          pd.Series(False, index=c.index), pd.Series(False, index=c.index), 1.5, 3.0, 100)
    # ORB : 1re bougie 1h de la session NY (13h UTC) ; cassure dans la journée, sortie fin de journée
    hr = df.index.hour
    orb_h = pd.Series(np.where(hr == 13, df.high, np.nan), index=c.index).groupby(df.index.date).transform("max")
    orb_l = pd.Series(np.where(hr == 13, df.low, np.nan), index=c.index).groupby(df.index.date).transform("min")
    after = (hr > 13) & (hr < 20)
    first_l = after & cross_up(c, orb_h); first_s = after & cross_dn(c, orb_l)
    eod = pd.Series(hr >= 20, index=c.index)
    out["ORB New York"] = (first_l, first_s, eod, eod, 1.0, 2.0, 8)
    return {k: tuple(F(x) if isinstance(x, pd.Series) else x for x in v) for k, v in out.items()}

# ---------- moteur commun ----------
def simulate(df, sig, fee):
    li, si, lo, so, sl_m, tp_m, mh = sig
    o, h, l, c = (df[k].values for k in ["open", "high", "low", "close"]); a = atr(df).values
    n = len(c); pos = 0; e = sl = tp = 0.0; eb = 0; trades = []
    pend = 0  # action à exécuter au prochain open : +1 long, -1 short, 9 = flat
    for i in range(n):
        # exécution au open
        if pend != 0:
            if pos != 0 and (pend == 9 or pend == -pos):
                trades.append((eb, i, pos * (o[i] / e - 1) - fee / 100)); pos = 0
            if pend in (1, -1) and pos == 0 and not np.isnan(a[i - 1]):
                pos = pend; e = o[i]; eb = i
                sl = e - pos * sl_m * a[i - 1] if sl_m else None
                tp = e + pos * tp_m * a[i - 1] if tp_m else None
            pend = 0
        # SL / TP intrabar (SL prioritaire, gaps)
        if pos != 0:
            x = None
            if sl is not None and (l[i] <= sl if pos == 1 else h[i] >= sl):
                x = min(o[i], sl) if pos == 1 else max(o[i], sl)
            elif tp is not None and (h[i] >= tp if pos == 1 else l[i] <= tp) and i > eb:
                x = max(o[i], tp) if pos == 1 else min(o[i], tp)
            if x is not None:
                trades.append((eb, i, pos * (x / e - 1) - fee / 100)); pos = 0
                continue
        # signaux à la clôture
        if pos == 1 and (lo[i] or si[i] or (mh and i - eb >= mh)): pend = -1 if si[i] else 9
        elif pos == -1 and (so[i] or li[i] or (mh and i - eb >= mh)): pend = 1 if li[i] else 9
        elif pos == 0:
            if li[i]: pend = 1
            elif si[i]: pend = -1
    return trades

def metrics(trades, idx, n_years):
    if not trades: return dict(n=0, wr=np.nan, pf=np.nan, ret=0.0, dd=0.0, ret_is=0.0, ret_oos=0.0)
    r = np.array([t[2] for t in trades]); w = r[r > 0].sum(); ls = -r[r <= 0].sum()
    eq = np.cumsum(np.log1p(np.clip(r, -0.99, None))); dd = 1 - np.exp((eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min())
    oos = np.array([idx[t[0]] >= SPLIT for t in trades])
    return dict(n=len(r), wr=100 * (r > 0).mean(), pf=w / ls if ls > 0 else 9.9, ret=np.expm1(eq[-1]) * 100,
                dd=dd * 100, ret_is=np.expm1(np.log1p(r[~oos]).sum()) * 100, ret_oos=np.expm1(np.log1p(r[oos]).sum()) * 100)

def smc_trades(df, fee):
    p = dict(lint=3, lsw=10, bias="htf+swing", need_fvg=True, fvg_min=0.2, entry="fvg_top", sl_buf=0.2, rr=3.0,
             max_wait=10, max_hold=120, need_sweep=False, need_choch=False, kz=False, exit="rr", fee=0.0)
    tr, arms, _, _, fills = smc_run(df, p, collect=True)
    # rendement en % du prix : r(R) * risque% ; reconstruit via cr = prix/risque
    return [(t["fill"], t["exit"], t["r"] / t["cr"] - fee / 100) for t in tr]

def job(s):
    a, tf = s; df = load(a, tf)[["open", "high", "low", "close"]]; fee = FEE[a]
    yrs = (df.index[-1] - df.index[0]).days / 365.25
    rows = []
    for name, sig in S(df).items():
        rows.append(dict(strat=name, asset=a, tf=tf, **metrics(simulate(df, sig, fee), df.index, yrs)))
    rows.append(dict(strat="SMC Pro v2 (le nôtre)", asset=a, tf=tf, **metrics(smc_trades(df, fee), df.index, yrs)))
    bh = (df.close.iloc[-1] / df.close.iloc[0] - 1) * 100
    rows.append(dict(strat="Buy & Hold (référence)", asset=a, tf=tf, n=1, wr=100.0 if bh > 0 else 0.0, pf=np.nan, ret=bh,
                     dd=(1 - (df.close / df.close.cummax()).min()) * 100,
                     ret_is=(df.close[df.index < SPLIT].iloc[-1] / df.close.iloc[0] - 1) * 100,
                     ret_oos=(df.close.iloc[-1] / df.close[df.index >= SPLIT].iloc[0] - 1) * 100))
    return rows

if __name__ == "__main__":
    with Pool(2) as p:
        res = pd.DataFrame([r for rows in p.map(job, SETS) for r in rows])
    res.to_csv("shootout_raw.csv", index=False)
    g = res.groupby("strat")
    tab = pd.DataFrame(dict(
        trades=g.n.sum(),
        winrate=g.apply(lambda d: np.average(d.wr.fillna(0), weights=d.n.clip(lower=1))),
        pf=g.pf.median(),
        pos=g.apply(lambda d: (d.ret > 0).mean()),
        oos=g.apply(lambda d: (d.ret_oos > 0).mean()),
        dd=g.dd.median(),
        ret_med=g.ret.median(),
    ))
    edge = np.clip((tab.pf - 0.8) / 0.7, 0, 1).fillna(0)
    tab["score"] = (40 * edge + 25 * tab.pos + 20 * tab.oos + 15 * np.clip(1 - tab.dd / 60, 0, 1)).round(0)
    tab.loc["Buy & Hold (référence)", "score"] = np.nan
    pd.set_option("display.width", 200)
    print(tab.sort_values("score", ascending=False).round(2).to_string())
    print()
    print(res.pivot_table(index="strat", columns=["asset", "tf"], values="ret").round(0).to_string())
