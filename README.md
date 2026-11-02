# Confluence Alerts

Ton indicateur **Universal Confluence Pro v4** recalculé en Python : BUY/SELL + SL/TP/lots envoyés sur ntfy/Telegram **~20 s après chaque clôture de bougie 15m**.

**Univers (26 actifs)** : or · 10 indices (US500, US100, US30, US2000, GER40, FRA40, EU50, UK100, JP225, HK50) · 15 actions US du moment (plus gros volumes du jour, mises à jour chaque jour).

Gratuit : boucle continue sur GitHub Actions (repo public = minutes illimitées).

## Activer (1 min)
1. Repo → **Settings → Secrets and variables → Actions → New repository secret** : `NTFY_TOPIC` = ton topic secret.
2. App **ntfy** → *Subscribe to topic* → ce même topic.
3. **Actions** → *Confluence alerts* → *Run workflow* → coche **test** → notif reçue ✅
4. *Run workflow* sans cocher test → la boucle démarre, puis le cron horaire la relance tout seul.

## Telegram (optionnel)
1. @BotFather → `/newbot` → token.
2. Écris à ton bot, ouvre `https://api.telegram.org/bot<TOKEN>/getUpdates` → `chat.id`.
3. Secrets : `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`.

## Réglages (`config.yml`)
Capital, risque, timeframe, indices, nb d'actions, paramètres de l'indicateur.
`point_value` = taille de contrat MT5 **de ton broker** → vérifie-la, sinon les lots sont faux.

## Limites
- Données Yahoo : l'or (GC=F, futures) et certains indices hors US arrivent avec du retard → 2e scan 5 min après la clôture pour les rattraper. Un signal de plus de 30 min est ignoré.
- Prix Yahoo ≠ prix de ton broker (surtout l'or futures vs spot) : SL/TP = distances ATR, recalcule-les depuis ton entrée réelle sur MT5.
