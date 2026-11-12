import numpy as np, pandas as pd, glob, os
START=pd.Timestamp("2022-11-12"); SPLIT=pd.Timestamp("2024-11-12")
FEE={"fx":0.02,"cross":0.03,"XAUUSD":0.03,"XAGUSD":0.06,"idx":0.02}
def fee(s):
    if s in("XAUUSD","XAGUSD"): return FEE[s]
    if s in("US500","NAS100","GER40","US30"): return FEE["idx"]
    return FEE["cross"] if s in("EURJPY","GBPJPY","EURGBP") else FEE["fx"]
def rma(x,n): return x.ewm(alpha=1/n,adjust=False).mean()
def sma(x,n): return x.rolling(n).mean()
def ema(x,n): return x.ewm(span=n,adjust=False).mean()
def rsi(c,n):
    d=c.diff(); return 100-100/(1+rma(d.clip(lower=0),n)/rma((-d).clip(lower=0),n).replace(0,np.nan))
def atr(df,n=14):
    pc=df.close.shift(); tr=pd.concat([df.high-df.low,(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1); return rma(tr,n)
def load(s):
    d=pd.read_csv(f"{s}.csv",index_col=0,parse_dates=True)
    m=d[["open","close"]].max(axis=1); n=d[["open","close"]].min(axis=1)
    d["high"]=np.minimum(d.high,m*1.04); d["low"]=np.maximum(d.low,n*0.96)   # nettoie spikes yahoo
    return d
SYMS=[os.path.basename(f)[:-4] for f in sorted(glob.glob("*.csv"))]

# ---- stratégies : renvoie (long_entry, short_entry, long_exit, short_exit, max_hold) ----
def connors(d):
    c=d.close; r=rsi(c,2); s2=sma(c,200); s5=sma(c,5)
    return (c>s2)&(r<10),(c<s2)&(r>90),c>s5,c<s5,10
def donchian(d):
    c=d.close; hi=d.high.rolling(20).max().shift(); lo=d.low.rolling(20).min().shift()
    xl=d.low.rolling(10).min().shift(); xh=d.high.rolling(10).max().shift()
    return c>hi,c<lo,c<xl,c>xh,None
def emax(d):
    f,s=ema(d.close,20),ema(d.close,50); up=(f>s)&(f.shift()<=s.shift()); dn=(f<s)&(f.shift()>=s.shift())
    return up,dn,f<s,f>s,None
def boll(d):
    c=d.close; m=sma(c,20); sd=c.rolling(20).std(); s2=sma(c,200)
    return (c>s2)&(c<m-2*sd),(c<s2)&(c>m+2*sd),c>m,c<m,15
def tsmom(d):
    c=d.close; mom=c/c.shift(126)-1; tr=c>sma(c,100)
    return (mom>0)&tr&~((mom.shift()>0)&tr.shift().fillna(False)), (mom<0)&~tr&~((mom.shift()<0)&~tr.shift().fillna(True)), (mom<0)|~tr,(mom>0)|tr,None
def supert(d,n=10,m=3.0):
    a=atr(d,n).values; hl=((d.high+d.low)/2).values; c=d.close.values; up=hl-m*a; dn=hl+m*a
    fu,fd=up.copy(),dn.copy(); dr=np.ones(len(c))
    for i in range(1,len(c)):
        fu[i]=max(up[i],fu[i-1]) if c[i-1]>fu[i-1] else up[i]
        fd[i]=min(dn[i],fd[i-1]) if c[i-1]<fd[i-1] else dn[i]
        dr[i]=1 if c[i]>fd[i-1] else -1 if c[i]<fu[i-1] else dr[i-1]
    s=pd.Series(dr,index=d.index); return (s==1)&(s.shift()==-1),(s==-1)&(s.shift()==1),s==-1,s==1,None
def pullback(d):   # tendance EMA50>EMA200, achat repli RSI14<40, sortie RSI>60
    c=d.close; e50,e200=ema(c,50),ema(c,200); r=rsi(c,14)
    return (e50>e200)&(c>e200)&(r<40),(e50<e200)&(c<e200)&(r>60),r>60,r<40,20
def insidebar(d):  # inside bar dans la tendance, cassure du haut/bas de la bougie mère
    c=d.close; ib=(d.high<d.high.shift())&(d.low>d.low.shift()); tr=c>ema(c,50)
    return ib.shift()&tr&(c>d.high.shift()),ib.shift()&~tr&(c<d.low.shift()),None,None,5
STRATS={"Connors RSI-2":connors,"Donchian 20/10 (Turtle)":donchian,"Croisement EMA 20/50":emax,"Bollinger retour moyenne":boll,
        "Momentum 6 mois":tsmom,"Supertrend 10/3":supert,"Repli en tendance (RSI14)":pullback,"Inside bar tendance":insidebar}

def run(d,sig,f,sl_atr=2.0,tp_r=None):
    le,se,lx,sx,mh=sig; a=atr(d).values; o,h,l,c=(d[k].values for k in("open","high","low","close"))
    F=lambda x: np.zeros(len(d),bool) if x is None else x.fillna(False).values.astype(bool)
    le,se,lx,sx=F(le),F(se),F(lx),F(sx); idx=d.index; out=[]; i=0; n=len(d)
    while i<n-1:
        side=1 if le[i] else -1 if se[i] else 0
        if side==0 or idx[i]<START or np.isnan(a[i]): i+=1; continue
        e=o[i+1]; risk=sl_atr*a[i]; sl=e-side*risk; tp=e+side*tp_r*risk if tp_r else None; j=i+1; px=None
        while j<n:
            if side==1 and l[j]<=sl: px=min(o[j],sl); break
            if side==-1 and h[j]>=sl: px=max(o[j],sl); break
            if tp and ((side==1 and h[j]>=tp) or (side==-1 and l[j]<=tp)): px=tp; break
            ex=(lx[j] if side==1 else sx[j]) or (mh and j-i>=mh)
            if ex and j+1<n: px=o[j+1]; j+=1; break
            j+=1
        if px is None: px=c[-1]; j=n-1
        R=(side*(px-e)-e*f/100)/risk
        out.append((idx[i+1],R)); i=j
    return out

if __name__=="__main__":
    data={s:load(s) for s in SYMS}; rows=[]; allt=[]
    for name,fn in STRATS.items():
        for s,d in data.items():
            for t,R in run(d,fn(d),fee(s)): allt.append((name,s,t,R))
    T=pd.DataFrame(allt,columns=["strat","sym","t","R"]); T["oos"]=T.t>=SPLIT
    cls=lambda s:"or/argent" if s in("XAUUSD","XAGUSD") else "indices" if s in("US500","NAS100","GER40","US30") else "forex"
    T["cls"]=T.sym.map(cls); T.to_csv("trades.csv",index=False)
    def st(x):
        w=x[x>0].sum(); lo=-x[x<=0].sum(); return pd.Series(dict(n=len(x),wr=round(100*(x>0).mean(),1),pf=round(w/lo,2) if lo else 9.9,expR=round(x.mean(),3),totR=round(x.sum(),1)))
    print(T.groupby("strat").R.apply(st).unstack().sort_values("expR",ascending=False).to_string())
    print("\n--- IS (nov22-nov24) vs OOS (nov24-nov26) ---")
    print(T.groupby(["strat","oos"]).R.apply(st).unstack().unstack()[["wr","pf","expR"]].to_string())
    print("\n--- par classe ---")
    print(T.groupby(["strat","cls"]).R.apply(st).unstack()[["n","wr","pf","expR","totR"]].to_string())
