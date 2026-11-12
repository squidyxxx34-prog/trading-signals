import numpy as np, pandas as pd
SRC="/home/claude/ejtraderlabs/historical-data/"
SYMS=["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","EURJPY","GBPJPY","XAUUSD"]
COST={"EURUSD":10,"GBPUSD":12,"USDJPY":10,"AUDUSD":11,"USDCAD":13,"USDCHF":13,"EURJPY":16,"GBPJPY":25,"XAUUSD":35}  # spread+commission+slippage aller-retour, unités du fichier
SPLIT=pd.Timestamp("2018-01-01")
def load(s):
    d=pd.read_csv(f"{SRC}{s}/{s}m15.csv",parse_dates=["Date"]).set_index("Date")[["open","high","low","close"]].astype(float)
    d=d[~d.index.duplicated()].sort_index()
    d["day"]=d.index.normalize(); d["hm"]=d.index.hour*60+d.index.minute
    return d
def rma(x,n): return x.ewm(alpha=1/n,adjust=False).mean()
def atr(d,n=14):
    pc=d.close.shift(); return rma(pd.concat([d.high-d.low,(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1),n)
def rsi(c,n):
    x=c.diff(); return 100-100/(1+rma(x.clip(lower=0),n)/rma((-x).clip(lower=0),n).replace(0,np.nan))
def walk(o,h,l,c,i,side,e,sl,tp,last,same_bar=True):
    """Simule à partir de la barre i (entrée déjà faite à e dans la barre i si same_bar). SL prioritaire. Retourne (prix sortie, index)."""
    j=i
    if same_bar:
        if (side==1 and l[i]<=sl) or (side==-1 and h[i]>=sl): return sl,i
        j=i+1
    while j<=last:
        if side==1:
            if l[j]<=sl: return min(o[j],sl),j
            if tp is not None and h[j]>=tp: return max(o[j],tp),j
        else:
            if h[j]>=sl: return max(o[j],sl),j
            if tp is not None and l[j]<=tp: return min(o[j],tp),j
        j+=1
    return c[last],last
def R(side,e,x,risk,cost): return (side*(x-e)-cost)/risk
def stats(x):
    x=pd.Series(x,dtype=float)
    if len(x)==0: return dict(n=0)
    w=x[x>0].sum(); lo=-x[x<=0].sum(); eq=x.cumsum()
    return dict(n=len(x),wr=round(100*(x>0).mean(),1),pf=round(w/lo,2) if lo else 9.9,exp=round(x.mean(),3),tot=round(x.sum(),1),dd=round((eq-eq.cummax()).min(),1))
