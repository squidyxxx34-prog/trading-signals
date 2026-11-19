import glob, os, pandas as pd, numpy as np
import aplus
from aplus import backtest
os.makedirs('pq1h_new',exist_ok=True)
for s in sorted({os.path.basename(f).split('-')[0] for f in glob.glob('data1h/*.csv')}):
    dfs=[]
    for f in sorted(glob.glob(f'data1h/{s}-*.csv')):
        d=pd.read_csv(f,header=None)
        if not str(d.iloc[0,0]).isdigit(): d=d.iloc[1:]
        d=d.iloc[:,:6]; d.columns=['t','o','h','l','c','v']; dfs.append(d.astype(float))
    d=pd.concat(dfs).drop_duplicates('t').sort_values('t'); d['t']=pd.to_datetime(d.t.astype('int64'),unit='ms',utc=True)
    d.to_parquet(f'pq1h_new/{s}.parquet')
split=pd.Timestamp('2025-11-01',tz='UTC')
def rep(name,T):
    w=T[T.R>0].R.sum(); lo=-T[T.R<0].R.sum()
    print(f"{name}: n={len(T)} R/trade={T.R.mean():+.3f} win={(T.R>0).mean():.2f} PF={w/lo:.2f} sumR={T.R.sum():+.1f}")
Dn={os.path.basename(p)[:-8]:aplus.prep(p) for p in sorted(glob.glob('pq1h_new/*.parquet'))}
Do={os.path.basename(p)[:-8]:aplus.prep(p) for p in sorted(glob.glob('pq1h/*.parquet'))}
for kw,lab in [(dict(use_bias=1,use_sess=1,tp_mode=0),'bias+sess+liq'),(dict(use_bias=0,use_sess=0,tp_mode=0),'sans filtre+liq')]:
    print('==',lab)
    To=backtest(Do,**kw); Tn=backtest(Dn,**kw)
    rep(' 12 perps de depart (train)',To[To.t_fill<split]); rep(' 12 perps de depart (test)',To[To.t_fill>=split])
    rep(' 16 NOUVEAUX perps (3 ans, jamais vus)',Tn)
    allT=pd.concat([To,Tn]); rep(' TOTAL 28 perps',allT)
    allT.to_csv(f'trades_{lab}.csv',index=False)
