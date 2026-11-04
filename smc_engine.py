"""
Moteur SMC Pro v2 — miroir Python du script Pine (même logique, barre par barre, à la clôture).
Utilisé par smc_bot.py pour envoyer les notifs ntfy avec les MÊMES critères que le Pine.

  Continuation : cassure interne dans le sens du biais (EMA journalière + structure swing),
                 jambe avec FVG frais → ordre limite au bord du FVG, SL derrière l'extrême, TP en R.
  Reversal A+  : idem + sweep de liquidité + CHoCH interne + killzone.
"""
import numpy as np
import pandas as pd

DEF = dict(
    lint=3,            # force pivots internes
    lsw=10,            # force pivots swing (biais)
    bias="swing",      # "swing" | "ema" | "none"
    need_sweep=True,
    need_choch=True,   # MSS = CHoCH interne (sinon BOS accepté)
    need_fvg=True,     # displacement = FVG frais dans la jambe
    fvg_min=0.10,      # taille min FVG (x ATR)
    fvg_pick="first",  # "first" (le plus profond) | "last"
    entry="fvg_top",   # fvg_top | fvg_ce | ob_top | ob_mid | confirm
    pd_filter=False,   # entrée en discount (<50 %) de la jambe d'impulsion
    sl_buf=0.10,       # buffer SL (x ATR)
    rr=2.0,
    max_wait=20,       # bougies max pour être rempli
    max_hold=60,       # sortie au temps
    min_risk=0.25,     # risque min (x ATR)
    max_risk=4.0,      # risque max (x ATR)
    kz=False,          # MSS uniquement en killzone (Londres 02-05 NY, NY 07-11 NY)
    fee=0.10,          # frais + spread aller-retour en %
    exit="rr",         # "rr" (TP fixe) | "trail" (stop suiveur ATR, pas de TP)
    trail_mult=3.0,
    htf_len=50,        # EMA journalière pour le biais HTF
)


def htf_bias(df, n, htf_df=None):
    """+1 si la clôture du DERNIER jour clôturé > EMA(n) journalière de ce jour, -1 sinon (pas de look-ahead).
    = request.security("D", s[1], lookahead_on) du script Pine."""
    if htf_df is not None:
        d = htf_df["close"].dropna()
    else:
        d = df["close"].resample("1D", label="left", closed="left").last().dropna()
    e = pd.Series(ema(d.values.astype(float), n), index=d.index)
    b = np.sign(d - e).shift(1)            # valeur connue au début du jour suivant
    return b.reindex(df.index, method="ffill").fillna(0).values


def atr_rma(h, l, c, n=14):
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[np.nan, c[:-1]]), np.abs(l - np.r_[np.nan, c[:-1]])))
    tr[0] = h[0] - l[0]
    out = np.full_like(c, np.nan)
    a = 1.0 / n
    s = np.nan
    for i in range(len(c)):
        if i < n - 1:
            continue
        if i == n - 1:
            s = tr[:n].mean()
        else:
            s = s + a * (tr[i] - s)
        out[i] = s
    return out


def ema(x, n):
    out = np.full_like(x, np.nan)
    a = 2.0 / (n + 1)
    s = np.nan
    for i in range(len(x)):
        if i < n - 1:
            continue
        s = x[:n].mean() if i == n - 1 else s + a * (x[i] - s)
        out[i] = s
    return out


def pivots(h, l, L):
    """pivot haut en j=i-L confirmé en i : h[j] > max(h[j+1..i]) et h[j] >= max(h[j-L..j-1])."""
    n = len(h)
    ph = np.zeros(n, bool)
    pl = np.zeros(n, bool)
    for i in range(2 * L, n):
        j = i - L
        if h[j] > h[j + 1:i + 1].max() and h[j] >= h[j - L:j].max():
            ph[i] = True
        if l[j] < l[j + 1:i + 1].min() and l[j] <= l[j - L:j].min():
            pl[i] = True
    return ph, pl


def killzone_mask(index):
    ny = index.tz_convert("America/New_York")
    m = ny.hour * 60 + ny.minute
    return ((m >= 120) & (m < 300)) | ((m >= 420) & (m < 660))


def run(df, p=None, collect=False, htf_df=None):
    P = dict(DEF)
    if p:
        P.update(p)
    o = df["open"].values.astype(float)
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)
    c = df["close"].values.astype(float)
    n = len(c)
    atr = atr_rma(h, l, c, 14)
    e200 = ema(c, 200)
    kzm = killzone_mask(df.index) if P["kz"] else np.ones(n, bool)
    hb = htf_bias(df, P["htf_len"], htf_df) if "htf" in P["bias"] else np.zeros(n)
    Li, Ls = P["lint"], P["lsw"]
    iph, ipl = pivots(h, l, Li)
    sph, spl = pivots(h, l, Ls)

    # état structure interne
    ph_v = ph_b = None; ph_x = True; pl_before_ph = None
    pl_v = pl_b = None; pl_x = True; ph_before_pl = None
    t_int = 0
    # état structure swing
    sph_v = spl_v = None; sph_x = spl_x = True; t_sw = 0

    tsw_arr = np.zeros(n)
    fills = []
    pend = None     # ordre en attente
    pos = None      # position ouverte
    trades = []
    arms = []

    for i in range(n):
        # ---------- 1) gestion position ouverte ----------
        if pos is not None and i > pos["fbar"] and P["exit"] == "trail":
            d, e, rk, st = pos["d"], pos["e"], pos["rk"], pos["st"]
            r = None
            if d == 1:
                if o[i] <= st: r = (o[i] - e) / rk
                elif l[i] <= st: r = (st - e) / rk
            else:
                if o[i] >= st: r = (e - o[i]) / rk
                elif h[i] >= st: r = (e - st) / rk
            if r is None and i - pos["fbar"] >= P["max_hold"]:
                r = d * (c[i] - e) / rk
            if r is None:
                if d == 1:
                    pos["ext"] = max(pos["ext"], h[i]); pos["st"] = max(st, pos["ext"] - P["trail_mult"] * atr[i])
                else:
                    pos["ext"] = min(pos["ext"], l[i]); pos["st"] = min(st, pos["ext"] + P["trail_mult"] * atr[i])
            else:
                net = r - e * P["fee"] / 100.0 / rk
                trades.append(dict(arm=pos["arm"], fill=pos["fbar"], exit=i, d=d, r=net, risk_atr=rk / pos["atr"], cr=e / rk))
                pos = None
        if pos is not None and i > pos["fbar"] and P["exit"] == "rr":
            d, e, sl, tp, rk = pos["d"], pos["e"], pos["sl"], pos["tp"], pos["rk"]
            r = None
            if d == 1:
                if o[i] <= sl:
                    r = (o[i] - e) / rk
                elif o[i] >= tp:
                    r = (o[i] - e) / rk
                elif l[i] <= sl:
                    r = -1.0
                elif h[i] >= tp:
                    r = P["rr"]
            else:
                if o[i] >= sl:
                    r = (e - o[i]) / rk
                elif o[i] <= tp:
                    r = (e - o[i]) / rk
                elif h[i] >= sl:
                    r = -1.0
                elif l[i] <= tp:
                    r = P["rr"]
            if r is None and i - pos["fbar"] >= P["max_hold"]:
                r = d * (c[i] - e) / rk
            if r is not None:
                net = r - e * P["fee"] / 100.0 / rk
                trades.append(dict(arm=pos["arm"], fill=pos["fbar"], exit=i, d=d, r=net, risk_atr=rk / pos["atr"], cr=e / rk))
                pos = None

        # ---------- 2) ordre en attente : remplissage / annulation ----------
        if pend is not None and pos is None and i > pend["bar"]:
            d, e, sl, tp = pend["d"], pend["e"], pend["sl"], pend["tp"]
            filled = False
            fill_px = e
            if P["entry"] == "confirm":
                inzone = (l[i] <= pend["ztop"]) if d == 1 else (h[i] >= pend["zbot"])
                okclose = (c[i] > o[i] and c[i] > pend["zbot"] and c[i] > sl) if d == 1 else (c[i] < o[i] and c[i] < pend["ztop"] and c[i] < sl)
                if inzone and okclose:
                    filled = True; fill_px = c[i]
                elif (d == 1 and c[i] <= sl) or (d == -1 and c[i] >= sl):
                    pend = None
            else:
                if d == 1 and l[i] <= e:
                    filled = True; fill_px = min(e, o[i])
                elif d == -1 and h[i] >= e:
                    filled = True; fill_px = max(e, o[i])
            if pend is not None and not filled:
                ran = (h[i] >= tp) if d == 1 else (l[i] <= tp)
                if ran or i - pend["bar"] >= P["max_wait"]:
                    pend = None
            if filled:
                fills.append(dict(fill=i, d=d, e=fill_px, sl=sl, tp=tp))
                rk = (fill_px - sl) if d == 1 else (sl - fill_px)
                if P["entry"] == "confirm":
                    tp = fill_px + d * rk * P["rr"]
                if rk <= 0:
                    # gap au-delà du SL : stop immédiat
                    trades.append(dict(arm=pend["bar"], fill=i, exit=i, d=d, r=-1.0 - fill_px * P["fee"] / 100.0 / max(abs(e - sl), 1e-12), risk_atr=0, cr=fill_px / max(abs(e - sl), 1e-12)))
                    pend = None
                else:
                    pos = dict(d=d, e=fill_px, sl=sl, tp=tp, rk=rk, fbar=i, arm=pend["bar"], atr=pend["atr"], st=sl,
                               ext=(h[i] if d == 1 else l[i]))
                    if P["exit"] == "trail":
                        pos["st"] = max(sl, pos["ext"] - P["trail_mult"] * atr[i]) if d == 1 else min(sl, pos["ext"] + P["trail_mult"] * atr[i])
                    pend = None
                    # sur la bougie de remplissage : seul le SL compte (conservateur)
                    if P["entry"] != "confirm":
                        if (d == 1 and l[i] <= sl) or (d == -1 and h[i] >= sl):
                            net = -1.0 - fill_px * P["fee"] / 100.0 / rk
                            trades.append(dict(arm=pos["arm"], fill=i, exit=i, d=d, r=net, risk_atr=rk / pos["atr"], cr=fill_px / rk))
                            pos = None

        # ---------- 3) pivots ----------
        if iph[i]:
            j = i - Li
            ph_v, ph_b, ph_x = h[j], j, False
            pl_before_ph = pl_v
        if ipl[i]:
            j = i - Li
            pl_v, pl_b, pl_x = l[j], j, False
            ph_before_pl = ph_v
        if sph[i]:
            sph_v, sph_x = h[i - Ls], False
        if spl[i]:
            spl_v, spl_x = l[i - Ls], False

        # ---------- 4) structure swing (biais) ----------
        if sph_v is not None and not sph_x and c[i] > sph_v:
            sph_x = True; t_sw = 1
        if spl_v is not None and not spl_x and c[i] < spl_v:
            spl_x = True; t_sw = -1
        tsw_arr[i] = t_sw

        # ---------- 5) structure interne + setups ----------
        a = atr[i]
        sig = 0
        if ph_v is not None and not ph_x and c[i] > ph_v:
            prev = t_int
            ph_x = True; t_int = 1
            if not np.isnan(a):
                sig = arm_check(1, prev, i, ph_b, pl_before_ph, o, h, l, c, a, e200, t_sw, kzm, P, hb[i])
        if pl_v is not None and not pl_x and c[i] < pl_v:
            prev = t_int
            pl_x = True; t_int = -1
            if not np.isnan(a):
                sig = arm_check(-1, prev, i, pl_b, ph_before_pl, o, h, l, c, a, e200, t_sw, kzm, P, hb[i])
        if isinstance(sig, dict) and pos is None:
            pend = sig
            arms.append(sig)

    if collect:
        return trades, arms, tsw_arr, hb, fills
    return trades


def arm_check(d, prev_trend, i, piv_bar, liq, o, h, l, c, a, e200, t_sw, kzm, P, hbi=0):
    if P["need_choch"] and prev_trend != -d:
        return 0
    if "swing" in P["bias"] and t_sw != d:
        return 0
    if "htf" in P["bias"] and hbi != d:
        return 0
    if P["bias"] == "ema" and (np.isnan(e200[i]) or (d == 1 and c[i] < e200[i]) or (d == -1 and c[i] > e200[i])):
        return 0
    if not kzm[i]:
        return 0
    lo, hi = piv_bar + 1, i
    if lo > hi:
        return 0
    if hi - lo > 300:
        lo = hi - 300
    if d == 1:
        seg = l[lo:hi + 1]
        k = int(np.argmin(seg)); ext = seg[k]; ext_b = lo + k
        swept = liq is not None and ext < liq
        leg_hi = h[ext_b:i + 1].max()
    else:
        seg = h[lo:hi + 1]
        k = int(np.argmax(seg)); ext = seg[k]; ext_b = lo + k
        swept = liq is not None and ext > liq
        leg_lo = l[ext_b:i + 1].min()
    if P["need_sweep"] and not swept:
        return 0
    # FVG frais dans la jambe d'impulsion
    fvg = None
    js = range(ext_b + 2, i + 1)
    js = js if P["fvg_pick"] == "first" else reversed(js)
    for j in js:
        if d == 1:
            top, bot = l[j], h[j - 2]
            if top - bot >= P["fvg_min"] * a and (j == i or l[j + 1:i + 1].min() > top):
                fvg = (top, bot); break
        else:
            top, bot = l[j - 2], h[j]
            if top - bot >= P["fvg_min"] * a and (j == i or h[j + 1:i + 1].max() < bot):
                fvg = (top, bot); break
    if P["need_fvg"] and fvg is None:
        return 0
    obt, obb = h[ext_b], l[ext_b]
    mode = P["entry"]
    if mode in ("fvg_top", "fvg_ce", "confirm") and fvg is None:
        mode = "ob_top" if mode != "confirm" else mode
    if d == 1:
        if mode == "fvg_top": e = fvg[0]
        elif mode == "fvg_ce": e = (fvg[0] + fvg[1]) / 2
        elif mode == "ob_top": e = obt
        elif mode == "ob_mid": e = (obt + obb) / 2
        else: e = fvg[0] if fvg else obt
        sl = ext - P["sl_buf"] * a
        rk = e - sl
        ztop = fvg[0] if fvg else obt
        zbot = min(fvg[1], obb) if fvg else obb
        if P["pd_filter"] and e > (ext + leg_hi) / 2:
            return 0
        if e >= c[i]:
            return 0
    else:
        if mode == "fvg_top": e = fvg[1]
        elif mode == "fvg_ce": e = (fvg[0] + fvg[1]) / 2
        elif mode == "ob_top": e = obb
        elif mode == "ob_mid": e = (obt + obb) / 2
        else: e = fvg[1] if fvg else obb
        sl = ext + P["sl_buf"] * a
        rk = sl - e
        zbot = fvg[1] if fvg else obb
        ztop = max(fvg[0], obt) if fvg else obt
        if P["pd_filter"] and e < (ext + leg_lo) / 2:
            return 0
        if e <= c[i]:
            return 0
    if rk < P["min_risk"] * a or rk > P["max_risk"] * a:
        return 0
    tp = e + d * rk * P["rr"]
    return dict(d=d, e=e, sl=sl, tp=tp, bar=i, atr=a, ztop=ztop, zbot=zbot)


def stats(trades, index=None):
    if not trades:
        return dict(n=0)
    r = np.array([t["r"] for t in trades])
    w = r[r > 0].sum(); ls = -r[r <= 0].sum()
    eq = np.cumsum(r); dd = (np.maximum.accumulate(eq) - eq).max()
    out = dict(n=len(r), wr=round(100 * (r > 0).mean(), 1), pf=round(w / ls, 2) if ls > 0 else np.inf,
               exp=round(r.mean(), 3), totR=round(r.sum(), 1), maxdd=round(dd, 1))
    if index is not None:
        yrs = pd.Series(r, index=index[[t["fill"] for t in trades]].year)
        g = yrs.groupby(level=0).sum()
        out["years_pos"] = f"{(g > 0).sum()}/{len(g)}"
    return out


def random_control(df, trades, rr, fee, max_hold, seeds=200, rng=None):
    """Entrées au hasard (même nombre, même sens, même risque en ATR, même RR, mêmes frais),
    entrée au marché à la clôture, gestion identique et conservatrice."""
    rng = rng or np.random.default_rng(7)
    o = df["open"].values; h = df["high"].values; l = df["low"].values; c = df["close"].values
    atr = atr_rma(h, l, c, 14)
    n = len(c)
    dirs = np.array([t["d"] for t in trades]); ra = np.array([max(t["risk_atr"], 0.25) for t in trades])
    exps = []
    for s in range(seeds):
        bars = rng.integers(250, n - max_hold - 2, size=len(trades))
        rs = []
        for b, d, k in zip(bars, dirs, ra):
            e = c[b]; rk = k * atr[b]; sl = e - d * rk; tp = e + d * rk * rr
            r = None
            for i in range(b + 1, min(b + 1 + max_hold, n)):
                if d == 1:
                    if o[i] <= sl or o[i] >= tp: r = (o[i] - e) / rk; break
                    if l[i] <= sl: r = -1.0; break
                    if h[i] >= tp: r = rr; break
                else:
                    if o[i] >= sl or o[i] <= tp: r = (e - o[i]) / rk; break
                    if h[i] >= sl: r = -1.0; break
                    if l[i] <= tp: r = rr; break
            if r is None:
                i = min(b + max_hold, n - 1); r = d * (c[i] - e) / rk
            rs.append(r - e * fee / 100 / rk)
        exps.append(np.mean(rs))
    return np.array(exps)
