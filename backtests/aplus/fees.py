import pickle, pandas as pd, numpy as np
from aplus import backtest
D=pickle.load(open('D.pkl','rb')); split=pd.Timestamp('2025-11-01',tz='UTC')
for kw in [dict(use_bias=0,use_sess=0,tp_mode=1),dict(use_bias=1,use_sess=1,tp_mode=2),dict(use_bias=0,use_sess=0,tp_mode=2),dict(use_bias=1,use_sess=0,tp_mode=0)]:
    out=[]
    for fee in [0,0.0002,0.0005]:
        T=backtest(D,fee=fee,**kw)
        out.append(f"fee {fee*100:.2f}%: train {T[T.t_fill<split].R.mean():+.3f} test {T[T.t_fill>=split].R.mean():+.3f}")
    T=backtest(D,**kw); risk_pct=(abs(T.entry-T.sl)/T.entry*100)
    print(kw,'| SL moyen',round(risk_pct.median(),2),'% |',' ; '.join(out))
