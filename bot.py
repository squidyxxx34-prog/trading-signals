"""Universal Confluence Pro v4 -> alertes ntfy / Telegram.
Reproduit l'indicateur Pine en Python et notifie à la clôture de bougie.
"""
import json
import os
import sys
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

TF_MIN = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "1h": 60, "1d": 1440}


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


# ---------- données ----------
def fetch(ticker, interval, period):
    df = yf.download(ticker, interval=interval, period=period, progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


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
    h_close = htf_df["Close"].shift(1)
    h_ema = ema(htf_df["Close"], p["htf_ema_len"]).shift(1)
    h = pd.DataFrame({"hc": h_close, "he": h_ema})
    h = h.reindex(h.index.union(df.index)).ffill().reindex(df.index)

    adx_ok = adx >= p["min_adx"]
    out["long"] = ((e_fast > e_slow).astype(int) + (c > e_slow).astype(int) + (r > 50).astype(int)
                   + (macd > sig).astype(int) + (adx_ok & (pdi > mdi)).astype(int) + (h["hc"] > h["he"]).astype(int))
    out["short"] = ((e_fast < e_slow).astype(int) + (c < e_slow).astype(int) + (r < 50).astype(int)
                    + (macd < sig).astype(int) + (adx_ok & (mdi > pdi)).astype(int) + (h["hc"] < h["he"]).astype(int))
    out["close"] = c
    out["atr"] = atr
    return out


# ---------- notifications ----------
def notify(title, body, tags):
    sent = False
    topic = os.getenv("NTFY_TOPIC") or CFG.get("ntfy_topic")
    if topic:
        requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                      headers={"Title": title.encode("utf-8"), "Tags": tags, "Priority": "high"}, timeout=15)
        sent = True
    tok, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if tok and chat:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": f"{title}\n\n{body}"}, timeout=15)
        sent = True
    if not sent:
        print("[aucun canal configuré]", title, body)


def fmt(x, dec):
    return f"{x:.{dec}f}"


def main():
    p = CFG["params"]
    tf, htf = CFG["timeframe"], CFG["htf"]
    tf_min = TF_MIN[tf]
    now = pd.Timestamp(datetime.now(timezone.utc))
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    risk_money = CFG["capital"] * CFG["risk_pct"] / 100
    test = "--test" in sys.argv

    if test:
        notify("✅ Test Confluence Pro", "Les alertes arrivent bien sur ce canal.", "white_check_mark")
        return

    for sym in CFG["symbols"]:
        name, ticker = sym["name"], sym["ticker"]
        try:
            df = fetch(ticker, tf, "59d")
            hdf = fetch(ticker, htf, "729d")
        except Exception as e:  # noqa: BLE001
            print(f"{name}: erreur data {e}")
            continue
        if len(df) < p["slow_len"] + 50:
            print(f"{name}: pas assez de données")
            continue

        # barstate.isconfirmed : on ignore la bougie en cours
        closed = df[df.index + pd.Timedelta(minutes=tf_min) <= now]
        res = compute(closed, hdf, p)
        last_key = state.get(name)
        ms = p["min_score"]

        # on regarde les dernières bougies clôturées pas encore traitées (cron GitHub parfois en retard)
        for ts in res.index[-4:]:
            if last_key and str(ts) <= last_key:
                continue
            i = res.index.get_loc(ts)
            row, prev = res.iloc[i], res.iloc[i - 1]
            is_long = row["long"] >= ms and prev["long"] < ms
            is_short = row["short"] >= ms and prev["short"] < ms
            state[name] = str(ts)
            if not (is_long or is_short):
                continue

            stop = row["atr"] * p["atr_mult"]
            entry = row["close"]
            sl = entry - stop if is_long else entry + stop
            tp = entry + 2 * stop if is_long else entry - 2 * stop
            risk_per_lot = stop * sym["point_value"] * sym.get("units_per_lot", 1) * sym.get("currency_rate", 1)
            lots = risk_money / risk_per_lot if risk_per_lot > 0 else float("nan")
            dec = sym.get("decimals", 5)
            score = int(row["long"] if is_long else row["short"])
            side = "▲ BUY" if is_long else "▼ SELL"
            local = ts.tz_convert(CFG.get("timezone", "Europe/Paris")).strftime("%d/%m %H:%M")

            title = f"{side} {name} • {score}/6"
            body = (f"Entrée ~ {fmt(entry, dec)}\n"
                    f"SL {fmt(sl, dec)}\n"
                    f"TP {fmt(tp, dec)}  (R:R 1:2)\n"
                    f"Lots {lots:.2f}  (risque {risk_money:.0f}€)\n"
                    f"Bougie {tf} clôturée {local}")
            notify(title, body, "chart_with_upwards_trend" if is_long else "chart_with_downwards_trend")
            print("SIGNAL", title, body.replace("\n", " | "))

    STATE_FILE.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
