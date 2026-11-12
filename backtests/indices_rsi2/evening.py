from bt import *
IDX=["US500","NAS100","US30","GER40"]
def run_close(d,f,sl_atr=2.0):
    c=d.close; r=rsi(c,2); s2=sma(c,200); s5=sma(c,5); a=atr(d)
    le=((c>s2)&(r<10)).values; ex=(c>s5).values; o,h,l,cc,a=d.open.values,d.high.values,d.low.values,c.values,a.values
    out=[]; i=0; n=len(d)
    while i<n-1:
        if not le[i] or d.index[i]<START: i+=1; continue
        e=cc[i]; risk=sl_atr*a[i]; sl=e-risk; j=i+1; px=None
        while j<n:
            if l[j]<=sl: px=min(o[j],sl); break
            if ex[j] or j-i>=10: px=cc[j]; break
            j+=1
        if px is None: px=cc[-1]; j=n-1
        out.append((d.index[i],(px-e-e*f/100)/risk)); i=j
    return out
rows=[(s,t,R) for s in IDX for t,R in run_close(load(s),fee(s))]
T=pd.DataFrame(rows,columns=["s","t","R"]).sort_values("t")
x=T.R; eq=x.cumsum(); print(f"Entrée/sortie à la clôture : n={len(x)} wr={100*(x>0).mean():.1f}% pf={x[x>0].sum()/-x[x<=0].sum():.2f} exp={x.mean():+.3f}R tot={x.sum():+.1f}R maxDD={(eq-eq.cummax()).min():.1f}R")
hold=[]
for s in IDX:
    d=load(s); c=d.close; r=rsi(c,2); s2=sma(c,200); s5=sma(c,5)
print("trades/an:", round(len(x)/4,1))
T.to_csv("evening_trades.csv",index=False)
