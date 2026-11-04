"""Trouve de VRAIS exemples de patterns sur données CFD (forex + or, 2012-2022) et mesure leur fiabilité.
Sortie : patterns.json (fenêtres OHLC + annotations + stats)."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, ".")
from fx_common import load_fx, SYMS
from shootout import atr

def scale(sym): return 100 if sym == "XAUUSD" else 1000 if sym.endswith("JPY") else 100000
def dec(sym): return 2 if sym == "XAUUSD" else 3 if sym.endswith("JPY") else 5

def pivots(h, l, L):
    n = len(h); ph = np.zeros(n, bool); pl = np.zeros(n, bool)
    for j in range(L, n - L):
        if h[j] == h[j - L:j + L + 1].max(): ph[j] = True
        if l[j] == l[j - L:j + L + 1].min(): pl[j] = True
    return ph, pl

def outcome(o, h, l, c, a, i, d, n_ahead=20):
    """+1 ATR dans le sens du pattern avant -1 ATR contre (depuis la clôture du signal)."""
    e = c[i]; up, dn = e + a[i], e - a[i]
    for k in range(i + 1, min(i + 1 + n_ahead, len(c))):
        hit_up, hit_dn = h[k] >= up, l[k] <= dn
        if hit_up and hit_dn: return 0       # ambigu → compté comme échec
        if hit_up: return 1 if d == 1 else 0
        if hit_dn: return 1 if d == -1 else 0
    return 0

def detect(df):
    o, h, l, c = (df[k].values for k in ["open", "high", "low", "close"]); a = atr(df).values
    n = len(c); body = np.abs(c - o); rng = h - l; upw = h - np.maximum(o, c); low = np.minimum(o, c) - l
    bavg = pd.Series(body).rolling(20).mean().values
    lo20 = pd.Series(l).rolling(20).min().values; hi20 = pd.Series(h).rolling(20).max().values
    ev = {k: [] for k in ["engulf", "hammer", "star", "doji", "mstar", "inside", "dbottom", "dtop", "hs", "sr", "tri", "flag", "fvg", "ob", "sweep", "choch"]}
    ph, pl = pivots(h, l, 5)
    phi = np.where(ph)[0]; pli = np.where(pl)[0]
    for i in range(60, n - 25):
        if np.isnan(a[i]) or np.isnan(bavg[i]): continue
        locL = l[i - 2:i + 1].min() <= lo20[i]; locH = h[i - 2:i + 1].max() >= hi20[i]
        if c[i - 1] < o[i - 1] and c[i] > o[i] and c[i] >= o[i - 1] and o[i] <= c[i - 1] and body[i] > 1.3 * body[i - 1] and locL and body[i] > bavg[i]:
            ev["engulf"].append(dict(i=i, d=1, hl=[i - 1, i]))
        if rng[i] > 0 and low[i] >= 0.6 * rng[i] and upw[i] <= 0.15 * rng[i] and body[i] >= 0.1 * rng[i] and locL and rng[i] > a[i]:
            ev["hammer"].append(dict(i=i, d=1, hl=[i, i]))
        if rng[i] > 0 and upw[i] >= 0.6 * rng[i] and low[i] <= 0.15 * rng[i] and body[i] >= 0.1 * rng[i] and locH and rng[i] > a[i]:
            ev["star"].append(dict(i=i, d=-1, hl=[i, i]))
        if rng[i] > 0 and body[i] <= 0.08 * rng[i] and locH and rng[i] > 0.8 * a[i]:
            ev["doji"].append(dict(i=i, d=-1, hl=[i, i]))
        if c[i - 2] < o[i - 2] and body[i - 2] > bavg[i] and body[i - 1] < 0.5 * bavg[i] and c[i] > o[i] and c[i] > (o[i - 2] + c[i - 2]) / 2 and locL:
            ev["mstar"].append(dict(i=i, d=1, hl=[i - 2, i]))
        if h[i - 1] < h[i - 2] and l[i - 1] > l[i - 2] and c[i] > h[i - 2] and body[i] > bavg[i]:
            ev["inside"].append(dict(i=i, d=1, hl=[i - 2, i], box=[i - 2, h[i - 2], i - 1, l[i - 2]]))
        if l[i] > h[i - 2] and l[i] - h[i - 2] > 0.5 * a[i] and c[i - 1] > o[i - 1]:
            ev["fvg"].append(dict(i=i, d=1, box=[i - 2, l[i], i + 12, h[i - 2]], hl=[i - 1, i - 1]))
    # figures sur pivots (confirmées à la cassure de la ligne de cou)
    for k in range(1, len(pli)):
        j1, j2 = pli[k - 1], pli[k]
        if 10 <= j2 - j1 <= 45 and abs(l[j1] - l[j2]) < 0.35 * a[j2]:
            neck = h[j1:j2].max()
            if neck - max(l[j1], l[j2]) < 2 * a[j2]: continue
            for i in range(j2 + 6, min(j2 + 25, n - 25)):
                if c[i] > neck:
                    ev["dbottom"].append(dict(i=i, d=1, pts=[[int(j1), float(l[j1]), "1"], [int(j2), float(l[j2]), "2"]], lines=[[int(j1), float(neck), int(i), float(neck), "ligne de cou"]])); break
                if l[i] < min(l[j1], l[j2]) - 0.3 * a[i]: break
    for k in range(1, len(phi)):
        j1, j2 = phi[k - 1], phi[k]
        if 10 <= j2 - j1 <= 45 and abs(h[j1] - h[j2]) < 0.35 * a[j2]:
            neck = l[j1:j2].min()
            if min(h[j1], h[j2]) - neck < 2 * a[j2]: continue
            for i in range(j2 + 6, min(j2 + 25, n - 25)):
                if c[i] < neck:
                    ev["dtop"].append(dict(i=i, d=-1, pts=[[int(j1), float(h[j1]), "1"], [int(j2), float(h[j2]), "2"]], lines=[[int(j1), float(neck), int(i), float(neck), "ligne de cou"]])); break
                if h[i] > max(h[j1], h[j2]) + 0.3 * a[i]: break
    for k in range(2, len(phi)):
        s1, hd, s2 = phi[k - 2], phi[k - 1], phi[k]
        if not (8 <= hd - s1 <= 30 and 8 <= s2 - hd <= 30): continue
        if h[hd] > h[s1] + a[hd] and h[hd] > h[s2] + a[hd] and abs(h[s1] - h[s2]) < 0.8 * a[hd]:
            n1, n2 = l[s1:hd].argmin() + s1, l[hd:s2].argmin() + hd
            for i in range(s2 + 6, min(s2 + 20, n - 25)):
                neck = l[n1] + (l[n2] - l[n1]) * (i - n1) / max(n2 - n1, 1)
                if c[i] < neck:
                    ev["hs"].append(dict(i=i, d=-1, pts=[[int(s1), float(h[s1]), "É"], [int(hd), float(h[hd]), "T"], [int(s2), float(h[s2]), "É"]],
                                         lines=[[int(n1), float(l[n1]), int(i), float(neck), "ligne de cou"]])); break
                if h[i] > h[hd]: break
    # support / résistance : 3 rejets du même niveau
    for k in range(2, len(phi)):
        js = phi[k - 2:k + 1]
        if js[-1] - js[0] <= 60 and np.ptp(h[js]) < 0.3 * a[js[-1]] and js[-1] + 25 < n:
            lvl = h[js].max(); i = js[-1] + 5
            ev["sr"].append(dict(i=int(i), d=-1, pts=[[int(j), float(h[j]), "rejet"] for j in js], lines=[[int(js[0]) - 3, float(lvl), int(i) + 10, float(lvl), ""]]))
    # triangle : 2 sommets décroissants + 2 creux croissants, puis cassure
    for k in range(1, len(phi)):
        a1, a2 = phi[k - 1], phi[k]
        lows = pli[(pli > a1 - 15) & (pli < a2 + 10)]
        if len(lows) < 2 or not (8 <= a2 - a1 <= 35): continue
        b1, b2 = lows[0], lows[-1]
        if h[a2] < h[a1] - 0.5 * a[a2] and l[b2] > l[b1] + 0.5 * a[a2]:
            for i in range(max(a2, b2) + 6, min(max(a2, b2) + 15, n - 25)):
                top = h[a1] + (h[a2] - h[a1]) * (i - a1) / (a2 - a1); bot = l[b1] + (l[b2] - l[b1]) * (i - b1) / max(b2 - b1, 1)
                if c[i] > top:
                    ev["tri"].append(dict(i=i, d=1, lines=[[int(a1), float(h[a1]), int(i), float(top), ""], [int(b1), float(l[b1]), int(i), float(bot), ""]])); break
                if c[i] < bot:
                    ev["tri"].append(dict(i=i, d=-1, lines=[[int(a1), float(h[a1]), int(i), float(top), ""], [int(b1), float(l[b1]), int(i), float(bot), ""]])); break
    # drapeau : impulsion > 4 ATR en 6 bougies puis consolidation 6-14 bougies (< 40 % de retracement) puis cassure
    i = 60
    while i < n - 40:
        if c[i] - c[i - 6] > 4 * a[i]:
            top = h[i - 6:i + 1].max(); base = c[i - 6]
            for m in range(6, 15):
                seg_l = l[i + 1:i + m + 1].min(); seg_h = h[i + 1:i + m + 1].max()
                if top - seg_l > 0.4 * (top - base): break
                j = i + m + 1
                if c[j] > seg_h:
                    ev["flag"].append(dict(i=int(j), d=1, box=[int(i + 1), float(seg_h), int(i + m), float(seg_l)], lines=[[int(i - 6), float(base), int(i), float(top), "mât"]])); i = j; break
        i += 1
    # SMC : sweep d'un creux pivot + CHoCH (clôture au-dessus du dernier sommet) + OB + FVG
    for k in range(1, len(pli)):
        j_liq = pli[k - 1]
        for i in range(pli[k - 1] + 6, min(pli[k - 1] + 60, n - 25)):
            if l[i] < l[j_liq] and c[i] > l[j_liq]:            # sweep (mèche sous le creux, clôture au-dessus)
                prev_h = phi[phi <= i - 5]
                if len(prev_h) == 0: break
                ph_ = prev_h[-1]
                for m in range(i + 1, min(i + 15, n - 20)):
                    if c[m] > h[ph_]:
                        ob = i if c[i] < o[i] else (i - 1 if c[i - 1] < o[i - 1] else i)
                        fv = [g for g in range(i + 2, m + 1) if l[g] > h[g - 2]]
                        e = dict(i=int(m), d=1, sweep=[int(i), float(l[i]), int(j_liq), float(l[j_liq])],
                                 choch=[int(ph_), float(h[ph_]), int(m)], ob=[int(ob), float(h[ob]), int(m + 10), float(l[ob])],
                                 fvg=[int(fv[0] - 2), float(l[fv[0]]), int(m + 10), float(h[fv[0] - 2])] if fv else None)
                        ev["sweep"].append(e); ev["choch"].append(e); ev["ob"].append(e)
                        break
                break
    return ev

def stats_for(sym, tf):
    df = load_fx(sym, tf); o, h, l, c = (df[k].values for k in ["open", "high", "low", "close"]); a = atr(df).values
    ev = detect(df); out = {}
    for k, lst in ev.items():
        out[k] = [outcome(o, h, l, c, a, e["i"], e["d"]) for e in lst]
    return df, ev, out

if __name__ == "__main__":
    agg = {}; examples = {}
    rng = np.random.default_rng(3)
    for sym in SYMS:
        df, ev, out = stats_for(sym, "4h")
        for k, v in out.items(): agg.setdefault(k, []).extend(v)
        if sym in ("XAUUSD", "EURUSD", "GBPUSD", "USDJPY"):
            for k, lst in ev.items():
                for e, win in zip(lst, out[k]):
                    if win:
                        i = e["i"]; a_ = atr(df).values[i]; seg = df.iloc[i + 1:i + 13]
                        mfe = ((seg.high.max() - df.close.iloc[i]) if e["d"] == 1 else (df.close.iloc[i] - seg.low.min())) / a_
                        mae = ((df.close.iloc[i] - seg.low.min()) if e["d"] == 1 else (seg.high.max() - df.close.iloc[i])) / a_
                        e["q"] = mfe - mae
                        examples.setdefault(k, []).append((sym, df, e))
    res = {"stats": {k: dict(n=len(v), hit=round(100 * float(np.mean(v)), 1)) for k, v in agg.items() if v}, "examples": {}}
    pref = {"engulf": "XAUUSD", "hammer": "EURUSD", "star": "XAUUSD", "doji": "GBPUSD", "mstar": "EURUSD", "inside": "XAUUSD",
            "dbottom": "XAUUSD", "dtop": "EURUSD", "hs": "XAUUSD", "sr": "EURUSD", "tri": "XAUUSD", "flag": "XAUUSD",
            "fvg": "XAUUSD", "ob": "XAUUSD", "sweep": "EURUSD", "choch": "GBPUSD"}
    for k, lst in examples.items():
        cand = [x for x in lst if x[0] == pref[k]] or lst
        cand = [x for x in cand if x[1].index[x[2]["i"]].year >= 2018] or cand
        cand = sorted(cand, key=lambda x: -x[2]["q"])[:5]
        sym, df, e = cand[int(rng.integers(0, len(cand)))]
        lo = max(0, e["i"] - 40); hi = min(len(df), e["i"] + 16)
        if k in ("hs", "dtop", "dbottom", "sr", "tri"):
            first = min([p[0] for p in e.get("pts", [])] + [ln[0] for ln in e.get("lines", [])] + [e["i"]])
            lo = max(0, min(lo, first - 6)); hi = min(len(df), max(hi, e["i"] + 16))
        s = scale(sym); w = df.iloc[lo:hi]
        def X(i): return int(i) - lo
        ann = dict(sig=X(e["i"]), d=e["d"])
        if "hl" in e: ann["hl"] = [X(e["hl"][0]), X(e["hl"][1])]
        if e.get("box"): b = e["box"]; ann["box"] = [X(b[0]), b[1] / s, min(X(b[2]), hi - lo - 1), b[3] / s]
        if e.get("pts"): ann["pts"] = [[X(p[0]), p[1] / s, p[2]] for p in e["pts"]]
        if e.get("lines"): ann["lines"] = [[X(L[0]), L[1] / s, min(X(L[2]), hi - lo - 1), L[3] / s, L[4]] for L in e["lines"]]
        if k in ("sweep", "choch", "ob", "fvg") and "sweep" in e:
            sw = e["sweep"]; ch = e["choch"]; ob = e["ob"]
            if k == "sweep": ann["lines"] = [[X(sw[2]), sw[3] / s, X(sw[0]) + 3, sw[3] / s, "liquidité (ancien creux)"]]; ann["pts"] = [[X(sw[0]), sw[1] / s, "$ sweep"]]
            if k == "choch": ann["lines"] = [[X(ch[0]), ch[1] / s, X(ch[2]), ch[1] / s, "CHoCH"]]
            if k == "ob": ann["box"] = [X(ob[0]), ob[1] / s, min(X(ob[2]), hi - lo - 1), ob[3] / s]; ann["boxlabel"] = "Order Block"
        res["examples"][k] = dict(sym=sym, tf="H4", date=str(df.index[e["i"]].date()), dec=dec(sym),
                                  ohlc=[[round(v / s, dec(sym)) for v in row] for row in w[["open", "high", "low", "close"]].values.tolist()],
                                  t=[str(t)[:16] for t in w.index], ann=ann)
    json.dump(res, open("patterns.json", "w"))
    print(json.dumps(res["stats"], indent=1))
    print({k: (v["sym"], v["date"]) for k, v in res["examples"].items()})
