"""
Bot MT5 « Or M15 · SMC Continuation + filtre tendance 6 mois »
= ton Pine SMC Pro v2 (mode Continuation, mêmes réglages) sur XAUUSD M15,
  mais SEULEMENT dans le sens d'une tendance forte : l'or a bougé de plus de 10 % en 6 mois.

Backtest (frais inclus) : 2012-22 XAU M15 PF 1.13 (112 trades) | 2022-26 PAXG M15 PF 1.47 (200 trades)
Moteur de signaux = smc_engine.py (le même que le backtest et les notifs ntfy) -> aucune divergence de logique.

Fonctionnement : à chaque clôture M15, si le moteur arme un ordre limite (bord du FVG, SL derrière l'extrême,
TP 3R) ET que le filtre 6 mois est dans le même sens -> le bot pose l'ordre limite dans MT5 (valable 10 bougies).
Par défaut DRY_RUN = True : il écrit ce qu'il ferait, sans rien envoyer.
"""
import json, sys, time, logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smc_engine import run   # noqa: E402

# ===================== CONFIG =====================
DRY_RUN       = True           # False = ordres réels (DÉMO d'abord)
LOGIN, PASSWORD, SERVER, TERMINAL_PATH = 0, "", "", ""   # 0 = compte déjà connecté dans MT5
SYMBOL        = "XAUUSD"       # suffixe auto-détecté (XAUUSD.r, GOLD...)
RISK_PCT      = 0.5            # % du solde risqué par trade
MOM_DAYS      = 126            # ~6 mois de bourse
MOM_MIN       = 0.10           # tendance 6 mois > 10 % (dans le sens du trade)
BARS          = 5000           # historique M15 donné au moteur

PARAMS = dict(                 # = réglages par défaut du Pine SMC Pro v2, modèle Continuation
    lint=3, lsw=10, htf_len=50, fvg_min=0.2, fvg_pick="first", entry="fvg_top", sl_buf=0.2, rr=3.0,
    max_wait=10, max_hold=120, min_risk=0.25, max_risk=4.0,
    bias="htf+swing", need_fvg=True, need_sweep=False, need_choch=False, kz=False, exit="rr", fee=0.0)

DAILY_GUARD     = 150.0        # coupe tout si -150 $ sur la journée (limite FundedNext 6K = 180 $)
MAX_GUARD_FLOOR = 5700.0       # coupe tout et s'arrête si equity < 5700 (plancher FN = 5640)
MAGIC, COMMENT  = 240212, "smc-gold"
STATE = Path(__file__).with_name("gold_state.json")
# ==================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler(Path(__file__).with_name("gold_bot.log"), encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])
log = logging.info
TF = mt5.TIMEFRAME_M15


def load_state():
    try: return json.loads(STATE.read_text())
    except Exception: return {"last_bar": 0, "day": None, "day_ref": None, "halt_day": None, "halt_all": False}
def save_state(s): STATE.write_text(json.dumps(s, indent=1))


def connect():
    kw = {}
    if TERMINAL_PATH: kw["path"] = TERMINAL_PATH
    if LOGIN: kw.update(login=LOGIN, password=PASSWORD, server=SERVER)
    if not mt5.initialize(**kw): raise SystemExit(f"MT5 initialize KO : {mt5.last_error()}")
    ai, ti = mt5.account_info(), mt5.terminal_info()
    log(f"Connecté {ai.login} @ {ai.server} | solde {ai.balance:.2f} | DRY_RUN={DRY_RUN}")
    if not ti.trade_allowed: log("⚠️  Bouton 'Algo Trading' désactivé dans MT5.")
    if not ai.trade_expert: log("⚠️  Compte sans trading auto (add-on EA FundedNext ?).")

def resolve(base):
    if mt5.symbol_info(base): name = base
    else:
        c = [s.name for s in (mt5.symbols_get("*XAU*") or []) + (mt5.symbols_get("*GOLD*") or [])]
        if not c: raise SystemExit("Symbole or introuvable")
        name = c[0]
    mt5.symbol_select(name, True)
    return name

def bars(sym, tf, n):
    r = mt5.copy_rates_from_pos(sym, tf, 0, n)
    if r is None or len(r) < 300: return None
    df = pd.DataFrame(r)
    df.index = pd.to_datetime(df.time, unit="s").dt.tz_localize("UTC")   # heure serveur (journées = celles du broker)
    return df[["open", "high", "low", "close"]].astype(float).iloc[:-1]   # bougies CLÔTURÉES uniquement

def mine(kind):
    xs = (mt5.positions_get(symbol=SYM) if kind == "pos" else mt5.orders_get(symbol=SYM)) or []
    return [x for x in xs if x.magic == MAGIC]

def filling():
    fm = mt5.symbol_info(SYM).filling_mode
    return mt5.ORDER_FILLING_FOK if fm & 1 else mt5.ORDER_FILLING_IOC if fm & 2 else mt5.ORDER_FILLING_RETURN

def send(req, what):
    if DRY_RUN: log(f"[DRY] {what}"); return True
    res = mt5.order_send(req)
    ok = res is not None and res.retcode == mt5.TRADE_RETCODE_DONE
    log(f"{'OK' if ok else 'ÉCHEC'} {what} -> {res.retcode if res else mt5.last_error()} {getattr(res, 'comment', '')}")
    return ok

def close_pos(p, why):
    t = mt5.symbol_info_tick(SYM); buy = p.type == mt5.POSITION_TYPE_BUY
    send(dict(action=mt5.TRADE_ACTION_DEAL, symbol=SYM, volume=p.volume, position=p.ticket,
              type=mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY, price=t.bid if buy else t.ask,
              deviation=50, magic=MAGIC, comment=COMMENT, type_time=mt5.ORDER_TIME_GTC, type_filling=filling()),
         f"FERME #{p.ticket} ({why})")

def cancel(o, why):
    send(dict(action=mt5.TRADE_ACTION_REMOVE, order=o.ticket), f"ANNULE ordre #{o.ticket} ({why})")

def lots(side, e, sl):
    info = mt5.symbol_info(SYM)
    loss1 = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY if side > 0 else mt5.ORDER_TYPE_SELL, SYM, 1.0, e, sl)
    if not loss1: return 0.0
    v = (mt5.account_info().balance * RISK_PCT / 100) / abs(loss1)
    v = np.floor(v / info.volume_step) * info.volume_step
    return float(round(min(v, info.volume_max), 2)) if v >= info.volume_min else 0.0


def guards(st):
    ai = mt5.account_info(); tick = mt5.symbol_info_tick(SYM)
    day = datetime.fromtimestamp(tick.time, timezone.utc).strftime("%Y-%m-%d")
    if st["day"] != day: st.update(day=day, day_ref=max(ai.balance, ai.equity))
    if ai.equity < MAX_GUARD_FLOOR and not st["halt_all"]:
        st["halt_all"] = True; log(f"🛑 Equity {ai.equity:.2f} < {MAX_GUARD_FLOOR} : tout fermé, bot arrêté.")
        for p in mine("pos"): close_pos(p, "garde perte max")
        for o in mine("ord"): cancel(o, "garde perte max")
    if st["day_ref"] - ai.equity >= DAILY_GUARD and st["halt_day"] != day:
        st["halt_day"] = day; log(f"🛑 -{st['day_ref'] - ai.equity:.2f} $ aujourd'hui : tout fermé jusqu'à demain.")
        for p in mine("pos"): close_pos(p, "garde perte jour")
        for o in mine("ord"): cancel(o, "garde perte jour")
    return not st["halt_all"] and st["halt_day"] != day


def on_bar(df, d1, ok):
    tf_sec = 15 * 60
    last_close = int(df.index[-1].timestamp()) + tf_sec
    # 1) ménage : ordres expirés / TP déjà atteint avant remplissage, positions trop vieilles
    for o in mine("ord"):
        age = (last_close - o.time_setup) // tf_sec
        since = df[df.index >= pd.Timestamp(o.time_setup, unit="s", tz="UTC")]
        ran = (since.high.max() >= o.tp) if o.type == mt5.ORDER_TYPE_BUY_LIMIT else (since.low.min() <= o.tp)
        if age >= PARAMS["max_wait"] or ran: cancel(o, "expiré" if not ran else "TP atteint sans moi")
    for p in mine("pos"):
        if (last_close - p.time) // tf_sec >= PARAMS["max_hold"]: close_pos(p, f"{PARAMS['max_hold']} bougies")

    # 2) signal sur la bougie qui vient de clôturer ?
    _, arms, _, _, _ = run(df, PARAMS, collect=True, htf_df=d1)
    sig = next((a for a in arms if a["bar"] == len(df) - 1), None)
    c = d1.close
    mom = c.iloc[-1] / c.iloc[-1 - MOM_DAYS] - 1 if len(c) > MOM_DAYS else 0.0
    if sig is None:
        log(f"clôture {df.index[-1]:%d/%m %H:%M} · pas de signal · tendance 6 mois {mom:+.1%}"); return
    side = sig["d"]; e, sl, tp = sig["e"], sig["sl"], sig["tp"]
    txt = f"{'BUY' if side > 0 else 'SELL'} LIMIT {e:.2f} SL {sl:.2f} TP {tp:.2f}"
    if not (np.sign(mom) == side and abs(mom) > MOM_MIN):
        log(f"signal {txt} IGNORÉ : tendance 6 mois {mom:+.1%} (il faut > {MOM_MIN:.0%} dans le même sens)"); return
    if not ok: log(f"signal {txt} ignoré (garde-fou actif)"); return
    if mine("pos") or mine("ord"): log(f"signal {txt} ignoré (déjà un trade/ordre en cours)"); return

    info, t = mt5.symbol_info(SYM), mt5.symbol_info_tick(SYM)
    vol = lots(side, e, sl)
    if vol <= 0: log(f"signal {txt} : lot trop petit"); return
    rd = lambda x: round(x, info.digits)
    marketable = (side > 0 and t.ask <= e) or (side < 0 and t.bid >= e)    # prix déjà au-delà -> exécution au marché (= backtest)
    if marketable:
        req = dict(action=mt5.TRADE_ACTION_DEAL, type=mt5.ORDER_TYPE_BUY if side > 0 else mt5.ORDER_TYPE_SELL,
                   price=t.ask if side > 0 else t.bid, deviation=50, type_filling=filling())
    else:
        req = dict(action=mt5.TRADE_ACTION_PENDING, type=mt5.ORDER_TYPE_BUY_LIMIT if side > 0 else mt5.ORDER_TYPE_SELL_LIMIT,
                   price=rd(e), type_filling=mt5.ORDER_FILLING_RETURN)
    req.update(symbol=SYM, volume=vol, sl=rd(sl), tp=rd(tp), magic=MAGIC, comment=COMMENT, type_time=mt5.ORDER_TIME_GTC)
    send(req, f"{txt} · {vol} lot · tendance 6 mois {mom:+.1%}{' (au marché)' if marketable else ''}")


def main():
    global SYM
    connect(); SYM = resolve(SYMBOL); log(f"Symbole : {SYM}")
    st = load_state()
    while True:
        try:
            if mt5.terminal_info() is None: connect()
            ok = guards(st)
            df = bars(SYM, TF, BARS)
            if df is not None and int(df.index[-1].timestamp()) != st["last_bar"]:
                d1 = bars(SYM, mt5.TIMEFRAME_D1, 400)
                if st["last_bar"]: on_bar(df, d1, ok)          # 1er passage : on mémorise sans trader l'historique
                st["last_bar"] = int(df.index[-1].timestamp())
            save_state(st)
        except Exception as ex:
            log(f"Erreur : {ex!r}")
        time.sleep(10)


if __name__ == "__main__":
    main()
