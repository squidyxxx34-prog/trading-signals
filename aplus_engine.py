"""Moteur du setup A+ (SMC) — copie exacte du moteur backtesté (backtests/aplus, 18 nov 2026).

Sweep d'une liquidité importante (PDH/PDL ou EQH/EQL) -> CHoCH avec FVG -> ordre limite au bord du FVG
-> SL derrière la mèche du sweep -> TP sur la liquidité opposée la plus proche (trade ignoré si < 2R).
Filtres : biais de fond (EMA 200/800 bougies) + CHoCH entre 7h et 20h UTC. Aucune donnée future.
"""
import numpy as np
import pandas as pd

try:
    import numba as nb
except ImportError:  # sans numba : plus lent mais identique
    class nb:  # noqa: N801
        @staticmethod
        def njit(*a, **k):
            return (lambda f: f) if not (a and callable(a[0])) else a[0]

PIV = 3


def prep(d, adjust=False):
    """d : DataFrame avec colonnes t (UTC), o, h, l, c — bougies FERMÉES uniquement, triées."""
    d = d.reset_index(drop=True)
    o, h, l, c = (d[k].to_numpy(np.float64) for k in "ohlc")
    t = pd.to_datetime(d.t, utc=True)
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    cs = pd.Series(c)
    e_fast = cs.ewm(span=200, adjust=adjust).mean().to_numpy()
    e_slow = cs.ewm(span=800, adjust=adjust).mean().to_numpy()
    bias = np.where((c > e_slow) & (e_fast > e_slow), 1, np.where((c < e_slow) & (e_fast < e_slow), -1, 0)).astype(np.int8)
    day = t.dt.floor("D")
    g = d.groupby(day.values)
    daily = pd.DataFrame({"h": g.h.max(), "l": g.l.min()})
    prev = daily.shift(1)
    pdh = prev.h.reindex(day.values).to_numpy(); pdl = prev.l.reindex(day.values).to_numpy()
    n = len(c)
    phc = np.full(n, np.nan); plc = np.full(n, np.nan)
    for j in range(PIV, n - PIV):
        w = slice(j - PIV, j + PIV + 1)
        if h[j] == h[w].max(): phc[j + PIV] = h[j]
        if l[j] == l[w].min(): plc[j + PIV] = l[j]
    hour = t.dt.hour.to_numpy().astype(np.int8)
    dhs = g.h.cummax().to_numpy(); dls = g.l.cummin().to_numpy()
    return dict(t=t, o=o, h=h, l=l, c=c, atr=atr, bias=bias, pdh=pdh, pdl=pdl, phc=phc, plc=plc,
                hour=hour, dhs=dhs, dls=dls)


@nb.njit(cache=True)
def run(o, h, l, c, atr, bias, pdh, pdl, phc, plc, hour, dhs, dls,
        use_bias, use_sess, tp_mode, entry_mid, min_rr, fee, eq_tol, minfvg):
    # tp_mode : 0 = liquidite opposee la plus proche (skip si < min_rr), 1 = 2R fixe, 2 = 3R fixe
    n = len(c)
    MAXL = 64
    # niveaux EQ actifs (prix, indice de creation)
    eqh = np.full(MAXL, np.nan); eql = np.full(MAXL, np.nan)
    swh = np.full(MAXL, np.nan); swh_i = np.zeros(MAXL, np.int64)  # derniers pivots hauts
    swl = np.full(MAXL, np.nan); swl_i = np.zeros(MAXL, np.int64)
    nsh = 0; nsl = 0
    out = np.full((20000, 9), np.nan)  # side, i_sig, i_fill, i_exit, entry, sl, tp, R_net, reason
    nt = 0
    setups = np.full((20000, 6), np.nan)  # side, i_sig, entry, sl, tp, issue (0 en attente, 1 rempli, 2 annule)
    ns = 0
    # etat setup : 0 rien, 1 sweep en attente de CHoCH, 2 ordre limite pose, 3 position ouverte
    st = 0; side = 0; i_sw = 0; ext = 0.0; lvl = 0.0; ref = 0.0; i_sig = 0
    entry = 0.0; sl = 0.0; tp = 0.0; i_fill = 0
    last_sh = np.nan; last_sl_ = np.nan
    for i in range(PIV * 2 + 1, n):
        a = atr[i]
        # 1) maj des pivots confirmes a i (connus a la cloture de i)
        if not np.isnan(phc[i]):
            p = phc[i]
            for k in range(min(nsh, MAXL)):
                if i - swh_i[k] <= 96 and abs(swh[k] - p) <= eq_tol * a:
                    for m in range(MAXL):
                        if np.isnan(eqh[m]):
                            eqh[m] = max(p, swh[k]); break
                    break
            swh[nsh % MAXL] = p; swh_i[nsh % MAXL] = i; nsh += 1
            last_sh = p
        if not np.isnan(plc[i]):
            p = plc[i]
            for k in range(min(nsl, MAXL)):
                if i - swl_i[k] <= 96 and abs(swl[k] - p) <= eq_tol * a:
                    for m in range(MAXL):
                        if np.isnan(eql[m]):
                            eql[m] = min(p, swl[k]); break
                    break
            swl[nsl % MAXL] = p; swl_i[nsl % MAXL] = i; nsl += 1
            last_sl_ = p
        # pivots deja pris (le prix les a depasses) -> plus de la liquidite
        for k in range(MAXL):
            if not np.isnan(swh[k]) and h[i] > swh[k] and swh_i[k] < i: swh[k] = np.nan
            if not np.isnan(swl[k]) and l[i] < swl[k] and swl_i[k] < i: swl[k] = np.nan
        # 2) gestion de la position ouverte
        if st == 3:
            hit_sl = (l[i] <= sl) if side == 1 else (h[i] >= sl)
            hit_tp = (h[i] >= tp) if side == 1 else (l[i] <= tp)
            ex = np.nan; reason = 0
            if hit_sl:
                ex = sl; reason = -1
            elif hit_tp:
                ex = tp; reason = 1
            elif i - i_fill >= 48:
                ex = c[i]; reason = 0
            if not np.isnan(ex):
                risk = abs(entry - sl)
                r = (ex - entry) / risk * side - fee * 2 * entry / risk
                out[nt, 0] = side; out[nt, 1] = i_sig; out[nt, 2] = i_fill; out[nt, 3] = i
                out[nt, 4] = entry; out[nt, 5] = sl; out[nt, 6] = tp; out[nt, 7] = r; out[nt, 8] = reason
                nt += 1; st = 0
                if nt >= 20000: break
            continue
        # 3) ordre limite en attente
        if st == 2:
            filled = (l[i] <= entry) if side == 1 else (h[i] >= entry)
            target_first = (h[i] >= tp) if side == 1 else (l[i] <= tp)
            if filled:
                st = 3; i_fill = i
                setups[ns - 1, 5] = 1
                # meme bougie : SL touche ?
                if (side == 1 and l[i] <= sl) or (side == -1 and h[i] >= sl):
                    risk = abs(entry - sl)
                    r = -1.0 - fee * 2 * entry / risk
                    out[nt, 0] = side; out[nt, 1] = i_sig; out[nt, 2] = i; out[nt, 3] = i
                    out[nt, 4] = entry; out[nt, 5] = sl; out[nt, 6] = tp; out[nt, 7] = r; out[nt, 8] = -1
                    nt += 1; st = 0
                continue
            if target_first or i - i_sig > 16:
                st = 0
                setups[ns - 1, 5] = 2
            continue
        # 4) en attente de CHoCH apres un sweep
        if st == 1:
            # le sweep est invalide si une bougie cloture au-dela du niveau
            if (side == 1 and c[i] < lvl) or (side == -1 and c[i] > lvl) or i - i_sw > 16:
                st = 0
            else:
                if side == 1: ext = min(ext, l[i])
                else: ext = max(ext, h[i])
                choch = (side == 1 and c[i] > ref) or (side == -1 and c[i] < ref)
                if choch:
                    ok = True
                    if use_bias and bias[i] != side: ok = False
                    if use_sess and (hour[i] < 7 or hour[i] >= 20): ok = False
                    # FVG dans la jambe sweep -> CHoCH
                    fv_top = np.nan; fv_bot = np.nan
                    for m in range(i, i_sw + 1, -1):
                        if side == 1 and l[m] > h[m - 2] and l[m] - h[m - 2] >= minfvg * atr[m]:
                            fv_top = l[m]; fv_bot = h[m - 2]; break
                        if side == -1 and h[m] < l[m - 2] and l[m - 2] - h[m] >= minfvg * atr[m]:
                            fv_top = l[m - 2]; fv_bot = h[m]; break
                    if np.isnan(fv_top): ok = False
                    if ok:
                        if side == 1:
                            e = (fv_top + fv_bot) / 2 if entry_mid else fv_top
                            s = ext - 0.1 * a
                        else:
                            e = (fv_top + fv_bot) / 2 if entry_mid else fv_bot
                            s = ext + 0.1 * a
                        risk = abs(e - s)
                        if risk <= 0 or risk < 0.2 * a:
                            ok = False
                        else:
                            if tp_mode == 1: t_ = e + side * 2 * risk
                            elif tp_mode == 2: t_ = e + side * 3 * risk
                            else:
                                # liquidite opposee la plus proche : PDH/PDL, EQH/EQL actifs, pivots < 96 bougies
                                best = np.nan
                                if side == 1:
                                    cands = [pdh[i] if dhs[i] < pdh[i] else np.nan]
                                    for m in range(MAXL):
                                        if not np.isnan(eqh[m]): cands.append(eqh[m])
                                    for k in range(MAXL):
                                        if i - swh_i[k] <= 96 and not np.isnan(swh[k]): cands.append(swh[k])
                                    for x in cands:
                                        if not np.isnan(x) and x > e and (np.isnan(best) or x < best): best = x
                                else:
                                    cands = [pdl[i] if dls[i] > pdl[i] else np.nan]
                                    for m in range(MAXL):
                                        if not np.isnan(eql[m]): cands.append(eql[m])
                                    for k in range(MAXL):
                                        if i - swl_i[k] <= 96 and not np.isnan(swl[k]): cands.append(swl[k])
                                    for x in cands:
                                        if not np.isnan(x) and x < e and (np.isnan(best) or x > best): best = x
                                if np.isnan(best) or abs(best - e) < min_rr * risk:
                                    ok = False
                                    t_ = 0.0
                                else:
                                    t_ = best - side * 0.05 * a
                            if ok:
                                entry = e; sl = s; tp = t_; i_sig = i; st = 2
                                if ns < 20000:
                                    setups[ns, 0] = side; setups[ns, 1] = i; setups[ns, 2] = e
                                    setups[ns, 3] = s; setups[ns, 4] = t_; setups[ns, 5] = 0; ns += 1
                    if st != 2:
                        st = 0
            # pas de continue : un nouveau sweep peut remplacer
            if st != 0:
                continue
        # 5) detection d'un sweep a la bougie i (niveaux connus avant i)
        best_side = 0
        # long : sweep d'une SSL (PDL ou EQL)
        lv = np.nan
        x = pdl[i]
        if not np.isnan(x) and l[i] < x and c[i] > x: lv = x
        for m in range(MAXL):
            y = eql[m]
            if not np.isnan(y) and l[i] < y:
                if c[i] > y and (np.isnan(lv) or y < lv): lv = y
                eql[m] = np.nan  # niveau consomme
        if not np.isnan(lv) and not np.isnan(last_sh) and last_sh > c[i]:
            best_side = 1; lvl = lv; ext = l[i]; ref = last_sh
        lv2 = np.nan
        x = pdh[i]
        if not np.isnan(x) and h[i] > x and c[i] < x: lv2 = x
        for m in range(MAXL):
            y = eqh[m]
            if not np.isnan(y) and h[i] > y:
                if c[i] < y and (np.isnan(lv2) or y > lv2): lv2 = y
                eqh[m] = np.nan
        if best_side == 0 and not np.isnan(lv2) and not np.isnan(last_sl_) and last_sl_ < c[i]:
            best_side = -1; lvl = lv2; ext = h[i]; ref = last_sl_
        if best_side != 0:
            side = best_side; st = 1; i_sw = i
    return out[:nt], setups[:ns]


def scan(d, use_bias=1, use_sess=1, tp_mode=0, entry_mid=0, min_rr=2.0, fee=0.0005, eq_tol=0.15, minfvg=0.1, adjust=False):
    x = prep(d, adjust=adjust)
    trades, setups = run(x["o"], x["h"], x["l"], x["c"], x["atr"], x["bias"], x["pdh"], x["pdl"], x["phc"], x["plc"],
                         x["hour"], x["dhs"], x["dls"], use_bias, use_sess, tp_mode, entry_mid, min_rr, fee, eq_tol, minfvg)
    return x, trades, setups
