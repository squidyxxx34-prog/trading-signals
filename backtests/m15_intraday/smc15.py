import sys; sys.path.insert(0,"/home/claude/trading-signals")
import smc_engine as E
from lib import load, SYMS, COST, stats as st2, SPLIT
import pandas as pd, numpy as np, time
from multiprocessing import Pool
BASE=dict(bias="htf+swing",need_fvg=True,need_sweep=False,need_choch=False,kz=False,lint=3,lsw=10,htf_len=50,fvg_min=0.2,fvg_pick="first",entry="fvg_top",sl_buf=0.2,rr=3.0,max_wait=10,max_hold=120,min_risk=0.25,max_risk=4.0)
V={
 "Continuation FVG 3R (ton Pine)": dict(),
 "Continuation FVG 2R":            dict(rr=2.0),
 "Continuation OB bord 2R":        dict(entry="ob_top",rr=2.0),
 "Continuation FVG 2R killzones":  dict(rr=2.0,kz=True),
 "Reversal A+ (sweep+CHoCH+KZ) 2R": dict(need_sweep=True,need_choch=True,kz=True,rr=2.0),
 "Scalp : FVG 50% 1.5R KZ":       dict(entry="fvg_ce",rr=1.5,kz=True,max_hold=32,max_wait=6),
}
def prep(s):
    d=load(s)[["open","high","low","close"]]
    d.index=(d.index-pd.Timedelta(hours=7)).tz_localize("America/New_York",ambiguous="NaT",nonexistent="NaT")
    return d[d.index.notna()]
def job(args):
    s,name=args; d=prep(s); fee=COST[s]/d.close.median()*100
    p=dict(BASE); p.update(V[name]); p["fee"]=fee
    tr=E.run(d,p)
    return [(name,s,d.index[t["fill"]].tz_localize(None),t["r"]) for t in tr]
if __name__=="__main__":
    t0=time.time()
    with Pool(4) as pool: res=[x for r in pool.map(job,[(s,n) for n in V for s in SYMS]) for x in r]
    T=pd.DataFrame(res,columns=["strat","sym","t","R"]); T.to_csv("smc15_trades.csv",index=False)
    rows=[]
    for n,g in T.groupby("strat"):
        a=st2(g.R); i=st2(g.R[g.t<SPLIT]); o=st2(g.R[g.t>=SPLIT]); x=st2(g.R[g.sym=="XAUUSD"])
        rows.append(dict(strat=n,n=a["n"],wr=a["wr"],pf=a["pf"],exp=a["exp"],IS_pf=i["pf"],OOS_pf=o["pf"],or_pf=x.get("pf"),or_n=x.get("n"),paires_pos=round((g.groupby("sym").R.sum()>0).mean(),2)))
    print(pd.DataFrame(rows).sort_values("pf",ascending=False).to_string(index=False)); print(round(time.time()-t0),"s")
