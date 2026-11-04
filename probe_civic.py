import urllib.request, json
UA={"User-Agent":"midterm-night-board/1.0 (+github pages)"}
paths=["/api/v2/upcomingraces","/api/v2/races","/api/v2/races?country=US&year=2026","/api/v2/search?query=Senate%202026","/api/v2/race/US/NC/senate/2026","/api/v2/races/US/NC/senate/2026","/api/v2/race/us/nc/senate/2026","/api/v2/status","/api/v2/elections","/api/v2/results","/api/v1/upcomingraces","/api/v1/race/US/NC/senate/2026"]
for p in paths:
    try:
        req=urllib.request.Request("https://civicapi.org"+p,headers=UA)
        with urllib.request.urlopen(req,timeout=10) as r:
            b=r.read().decode("utf-8","replace")
            print("PROBE",r.status,p,b[:400].replace("\n"," "))
    except urllib.error.HTTPError as e:
        print("PROBE",e.code,p,e.read().decode("utf-8","replace")[:200].replace("\n"," "))
    except Exception as e:
        print("PROBE ERR",p,str(e)[:150])
