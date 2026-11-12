from gold import orb_tr, dtrend, load, stats, SPLIT, pd, np
d=load("XAUUSD"); TR=dtrend(d)
for lab,w0,tr in [("base 16h45-19h45 serveur",1005,None),("+tendance D1",1005,TR),("entrées après 16h30 Paris seulement",1050,None),("après 16h30 + tendance",1050,TR)]:
    T=pd.DataFrame(orb_tr(d,35,990,1005,w0,1185,1410,None,tr),columns=["day","R","Rg"])
    print(f"{lab:38s}", stats(T.R), "| OOS", stats(T.R[T.day>=SPLIT])["pf"])
T=pd.DataFrame(orb_tr(d,35,990,1005,1005,1185,1410,None,None),columns=["day","R","Rg"])
print(T.groupby(T.day.dt.year).R.agg(["count","mean","sum"]).round(3).T.to_string())
for c in [20,35,50,70]:
    t=pd.DataFrame(orb_tr(d,c,990,1005,1005,1185,1410,None,None),columns=["day","R","Rg"]); print("coût",c/100,"$ ->",stats(t.R))
# ----- PAXG 2022-2026 (heure de New York)
p=pd.read_parquet("/tmp/claude-0/-home-claude/731c2de4-dd0d-588b-9e3e-3ad607beea74/scratchpad/data/PAXGUSDT_15m.parquet")[["open","high","low","close"]]
p.index=p.index.tz_convert("America/New_York").tz_localize(None)+pd.Timedelta(hours=7)   # -> même horloge que les données serveur
p=p[p.index.dayofweek<5]; p["day"]=p.index.normalize(); p["hm"]=p.index.hour*60+p.index.minute
p=p[p.index>=pd.Timestamp("2022-03-07")]
for c in [0.30,0.50]:
    t=pd.DataFrame(orb_tr(p,c,990,1005,1005,1185,1410,None,None),columns=["day","R","Rg"])
    print(f"PAXG 2022-26 coût {c}$:",stats(t.R),"| brut",round(t.Rg.mean(),3))
    print(t.groupby(t.day.dt.year).R.agg(["count","mean","sum"]).round(3).T.to_string())
