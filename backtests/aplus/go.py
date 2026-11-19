import time, pandas as pd, numpy as np, pickle
from aplus import *
t0=time.time(); D=load_all(); print('prep',round(time.time()-t0,1),'s')
pickle.dump(D,open('D.pkl','wb'))
t0=time.time(); T=backtest(D); print('bt',round(time.time()-t0,1),'s', len(T))
split=pd.Timestamp('2025-11-01',tz='UTC')
for name,g in [('train',T[T.t_fill<split]),('test',T[T.t_fill>=split])]:
    w=g[g.R>0].R.sum(); lo=-g[g.R<0].R.sum()
    print(name,len(g),'R/trade',round(g.R.mean(),3),'win',round((g.R>0).mean(),3),'PF',round(w/lo,2) if lo else None,'sumR',round(g.R.sum(),1))
print(T.reason.value_counts())
print(T.groupby('sym').R.agg(['count','mean']).round(3))
