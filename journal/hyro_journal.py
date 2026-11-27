"""Journal de trading auto pour HyroTrader (comptes Bybit).

Deux sources possibles :
  1. API Bybit (clé LECTURE SEULE) :  python hyro_journal.py --days 30
     -> variables d'env BYBIT_KEY / BYBIT_SECRET (et BYBIT_URL si besoin)
  2. Export CSV (Closed P&L Bybit / historique Hyro) :  python hyro_journal.py --csv export.csv

Sorties (dossier du script) :
  journal.csv  : tous les trades (dédoublonnés, cumulés d'un lancement à l'autre)
  notes.csv    : tes colonnes à remplir à la main (setup, étoiles, commentaire) — jamais écrasées
  journal.html : tableau + stats + courbe d'équité, PnL NET FINAL en gros

PnL net = PnL clôturé Bybit (déjà frais d'ouverture/fermeture déduits) + funding.
"""
import argparse, csv, hashlib, hmac, html, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
JOURNAL, NOTES, HTML = HERE / "journal.csv", HERE / "notes.csv", HERE / "journal.html"
COLS = ["id", "date", "symbol", "side", "qty", "entry", "exit", "gross", "fees", "funding", "net"]
NOTE_COLS = ["id", "setup", "etoiles", "commentaire"]


# ---------------- API Bybit v5 ----------------
def bybit_get(path, params, key, secret, base):
    ts, rw = str(int(time.time() * 1000)), "10000"
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    sign = hmac.new(secret.encode(), (ts + key + rw + qs).encode(), hashlib.sha256).hexdigest()
    h = {"X-BAPI-API-KEY": key, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": rw, "X-BAPI-SIGN": sign}
    r = requests.get(f"{base}{path}?{qs}", headers=h, timeout=20).json()
    if r.get("retCode") != 0:
        sys.exit(f"Erreur Bybit {path}: {r.get('retMsg')}")
    return r["result"]


def paged(path, params, key, secret, base):
    cursor = ""
    while True:
        p = dict(params, **({"cursor": cursor} if cursor else {}))
        res = bybit_get(path, p, key, secret, base)
        yield from res.get("list", [])
        cursor = res.get("nextPageCursor") or ""
        if not cursor:
            break


def from_api(days):
    key, secret = os.getenv("BYBIT_KEY"), os.getenv("BYBIT_SECRET")
    base = os.getenv("BYBIT_URL", "https://api.bybit.com")
    if not key or not secret:
        sys.exit("Mets BYBIT_KEY et BYBIT_SECRET (clé API en lecture seule).")
    now = int(time.time() * 1000)
    week = 7 * 24 * 3600 * 1000  # Bybit limite chaque requête à 7 jours
    trades, funding = [], []
    start = now - days * 24 * 3600 * 1000
    while start < now:
        end = min(start + week, now)
        win = {"category": "linear", "limit": 100, "startTime": start, "endTime": end}
        for t in paged("/v5/position/closed-pnl", win, key, secret, base):
            fees = float(t.get("openFee") or 0) + float(t.get("closeFee") or 0)
            net = float(t["closedPnl"])
            trades.append({
                "id": t["orderId"],
                "date": datetime.fromtimestamp(int(t["updatedTime"]) / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "symbol": t["symbol"],
                # side = sens de l'ordre de CLÔTURE -> Sell = c'était un long
                "side": "LONG" if t["side"] == "Sell" else "SHORT",
                "qty": t["qty"], "entry": t["avgEntryPrice"], "exit": t["avgExitPrice"],
                "gross": round(net + fees, 4), "fees": round(fees, 4), "funding": 0.0, "net": round(net, 4),
            })
        log = dict(win, accountType="UNIFIED", type="SETTLEMENT", limit=50)
        for f in paged("/v5/account/transaction-log", log, key, secret, base):
            funding.append((f.get("symbol"), int(f["transactionTime"]), float(f.get("change") or 0)))
        start = end
    # rattache chaque paiement de funding au trade du même symbole clôturé juste après
    for sym, ts, chg in funding:
        later = [t for t in trades if t["symbol"] == sym and t["date"] >= datetime.fromtimestamp(ts / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")]
        if later:
            t = min(later, key=lambda x: x["date"])
            t["funding"] = round(t["funding"] + chg, 4)
            t["net"] = round(t["net"] + chg, 4)
    return trades


# ---------------- Import CSV ----------------
ALIASES = {
    "symbol": ["contracts", "symbol", "contract", "market", "pair"],
    "side": ["closing direction", "side", "direction", "trade type", "type"],
    "qty": ["qty", "quantity", "size", "amount"],
    "entry": ["entry price", "avg entry", "open price", "entry"],
    "exit": ["exit price", "avg exit", "close price", "exit"],
    "net": ["closed p&l", "closed pnl", "realized pnl", "realised pnl", "pnl", "profit"],
    "fees": ["fee", "fees", "commission"],
    "funding": ["funding"],
    "date": ["trade time", "close time", "time", "date"],
    "id": ["order id", "orderid", "id"],
}


def num(x):
    try:
        return float(str(x).replace(",", "").replace("USDT", "").strip() or 0)
    except ValueError:
        return 0.0


def from_csv(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    if not rows:
        sys.exit("CSV vide.")
    heads = {h.lower().strip(): h for h in rows[0]}

    def cols(field):
        return [heads[h] for h in heads if any(a in h for a in ALIASES[field])]

    out = []
    for i, r in enumerate(rows):
        g = lambda f: r[cols(f)[0]] if cols(f) else ""
        fees = sum(num(r[c]) for c in cols("fees") if "funding" not in c.lower())
        fund = sum(num(r[c]) for c in cols("funding"))
        net = num(g("net"))
        side = g("side").lower()
        out.append({
            "id": g("id") or hashlib.md5(str(r).encode()).hexdigest()[:12],
            "date": g("date")[:16], "symbol": g("symbol"),
            "side": "LONG" if ("long" in side or "sell" in side) else "SHORT",
            "qty": g("qty"), "entry": g("entry"), "exit": g("exit"),
            "gross": round(net + abs(fees), 4), "fees": round(abs(fees), 4),
            "funding": round(fund, 4), "net": round(net + fund, 4),
        })
    return out


# ---------------- Journal + rendu ----------------
def load(p, cols):
    return {r["id"]: r for r in csv.DictReader(open(p, encoding="utf-8"))} if p.exists() else {}


def save(p, cols, rows):
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def render(trades, notes, risk):
    trades = sorted(trades, key=lambda t: t["date"])
    nets = [float(t["net"]) for t in trades]
    wins = [x for x in nets if x > 0]
    net_total = sum(nets)
    fees = sum(float(t["fees"]) for t in trades)
    fund = sum(float(t["funding"]) for t in trades)
    wr = 100 * len(wins) / len(nets) if nets else 0
    loss = -sum(x for x in nets if x < 0)
    pf = (sum(wins) / loss) if loss else float("inf")
    eq, curve = 0, []
    for x in nets:
        eq += x
        curve.append(eq)
    # courbe d'équité SVG
    W, H = 760, 180
    pts = ""
    if curve:
        lo, hi = min(0, *curve), max(0, *curve)
        span = (hi - lo) or 1
        pts = " ".join(f"{20 + i * (W - 40) / max(1, len(curve) - 1):.1f},{H - 15 - (v - lo) / span * (H - 30):.1f}" for i, v in enumerate(curve))
    col = "#26a69a" if net_total >= 0 else "#ef5350"
    rows = ""
    for t in reversed(trades):
        n = notes.get(t["id"], {})
        r = f"{float(t['net']) / risk:+.2f}R" if risk else ""
        c = "#26a69a" if float(t["net"]) >= 0 else "#ef5350"
        rows += (f"<tr><td>{t['date']}</td><td>{t['symbol']}</td><td>{t['side']}</td><td>{t['qty']}</td>"
                 f"<td>{t['entry']}</td><td>{t['exit']}</td><td>{float(t['fees']):.2f}</td><td>{float(t['funding']):.2f}</td>"
                 f"<td style='color:{c};font-weight:600'>{float(t['net']):+.2f}</td><td>{r}</td>"
                 f"<td>{html.escape(n.get('setup', ''))}</td><td>{html.escape(n.get('etoiles', ''))}</td>"
                 f"<td>{html.escape(n.get('commentaire', ''))}</td></tr>")
    page = f"""<!DOCTYPE html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Journal Hyro</title><style>
body{{background:#131722;color:#d1d4dc;font-family:system-ui;margin:16px}}
.big{{font-size:44px;font-weight:700;color:{col}}}.k{{display:inline-block;margin:6px 18px 6px 0}}
.k b{{display:block;font-size:20px}}table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:14px}}
td,th{{border-bottom:1px solid #2a2e39;padding:6px;text-align:left;white-space:nowrap}}th{{color:#787b86}}
.wrap{{overflow-x:auto}}</style>
<h2>Journal HyroTrader</h2><div>PnL NET FINAL</div><div class="big">{net_total:+.2f} $</div>
<div class="k">Trades<b>{len(nets)}</b></div><div class="k">Winrate<b>{wr:.0f} %</b></div>
<div class="k">Profit factor<b>{pf:.2f}</b></div><div class="k">Frais<b>-{fees:.2f} $</b></div>
<div class="k">Funding<b>{fund:+.2f} $</b></div>
<svg width="100%" viewBox="0 0 {W} {H}" style="background:#1e222d;border-radius:8px;margin-top:10px">
<polyline fill="none" stroke="{col}" stroke-width="2" points="{pts}"/></svg>
<div class="wrap"><table><tr><th>Date (UTC)</th><th>Actif</th><th>Sens</th><th>Qté</th><th>Entrée</th><th>Sortie</th>
<th>Frais</th><th>Funding</th><th>Net $</th><th>R</th><th>Setup</th><th>Étoiles</th><th>Commentaire</th></tr>{rows}</table></div>
<p style="color:#787b86">Mis à jour {datetime.now().strftime('%d/%m/%Y %H:%M')}</p></html>"""
    HTML.write_text(page, encoding="utf-8")
    return net_total, len(nets), wr, fees, fund


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="importer un export CSV au lieu de l'API")
    ap.add_argument("--days", type=int, default=30, help="historique API (jours)")
    ap.add_argument("--risk", type=float, default=25, help="risque par trade en $ (pour la colonne R)")
    a = ap.parse_args()
    new = from_csv(a.csv) if a.csv else from_api(a.days)
    journal = load(JOURNAL, COLS)
    for t in new:
        journal[t["id"]] = t
    trades = list(journal.values())
    save(JOURNAL, COLS, sorted(trades, key=lambda t: t["date"]))
    notes = load(NOTES, NOTE_COLS)
    for t in trades:
        notes.setdefault(t["id"], {"id": t["id"], "setup": "", "etoiles": "", "commentaire": ""})
    save(NOTES, NOTE_COLS, list(notes.values()))
    net, n, wr, fees, fund = render(trades, notes, a.risk)
    print(f"{n} trades | winrate {wr:.0f}% | frais -{fees:.2f} $ | funding {fund:+.2f} $")
    print(f"PnL NET FINAL : {net:+.2f} $")
    print(f"-> {HTML}")


if __name__ == "__main__":
    main()
