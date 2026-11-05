"""Order Blocks : vrais (checklist complète) vs faux, sur vraies bougies H4 forex + or (2012-2022).
Aucune donnée future : pivots utilisés seulement une fois confirmés (5 bougies après)."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, ".")
from fx_common import load_fx, SYMS
from shootout import atr, ema

L = 5
def scale(s): return 100 if s == "XAUUSD" else 1000 if s.endswith("JPY") else 100000
def dec(s): return 2 if s == "XAUUSD" else 3 if s.endswith("JPY") else 5

def find(sym, tf="4h"):
    df = load_fx(sym, tf); o, h, l, c = (df[k].values for k in ["open", "high", "low", "close"]); a = atr(df).values; n = len(c)
    d = df.close.resample("1D").last().dropna(); bias = np.sign(d - ema(d, 50)).shift(1).reindex(df.index, method="ffill").fillna(0).values
    ph = [j for j in range(L, n - L) if h[j] == h[j - L:j + L + 1].max()]
    pl = [j for j in range(L, n - L) if l[j] == l[j - L:j + L + 1].min()]
    out = []; used = set()
    for side in (1, -1):
        piv = ph if side == 1 else pl; opp = pl if side == 1 else ph
        for j in piv:
            lvl = h[j] if side == 1 else l[j]
            # BOS : 1re clôture au-delà du pivot, après sa confirmation (j+L)
            br = next((i for i in range(j + L, min(j + 80, n - 40)) if (c[i] > lvl if side == 1 else c[i] < lvl)), None)
            if br is None or br in used or np.isnan(a[br]): continue
            seg = range(j + 1, br + 1)
            ext = min(seg, key=lambda k: l[k]) if side == 1 else max(seg, key=lambda k: h[k])
            ob = next((k for k in range(ext, max(ext - 4, j), -1) if (c[k] < o[k] if side == 1 else c[k] > o[k])), ext)
            if br - ob < 1: continue
            prev = [p for p in opp if p < j and p + L <= br]
            swept = bool(prev) and ((l[ext] < l[prev[-1]]) if side == 1 else (h[ext] > h[prev[-1]]))
            fvg = None
            for g in range(ob + 2, br + 1):
                gap = (l[g] - h[g - 2]) if side == 1 else (l[g - 2] - h[g])
                if gap > 0.2 * a[br]: fvg = g; break
            trend = bias[br] == side
            top, bot = h[ob], l[ob]
            entry = top if side == 1 else bot
            sl = (bot - 0.2 * a[br]) if side == 1 else (top + 0.2 * a[br])
            risk = abs(entry - sl)
            if risk <= 0 or risk > 4 * a[br]: continue
            tp = entry + side * 2 * risk
            # 1er et 2e retour dans l'OB, issue : +2R avant SL ?
            touches = []; k = br + 1
            while k < min(br + 120, n - 2) and len(touches) < 2:
                if (l[k] <= entry if side == 1 else h[k] >= entry):
                    res = None; m = k
                    if (l[k] <= sl if side == 1 else h[k] >= sl): res, m = "SL", k
                    else:
                        for m in range(k + 1, min(k + 60, n)):
                            if (l[m] <= sl if side == 1 else h[m] >= sl): res = "SL"; break
                            if (h[m] >= tp if side == 1 else l[m] <= tp): res = "TP"; break
                    if res is None: break
                    touches.append((k, res, m))
                    k = m + 1
                    if res == "SL": break
                    # attend que le prix ressorte de la zone avant de compter un 2e test
                    while k < n - 2 and (l[k] <= entry if side == 1 else h[k] >= entry): k += 1
                else:
                    if (c[k] < bot if side == 1 else c[k] > top): break
                    k += 1
            if not touches: continue
            used.add(br)
            out.append(dict(sym=sym, side=side, piv=j, lvl=float(lvl), br=br, ext=ext, ob=ob, swept=swept, fvg=fvg, trend=bool(trend),
                            prev=prev[-1] if prev else None, top=float(top), bot=float(bot), entry=float(entry), sl=float(sl), tp=float(tp),
                            touches=touches, df=df))
    return out

def window(e, which):
    df = e["df"]; s = scale(e["sym"]); k, res, m = e["touches"][which]
    lo = max(0, min(e["piv"], e["prev"] or e["piv"]) - 8); hi = min(len(df), m + 6)
    if hi - lo > 90: lo = hi - 90
    X = lambda i: int(i) - lo
    w = df.iloc[lo:hi]
    ann = dict(d=e["side"], ob=[X(e["ob"]), e["top"] / s, X(m), e["bot"] / s],
               bos=[X(e["piv"]), e["lvl"] / s, X(e["br"])], entry=[X(k), e["entry"] / s], res=res, exit=[X(m), (e["tp"] if res == "TP" else e["sl"]) / s],
               sl=e["sl"] / s, tp=e["tp"] / s)
    if e["fvg"] is not None:
        g = e["fvg"]; dfv = df
        top, bot = (dfv.low.iloc[g], dfv.high.iloc[g - 2]) if e["side"] == 1 else (dfv.low.iloc[g - 2], dfv.high.iloc[g])
        ann["fvg"] = [X(g - 2), top / s, min(X(g + 6), hi - lo - 1), bot / s]
    if e["swept"] and e["prev"] is not None and X(e["prev"]) >= 0:
        pv = e["prev"]; lv = df.low.iloc[pv] if e["side"] == 1 else df.high.iloc[pv]
        ann["sweep"] = [X(pv), lv / s, X(e["ext"])]
    if which == 1:
        k0, r0, m0 = e["touches"][0]; ann["first"] = [X(k0), e["entry"] / s, r0]
    d = dec(e["sym"])
    return dict(sym=e["sym"], date=str(df.index[k].date()), dec=d, ann=ann,
                ohlc=[[round(v / s, d) for v in r] for r in w[["open", "high", "low", "close"]].values.tolist()],
                t=[str(t)[:16] for t in w.index],
                checks=dict(trend=e["trend"], swept=e["swept"], bos=True, fvg=e["fvg"] is not None, fresh=which == 0))

if __name__ == "__main__":
    allev = []
    for s in SYMS: allev += find(s)
    def wr(lst, which=0):
        r = [e["touches"][which][1] == "TP" for e in lst if len(e["touches"]) > which]
        return dict(n=len(r), win=round(100 * np.mean(r), 1) if r else None)
    full = [e for e in allev if e["trend"] and e["fvg"] is not None and e["swept"]]
    stats = {
        "full": wr(full),
        "nofvg": wr([e for e in allev if e["fvg"] is None]),
        "counter": wr([e for e in allev if not e["trend"] and e["fvg"] is not None]),
        "second": wr([e for e in allev if e["trend"] and e["fvg"] is not None and len(e["touches"]) > 1], 1),
        "all": wr(allev),
    }
    print(json.dumps(stats, indent=1))
    rng = np.random.default_rng(11)
    def pick(lst, which, res, syms, n):
        c = [e for e in lst if len(e["touches"]) > which and e["touches"][which][1] == res and e["sym"] in syms
             and e["df"].index[e["br"]].year >= 2016 and (e["touches"][which][0] - e["br"]) <= 25 and (e["touches"][which][2] - e["touches"][which][0]) <= 30]
        out, seen = [], set()
        for i in rng.permutation(len(c)):
            if c[i]["sym"] in seen: continue
            out.append(c[i]); seen.add(c[i]["sym"])
            if len(out) == n: break
        return out
    good = pick(full, 0, "TP", {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY"}, 3)
    bad_nofvg = pick([e for e in allev if e["fvg"] is None and e["trend"]], 0, "SL", {"XAUUSD", "EURUSD", "GBPUSD"}, 1)
    bad_counter = pick([e for e in allev if not e["trend"] and e["fvg"] is not None], 0, "SL", {"EURUSD", "XAUUSD", "USDJPY"}, 1)
    bad_second = pick([e for e in full if len(e["touches"]) > 1], 1, "SL", {"XAUUSD", "GBPUSD", "EURUSD", "USDJPY"}, 1)
    res = dict(stats=stats,
               good=[window(e, 0) for e in good],
               bad=[dict(kind="nofvg", **window(e, 0)) for e in bad_nofvg] + [dict(kind="counter", **window(e, 0)) for e in bad_counter]
                   + [dict(kind="second", **window(e, 1)) for e in bad_second])
    json.dump(res, open("ob_examples.json", "w"), default=lambda x: x.item() if hasattr(x, "item") else str(x))
    for g in res["good"]: print("VRAI", g["sym"], g["date"], g["checks"])
    for b in res["bad"]: print("FAUX", b["kind"], b["sym"], b["date"], b["checks"])
