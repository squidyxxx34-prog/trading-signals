# Confluence Alerts

Ton indicateur **Universal Confluence Pro v4** recalculé en Python, qui t'envoie BUY/SELL + SL/TP/lots à chaque clôture de bougie. Gratuit : tourne sur GitHub Actions.

## Activer (1 min)
1. Installe l'app **ntfy** (Android/iOS) → *Subscribe to topic* → `confluence-1aeaec42ca`
2. Onglet **Actions** → *Confluence alerts* → *Run workflow* → coche **test** → tu dois recevoir une notif.
3. Fini : scan 2 min après chaque clôture 15m, 7h–22h (Paris), lun–ven. Reste dans les 2000 min gratuites/mois.

## Telegram (optionnel)
1. @BotFather → `/newbot` → récupère le token.
2. Envoie un message à ton bot, puis ouvre `https://api.telegram.org/bot<TOKEN>/getUpdates` → récupère `chat.id`.
3. Repo → Settings → Secrets → Actions : `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`.

## Réglages
Tout est dans `config.yml` : capital, risque, timeframe, symboles, paramètres de l'indicateur.

## Limites
- Le cron GitHub peut avoir 2–15 min de retard aux heures chargées → alerte parfois en retard. Vérifie toujours le prix sur MT5 avant d'entrer.
- Données Yahoo Finance : léger écart possible avec le flux de ton broker (surtout l'or via GC=F). Les SL/TP sont des distances ATR, recalcule-les depuis ton prix d'entrée réel.
- GitHub désactive les crons d'un repo sans activité 60 jours — ici le commit de `state.json` le garde actif.
