import pandas as pd, sys
for f in sys.argv[1:]:
    T=pd.read_csv(f); print('\n=====',f, len(T))
    def rep(m,lab):
        s=T[m]; out=[lab.ljust(26), f'n={len(s):5d}']
        for R in (1,2,3):
            x=s[f'r{R}'].dropna(); out.append(f'{R}R: WR {100*(x>0).mean():4.1f}% exp {x.mean():+.3f}R')
        print(' | '.join(out))
    rep(T.stars>=0,'tous (étoiles 1+4)')
    for k in (2,3,4,5): rep(T.stars==k,f'{k} étoiles')
    rep(T.stars>=4,'>=4 étoiles (règle Kasper)')
    rep((T.stars==5)&T.sweep,'5 étoiles + sweep bonus')
    rep(T.st2,'étoile 2 seule ok'); rep(T.st5,'étoile 5 ok'); rep(T.st3,'étoile 3 ok')
    # par année, 5 étoiles 2R
    T['y']=pd.to_datetime(T.t).dt.year
    print((T[T.stars==5].groupby('y').r2.agg(['count','mean'])).round(3).T)
