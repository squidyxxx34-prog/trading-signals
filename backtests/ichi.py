"""Ichimoku : analyse des pertes (IN-SAMPLE 2012-2018 uniquement) puis filtres, puis retest OOS 2019-2022."""
import sys, itertools, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, ".")
from fx_common import load_fx, SYMS, fee as fx_fee
from shootout import ema, sma, atr, rma, cross_up, cross_dn, simulate

SPLIT = pd.Timestamp("2019-01-01", tz="UTC")
TFS = ["1h", "4h", "1D"]

def feats(df):
    c, h, l = df.close, df.high, df.low
    t = (h.rolling(9).max() + l.rolling(9).min()) / 2
    k = (h.rolling(26).max() + l.rolling(26).min()) / 2
    sa_raw = (t + k) / 2; sb_raw = (h.rolling(52).max() + l.rolling(52).min()) / 2
    sa, sb = sa_raw.shift(26), sb_raw.shift(26)
    top, bot = np.maximum(sa, sb), np.minimum(sa, sb)
    a = atr(df)
    up = h.diff(); dn = -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=c.index); mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=c.index)
    pdi = 100 * rma(pdm, 14) / a; mdi = 100 * rma(mdm, 14) / a
    adx = rma(100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan), 14)
    # biais journalier : clôture du jour précédent vs EMA50 journalière
    d = c.resample("1D").last().dropna(); de = ema(d, 50)
    hb = np.sign(d - de).shift(1).reindex(c.index, method="ffill").fillna(0)
    return dict(c=c, t=t, k=k, top=top, bot=bot, fut_bull=sa_raw > sb_raw, chikou_up=c > c.shift(26), chikou_dn=c < c.shift(26),
                adx=adx, atr=a, dist=(c - k) / a, thick=(top - bot) / a, hb=hb)

def signals(df, f, cfg):
    c, t, k = f["c"], f["t"], f["k"]
    li = cross_up(t, k) & (c > f["top"])
    si = cross_dn(t, k) & (c < f["bot"])
    if cfg.get("chikou"): li &= f["chikou_up"]; si &= f["chikou_dn"]
    if cfg.get("future"): li &= f["fut_bull"]; si &= ~f["fut_bull"]
    if cfg.get("adx"): li &= f["adx"] > cfg["adx"]; si &= f["adx"] > cfg["adx"]
    if cfg.get("htf"): li &= f["hb"] > 0; si &= f["hb"] < 0
    if cfg.get("maxdist"): li &= f["dist"] < cfg["maxdist"]; si &= f["dist"] > -cfg["maxdist"]
    if cfg.get("thick"): li &= f["thick"] > cfg["thick"]; si &= f["thick"] > cfg["thick"]
    lo, so = c < k, c > k
    if cfg.get("exit") == "cloud": lo, so = c < f["bot"], c > f["top"]
    if cfg.get("exit") == "kbuf": b = cfg.get("buf", 0.5) * f["atr"]; lo, so = c < k - b, c > k + b
    if cfg.get("exit") == "k2": lo, so = (c < k) & (c.shift() < k.shift()), (c > k) & (c.shift() > k.shift())
    if cfg.get("exit") == "chand":
        m = cfg.get("cm", 3.0) * f["atr"]
        lo = c < df.high.rolling(22).max() - m; so = c > df.low.rolling(22).min() + m
    F = lambda x: x.fillna(False).values
    return (F(li), F(si), F(lo), F(so), cfg.get("sl"), cfg.get("tp"), None)

def trade_feats(df, f, trades):
    rows = []
    for eb, xb, r in trades:
        i = eb - 1  # bougie du signal
        rows.append(dict(r=r, oos=df.index[eb] >= SPLIT, adx=f["adx"].iloc[i], dist=f["dist"].iloc[i], thick=f["thick"].iloc[i],
                         chikou=bool(f["chikou_up"].iloc[i]) if f["c"].iloc[eb] > 0 else None, hold=xb - eb,
                         htf_ok=None, hour=df.index[eb].hour))
    return rows

def run_set(args):
    sym, tf, cfg = args
    df = load_fx(sym, tf); f = feats(df)
    sig = signals(df, f, cfg)
    tr = simulate(df, sig, fx_fee(sym))
    out = []
    for eb, xb, r in tr:
        i = eb - 1; d = 1 if sig[0][i] else -1
        out.append(dict(sym=sym, tf=tf, r=r, oos=df.index[eb] >= SPLIT, d=d,
                        adx=f["adx"].iloc[i], dist=abs(f["dist"].iloc[i]), thick=f["thick"].iloc[i],
                        chik=bool(f["chikou_up"].iloc[i]) if d == 1 else bool(f["chikou_dn"].iloc[i]),
                        fut=bool(f["fut_bull"].iloc[i]) if d == 1 else not bool(f["fut_bull"].iloc[i]),
                        htf=(f["hb"].iloc[i] == d), hold=xb - eb))
    return out

def summary(t):
    if len(t) == 0: return dict(n=0)
    r = t.r.values; w = r[r > 0].sum(); l = -r[r <= 0].sum()
    by = t.groupby(["sym", "tf"]).r.sum()
    return dict(n=len(r), wr=round(100 * (r > 0).mean(), 1), pf=round(w / l, 2) if l else 9.9, exp_bp=round(1e4 * r.mean(), 2),
                pos=round((by > 0).mean(), 2))

def evaluate(cfg, pool):
    res = pd.DataFrame([x for rows in pool.map(run_set, [(s, tf, cfg) for s in SYMS for tf in TFS]) for x in rows])
    return res

if __name__ == "__main__":
    with Pool(2) as pool:
        base = evaluate({}, pool)
        ins = base[~base.oos]
        print("=== BASE Ichimoku · IN-SAMPLE 2012-2018 ===", summary(ins))
        print("\n--- D'où viennent les pertes (in-sample) ---")
        for col, bins in [("adx", [0, 15, 20, 25, 30, 40, 100]), ("dist", [0, 0.5, 1, 1.5, 2, 3, 20]), ("thick", [0, 0.5, 1, 2, 4, 50]), ("hold", [0, 3, 10, 30, 100, 10000])]:
            g = ins.groupby(pd.cut(ins[col], bins)).r
            print(f"\n{col}:", pd.DataFrame(dict(n=g.size(), wr=(g.apply(lambda x: (x > 0).mean() * 100)).round(0), exp_bp=(g.mean() * 1e4).round(1))).to_string())
        for col in ["chik", "fut", "htf"]:
            g = ins.groupby(col).r
            print(f"\n{col}:", pd.DataFrame(dict(n=g.size(), wr=(g.apply(lambda x: (x > 0).mean() * 100)).round(0), exp_bp=(g.mean() * 1e4).round(1))).to_string())
        print("\npar TF:", ins.groupby("tf").r.agg(["size", "mean"]).assign(mean=lambda d: (d["mean"] * 1e4).round(1)).to_string())

        def tab(cands, tfs):
            global TFS
            old = TFS; TFS = tfs; rows = []
            for name, cfg in cands.items():
                r = evaluate(cfg, pool)
                rows.append(dict(filtre=name, **{f"IS_{k}": v for k, v in summary(r[~r.oos]).items()},
                                 **{f"OOS_{k}": v for k, v in summary(r[r.oos]).items()}))
            TFS = old
            return pd.DataFrame(rows)
        exits = {"base (sortie Kijun)": {}, "sortie Kijun ±0.5 ATR": dict(exit="kbuf", buf=0.5), "sortie Kijun ±1 ATR": dict(exit="kbuf", buf=1.0),
                 "sortie 2 clôtures": dict(exit="k2"), "sortie chandelier 3 ATR": dict(exit="chand", cm=3.0), "sortie chandelier 4 ATR": dict(exit="chand", cm=4.0)}
        t1 = tab(exits, ["4h"])
        print("\n=== Sorties anti-whipsaw, 4h (choix sur IS) ===")
        print(t1[[c for c in t1.columns if c.startswith(("filtre", "IS_"))]].to_string(index=False))
        best_exit = exits[t1.sort_values("IS_pf", ascending=False).iloc[0].filtre]
        print("sortie retenue (IS):", best_exit)
        combos = {
            "V0 Ichimoku de base": {},
            "V1 + chikou": dict(chikou=1),
            "V2 + chikou + nuage futur": dict(chikou=1, future=1),
            "V3 = V2 + sortie anti-whipsaw": dict(chikou=1, future=1, **best_exit),
            "V4 = V3 + biais D1": dict(chikou=1, future=1, htf=1, **best_exit),
        }
        for tfs in (["4h"], ["1h"], ["1D"]):
            t2 = tab(combos, tfs)
            print(f"\n=== Améliorations cumulées · {tfs[0]} · IS 2012-18 puis OOS 2019-22 (jamais vu) ===")
            print(t2.to_string(index=False))
        final = dict(chikou=1, future=1, **best_exit)
        r = evaluate(final, pool); r = r[r.tf == "4h"]
        print("\n=== V3 4h par paire (IS / OOS, somme %) ===")
        print((r.groupby(["sym", "oos"]).r.sum().unstack() * 100).round(1).rename(columns={False: "IS", True: "OOS"}).to_string())
        b = evaluate({}, pool); b = b[b.tf == "4h"]
        print("\nbase 4h par paire:", (b.groupby(["sym", "oos"]).r.sum().unstack() * 100).round(1).rename(columns={False: "IS", True: "OOS"}).to_string())
