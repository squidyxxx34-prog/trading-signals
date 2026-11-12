from strats import *
def orb_tr(d,cost,r0,r1,w0,w1,xend,tpR,trend=None,slbuf=0.0):
    o,h,l,c,hm=d.open.values,d.high.values,d.low.values,d.close.values,d.hm.values; out=[]
    for day,ix in days(d):
        rng=ix[(hm[ix]>=r0)&(hm[ix]<r1)]; win=ix[(hm[ix]>=w0)&(hm[ix]<w1)]; ex=ix[hm[ix]<xend]
        if len(rng)==0 or len(win)==0 or len(ex)==0: continue
        hi,lo=h[rng].max(),l[rng].min(); W=hi-lo
        if W<=0: continue
        t=0 if trend is None else trend.get(day,0)
        for i in win:
            up,dn=h[i]>=hi,l[i]<=lo
            if up and dn: break
            if up or dn:
                side=1 if up else -1
                if t!=0 and side!=t: break
                e=max(o[i],hi) if up else min(o[i],lo); sl=(lo-slbuf*W) if up else (hi+slbuf*W); risk=abs(e-sl)
                tp=e+side*tpR*risk if tpR else None
                x,j=walk(o,h,l,c,i,side,e,sl,tp,ex[-1]); out.append((day,R(side,e,x,risk,cost),R(side,e,x,risk,0))); break
    return out
def dtrend(d):
    D=d.close.resample("1D").last().dropna(); return np.sign(D-D.ewm(span=50,adjust=False).mean()).shift(1).to_dict()
d=load("XAUUSD"); TR=dtrend(d); rows=[]
for (nm,r0,r1),tp,tf in itertools.product([("NY 15m",990,1005),("NY 30m",990,1020),("NY 60m",990,1050),("London 1h",600,660),("Asie->London",60,540)],[1.0,1.5,2.0,3.0,None],[False,True]):
    w0=r1; w1=r1+180; xe=1410
    t=orb_tr(d,35,r0,r1,w0,w1,xe,tp,TR if tf else None)
    T=pd.DataFrame(t,columns=["day","R","Rg"]); T["oos"]=T.day>=SPLIT
    i,o=stats(T.R[~T.oos]),stats(T.R[T.oos])
    rows.append(dict(range=nm,tp=tp,trend=tf,n=len(T),brut_exp=round(T.Rg.mean(),3),IS_pf=i["pf"],IS_exp=i["exp"],OOS_pf=o["pf"],OOS_exp=o["exp"]))
print(pd.DataFrame(rows).sort_values("IS_exp",ascending=False).head(15).to_string(index=False))
