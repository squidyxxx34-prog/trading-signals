import yfinance as yf, pandas as pd
T={"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","AUDUSD":"AUDUSD=X","NZDUSD":"NZDUSD=X","USDJPY":"JPY=X","USDCHF":"CHF=X","USDCAD":"CAD=X",
   "EURJPY":"EURJPY=X","GBPJPY":"GBPJPY=X","EURGBP":"EURGBP=X","XAUUSD":"GC=F","XAGUSD":"SI=F","US500":"ES=F","NAS100":"NQ=F","GER40":"^GDAXI","US30":"YM=F"}
for k,t in T.items():
    d=yf.download(t,start="2021-09-01",end="2026-11-12",interval="1d",progress=False,auto_adjust=False)
    d.columns=[c[0].lower() for c in d.columns]; d=d[["open","high","low","close"]].dropna()
    d=d[(d.high>=d.low)]; d.to_csv(f"{k}.csv"); print(k,len(d),d.index[0].date(),d.index[-1].date())
