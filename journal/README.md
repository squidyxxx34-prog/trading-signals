# Journal HyroTrader

```
pip install requests
# Option A — API Bybit (clé LECTURE SEULE créée sur le compte Hyro/Bybit)
set BYBIT_KEY=xxx & set BYBIT_SECRET=yyy        (Windows)
python hyro_journal.py --days 30
# Option B — export CSV (Closed P&L)
python hyro_journal.py --csv export.csv
```
Ouvre `journal.html` → PnL NET FINAL (frais + funding déduits), winrate, profit factor, courbe d'équité.
Remplis `notes.csv` (setup, étoiles, commentaire) : relance le script, ça s'affiche dans le tableau.
`--risk 25` = colonne R. Compte démo Bybit : `set BYBIT_URL=https://api-demo.bybit.com`.
