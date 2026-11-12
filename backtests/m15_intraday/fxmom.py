import sys; sys.path.insert(0,"/home/claude/trading-signals")
import smc_engine as E, pandas as pd, numpy as np
from smc15 import BASE, prep
from lib import stats, COST, SYMS
from multiprocessing import Pool
def job(s):
    p=prep(s); q=dict(BASE); q["fee"]=COST[s]/p.close.median()*100; tr=E.run(p,q)
    D=p.close.resample("1D").last().dropna(); D.index=D.index.tz_localize(None); mom=(D/D.shift(126)-1).shift(1)
    m=mom.reindex(p.index.tz_localize(None).normalize()).values
    return [(s,t["r"],t["d"],m[t["fill"]]) for t in tr]
if __name__=="__main__":
    with Pool(4) as pl: T=pd.DataFrame([x for r in pl.map(job,[s for s in SYMS if s!="XAUUSD"]) for x in r],columns=["s","r","d","mom"])
    for thr in [0,0.03,0.05,0.08]:
        k=T[(np.sign(T.mom)==T.d)&(T.mom.abs()>thr)]; print("FX momentum même sens >",thr,stats(k.r))
