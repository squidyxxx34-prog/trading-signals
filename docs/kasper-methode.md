# Méthode Kasper — synthèse (19 nov 2026)

Sources (transcriptions) : « Comment Identifier les Meilleurs OrderBlocks », « Mon Processus de Prise de Trade de A à Z », « Si tu as seulement 50€… chaque matin », « La Meilleure Stratégie de Scalping pour les Débutants 2026 ».

## 1. Préparation (la « météo »)
1. **Type de marché** : expansion (prix qui part en ligne droite → être rapide) ou range/accumulation (pièges → patient, seulement des setups 5 étoiles).
2. **Liquidité** (concept n°1 pour lui) : equal highs, equal lows, trendlines, haut/bas de session asiatique, derniers plus hauts/plus bas (tracés en 10-15 min). Rôle double : éviter les pièges + objectifs de TP. « Le prix va de poche de liquidité en poche de liquidité. »
3. **Tendance** : 4h puis 15 min. Outils : structure (Dow) ou Ripster EMA Cloud en 1h (clouds 1-2-3), ou Supertrend. On ne trade que dans le sens.
4. **News** : calendrier éco, pas de trade 5 min avant/après. Les meilleurs trades viennent souvent juste APRÈS une grosse news.
5. **Kill zones (heure FR)** : Asie ~0h-2h / 4h-6h, Londres 9h-11h, **US 15h-17h (la plus forte)**. Entre les deux : peu de mouvement (ex. 13h = mort).

## 2. Zones (top-down 4h → 1h → 30m → 15m → 5m → 1m)
### Setup A — OB 5 étoiles
OB = dernière bougie inverse avant un mouvement violent, mèche à mèche. Se cache dans les petits ranges des schémas R-A-E ou E-A-E.
- ⭐1 Imbalance : bougie 1 ne touche pas bougie 3 (éliminatoire)
- ⭐2 Tendance, pas de range, dans le bon sens
- ⭐3 Pas de liquidité non prise derrière l'OB (bonus : OB créé par une prise de liquidité)
- ⭐4 OB vierge (1re touche seulement)
- ⭐5 Fibo haut/bas de marché : OB entier en discount (achat) / premium (vente)
Règle : 4-5 étoiles uniquement. Confluence si l'OB existe sur plusieurs UT.

### Setup B — Scalping OTE (or, 5m/1m)
1. Tendance 1h (EMA Cloud) → que des ventes si rouge, que des achats si vert.
2. Fibo du dernier swing (haut→bas en baisse, bas→haut en hausse). Garder 0 / 0,5 / 0,618 / 0,786 / 1.
3. **OTE = 0,618–0,786**. Réajuster le Fibo à chaque nouveau plus bas/haut.
4. Prix dans l'OTE → bougie de réaction (1m ou 5m) qui ressort de l'OTE dans le sens du trade.
5. Entrée immédiate, SL au-delà de l'OTE (sur le plus haut/bas du swing).
6. TP 1,5R. Objectif +1 %/jour puis on coupe.
Uniquement en kill zone.

## 3. Scénarios
Avant la session : 2 scénarios écrits (quelle liquidité est prise, sur quelle zone ça réagit, quel objectif). Si le marché invalide → on efface et on refait, sans ego.

## 4. Confirmations d'entrée (une suffit)
1. **CHoCH** en petite UT dans la zone.
2. **Mini support/résistance (souvent une imbalance)** formé juste avant, qui casse → entrée.
3. **Clôture d'une bougie dans le sens** (marché très volatil).

## 5. Gestion
- SL juste derrière la zone travaillée (ni pixel, ni énorme).
- TP : poche de liquidité opposée, ou 2R (débutant), 1,5R en scalping OTE.
- BE à +1R, partiels vers +2R.

## Ce qu'on a mesuré
Backtest OB 5 étoiles (règles exactes, sans frais) : ~50 % à 1R, ~33 % à 2R → break-even en crypto 5m et sur l'or (voir `ob5-kasper-backtest.md`). Les 70 % annoncés ne sont pas confirmés.
