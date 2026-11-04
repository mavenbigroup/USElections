import urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (compatible; midterm-night-board/1.0)"}
B="https://civicapi.org/api/v2"
for q in ["/race/search?startDate=2026-11-03&endDate=2026-11-03","/race/search?startDate=2026-11-03&endDate=2026-11-04&country=US","/race/search?startDate=2026-11-03"]:
    try:
        with urllib.request.urlopen(urllib.request.Request(B+q,headers=UA),timeout=40) as r:
            b=r.read().decode("utf-8","replace")
        print("PROBE",q,"len",len(b))
        try:
            d=json.loads(b)
            if isinstance(d,dict): print("PROBE keys",list(d.keys())[:20])
            arr=d if isinstance(d,list) else next((v for v in d.values() if isinstance(v,list)),[])
            print("PROBE count",len(arr))
            for x in arr[:3]: print("PROBE item",json.dumps(x)[:900])
        except Exception as e: print("PROBE raw",b[:600])
        break
    except Exception as e:
        print("PROBE ERR",q,str(e)[:200])
