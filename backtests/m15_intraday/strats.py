from lib import *
import itertools, sys

def days(d):
    idx=np.arange(len(d)); g=pd.Series(idx,index=d.index).groupby(d.day)
    return [(k,v.values) for k,v in g]

def orb(d,cost,r0,r1,w0,w1,xend,tpR,slmode="opp",fade=False,dATR=None,fmin=0,fmax=99):
    o,h,l,c,hm=d.open.values,d.high.values,d.low.values,d.close.values,d.hm.values; out=[]
    for day,ix in days(d):
        rng=ix[(hm[ix]>=r0)&(hm[ix]<r1)]; win=ix[(hm[ix]>=w0)&(hm[ix]<w1)]; ex=ix[hm[ix]<xend]
        if len(rng)<(r1-r0)//15*0.8 or len(win)==0 or len(ex)==0: continue
        hi,lo=h[rng].max(),l[rng].min(); W=hi-lo
        if W<=0: continue
        if dATR is not None:
            a=dATR.get(day,np.nan)
            if not (fmin*a<=W<=fmax*a): continue
        last=ex[-1]
        if not fade:
            for i in win:
                up,dn=h[i]>=hi,l[i]<=lo
                if up and dn: break
                if up or dn:
                    side=1 if up else -1; e=max(o[i],hi) if up else min(o[i],lo)
                    sl=(lo if up else hi) if slmode=="opp" else (hi+lo)/2; risk=abs(e-sl)
                    if risk<=0: break
                    tp=e+side*tpR*risk if tpR else None
                    x,j=walk(o,h,l,c,i,side,e,sl,tp,last); out.append((day,R(side,e,x,risk,cost))); break
        else:   # faux break : mèche au-delà puis clôture dans le range -> contre
            for i in win[:-1]:
                if h[i]>hi and c[i]<hi and l[i]>lo: side=-1; ext=h[i]
                elif l[i]<lo and c[i]>lo and h[i]<hi: side=1; ext=l[i]
                else: continue
                e=o[i+1]; sl=ext+side*(-1)*0.1*W*(-1) if False else (ext+0.1*W if side==-1 else ext-0.1*W)
                risk=abs(e-sl); tp=(hi+lo)/2 if tpR=="mid" else (lo if side==-1 else hi)
                if risk<=0 or (tp-e)*side<=0: break
                x,j=walk(o,h,l,c,i+1,side,e,sl,tp,last); out.append((day,R(side,e,x,risk,cost))); break
    return out

def pullback(d,cost,lo_r=5,slm=2.0,tpR=1.0,hold=8,h0=540,h1=1200):
    hc=d.close.resample("1h").last().dropna(); e50,e200=hc.ewm(span=50,adjust=False).mean(),hc.ewm(span=200,adjust=False).mean()
    tr=np.sign(e50-e200).shift(1).reindex(d.index,method="ffill").fillna(0).values  # tendance H1 clôturée
    r=rsi(d.close,2).values; a=atr(d).values; o,h,l,c,hm=d.open.values,d.high.values,d.low.values,d.close.values,d.hm.values
    out=[]; i=250; n=len(d)
    while i<n-hold-2:
        if h0<=hm[i]<h1 and ((tr[i]>0 and r[i]<lo_r) or (tr[i]<0 and r[i]>100-lo_r)):
            side=1 if tr[i]>0 else -1; e=o[i+1]; risk=slm*a[i]; sl=e-side*risk; tp=e+side*tpR*risk
            x,j=walk(o,h,l,c,i+1,side,e,sl,tp,i+1+hold); out.append((d.index[i],R(side,e,x,risk,cost))); i=j+1
        else: i+=1
    return out

def asian_mr(d,cost,h0=0,h1=420,xend=540,k=2.0,slm=2.0):
    m=d.close.rolling(20).mean(); sd=d.close.rolling(20).std(); a=atr(d).values
    o,h,l,c,hm=d.open.values,d.high.values,d.low.values,d.close.values,d.hm.values; mv,sv=m.values,sd.values
    out=[]; i=25; n=len(d)
    while i<n-40:
        if h0<=hm[i]<h1 and (c[i]<mv[i]-k*sv[i] or c[i]>mv[i]+k*sv[i]):
            side=1 if c[i]<mv[i] else -1; e=o[i+1]; risk=slm*a[i]; sl=e-side*risk; tp=mv[i]
            if (tp-e)*side<=0: i+=1; continue
            last=i+1
            while last<n-1 and hm[last+1]<xend and hm[last+1]>=hm[i]: last+=1
            x,j=walk(o,h,l,c,i+1,side,e,sl,tp,last); out.append((d.index[i],R(side,e,x,risk,cost))); i=j+1
        else: i+=1
    return out

def momentum(d,cost,t_sig=1050,xend=1380,thr=0.3,dATR=None,slm=0.5):
    o,h,l,c,hm=d.open.values,d.high.values,d.low.values,d.close.values,d.hm.values; out=[]
    for day,ix in days(d):
        a=dATR.get(day,np.nan)
        if np.isnan(a): continue
        s=ix[hm[ix]==t_sig-15]; ex=ix[(hm[ix]>=t_sig)&(hm[ix]<xend)]
        if len(s)==0 or len(ex)<2: continue
        ret=c[s[0]]-o[ix[0]]
        if abs(ret)<thr*a: continue
        side=int(np.sign(ret)); i=ex[0]; e=o[i]; risk=slm*a; sl=e-side*risk
        x,j=walk(o,h,l,c,i,side,e,sl,None,ex[-1],same_bar=True); out.append((day,R(side,e,x,risk,cost)))
    return out

def daily_atr(d):
    D=d.resample("1D").agg({"high":"max","low":"min","close":"last"}).dropna()
    pc=D.close.shift(); tr=pd.concat([D.high-D.low,(D.high-pc).abs(),(D.low-pc).abs()],axis=1).max(axis=1)
    return rma(tr,14).shift(1).to_dict()   # ATR des jours précédents

VARIANTS={
 "London ORB SL opp TP1":  lambda d,c,A: orb(d,c,60,540,540,840,1320,1.0),
 "London ORB SL opp TP2":  lambda d,c,A: orb(d,c,60,540,540,840,1320,2.0),
 "London ORB SL mid TP1":  lambda d,c,A: orb(d,c,60,540,540,840,1320,1.0,"mid"),
 "London ORB SL mid TP2":  lambda d,c,A: orb(d,c,60,540,540,840,1320,2.0,"mid"),
 "London ORB filtre range": lambda d,c,A: orb(d,c,60,540,540,840,1320,1.0,"opp",dATR=A,fmin=0.2,fmax=0.6),
 "Faux break Asie -> milieu": lambda d,c,A: orb(d,c,60,540,540,840,1320,"mid",fade=True),
 "Faux break Asie -> autre bord": lambda d,c,A: orb(d,c,60,540,540,840,1320,"opp",fade=True),
 "NY ORB 30m TP1":         lambda d,c,A: orb(d,c,990,1020,1020,1200,1410,1.0),
 "NY ORB 30m TP2":         lambda d,c,A: orb(d,c,990,1020,1020,1200,1410,2.0),
 "Repli tendance H1 RSI2": lambda d,c,A: pullback(d,c),
 "Repli tendance TP2 hold16": lambda d,c,A: pullback(d,c,tpR=2.0,hold=16),
 "Bollinger nuit asiatique": lambda d,c,A: asian_mr(d,c),
 "Momentum intraday 17h30":  lambda d,c,A: momentum(d,c,dATR=A),
}
if __name__=="__main__":
    from multiprocessing import Pool
    def job(s):
        d=load(s); A=daily_atr(d); rows=[]
        for name,f in VARIANTS.items():
            for t,r in f(d,COST[s],A): rows.append((name,s,t,r))
        return rows
    with Pool(4) as p: res=[x for rr in p.map(job,SYMS) for x in rr]
    T=pd.DataFrame(res,columns=["strat","sym","t","R"]); T["oos"]=pd.to_datetime(T.t)>=SPLIT; T.to_csv("m15_trades.csv",index=False)
    rows=[]
    for name,g in T.groupby("strat"):
        a=stats(g.R); i=stats(g.R[~g.oos]); o=stats(g.R[g.oos]); gx=stats(g.R[g.sym=="XAUUSD"])
        pos=(g.groupby("sym").R.sum()>0).mean()
        rows.append(dict(strat=name,n=a["n"],wr=a["wr"],pf=a["pf"],exp=a["exp"],IS_pf=i["pf"],OOS_pf=o["pf"],OOS_exp=o["exp"],or_pf=gx.get("pf"),paires_pos=round(pos,2)))
    print(pd.DataFrame(rows).sort_values("OOS_exp",ascending=False).to_string(index=False))
