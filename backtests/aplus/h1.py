import glob, os, pandas as pd, numpy as np, itertools
import aplus
from aplus import backtest
os.makedirs('pq1h',exist_ok=True)
for p in glob.glob('pq/*.parquet'):
    d=pd.read_parquet(p).set_index('t')
    r=d.resample('1h').agg({'o':'first','h':'max','l':'min','c':'last','v':'sum'}).dropna().reset_index()
    r.to_parquet('pq1h/'+os.path.basename(p))
D={os.path.basename(p)[:-8]:aplus.prep(p) for p in sorted(glob.glob('pq1h/*.parquet'))}
split=pd.Timestamp('2025-11-01',tz='UTC')
for b,s,tp in itertools.product([1,0],[1,0],[0,1,2]):
    r=[]
    for fee in [0,0.0005]:
        T=backtest(D,use_bias=b,use_sess=s,tp_mode=tp,fee=fee)
        tr=T[T.t_fill<split]; te=T[T.t_fill>=split]
        r.append(f"fee{fee*100:.2f}% tr {len(tr)} {tr.R.mean():+.3f} | te {len(te)} {te.R.mean():+.3f}")
    print(f"1h bias={b} sess={s} tp={['liq','2R','3R'][tp]} :: "+' || '.join(r))
