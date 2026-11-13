//+------------------------------------------------------------------+
//| RSI2_Indices.mq5 - Connors RSI-2 (journalier) pour le testeur MT5 |
//| Achat : clôture > SMA200 et RSI(2) < 10 · Sortie : clôture > SMA5 |
//| ou 10 bougies · Stop : 2 x ATR(14). Backtest python 2022-26 sur   |
//| US500/NAS100/US30/GER40 : 70 % gagnants, PF 1,8 (frais inclus).   |
//| À tester sur le graphique D1 d'un indice.                         |
//+------------------------------------------------------------------+
#property copyright "Maxence"
#property version   "1.00"
#include <Trade\Trade.mqh>

input int    InpRsiLen   = 2;      // RSI : période
input double InpBuyLvl   = 10;     // Achat si RSI <
input double InpSellLvl  = 90;     // Vente si RSI > (si ventes activées)
input bool   InpShorts   = false;  // Autoriser les ventes (perdantes en backtest)
input int    InpTrend    = 200;    // Filtre tendance : SMA
input int    InpExitMa   = 5;      // Sortie : SMA
input int    InpMaxHold  = 10;     // Sortie au temps (bougies)
input double InpSlAtr    = 2.0;    // Stop = x ATR(14)
input double InpRiskPct  = 0.5;    // Risque par trade (% du solde)
input long   InpMagic    = 240213; // Numéro magique

CTrade trade;
int hRsi, hTrend, hExit, hAtr;
datetime lastBar = 0;

int OnInit()
{
   hRsi   = iRSI(_Symbol, _Period, InpRsiLen, PRICE_CLOSE);
   hTrend = iMA(_Symbol, _Period, InpTrend, 0, MODE_SMA, PRICE_CLOSE);
   hExit  = iMA(_Symbol, _Period, InpExitMa, 0, MODE_SMA, PRICE_CLOSE);
   hAtr   = iATR(_Symbol, _Period, 14);
   if(hRsi == INVALID_HANDLE || hTrend == INVALID_HANDLE || hExit == INVALID_HANDLE || hAtr == INVALID_HANDLE)
      return INIT_FAILED;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(50);
   return INIT_SUCCEEDED;
}

double Val(int h, int shift)
{
   double b[1];
   if(CopyBuffer(h, 0, shift, 1, b) != 1) return EMPTY_VALUE;
   return b[0];
}

bool MyPosition(ulong &ticket, long &type, datetime &opened)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic)
      {
         ticket = t;
         type   = PositionGetInteger(POSITION_TYPE);
         opened = (datetime)PositionGetInteger(POSITION_TIME);
         return true;
      }
   }
   return false;
}

double LotsFor(ENUM_ORDER_TYPE type, double price, double sl)
{
   double loss1 = 0;
   if(!OrderCalcProfit(type, _Symbol, 1.0, price, sl, loss1) || loss1 == 0) return 0;
   double risk = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPct / 100.0;
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double v = MathFloor(risk / MathAbs(loss1) / step) * step;
   if(v < vmin) return 0;
   return MathMin(v, vmax);
}

void OnTick()
{
   datetime bar = iTime(_Symbol, _Period, 0);
   if(bar == lastBar) return;            // une fois par nouvelle bougie
   lastBar = bar;

   double c1   = iClose(_Symbol, _Period, 1);   // dernière bougie CLÔTURÉE
   double rsi  = Val(hRsi, 1);
   double tr   = Val(hTrend, 1);
   double ex   = Val(hExit, 1);
   double atr  = Val(hAtr, 1);
   if(rsi == EMPTY_VALUE || tr == EMPTY_VALUE || ex == EMPTY_VALUE || atr == EMPTY_VALUE) return;

   // 1) sorties
   ulong ticket; long type; datetime opened;
   if(MyPosition(ticket, type, opened))
   {
      int held = iBarShift(_Symbol, _Period, opened);   // bougies depuis l'entrée
      bool exitSig = (type == POSITION_TYPE_BUY && c1 > ex) || (type == POSITION_TYPE_SELL && c1 < ex);
      if(exitSig || held >= InpMaxHold)
         trade.PositionClose(ticket);
      return;
   }

   // 2) entrées
   int side = 0;
   if(c1 > tr && rsi < InpBuyLvl) side = 1;
   else if(InpShorts && c1 < tr && rsi > InpSellLvl) side = -1;
   if(side == 0) return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   int    dg  = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(side == 1)
   {
      double sl  = NormalizeDouble(ask - InpSlAtr * atr, dg);
      double vol = LotsFor(ORDER_TYPE_BUY, ask, sl);
      if(vol > 0) trade.Buy(vol, _Symbol, ask, sl, 0, "RSI2");
   }
   else
   {
      double sl  = NormalizeDouble(bid + InpSlAtr * atr, dg);
      double vol = LotsFor(ORDER_TYPE_SELL, bid, sl);
      if(vol > 0) trade.Sell(vol, _Symbol, bid, sl, 0, "RSI2");
   }
}
//+------------------------------------------------------------------+
