"""Universal Confluence Pro v4 -> alertes ntfy / Telegram.
Reproduit l'indicateur Pine en Python. Mode boucle : scan ~20 s après chaque clôture de bougie.
Usage : python bot.py            (boucle, durée = LOOP_MINUTES)
        python bot.py --once     (un seul scan)
        python bot.py --test     (notif de test)
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yaml
import yfinance as yf

ROOT = Path(__file__).parent
CFG = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
STATE_FILE = ROOT / "state.json"
TF_MIN = {"5m": 5, "15m": 15, "30m": 30, "60m": 60, "1h": 60}


# ---------- indicateurs (mêmes formules que TradingView) ----------
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rma(s, n):
    return s.ewm(alpha=1 / n, adjust=False).mean()


def rsi(close, n):
    d = close.diff()
    up = rma(d.clip(lower=0), n)
    dn = rma((-d).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def true_range(df):
    pc = df["Close"].shift(1)
    return pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)


def dmi(df, di_len, adx_len):
    up = df["High"].diff()
    dn = -df["Low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = rma(true_range(df), di_len)
    pdi = 100 * rma(pd.Series(plus_dm, index=df.index), di_len) / tr
    mdi = 100 * rma(pd.Series(minus_dm, index=df.index), di_len) / tr
    s = (pdi + mdi).replace(0, np.nan)
    adx = 100 * rma((pdi - mdi).abs() / s, adx_len)
    return pdi, mdi, adx


def compute(df, htf_df, p):
    out = pd.DataFrame(index=df.index)
    c = df["Close"]
    e_fast, e_slow = ema(c, p["fast_len"]), ema(c, p["slow_len"])
    r = rsi(c, p["rsi_len"])
    macd = ema(c, 12) - ema(c, 26)
    sig = ema(macd, 9)
    pdi, mdi, adx = dmi(df, p["adx_len"], p["adx_smooth"])
    atr = rma(true_range(df), p["atr_len"])

    # request.security(close[1], lookahead_on) = clôture de la bougie HTF précédente
    h = pd.DataFrame({"hc": htf_df["Close"].shift(1), "he": ema(htf_df["Close"], p["htf_ema_len"]).shift(1)})
    h = h.reindex(h.index.union(df.index)).ffill().reindex(df.index)

    adx_ok = adx >= p["min_adx"]
    out["long"] = ((e_fast > e_slow).astype(int) + (c > e_slow).astype(int) + (r > 50).astype(int)
                   + (macd > sig).astype(int) + (adx_ok & (pdi > mdi)).astype(int) + (h["hc"] > h["he"]).astype(int))
    out["short"] = ((e_fast < e_slow).astype(int) + (c < e_slow).astype(int) + (r < 50).astype(int)
                    + (macd < sig).astype(int) + (adx_ok & (mdi > pdi)).astype(int) + (h["hc"] < h["he"]).astype(int))
    out["close"] = c
    out["atr"] = atr
    return out


# ---------- univers ----------
def hot_stocks(n, min_price):
    """Actions US du moment = plus gros volumes du jour (screener Yahoo)."""
    try:
        res = yf.screen("most_actives", count=60)
        quotes = res.get("quotes", [])
        picks = [q["symbol"] for q in quotes
                 if q.get("regularMarketPrice", 0) >= min_price and q.get("quoteType") == "EQUITY"
                 and "." not in q["symbol"]]
        if len(picks) >= n:
            return picks[:n]
    except Exception as e:  # noqa: BLE001
        print("screener KO:", e)
    return CFG["stocks"]["fallback"][:n]


def universe():
    syms = [dict(s, group="or") for s in CFG["gold"]] + [dict(s, group="indice") for s in CFG["indices"]]
    st = CFG["stocks"]
    for t in hot_stocks(st["count"], st["min_price"]):
        syms.append({"name": t, "ticker": t, "point_value": st["point_value"],
                     "currency_rate": st["currency_rate"], "decimals": 2, "group": "action"})
    return syms


# ---------- données ----------
def download(tickers, interval, period):
    data = yf.download(tickers, interval=interval, period=period, progress=False,
                       auto_adjust=False, group_by="ticker", threads=True)
    out = {}
    for t in tickers:
        try:
            df = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
            df.index = pd.to_datetime(df.index, utc=True)
            out[t] = df
        except Exception:  # noqa: BLE001
            pass
    return out


# ---------- notifications ----------
def notify(title, body, tags):
    sent = False
    topic = os.getenv("NTFY_TOPIC")
    if topic:
        try:
            requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                          headers={"Title": title.encode("utf-8"), "Tags": tags, "Priority": "high"}, timeout=15)
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
        print("[aucun canal configuré]", title, body)


# ---------- scan ----------
def load_state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))
    if os.getenv("GITHUB_ACTIONS"):
        subprocess.run("git add state.json && (git diff --cached --quiet || "
                       "(git commit -qm state && git pull -q --rebase && git push -q))", shell=True, check=False)


def scan(syms, state):
    p = CFG["params"]
    tf, htf = CFG["timeframe"], CFG["htf"]
    tf_min = TF_MIN[tf]
    now = pd.Timestamp(datetime.now(timezone.utc))
    risk_money = CFG["capital"] * CFG["risk_pct"] / 100
    tickers = [s["ticker"] for s in syms]
    ltf, hft = download(tickers, tf, "59d"), download(tickers, htf, "180d")
    changed = False

    for sym in syms:
        name, t = sym["name"], sym["ticker"]
        df, hdf = ltf.get(t), hft.get(t)
        if df is None or hdf is None or len(df) < p["slow_len"] + 50:
            continue
        closed = df[df.index + pd.Timedelta(minutes=tf_min) <= now]   # barstate.isconfirmed
        if closed.empty:
            continue
        res = compute(closed, hdf, p)
        last = state.get(name)
        if last is None:                       # 1er passage : on mémorise sans alerter l'historique
            state[name] = str(res.index[-1])
            changed = True
            continue
        ms = p["min_score"]
        for ts in res.index[-4:]:
            if str(ts) <= last:
                continue
            i = res.index.get_loc(ts)
            row, prev = res.iloc[i], res.iloc[i - 1]
            state[name] = str(ts)
            changed = True
            is_long = row["long"] >= ms and prev["long"] < ms
            is_short = row["short"] >= ms and prev["short"] < ms
            if not (is_long or is_short):
                continue
            age = (now - (ts + pd.Timedelta(minutes=tf_min))).total_seconds() / 60
            if age > CFG.get("max_signal_age_min", 20):   # signal trop vieux -> plus exploitable
                print(f"skip {name} {ts} (vieux de {age:.0f} min)")
                continue
            stop = row["atr"] * p["atr_mult"]
            entry = row["close"]
            sl = entry - stop if is_long else entry + stop
            tp = entry + 2 * stop if is_long else entry - 2 * stop
            rpl = stop * sym["point_value"] * sym.get("units_per_lot", 1) * sym.get("currency_rate", 1)
            lots = risk_money / rpl if rpl > 0 else float("nan")
            d = sym.get("decimals", 2)
            score = int(row["long"] if is_long else row["short"])
            side = "▲ BUY" if is_long else "▼ SELL"
            local = ts.tz_convert(CFG["timezone"]).strftime("%d/%m %H:%M")
            title = f"{side} {name} • {score}/6"
            body = (f"Entrée ~ {entry:.{d}f}\nSL {sl:.{d}f}\nTP {tp:.{d}f}  (R:R 1:2)\n"
                    f"Lots {lots:.2f}  (risque {risk_money:.0f}€)\n"
                    f"{sym['group']} • bougie {tf} clôturée {local}")
            notify(title, body, "chart_with_upwards_trend" if is_long else "chart_with_downwards_trend")
            print("SIGNAL", title, "|", body.replace("\n", " | "), flush=True)
    return changed


def main():
    if "--test" in sys.argv:
        notify("✅ Test Confluence Pro", "Les alertes arrivent bien sur ce canal.", "white_check_mark")
        return
    state = load_state()
    tf_sec = TF_MIN[CFG["timeframe"]] * 60
    delay = CFG.get("scan_delay_sec", 20)
    end = time.time() + float(os.getenv("LOOP_MINUTES", "0")) * 60
    syms, syms_day = None, None

    while True:
        today = datetime.now(timezone.utc).date()
        if syms is None or syms_day != today:          # rafraîchit les actions du moment 1x/jour
            syms, syms_day = universe(), today
            print("Univers:", ", ".join(s["name"] for s in syms), flush=True)
        try:
            if scan(syms, state):
                save_state(state)
        except Exception as e:  # noqa: BLE001
            print("scan KO:", e, flush=True)
        if "--once" in sys.argv:
            break
        # scans à clôture + 20 s, puis clôture + 5 min (rattrape les flux Yahoo en retard : or, indices hors US)
        base = time.time() // tf_sec * tf_sec
        cands = [base + o for o in (delay, 300)] + [base + tf_sec + delay]
        nxt = min(c for c in cands if c > time.time() + 1)
        if nxt > end:
            break
        time.sleep(max(1, nxt - time.time()))


if __name__ == "__main__":
    main()
