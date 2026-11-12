from bt import *
IDX=["US500","NAS100","US30","GER40"]
data={s:load(s) for s in IDX}
def st(x):
    w=x[x>0].sum(); lo=-x[x<=0].sum(); eq=x.cumsum(); dd=(eq-eq.cummax()).min()
    return f"n={len(x):3d} wr={100*(x>0).mean():5.1f}% pf={w/lo if lo else 9.9:5.2f} exp={x.mean():+.3f}R tot={x.sum():+6.1f}R maxDD={dd:5.1f}R"
def conn(d,lo=10,hi=90,x=5):
    c=d.close; r=rsi(c,2); s2=sma(c,200); sx=sma(c,x)
    return (c>s2)&(r<lo),(c<s2)&(r>hi),c>sx,c<sx,10
base=[]
for s,d in data.items():
    for t,R in run(d,conn(d),fee(s)): base.append((s,t,R,1 if conn(d)[0].shift(1).reindex([t]).iloc[0] else -1))
T=pd.DataFrame(base,columns=["s","t","R","side"])
print("TOTAL      ",st(T.R)); print("IS 22-24   ",st(T.R[T.t<SPLIT])); print("OOS 24-26  ",st(T.R[T.t>=SPLIT]))
print("Longs      ",st(T.R[T.side==1])); print("Shorts     ",st(T.R[T.side==-1]))
for s in IDX: print(f"{s:7s}    ",st(T.R[T.s==s]))
for y in [2022,2023,2024,2025,2026]: print(f"{y}       ",st(T.R[T.t.dt.year==y]))
print("\n--- robustesse (paramètres voisins) ---")
for lo,hi in [(5,95),(10,90),(15,85),(20,80),(25,75)]:
    for slm in [1.5,2.0,3.0]:
        r=[R for s,d in data.items() for t,R in run(d,conn(d,lo,hi),fee(s),sl_atr=slm)]
        print(f"RSI<{lo:2d} stop {slm}ATR ",st(pd.Series(r)))
T.to_csv("idx_trades.csv",index=False)
