# Backtest « OB 5 étoiles » (Kasper) — crypto perps

12 perps (BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, LTC, SUI, HYPE), nov 2023 → oct 2026, frais 0,05 %/côté.
Étoiles 1 (imbalance) et 4 (OB vierge) obligatoires ; 2 = Supertrend stable ≥10 bougies ; 3 = pas de liquidité ≤1 ATR derrière ; 5 = discount/premium (range 100 bougies).
Entrée limite au bord de l'OB, SL de l'autre côté de l'OB.

| TF | Filtre | n | WR 1R | WR 2R | Exp 2R |
|---|---|---|---|---|---|
| 15m | ≥4 ét. | 31987 | 47,6 % | 32,5 % | −0,30R |
| 1h | ≥4 ét. | 7536 | 48,2 % | 33,4 % | −0,13R |
| 1h | 5 ét. | 437 | 46,7 % | 35,2 % | −0,10R |
| 4h | 5 ét. | 137 | 51,8 % | 35,0 % | −0,01R |

Sans frais, 1h 5 étoiles en 2R = +0,06R. Les étoiles améliorent un peu (+2-3 pts de WR) mais on est loin des 70 % annoncés. Verdict : pas d'avantage exploitable seul.

## V2 — règles exactes de la vidéo, sans frais (`backtests/ob5/ob5k.py`)
OB = bougie 1 du FVG (bougie 1 ne touche pas bougie 3), Supertrend(10,3) sans range, liquidité non prise ≤2 ATR derrière, OB vierge, OB entier en premium/discount (Fibo haut/bas de marché). Entrée à la clôture de la 1re bougie de réaction dans l'OB, SL derrière l'OB, TP 2R.

| TF | Règle ≥4 ét. n | WR 2R | Exp 2R | 5 ét. n | WR 2R | Exp 2R |
|---|---|---|---|---|---|---|
| 15m | 12276 | 32,6 % | −0,02R | 725 | 34,6 % | +0,04R |
| 1h | 2930 | 33,6 % | +0,01R | 195 | 35,9 % | +0,08R |
| 4h | 739 | 34,1 % | +0,02R | 61 | 42,6 % | +0,28R |

Seuil de rentabilité à 2R = 33,3 %. Verdict : ≈ break-even sans frais ; seul le 5 étoiles 4h sort du lot, mais sur 61 trades.
