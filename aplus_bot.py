"""Alertes A+ crypto -> ntfy / Telegram.

Chaque heure, juste après la clôture de la bougie 1h : scanne tous les perps USDT (Bitget, prix ≈ Bybit/Hyro),
fait tourner le moteur A+ (aplus_engine.py, identique au backtest) et envoie une notif pour chaque
nouvel ordre limite à placer (entrée, SL, TP, R, taille pour ton risque).

Usage : python aplus_bot.py           (un scan, envoie les alertes)
        python aplus_bot.py --dry     (un scan, affiche sans envoyer ni sauver)
        python aplus_bot.py --test    (notif de test)
"""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yaml

from aplus_engine import scan

ROOT = Path(__file__).parent
CFG = yaml.safe_load((ROOT / "aplus_config.yml").read_text(encoding="utf-8"))
STATE_FILE = ROOT / "aplus_state.json"
API = "https://api.bitget.com/api/v2/mix/market"
TF_MS = 3_600_000
S = requests.Session()


# ---------- données ----------
def get(url, params, tries=4):
    for k in range(tries):
        try:
            r = S.get(url, params=params, timeout=15)
            if r.status_code == 429:
                time.sleep(1 + k); continue
            j = r.json()
            if j.get("code") == "00000":
                return j["data"]
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5 + k)
    return None


def universe():
    contracts = get(f"{API}/contracts", {"productType": "USDT-FUTURES"}) or []
    ok = {c["symbol"] for c in contracts if c.get("symbolStatus") == "normal"}
    vol = {t["symbol"]: float(t.get("usdtVolume") or 0) for t in (get(f"{API}/tickers", {"productType": "USDT-FUTURES"}) or [])}
    wl = ROOT / CFG.get("whitelist_file", "aplus_symbols.txt")
    if wl.exists():
        names = {s.strip().upper().replace("/", "").replace("-", "") for s in wl.read_text().split() if s.strip()}
        names = {n if n.endswith("USDT") else n + "USDT" for n in names}
        if names:
            ok &= names
    syms = [s for s in ok if vol.get(s, 0) >= CFG.get("min_volume_24h_usdt", 0)]
    return sorted(syms), vol


def candles(sym, now_ms):
    data = get(f"{API}/candles", {"symbol": sym, "productType": "USDT-FUTURES",
                                  "granularity": CFG.get("timeframe", "1H"), "limit": 1000})
    if not data:
        return None
    d = pd.DataFrame([r[:5] for r in data], columns=["t", "o", "h", "l", "c"]).astype(float)
    d = d[d.t + TF_MS <= now_ms]                      # bougies fermées uniquement
    d = d.drop_duplicates("t").sort_values("t")
    d["t"] = pd.to_datetime(d.t.astype("int64"), unit="ms", utc=True)
    return d if len(d) >= 300 else None


# ---------- notifications ----------
def notify(title, body, tags, priority="high"):
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


def fmt(x):
    if x >= 1000: return f"{x:,.1f}".replace(",", " ")
    if x >= 1: return f"{x:.4f}".rstrip("0").rstrip(".")
    return f"{x:.6g}"


def fqty(q):
    if q >= 1000: return f"{q:,.0f}".replace(",", " ")
    if q >= 1: return f"{q:.2f}".rstrip("0").rstrip(".")
    return f"{q:.4g}"


def message(sym, side, entry, sl, tp, t_sig, vol24):
    risk = abs(entry - sl)
    rr = abs(tp - entry) / risk
    qty = CFG["risk_usd"] / risk
    notional = qty * entry
    lev = CFG.get("leverage", 5)
    base = sym[:-4]
    sens = "LONG" if side == 1 else "SHORT"
    ordre = "BUY LIMIT" if side == 1 else "SELL LIMIT"
    paris = t_sig.tz_convert("Europe/Paris")
    title = f"A+ {sens} {base} – {ordre}"
    body = (f"Entrée {fmt(entry)} (limite)\n"
            f"SL {fmt(sl)} · TP {fmt(tp)} ({rr:.1f}R)\n"
            f"Taille pour {CFG['risk_usd']} $ : {fqty(qty)} {base} (~{notional:,.0f} $)".replace(",", " ") + "\n"
            f"Levier x{lev} → marge ~{notional / lev:,.0f} $".replace(",", " ") + "\n"
            f"Valable {CFG.get('order_valid_hours', 16)} h, s'annule si le TP est touché avant\n"
            f"Signal : clôture 1h de {paris:%d/%m %Hh%M} (Paris) · vol 24h {vol24 / 1e6:.1f} M$\n"
            f"Vérifie le prix sur Hyro (Bitget ≈ Bybit) et place SL + TP avec l'ordre.")
    return title, body, ("green_circle" if side == 1 else "red_circle")


# ---------- état ----------
def load_state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(st):
    STATE_FILE.write_text(json.dumps(dict(sorted(st.items())), indent=1))
    if os.getenv("GITHUB_ACTIONS"):
        subprocess.run("git add aplus_state.json && (git diff --cached --quiet || "
                       "(git commit -qm aplus-state && git pull -q --rebase && git push -q))", shell=True, check=False)


# ---------- scan ----------
def run_once(dry=False):
    now_ms = int(time.time() * 1000)
    syms, vol = universe()
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · {len(syms)} perps")
    with ThreadPoolExecutor(8) as ex:
        data = dict(zip(syms, ex.map(lambda s: candles(s, now_ms), syms)))
    state = load_state()
    max_age = CFG.get("max_signal_age_bars", 2)
    n_alert = n_ok = 0
    for sym, d in data.items():
        if d is None:
            continue
        n_ok += 1
        try:
            x, _, setups = scan(d, use_bias=CFG["use_bias"], use_sess=CFG["use_session"], min_rr=CFG["min_rr"], adjust=True)
        except Exception as e:  # noqa: BLE001
            print(sym, "erreur moteur:", e); continue
        n = len(x["c"])
        for side, i_sig, entry, sl, tp, issue in setups:
            i_sig = int(i_sig)
            if issue != 0 or i_sig < n - 1 - max_age:     # ordre déjà rempli/annulé ou trop vieux
                continue
            t_sig = x["t"].iloc[i_sig]
            key = f"{sym}"
            if state.get(key, "") >= str(t_sig):
                continue
            title, body, tags = message(sym, int(side), entry, sl, tp, t_sig, vol.get(sym, 0))
            print("ALERTE", title, "|", body.replace("\n", " | "))
            if not dry:
                notify(title, body, tags)
                state[key] = str(t_sig)
            n_alert += 1
    print(f"{n_ok} perps analysés · {n_alert} alerte(s)")
    if not dry:
        save_state(state)


if __name__ == "__main__":
    if "--test" in sys.argv:
        notify("A+ crypto – test", "Les alertes A+ arrivent bien sur ce canal ✅\n(1 scan par heure, tous les perps USDT)",
               "white_check_mark")
    else:
        run_once(dry="--dry" in sys.argv)
