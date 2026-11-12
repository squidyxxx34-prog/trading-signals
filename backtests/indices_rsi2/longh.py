import yfinance as yf, sys
sys.path.insert(0,".")
from bt import *
import bt
T={"US500":"^GSPC","NAS100":"^NDX","US30":"^DJI","GER40":"^GDAXI"}
def st(x):
    w=x[x>0].sum(); lo=-x[x<=0].sum(); eq=x.cumsum(); dd=(eq-eq.cummax()).min()
    return f"n={len(x):4d} wr={100*(x>0).mean():5.1f}% pf={w/lo:5.2f} exp={x.mean():+.3f}R maxDD={dd:5.1f}R"
def conn(d):
    c=d.close; r=rsi(c,2); s2=sma(c,200); s5=sma(c,5); z=pd.Series(False,index=d.index)
    return (c>s2)&(r<10),z,c>s5,z,10
bt.START=pd.Timestamp("2000-01-01"); rows=[]
for k,t in T.items():
    d=yf.download(t,start="1999-01-01",end="2022-11-12",progress=False,auto_adjust=False); d.columns=[c[0].lower() for c in d.columns]
    d=d[["open","high","low","close"]].dropna(); d=d[d.open>0]
    for tt,R in run(d,conn(d),0.02): rows.append((k,tt,R))
D=pd.DataFrame(rows,columns=["s","t","R"])
print("2000-2022 longs:",st(D.R))
for a,b in [(2000,2002),(2003,2007),(2008,2009),(2010,2019),(2020,2020),(2021,2022)]:
    print(f"{a}-{b}",st(D.R[(D.t.dt.year>=a)&(D.t.dt.year<=b)]))
