"""Backtest 'OB 5 étoiles' (Kasper) sur crypto perps.
Etoile 1 (imbalance) et 4 (OB vierge, 1re touche) = obligatoires (construction).
Etoile 2 = tendance Supertrend(10,3) stable >= 10 bougies, sens du trade.
Etoile 3 = pas de pivot non pris juste derrière l'OB (<= 1 ATR).
Etoile 5 = OB en discount (achat) / premium (vente) du range 100 bougies.
Entrée limite au bord proche de l'OB, SL bord opposé - 0.1 ATR, TP = R x risque.
Frais 0.05 %/côté. Pas de lookahead : OB actif après la bougie qui crée le FVG.
"""
import sys, glob, numpy as np, pandas as pd

FEE = 0.0005
EXP = 300

def atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().values

def supertrend(h, l, c, a, m=3.0):
    hl2 = (h + l) / 2; up = hl2 + m * a; dn = hl2 - m * a
    n = len(c); fu = up.copy(); fd = dn.copy(); d = np.ones(n, int)
    for i in range(1, n):
        fu[i] = up[i] if (up[i] < fu[i-1] or c[i-1] > fu[i-1]) else fu[i-1]
        fd[i] = dn[i] if (dn[i] > fd[i-1] or c[i-1] < fd[i-1]) else fd[i-1]
        if d[i-1] == 1: d[i] = -1 if c[i] < fd[i] else 1
        else: d[i] = 1 if c[i] > fu[i] else -1
    run = np.zeros(n, int)
    for i in range(1, n): run[i] = run[i-1] + 1 if d[i] == d[i-1] else 0
    return d, run

def pivots(h, l, k=3):
    n = len(h); ph = np.zeros(n, bool); pl = np.zeros(n, bool)
    for i in range(k, n - k):
        if h[i] == h[i-k:i+k+1].max(): ph[i] = True
        if l[i] == l[i-k:i+k+1].min(): pl[i] = True
    return ph, pl  # confirmé à i+k

def bt(d, RR=(1, 2, 3)):
    o, h, l, c = (d[x].values.astype(float) for x in 'ohlc')
    n = len(c); a = atr(h, l, c); sd, srun = supertrend(h, l, c, a)
    ph, pl = pivots(h, l)
    hi100 = pd.Series(h).rolling(100).max().values
    lo100 = pd.Series(l).rolling(100).min().values
    out = []; seen = set()
    for j in range(120, n - 2):
        for side in (1, -1):
            if side == 1 and not l[j] > h[j-2]: continue
            if side == -1 and not h[j] < l[j-2]: continue
            k = None
            for kk in range(j - 2, j - 7, -1):
                if (side == 1 and c[kk] < o[kk]) or (side == -1 and c[kk] > o[kk]):
                    k = kk; break
            if k is None or (k, side) in seen: continue
            seen.add((k, side))
            top, bot = h[k], l[k]
            # OB doit rester vierge entre k+1 et j (pas déjà retesté)
            if side == 1 and l[k+2:j+1].min() <= top: continue
            if side == -1 and h[k+2:j+1].max() >= bot: continue
            e = top if side == 1 else bot
            sl = bot - 0.1 * a[j] if side == 1 else top + 0.1 * a[j]
            risk = abs(e - sl)
            if risk <= 0 or risk / e < 0.001: continue
            s, t = j + 1, min(n, j + 1 + EXP)
            touch = (l[s:t] <= e) if side == 1 else (h[s:t] >= e)
            if not touch.any(): continue
            f = s + int(touch.argmax())
            # étoiles évaluées à la bougie de création j (connu avant l'entrée)
            st2 = (sd[j] == side) and srun[j] >= 10
            lim = j - 3  # pivots confirmés
            if side == 1:
                idx = np.where(pl[k-60:lim])[0] + k - 60
                st3 = not any((bot - a[j] <= l[p] < bot) and l[p+1:j+1].min() >= l[p] for p in idx)
                st5 = top < (hi100[j] + lo100[j]) / 2
            else:
                idx = np.where(ph[k-60:lim])[0] + k - 60
                st3 = not any((top < h[p] <= top + a[j]) and h[p+1:j+1].max() <= h[p] for p in idx)
                st5 = bot > (hi100[j] + lo100[j]) / 2
            sweep = (l[k] < l[k-20:k].min()) if side == 1 else (h[k] > h[k-20:k].max())
            row = dict(t=d.t.iloc[f], side=side, st2=st2, st3=st3, st5=st5,
                       sweep=sweep, stars=3 + int(st2) + int(st3) + int(st5) - 1)
            fee_r = 2 * FEE * e / risk
            for R in RR:
                tp = e + side * R * risk
                hs = (l[f:] <= sl) if side == 1 else (h[f:] >= sl)
                ht = (h[f:] >= tp) if side == 1 else (l[f:] <= tp)
                ht[0] = False  # pas de TP sur la bougie de remplissage (conservateur)
                iS = hs.argmax() if hs.any() else 10**9
                iT = ht.argmax() if ht.any() else 10**9
                if iS == iT == 10**9: res = np.nan
                elif iS <= iT: res = -1 - fee_r
                else: res = R - fee_r
                row[f'r{R}'] = res
            out.append(row)
    return out

if __name__ == '__main__':
    folder = sys.argv[1]
    rows = []
    for fn in sorted(glob.glob(f'{folder}/*.parquet')):
        d = pd.read_parquet(fn).reset_index(drop=True)
        r = bt(d); sym = fn.split('/')[-1][:-8]
        for x in r: x['sym'] = sym
        rows += r; print(sym, len(r), flush=True)
    T = pd.DataFrame(rows); T.to_csv(f'ob5_{folder}.csv', index=False)
