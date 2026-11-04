import pandas as pd, numpy as np
D = "data/"  # parquets Binance (data.binance.vision)
FEE = {"PAXG": 0.05, "BTC": 0.10, "ETH": 0.10}
def rs(df, rule):
    return df.resample(rule, label="left", closed="left").agg(dict(open="first", high="max", low="min", close="last", volume="sum")).dropna()
def load(asset, tf):
    sym = asset + "USDT"
    if tf == "15m": return pd.read_parquet(D + f"{sym}_15m.parquet")
    df = pd.read_parquet(D + f"{sym}_1h.parquet")
    return df if tf == "1h" else rs(df, tf)
def pooled(trs, fee_by_set):
    g, net = [], []
    for k, tr in trs.items():
        for t in tr:
            g.append(t["r"]); net.append(t["r"] - t["cr"] * fee_by_set[k] / 100)
    g, net = np.array(g), np.array(net)
    if len(g) == 0: return dict(n=0)
    se = net.std(ddof=1) / np.sqrt(len(net)) if len(net) > 1 else np.nan
    w = net[net > 0].sum(); l = -net[net <= 0].sum()
    return dict(n=len(g), gross=g.mean(), net=net.mean(), t=net.mean() / se if se else np.nan, pf=w / l if l > 0 else np.inf, wr=(net > 0).mean())
