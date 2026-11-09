"""
Bot MT5 « Connors RSI-2 » (journalier) – la stratégie au winrate le plus élevé de nos backtests.

Règles (bougies D1 clôturées uniquement, aucun repaint) :
  BUY   si clôture > SMA200 et RSI(2) < 10
  SELL  si clôture < SMA200 et RSI(2) > 90
  Sortie : clôture repasse au-dessus de SMA5 (buy) / en dessous (sell), ou 10 jours max
  Stop serveur : 2 x ATR(14) dès l'ouverture
Backtest 2012-2022, 6 majeures, frais inclus :
  IS 2012-18 winrate 64 % PF 1.20 | hors échantillon 2019-22 winrate 65 % PF 1.14
  -> gagne souvent, petit gain moyen, perte moyenne ~1.6x plus grosse. Avantage mince.

Garde-fous FundedNext Stellar 1-Step 6K intégrés (perte jour / perte max).
Par défaut DRY_RUN = True : le bot écrit ce qu'il ferait, sans envoyer d'ordre.
"""
import json, time, logging, sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

# ===================== CONFIG =====================
DRY_RUN        = True          # False = ordres réels (teste d'abord en DÉMO)
LOGIN          = 0             # 0 = utilise le compte déjà connecté dans MT5
PASSWORD       = ""
SERVER         = ""
TERMINAL_PATH  = ""            # ex r"C:\Program Files\FundedNext MT5 Terminal\terminal64.exe" ("" = auto)

SYMBOLS        = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
RISK_PCT       = 0.5           # % du solde risqué par trade (distance au stop)
MAX_POSITIONS  = 3             # positions simultanées max (le bot)
SL_ATR         = 2.0
MAX_HOLD_DAYS  = 10
DELAY_MIN      = 30            # attend X min après l'ouverture D1 (spread de rollover)

INITIAL_BALANCE = 6000.0       # FundedNext : limites calculées sur le solde initial
DAILY_GUARD     = 150.0        # coupe tout si -150 $ sur la journée (limite FN = 180 $)
MAX_GUARD_FLOOR = 5700.0       # coupe tout et s'arrête si equity < 5700 (plancher FN = 5640)

MAGIC   = 240211
COMMENT = "connors2"
STATE   = Path(__file__).with_name("mt5_state.json")
# ==================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler(Path(__file__).with_name("mt5_bot.log"), encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])
log = logging.info


# ---------- indicateurs (identiques au backtest) ----------
def rma(s, n): return s.ewm(alpha=1 / n, adjust=False).mean()
def sma(s, n): return s.rolling(n).mean()
def rsi(c, n):
    d = c.diff(); up = rma(d.clip(lower=0), n); dn = rma((-d).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))
def atr(df, n=14):
    pc = df.close.shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return rma(tr, n)


# ---------- état ----------
def load_state():
    try: return json.loads(STATE.read_text())
    except Exception: return {"done": {}, "day": None, "day_ref": None, "halt_day": None, "halt_all": False}
def save_state(s): STATE.write_text(json.dumps(s, indent=1))


# ---------- MT5 ----------
def connect():
    kw = {}
    if TERMINAL_PATH: kw["path"] = TERMINAL_PATH
    if LOGIN: kw.update(login=LOGIN, password=PASSWORD, server=SERVER)
    if not mt5.initialize(**kw):
        raise SystemExit(f"MT5 initialize a échoué : {mt5.last_error()}")
    ti, ai = mt5.terminal_info(), mt5.account_info()
    log(f"Connecté {ai.login} @ {ai.server} | solde {ai.balance:.2f} {ai.currency} | DRY_RUN={DRY_RUN}")
    if not ti.trade_allowed: log("⚠️  'Trading algorithmique' désactivé dans MT5 (bouton Algo Trading).")
    if not ai.trade_expert: log("⚠️  Le compte refuse le trading automatique (add-on EA FundedNext ?).")

def resolve(base):
    if mt5.symbol_info(base): name = base
    else:
        c = [s.name for s in (mt5.symbols_get(f"*{base}*") or []) if s.name.startswith(base)]
        if not c: return None
        name = c[0]
    mt5.symbol_select(name, True)
    return name

def d1(sym, n=320):
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, n)
    if r is None or len(r) < 220: return None, None
    df = pd.DataFrame(r); df["time"] = pd.to_datetime(df.time, unit="s")
    return df.iloc[:-1].set_index("time"), int(r[-1]["time"])   # bougies clôturées, ouverture bougie en cours

def my_positions(sym=None):
    ps = mt5.positions_get(symbol=sym) if sym else mt5.positions_get()
    return [p for p in (ps or []) if p.magic == MAGIC]

def filling(sym):
    fm = mt5.symbol_info(sym).filling_mode
    return mt5.ORDER_FILLING_FOK if fm & 1 else mt5.ORDER_FILLING_IOC if fm & 2 else mt5.ORDER_FILLING_RETURN

def send(req, what):
    if DRY_RUN:
        log(f"[DRY] {what} -> {req}"); return True
    res = mt5.order_send(req)
    ok = res is not None and res.retcode == mt5.TRADE_RETCODE_DONE
    log(f"{'OK' if ok else 'ÉCHEC'} {what} -> {res.retcode if res else mt5.last_error()} {getattr(res, 'comment', '')}")
    return ok

def close(p, why):
    t = mt5.symbol_info_tick(p.symbol)
    buy = p.type == mt5.POSITION_TYPE_BUY
    req = dict(action=mt5.TRADE_ACTION_DEAL, symbol=p.symbol, volume=p.volume, position=p.ticket,
               type=mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY, price=t.bid if buy else t.ask,
               deviation=30, magic=MAGIC, comment=COMMENT, type_time=mt5.ORDER_TIME_GTC, type_filling=filling(p.symbol))
    return send(req, f"FERME {p.symbol} #{p.ticket} ({why})")

def lots_for(sym, side, price, sl, balance):
    info = mt5.symbol_info(sym)
    loss1 = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY if side > 0 else mt5.ORDER_TYPE_SELL, sym, 1.0, price, sl)
    if not loss1: return 0.0
    v = (balance * RISK_PCT / 100) / abs(loss1)
    v = np.floor(v / info.volume_step) * info.volume_step
    return float(round(min(v, info.volume_max), 2)) if v >= info.volume_min else 0.0

def open_trade(sym, side, a, balance):
    info, t = mt5.symbol_info(sym), mt5.symbol_info_tick(sym)
    price = t.ask if side > 0 else t.bid
    dist = max(SL_ATR * a, (info.trade_stops_level + 5) * info.point)
    sl = round(price - side * dist, info.digits)
    vol = lots_for(sym, side, price, sl, balance)
    if vol <= 0: log(f"{sym} : lot trop petit pour {RISK_PCT}% de risque, ignoré"); return
    req = dict(action=mt5.TRADE_ACTION_DEAL, symbol=sym, volume=vol, type=mt5.ORDER_TYPE_BUY if side > 0 else mt5.ORDER_TYPE_SELL,
               price=price, sl=sl, deviation=30, magic=MAGIC, comment=COMMENT,
               type_time=mt5.ORDER_TIME_GTC, type_filling=filling(sym))
    send(req, f"{'BUY' if side > 0 else 'SELL'} {sym} {vol} lot @ {price} SL {sl}")


# ---------- garde-fous FundedNext ----------
def guards(st, server_ts):
    ai = mt5.account_info()
    day = datetime.fromtimestamp(server_ts, timezone.utc).strftime("%Y-%m-%d")   # jour serveur
    if st["day"] != day:
        st.update(day=day, day_ref=max(ai.balance, ai.equity))
        log(f"Nouveau jour serveur {day} | référence {st['day_ref']:.2f}")
    if ai.equity < MAX_GUARD_FLOOR and not st["halt_all"]:
        st["halt_all"] = True; log(f"🛑 Equity {ai.equity:.2f} < {MAX_GUARD_FLOOR} : tout fermé, bot arrêté.")
        for p in my_positions(): close(p, "garde perte max")
    if st["day_ref"] - ai.equity >= DAILY_GUARD and st["halt_day"] != day:
        st["halt_day"] = day; log(f"🛑 -{st['day_ref'] - ai.equity:.2f} $ aujourd'hui : tout fermé jusqu'à demain.")
        for p in my_positions(): close(p, "garde perte jour")
    return not st["halt_all"] and st["halt_day"] != day


# ---------- logique principale ----------
def process(sym, st, can_open):
    df, cur_open = d1(sym)
    if df is None: return
    if st["done"].get(sym) == cur_open: return                    # déjà traité pour cette bougie
    tick = mt5.symbol_info_tick(sym)
    if tick is None or tick.time - cur_open < DELAY_MIN * 60: return

    c = df.close; r2 = rsi(c, 2); s200 = sma(c, 200); s5 = sma(c, 5); a = atr(df).iloc[-1]
    last, r, m200, m5 = c.iloc[-1], r2.iloc[-1], s200.iloc[-1], s5.iloc[-1]

    # 1) sorties
    for p in my_positions(sym):
        held = int((df.index > pd.to_datetime(p.time, unit="s")).sum())
        buy = p.type == mt5.POSITION_TYPE_BUY
        if (buy and last > m5) or (not buy and last < m5): close(p, "retour SMA5")
        elif held >= MAX_HOLD_DAYS: close(p, f"{held} jours")

    # 2) entrées
    if can_open and not my_positions(sym) and len(my_positions()) < MAX_POSITIONS and not np.isnan(m200):
        side = 1 if (last > m200 and r < 10) else -1 if (last < m200 and r > 90) else 0
        log(f"{sym} clôture {last} | RSI2 {r:.1f} | SMA200 {m200:.5f} | signal {side}")
        if side: open_trade(sym, side, a, mt5.account_info().balance)

    st["done"][sym] = cur_open


def main():
    connect()
    syms = [s for s in (resolve(b) for b in SYMBOLS) if s]
    log(f"Symboles : {syms}")
    st = load_state()
    while True:
        try:
            if mt5.terminal_info() is None: connect()
            tick = mt5.symbol_info_tick(syms[0])
            if tick:
                ok = guards(st, tick.time)
                for s in syms: process(s, st, ok)
                save_state(st)
        except Exception as e:
            log(f"Erreur : {e!r}")
        time.sleep(30)


if __name__ == "__main__":
    main()
