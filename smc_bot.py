"""SMC Pro v2 -> notifications ntfy / Telegram, avec EXACTEMENT les critères du script Pine.

Le moteur (smc_engine.py) est le miroir barre par barre du Pine « SMC Pro v2 » :
mêmes pivots, même structure interne / swing, même biais HTF (EMA journalière, jour clôturé),
même FVG frais, même entrée / SL / TP, même gestion de l'ordre en attente et de la position.
Une notif part quand le script afficherait « BUY LIMIT / SELL LIMIT » (ordre à placer),
et en option quand l'ordre est rempli. Marchés : forex + métaux (CFD).

Usage : python smc_bot.py            (boucle, durée = LOOP_MINUTES)
        python smc_bot.py --once     (un seul scan)
        python smc_bot.py --test     (notif de test)
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yaml
import yfinance as yf

from smc_engine import run

ROOT = Path(__file__).parent
CFG = yaml.safe_load((ROOT / "smc_config.yml").read_text(encoding="utf-8"))
STATE_FILE = ROOT / "smc_state.json"
TF_MIN = {"15m": 15, "30m": 30, "60m": 60, "1h": 60}
PERIOD = {"15m": "59d", "30m": "59d", "60m": "729d", "1h": "729d"}


# ---------- données ----------
def _clean(df):
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close"]]
    return df[~df.index.duplicated(keep="last")].sort_index()


def download(tickers, interval, period):
    data = yf.download(tickers, interval=interval, period=period, progress=False,
                       auto_adjust=False, group_by="ticker", threads=True)
    out = {}
    for t in tickers:
        try:
            df = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            out[t] = _clean(df)
        except Exception:  # noqa: BLE001
            pass
    return out


def daily(tickers):
    d = download(tickers, "1d", "2y")
    for t, df in d.items():   # bougie journalière datée à 00:00 UTC du jour
        df.index = df.index.tz_convert("UTC").normalize()
        d[t] = df[~df.index.duplicated(keep="last")]
    return d


# ---------- notifications ----------
def notify(title, body, tags, priority="urgent"):
    sent = False
    topic = os.getenv("NTFY_TOPIC")
    if topic:
        try:
            requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                          headers={"Title": title.encode("utf-8"), "Tags": tags, "Priority": priority}, timeout=15)
            sent = True
        except Exception as e:  # noqa: BLE001
            print("ntfy KO:", e)
    tok, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if tok and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": f"{title}\n\n{body}"}, timeout=15)
            sent = True
        except Exception as e:  # noqa: BLE001
            print("telegram KO:", e)
    if not sent:
        print("[aucun canal configuré]", title, "|", body.replace("\n", " | "))


# ---------- état ----------
def load_state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))
    if os.getenv("GITHUB_ACTIONS"):
        subprocess.run("git add smc_state.json && (git diff --cached --quiet || "
                       "(git commit -qm smc-state && git pull -q --rebase && git push -q))", shell=True, check=False)


# ---------- scan ----------
def params():
    p = dict(CFG["params"])
    model = CFG.get("model", "continuation")
    p["bias"] = "htf+swing"
    p["need_fvg"] = True
    p["exit"] = "rr"
    p["fee"] = 0.0
    if model == "reversal":
        p.update(need_sweep=True, need_choch=True, kz=CFG.get("reversal_killzone_only", True))
    else:
        p.update(need_sweep=False, need_choch=False, kz=False)
    return p


def lots_for(sym, entry, sl):
    risk = CFG["capital"] * CFG["risk_pct"] / 100
    per_lot = abs(entry - sl) * sym["contract"] * sym.get("currency_rate", 1)
    return risk, (risk / per_lot if per_lot > 0 else float("nan"))


def scan(state):
    tf = CFG["timeframe"]
    tf_min = TF_MIN[tf]
    now = pd.Timestamp(datetime.now(timezone.utc))
    syms = CFG["symbols"]
    tickers = [s["ticker"] for s in syms]
    ltf, dly = download(tickers, tf, PERIOD[tf]), daily(tickers)
    p = params()
    max_age = CFG.get("max_signal_age_min", 90)
    changed = False

    for sym in syms:
        name, t = sym["name"], sym["ticker"]
        df, hdf = ltf.get(t), dly.get(t)
        if df is None or hdf is None or len(df) < 300:
            print(f"{name}: pas assez de données")
            continue
        closed = df[df.index + pd.Timedelta(minutes=tf_min) <= now]   # = barstate.isconfirmed
        if closed.empty:
            continue
        trades, arms, _, _, fills = run(closed, p, collect=True, htf_df=hdf)
        idx = closed.index
        last_ts = str(idx[-1])
        prev = state.get(name)
        state[name] = last_ts
        changed = changed or prev != last_ts
        if prev is None:              # 1er passage : on mémorise sans notifier l'historique
            continue

        d = sym.get("decimals", 5)
        events = [("arm", a["bar"], a) for a in arms]
        if CFG.get("notify_fill", False):
            events += [("fill", f["fill"], f) for f in fills]
        for kind, bar, ev in sorted(events, key=lambda x: x[1]):
            ts = idx[bar]
            if str(ts) <= prev:
                continue
            age = (now - (ts + pd.Timedelta(minutes=tf_min))).total_seconds() / 60
            if age > max_age:
                print(f"skip {name} {kind} {ts} (vieux de {age:.0f} min)")
                continue
            local = (ts + pd.Timedelta(minutes=tf_min)).tz_convert(CFG["timezone"]).strftime("%d/%m %H:%M")
            if kind == "arm":
                buy = ev["d"] == 1
                risk, lots = lots_for(sym, ev["e"], ev["sl"])
                title = f"{'🟢 BUY' if buy else '🔴 SELL'} LIMIT {name} {tf}"
                body = (f"Ordre limite à {ev['e']:.{d}f}\nSL {ev['sl']:.{d}f}\nTP {ev['tp']:.{d}f}  ({p['rr']:g}R)\n"
                        f"Lots ≈ {lots:.2f}  (risque {risk:.0f}€)\n"
                        f"Valable {p['max_wait']} bougies · signal à la clôture de {local}")
                if sym.get("note"):
                    body += f"\n{sym['note']}"
                notify(title, body, "chart_with_upwards_trend" if buy else "chart_with_downwards_trend")
                print("SIGNAL", title, "|", body.replace("\n", " | "), flush=True)
            else:
                title = f"✅ {'BUY' if ev['d'] == 1 else 'SELL'} rempli {name} {tf}"
                notify(title, f"Exécuté à {ev['e']:.{d}f} · SL {ev['sl']:.{d}f} · TP {ev['tp']:.{d}f}\nBougie de {local}", "white_check_mark", "default")
    return changed


def main():
    if "--test" in sys.argv:
        notify("✅ Test SMC Pro", "Les notifs SMC Pro arrivent bien sur ce canal.", "white_check_mark")
        return
    state = load_state()
    tf_sec = TF_MIN[CFG["timeframe"]] * 60
    delay = CFG.get("scan_delay_sec", 60)
    end = time.time() + float(os.getenv("LOOP_MINUTES", "0")) * 60
    while True:
        try:
            if scan(state):
                save_state(state)
        except Exception as e:  # noqa: BLE001
            print("scan KO:", e, flush=True)
        if "--once" in sys.argv:
            break
        # scan à clôture + 60 s puis + 5 min (rattrape les flux Yahoo en retard)
        base = time.time() // tf_sec * tf_sec
        cands = [base + o for o in (delay, 300)] + [base + tf_sec + delay]
        nxt = min(c for c in cands if c > time.time() + 1)
        if nxt > end:
            break
        time.sleep(max(1, nxt - time.time()))


if __name__ == "__main__":
    main()
