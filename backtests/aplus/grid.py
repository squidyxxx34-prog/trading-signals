import pickle, itertools, pandas as pd, numpy as np
from aplus import backtest
D=pickle.load(open('D.pkl','rb'))
split=pd.Timestamp('2025-11-01',tz='UTC')
def st(g):
    if len(g)==0: return (0,np.nan,np.nan,np.nan)
    w=g[g.R>0].R.sum(); lo=-g[g.R<0].R.sum()
    return (len(g), round(g.R.mean(),3), round((g.R>0).mean(),2), round(w/lo,2) if lo else np.nan)
rows=[]
for b,s,tp,em in itertools.product([1,0],[1,0],[0,1,2],[0,1]):
    T=backtest(D,use_bias=b,use_sess=s,tp_mode=tp,entry_mid=em)
    tr=T[T.t_fill<split]; te=T[T.t_fill>=split]
    rows.append(dict(bias=b,sess=s,tp=['liq','2R','3R'][tp],entry=['bord','milieu'][em],
        **{f'tr_{k}':v for k,v in zip(['n','R','win','PF'],st(tr))},**{f'te_{k}':v for k,v in zip(['n','R','win','PF'],st(te))}))
R=pd.DataFrame(rows); pd.set_option('display.width',200)
print(R.sort_values('tr_R',ascending=False).to_string(index=False))
R.to_csv('grid.csv',index=False)
