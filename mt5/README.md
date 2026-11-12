# Bot MT5 – Connors RSI-2 (D1)

Stratégie au winrate le plus élevé de nos backtests (≈ 64 % sur 6 majeures, 2012-2022, frais inclus, PF 1.14 hors échantillon).
Avantage mince : gagne souvent, mais la perte moyenne est plus grosse que le gain moyen.

## ⚠️ FundedNext
- Les bots (EA, Python via MT5) exigent l'**add-on EA payant** (comptes 5K-25K). Sans add-on → risque de breach.
- Interdit : HFT, grid, tick scalping, bots reliés à Telegram/WhatsApp (ce bot n'envoie aucune notif).
- Ne fais pas tourner le même bot sur plusieurs comptes FundedNext (détection de trades identiques).

## Setup (Windows)
1. MT5 de FundedNext installé, connecté au compte (démo d'abord).
2. MT5 → Outils → Options → Expert Advisors → cocher **Autoriser le trading algorithmique**. Bouton **Algo Trading** vert.
3. Python 3.11 ou 3.12 **64 bits** (python.org, cocher « Add to PATH »).
4. `pip install -r mt5/requirements.txt`
5. Ouvre `mt5/mt5_bot.py`, vérifie la section CONFIG (laisser `DRY_RUN = True` au début).
6. `python mt5/mt5_bot.py` (MT5 doit rester ouvert, PC allumé, veille désactivée).
7. Après quelques jours en DRY sans erreur → `DRY_RUN = False` sur **démo** 2-4 semaines → puis compte réel.

Démarrage auto : Planificateur de tâches Windows → « À l'ouverture de session » → `python C:\...\mt5\mt5_bot.py`.

Fichiers créés : `mt5_bot.log` (journal), `mt5_state.json` (état).

---

# Bot MT5 – Or M15 · SMC Continuation + filtre tendance 6 mois (`gold_smc_bot.py`)

Même moteur que ton Pine SMC Pro v2 (smc_engine.py), sur XAUUSD M15, uniquement dans le sens d'une tendance 6 mois > 10 %.
Backtest : 2012-22 PF 1.13 (112 trades) · 2022-26 PF 1.47 (200 trades). Piste prometteuse, moins solide que le RSI-2 indices.

Lancer (même setup que plus haut) : `python mt5/gold_smc_bot.py` depuis le dossier `trading-signals` cloné en entier
(le bot importe `smc_engine.py` à la racine). Journal : `mt5/gold_bot.log`.
