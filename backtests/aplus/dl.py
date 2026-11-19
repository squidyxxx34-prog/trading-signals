import os, sys, io, zipfile, urllib.request, concurrent.futures as cf
syms=sys.argv[1:]
months=[(y,m) for y in (2023,2024,2025,2026) for m in range(1,13) if (y,m)>=(2023,11) and (y,m)<=(2026,10)]
def get(s,y,m):
    fn=f"data/{s}-{y}-{m:02d}.csv"
    if os.path.exists(fn): return fn,'cached'
    url=f"https://data.binance.vision/data/futures/um/monthly/klines/{s}/15m/{s}-15m-{y}-{m:02d}.zip"
    try:
        b=urllib.request.urlopen(url,timeout=60).read()
        z=zipfile.ZipFile(io.BytesIO(b)); open(fn,'wb').write(z.read(z.namelist()[0])); return fn,'ok'
    except Exception as e: return fn,f'ERR {e}'
jobs=[(s,y,m) for s in syms for (y,m) in months]
with cf.ThreadPoolExecutor(16) as ex:
    res=list(ex.map(lambda a:get(*a),jobs))
from collections import Counter
print(Counter(r[1][:3] for r in res))
for s in syms:
    print(s, sum(1 for (f,st) in res if f.startswith(f'data/{s}-') and st in('ok','cached')))
