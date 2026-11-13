//+------------------------------------------------------------------+
//| Scalper15s_DEMO.mq5 - scalper de 15 secondes, COMPTE DÉMO SEUL    |
//| Entrée : micro-élan (le prix a bougé de X points sur N ticks)     |
//| Sortie : TP / SL en points, ou fermeture forcée après 15 s.       |
//| Plusieurs positions en même temps (MaxPositions).                 |
//| Refuse de démarrer sur un compte réel ou prop.                    |
//| Testeur MT5 : modélisation « Every tick based on real ticks ».    |
//+------------------------------------------------------------------+
#property copyright "Maxence"
#property version   "1.00"
#include <Trade\Trade.mqh>

input double InpLots        = 0.10;   // Lots par position
input int    InpMaxPos      = 5;      // Positions simultanées max
input int    InpHoldSec     = 15;     // Durée max d'une position (secondes)
input int    InpTpPoints    = 30;     // Take profit (points)
input int    InpSlPoints    = 60;     // Stop loss (points)
input int    InpMomTicks    = 5;      // Élan : nombre de ticks regardés
input int    InpMomPoints   = 15;     // Élan : mouvement min (points)
input int    InpMaxSpread   = 30;     // Spread max pour entrer (points)
input int    InpCooldownSec = 2;      // Pause min entre deux entrées (s)
input bool   InpDemoOnly    = true;   // Sécurité : démo uniquement
input long   InpMagic       = 151515; // Numéro magique

CTrade trade;
double   ticks[];
int      nTicks = 0;
datetime lastEntry = 0;

int OnInit()
{
   if(InpDemoOnly && AccountInfoInteger(ACCOUNT_TRADE_MODE) != ACCOUNT_TRADE_MODE_DEMO)
   {
      Alert("Scalper15s : compte NON démo -> arrêt. Ce robot est fait pour la démo uniquement.");
      return INIT_FAILED;
   }
   ArrayResize(ticks, InpMomTicks + 1);
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(20);
   EventSetTimer(1);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   // bilan dans le journal
   HistorySelect(0, TimeCurrent());
   int n = 0, w = 0; double net = 0, gross = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong d = HistoryDealGetTicket(i);
      if(HistoryDealGetInteger(d, DEAL_MAGIC) != InpMagic || HistoryDealGetInteger(d, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;
      double p = HistoryDealGetDouble(d, DEAL_PROFIT);
      double f = HistoryDealGetDouble(d, DEAL_COMMISSION) * 2 + HistoryDealGetDouble(d, DEAL_SWAP);
      n++; if(p + f > 0) w++;
      gross += p; net += p + f;
   }
   PrintFormat("Scalper15s BILAN : %d trades | %.1f %% gagnants | brut %.2f | net (commissions incluses) %.2f",
               n, n ? 100.0 * w / n : 0, gross, net);
}

int MyCount()
{
   int k = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(PositionGetTicket(i) && PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic) k++;
   return k;
}

void CloseOld()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(TimeCurrent() - (datetime)PositionGetInteger(POSITION_TIME) >= InpHoldSec)
         trade.PositionClose(t);
   }
}

void OnTimer() { CloseOld(); }

void OnTick()
{
   CloseOld();

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   // mémorise les derniers ticks
   for(int i = InpMomTicks; i > 0; i--) ticks[i] = ticks[i - 1];
   ticks[0] = bid;
   if(nTicks <= InpMomTicks) { nTicks++; return; }

   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(spread > InpMaxSpread) return;
   if(TimeCurrent() - lastEntry < InpCooldownSec) return;
   if(MyCount() >= InpMaxPos) return;

   double move = (ticks[0] - ticks[InpMomTicks]) / _Point;
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(move >= InpMomPoints)
   {
      if(trade.Buy(InpLots, _Symbol, ask, NormalizeDouble(ask - InpSlPoints * _Point, dg), NormalizeDouble(ask + InpTpPoints * _Point, dg), "scalp15"))
         lastEntry = TimeCurrent();
   }
   else if(move <= -InpMomPoints)
   {
      if(trade.Sell(InpLots, _Symbol, bid, NormalizeDouble(bid + InpSlPoints * _Point, dg), NormalizeDouble(bid - InpTpPoints * _Point, dg), "scalp15"))
         lastEntry = TimeCurrent();
   }
}
//+------------------------------------------------------------------+
