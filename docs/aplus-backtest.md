# Setup A+ crypto — backtest (18 nov 2026)

Code : `backtests/aplus/` (données Binance USDT-M, nov 2023 → oct 2026, frais 0,05 %/côté).

- **15 min** (12 perps, 24 variantes) : toutes négatives sur 2023-25, aucune positive sur les deux périodes.
- **1h, version retenue** (tendance de fond + CHoCH 7h-20h UTC + TP liquidité opposée ≥ 2R) :

| | trades | R/trade | winrate | PF |
|---|---|---|---|---|
| 12 perps 2023-25 | 32 | +0,23 | 38 % | 1,36 |
| 12 perps 2025-26 | 28 | +0,11 | 36 % | 1,16 |
| 16 perps jamais vus | 62 | +0,13 | 37 % | 1,19 |
| **Total 28 perps** | **122** | **+0,15** | **37 %** | **1,23** |

Gain moyen +2,2 R, perte -1,06 R, pire série 10 pertes, t-stat 0,94 (pas significatif).
Sans les filtres : -0,08 R/trade. → À utiliser comme alertes + journal, pas comme bot automatique.
Le moteur live (`aplus_engine.py`) sort exactement les mêmes 122 trades que le backtest.
