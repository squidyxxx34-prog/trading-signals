"""OB 5 étoiles — règles EXACTES de la vidéo Kasper (transcription).
OB      = dernière bougie inverse avant le mouvement violent, mèche à mèche.
Etoile1 = (éliminatoire) imbalance : bougie 1 (l'OB) ne touche pas la bougie 3.
Etoile2 = Supertrend(10,3) dans le sens du trade + pas de range
          (range = nuage qui alterne : >3 changements de couleur sur 100 bougies).
Etoile3 = pas de liquidité non prise derrière l'OB (swing high/low ou equal
          non récupérés à moins de 2 ATR au-delà de l'OB). Trendlines non codées.
Etoile4 = OB vierge (jamais touché avant).
Etoile5 = Fibo du haut au bas de marché : OB entier en premium (vente) /
          discount (achat).
Trade   = seulement 4 ou 5 étoiles. On attend que le prix revienne dans l'OB,
          puis 1 bougie de réaction dans le sens du trade -> entrée à sa clôture.
          SL juste derrière l'OB. TP 2R (conseil débutant). Pas de frais.
"""
import sys, glob, numpy as np, pandas as pd

LOOK = 100      # bougies pour trouver le haut/bas de marché
EXP = 300       # durée de vie max d'un OB
CONF = 10       # bougies max pour la bougie de réaction après la touche

def atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().values

def supertrend(h, l, c, n=10, m=3.0):
    a = pd.Series(np.maximum(h - l, np.maximum(abs(h - np.r_[c[0], c[:-1]]),
                  abs(l - np.r_[c[0], c[:-1]])))).rolling(n).mean().bfill().values
    hl2 = (h + l) / 2; up = hl2 + m * a; dn = hl2 - m * a
    N = len(c); fu = up.copy(); fd = dn.copy(); d = np.ones(N, int)
    for i in range(1, N):
        fu[i] = up[i] if (up[i] < fu[i-1] or c[i-1] > fu[i-1]) else fu[i-1]
        fd[i] = dn[i] if (dn[i] > fd[i-1] or c[i-1] < fd[i-1]) else fd[i-1]
        if d[i-1] == 1: d[i] = -1 if c[i] < fd[i] else 1
        else: d[i] = 1 if c[i] > fu[i] else -1
    flips = pd.Series((d != np.r_[d[0], d[:-1]]).astype(int)).rolling(100).sum().fillna(99).values
    return d, flips

def pivots(h, l, k=5):
    N = len(h); ph = np.zeros(N, bool); pl = np.zeros(N, bool)
    for i in range(k, N - k):
        if h[i] == h[i-k:i+k+1].max(): ph[i] = True
        if l[i] == l[i-k:i+k+1].min(): pl[i] = True
    return ph, pl

def bt(d, RR=(1, 2, 3)):
    o, h, l, c = (d[x].values.astype(float) for x in 'ohlc')
    N = len(c); a = atr(h, l, c); sd, flips = supertrend(h, l, c)
    ph, pl = pivots(h, l)
    out = []
    for k in range(LOOK + 10, N - 5):
        for side in (1, -1):
            # OB = bougie inverse, suivie du mouvement ; FVG bougie1(OB)/bougie3
            if side == 1:
                if not (c[k] < o[k] and c[k+1] > o[k+1] and l[k+2] > h[k]): continue
            else:
                if not (c[k] > o[k] and c[k+1] < o[k+1] and h[k+2] < l[k]): continue
            top, bot = h[k], l[k]
            j = k + 2                    # OB connu à la clôture de k+2
            # étoile 2 (au moment où l'OB est créé)
            st2 = sd[j] == side and flips[j] <= 3
            # étoile 3 : liquidité non prise derrière l'OB (pivots confirmés)
            lim = j - 5
            if side == 1:
                ps = [p for p in np.where(pl[k-LOOK:lim])[0] + k - LOOK
                      if bot - 2*a[j] <= l[p] < bot and l[p+1:j+1].min() >= l[p]]
            else:
                ps = [p for p in np.where(ph[k-LOOK:lim])[0] + k - LOOK
                      if top < h[p] <= top + 2*a[j] and h[p+1:j+1].max() <= h[p]]
            st3 = len(ps) == 0
            # étoile 4 : vierge -> on ne prend que la 1re touche
            s, t = j + 1, min(N, j + 1 + EXP)
            touch = (l[s:t] <= top) if side == 1 else (h[s:t] >= bot)
            if not touch.any(): continue
            ti = s + int(touch.argmax())
            # étoile 5 : Fibo haut/bas de marché, évalué avant la touche
            if side == 1:
                mh = h[k:ti].max(); ml = l[k-LOOK:k+1].min()
                st5 = top < (mh + ml) / 2
            else:
                ml = l[k:ti].min(); mh = h[k-LOOK:k+1].max()
                st5 = bot > (mh + ml) / 2
            stars = 2 + int(st2) + int(st3) + int(st5)   # 1 et 4 acquises
            # bougie de réaction dans l'OB, SL non touché
            sl = bot if side == 1 else top
            e = None
            for q in range(ti, min(N, ti + CONF)):
                if (side == 1 and l[q] <= sl) or (side == -1 and h[q] >= sl): break
                if (side == 1 and c[q] > o[q]) or (side == -1 and c[q] < o[q]):
                    e = c[q]; f = q; break
            if e is None: continue
            risk = abs(e - sl)
            if risk <= 0: continue
            row = dict(t=d.t.iloc[f], side=side, st2=st2, st3=st3, st5=st5, stars=stars)
            for R in RR:
                tp = e + side * R * risk
                hs = (l[f+1:] <= sl) if side == 1 else (h[f+1:] >= sl)
                ht = (h[f+1:] >= tp) if side == 1 else (l[f+1:] <= tp)
                iS = hs.argmax() if hs.any() else 10**9
                iT = ht.argmax() if ht.any() else 10**9
                row[f'r{R}'] = np.nan if iS == iT == 10**9 else (-1.0 if iS <= iT else float(R))
            out.append(row)
    return out

if __name__ == '__main__':
    folder = sys.argv[1]; rows = []
    for fn in sorted(glob.glob(f'{folder}/*.parquet')):
        r = bt(pd.read_parquet(fn).reset_index(drop=True)); sym = fn.split('/')[-1][:-8]
        for x in r: x['sym'] = sym
        rows += r
    T = pd.DataFrame(rows); T.to_csv(f'ob5k_{folder}.csv', index=False)
    print(f'===== {folder}')
    for lab, m in [('toutes étoiles (1+4)', T.stars >= 2), ('3 étoiles', T.stars == 3),
                   ('4 étoiles', T.stars == 4), ('5 étoiles', T.stars == 5),
                   ('RÈGLE KASPER >=4', T.stars >= 4)]:
        s = T[m]; line = [lab.ljust(22), f'n={len(s):5d}']
        for R in (1, 2, 3):
            x = s[f'r{R}'].dropna()
            line.append(f'{R}R WR {100*(x>0).mean():4.1f}% exp {x.mean():+.3f}R')
        print(' | '.join(line))
    k = T[T.stars >= 4].copy(); k['y'] = pd.to_datetime(k.t).dt.year
    print('>=4 étoiles à 2R par année :', k.groupby('y').r2.agg(['count', 'mean']).round(3).to_dict('index'))
