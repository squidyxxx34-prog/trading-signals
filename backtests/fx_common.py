import pandas as pd
RAW = "data/fx/"  # CSV ejtraderLabs/historical-data (h1/h4/d1)
SYMS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD", "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURCHF", "XAUUSD"]
CROSS = {"EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURCHF"}
def fee(sym): return 0.03 if sym in CROSS or sym == "XAUUSD" else 0.02   # spread + commission CFD aller-retour, %
def load_fx(sym, tf):
    f = {"1h": "h1", "4h": "h4", "1D": "d1"}[tf]
    df = pd.read_csv(RAW + f"{sym}{f}.csv", parse_dates=["Date"]).set_index("Date")
    df.index = df.index.tz_localize("UTC")
    return df[["open", "high", "low", "close"]].astype(float).sort_index()
